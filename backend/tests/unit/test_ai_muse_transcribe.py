"""muse_transcribe adapter over a fake HTTP transport (04 sections 3, 8.3). No network."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.ai.adapters import muse_transcribe as mt
from app.ai.adapters.muse_transcribe import MuseTranscriber, detect_language
from app.ai.cost import PriceTable
from app.ai.errors import (
    AiInvalidOutput,
    AiPermanentError,
    AiTransientError,
    to_job_error,
)
from app.ai.types import TranscribeRequest
from app.config import AiConnection

PRICES = PriceTable.from_file(Path(__file__).parents[2] / "app/ai/prices.json")
CONN = AiConnection(
    base_url="https://api.example.test/v1", model="muse-voice-transcribe-1.0", api_key="sekret"
)

GOOD = {
    "sessionId": "c1",
    "transcript": "This is Biscuit. She is shy. Now my friend walks up.",
    "audioDurationMs": 118400,
    "turns": [
        {"turnId": 1, "startMs": 3600, "endMs": 9800, "transcript": "Now my friend walks up."},
        {"turnId": 0, "startMs": 120, "endMs": 3400, "transcript": "This is Biscuit. She is shy.",
         "speaker": None, "extra": 1},
    ],
}


def make(handler, **kw):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return MuseTranscriber(CONN, PRICES, timeout_s=5, client=client, **kw)


def reply(status=200, body=None, headers=None, content=None):
    def handler(request):
        handler.seen = request
        if content is not None:
            return httpx.Response(status, content=content, headers=headers)
        return httpx.Response(status, json=body, headers=headers)

    return handler


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "audio.wav"
    p.write_bytes(b"RIFF" + b"\0" * 100)
    return p


def req(wav, **kw):
    return TranscribeRequest(audio_path=str(wav), duration_s=kw.pop("duration_s", 120.0), **kw)


def test_success_two_turns(wav):
    h = reply(body=GOOD)
    result, usages = make(h).transcribe(req(wav, keywords=["Biscuit"], lang_hint="en"))
    assert [(s.seq, s.start_s, s.end_s, s.text) for s in result.segments] == [
        (0, 0.1, 3.4, "This is Biscuit. She is shy."),
        (1, 3.6, 9.8, "Now my friend walks up."),
    ]
    assert result.full_text == GOOD["transcript"]
    assert result.language == "en"
    (u,) = usages
    assert (u.provider, u.purpose, u.audio_s, u.usd_micros) == ("muse", "transcribe", 118.4, 5920)
    r = h.seen
    assert str(r.url) == "https://api.example.test/v1/asr/transcribe"
    assert r.headers["authorization"] == "Bearer sekret"
    assert r.headers["content-type"].startswith("multipart/form-data")
    raw = r.read()
    assert b'name="request"' in raw and b'filename="audio.wav"' in raw
    meta = json.loads(raw.split(b'name="request"')[1].split(b"\r\n\r\n", 1)[1].split(b"\r\n--")[0])
    assert meta == {
        "model": "muse-voice-transcribe-1.0",
        "audioEncoding": "WAV",
        "mode": "ENDPOINTING",
        "languageBias": ["English"],
        "keywords": ["Biscuit"],
    }


def test_korean_language_and_clamp(wav):
    body = {
        "transcript": "안녕하세요 비스킷이에요",
        "audioDurationMs": 5000,
        "turns": [{"startMs": 0, "endMs": 9000, "transcript": "안녕하세요 비스킷이에요"}],
    }
    result, usages = make(reply(body=body)).transcribe(req(wav, duration_s=5.0))
    assert result.language == "ko"
    assert (result.segments[0].start_s, result.segments[0].end_s) == (0.0, 5.0)
    assert usages[0].usd_micros == 250


def test_empty_transcript_is_valid(wav):
    body = {"transcript": "", "audioDurationMs": 3000, "turns": []}
    result, usages = make(reply(body=body)).transcribe(req(wav))
    assert result.segments == [] and result.full_text == ""
    assert usages[0].audio_s == 3.0


def test_no_turns_but_text_makes_one_segment(wav):
    body = {"transcript": "Hello there", "turns": []}
    result, usages = make(reply(body=body)).transcribe(req(wav, duration_s=4.0))
    assert [(s.start_s, s.end_s, s.text) for s in result.segments] == [(0.0, 4.0, "Hello there")]
    assert usages[0].audio_s == 4.0  # falls back to the file duration


def test_empty_and_tiny_turns_are_dropped(wav):
    body = {
        "transcript": "Hi",
        "turns": [
            {"startMs": 0, "endMs": 1000, "transcript": "  "},
            {"startMs": 1000, "endMs": 1040, "transcript": "tiny"},
            {"startMs": 2000, "endMs": 3000, "transcript": "Hi\x00 "},
        ],
    }
    result, _ = make(reply(body=body)).transcribe(req(wav))
    assert [(s.seq, s.text) for s in result.segments] == [(0, "Hi")]


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_transient_statuses(wav, status):
    h = reply(status, {"error": "x"}, headers={"Retry-After": "7"})
    with pytest.raises(AiTransientError) as ei:
        make(h).transcribe(req(wav))
    if status == 429:
        assert ei.value.retry_after_s == 7.0
    err = to_job_error(ei.value, "transcribe")
    assert (err.code if hasattr(err, "code") else "ai_failed") == "ai_failed"
    assert err.retryable is True


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 413])
def test_permanent_statuses(wav, status):
    with pytest.raises(AiPermanentError) as ei:
        make(reply(status, {"error": "secret body"})).transcribe(req(wav))
    assert str(ei.value) == f"HTTP {status}"
    assert to_job_error(ei.value, "transcribe").retryable is False


def test_network_error_is_transient(wav):
    def boom(request):
        raise httpx.ConnectTimeout("t")

    with pytest.raises(AiTransientError):
        make(boom).transcribe(req(wav))


@pytest.mark.parametrize(
    "kw",
    [
        {"content": b"not json"},
        {"body": ["x"]},
        {"body": {"turns": []}},
        {"body": {"transcript": "x", "turns": "no"}},
        {"body": {"transcript": "x", "turns": [{"startMs": "a", "endMs": 2, "transcript": "x"}]}},
        {"body": {"transcript": "x", "turns": [{"startMs": 1, "endMs": 2}]}},
    ],
)
def test_malformed_answer_is_invalid_output(wav, kw):
    with pytest.raises(AiInvalidOutput) as ei:
        make(reply(**kw)).transcribe(req(wav))
    err = to_job_error(ei.value, "transcribe")
    assert err.retryable is False


def test_file_over_limit_is_permanent_without_a_call(wav, monkeypatch):
    monkeypatch.setattr(mt, "MAX_BODY_BYTES", 10)

    def never(request):
        raise AssertionError("must not upload")

    with pytest.raises(AiPermanentError):
        make(never).transcribe(req(wav))


def test_audio_over_ten_minutes_is_permanent(wav):
    with pytest.raises(AiPermanentError):
        make(reply(body=GOOD)).transcribe(req(wav, duration_s=601.0))


def test_keywords_capped_at_twenty(wav):
    h = reply(body=GOOD)
    make(h).transcribe(req(wav, keywords=[f"k{i}" for i in range(30)]))
    raw = h.seen.read().decode("latin-1")
    assert "k19" in raw and "k20" not in raw


def test_detect_language():
    assert detect_language("") == "en"
    assert detect_language("12 !") == "en"
    assert detect_language("Hello 안녕하세요 world") == "ko"
    assert detect_language("Привет мир") == "other"
