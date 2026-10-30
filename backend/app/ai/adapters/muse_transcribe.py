"""`muse_transcribe`: Transcriber over Meta Muse Voice Transcribe (04 section 8.3).

One multipart `POST {base_url}/asr/transcribe` per clip, mode `ENDPOINTING`.
Turns become `TranscriptSegmentOut` rows (04 section 3.2). Adapter-internal
`AiError`s are raised as-is; the pipeline handler converts them with
`to_job_error` (like the mock adapter).
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any, Literal

import httpx

from app.ai.cost import PriceTable
from app.ai.errors import AiInvalidOutput, AiPermanentError, AiTransientError
from app.ai.types import (
    TranscribeRequest,
    TranscriptResult,
    TranscriptSegmentOut,
    Usage,
)
from app.config import AiConnection

PROVIDER = "muse"
MAX_BODY_BYTES = 32 * 1024 * 1024  # provider limit (413 above)
MAX_AUDIO_S = 10 * 60  # provider limit (400 above)
MAX_KEYWORDS = 20
MAX_TEXT_CHARS = 500
_LANGUAGE_BIAS = {
    "auto": ["English", "Korean"],
    "en": ["English"],
    "ko": ["Korean"],
}


def _retry_after(headers: Any) -> float | None:
    try:
        return max(0.0, float(headers.get("retry-after")))
    except (AttributeError, TypeError, ValueError):
        return None


def _is_hangul(c: str) -> bool:
    return "가" <= c <= "힣" or "ᄀ" <= c <= "ᇿ" or "㄰" <= c <= "㆏"


def detect_language(text: str) -> Literal["en", "ko", "other"]:
    """Server-side language (04 section 3.1): >= 30% Hangul letters -> ko."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    hangul = sum(1 for c in letters if _is_hangul(c))
    if hangul * 10 >= len(letters) * 3:
        return "ko"
    latin = sum(1 for c in letters if unicodedata.name(c, "").startswith("LATIN"))
    return "en" if latin * 2 > len(letters) else "other"


def _clean(text: str) -> str:
    """Drop control characters, trim, NFC, cap at 500 chars (04 section 3.2)."""
    text = "".join(" " if c in "\n\t" else c for c in text)
    text = "".join(c for c in text if unicodedata.category(c) != "Cc")
    return unicodedata.normalize("NFC", text).strip()[:MAX_TEXT_CHARS].strip()


class MuseTranscriber:
    def __init__(
        self,
        conn: AiConnection,
        prices: PriceTable,
        *,
        timeout_s: float,
        client: httpx.Client | None = None,
    ):
        self._conn = conn
        self._prices = prices
        self._url = conn.base_url.rstrip("/") + "/asr/transcribe"
        self._client = client or httpx.Client(timeout=timeout_s)
        self._timeout_s = timeout_s

    # ------------------------------------------------------------ protocol
    def transcribe(
        self, req: TranscribeRequest
    ) -> tuple[TranscriptResult, list[Usage]]:
        if req.duration_s > MAX_AUDIO_S:
            raise AiPermanentError("audio longer than 10 minutes")
        try:
            size = Path(req.audio_path).stat().st_size
        except OSError:
            raise AiPermanentError("audio file is missing") from None
        if size > MAX_BODY_BYTES:
            raise AiPermanentError(
                "audio over 32 MB"
            )  # no upload: the API would answer 413
        return self._parse(self._post(req), req)

    # ---------------------------------------------------------------- http
    def _post(self, req: TranscribeRequest) -> Any:
        meta: dict[str, Any] = {
            "model": self._conn.model,
            "audioEncoding": "WAV",
            "mode": "ENDPOINTING",
            "languageBias": _LANGUAGE_BIAS[req.lang_hint],
        }
        keywords = [k for k in req.keywords if k and k.strip()][:MAX_KEYWORDS]
        if keywords:
            meta["keywords"] = keywords
        headers = {}
        if self._conn.api_key:
            headers["Authorization"] = f"Bearer {self._conn.api_key}"
        try:
            with open(req.audio_path, "rb") as fh:
                resp = self._client.post(
                    self._url,
                    headers=headers,
                    files={
                        "request": (None, json.dumps(meta), "application/json"),
                        "audio": ("audio.wav", fh, "audio/wav"),
                    },
                    timeout=self._timeout_s,
                )
        except httpx.HTTPError as exc:  # timeouts and connection errors
            raise AiTransientError(f"network error: {type(exc).__name__}") from None
        except OSError:
            raise AiPermanentError("audio file is unreadable") from None
        status = resp.status_code
        if status >= 400:
            # Only the status is kept; the body never is.
            detail = f"HTTP {status}"
            if status in (408, 429) or status >= 500:
                raise AiTransientError(detail, retry_after_s=_retry_after(resp.headers))
            raise AiPermanentError(detail)
        try:
            return resp.json()
        except ValueError:
            raise AiInvalidOutput("response is not JSON") from None

    # --------------------------------------------------------------- parse
    def _parse(
        self, body: Any, req: TranscribeRequest
    ) -> tuple[TranscriptResult, list[Usage]]:
        if not isinstance(body, dict) or not isinstance(body.get("transcript"), str):
            raise AiInvalidOutput("response has no transcript")
        turns = body.get("turns")
        if turns is None:
            turns = []
        if not isinstance(turns, list):
            raise AiInvalidOutput("turns is not a list")
        parsed: list[tuple[float, float, str, str | None]] = []
        for turn in turns:
            if not isinstance(turn, dict):
                raise AiInvalidOutput("turn is not an object")
            text = turn.get("transcript")
            start, end = turn.get("startMs"), turn.get("endMs")
            if (
                not isinstance(text, str)
                or isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, (int, float))
                or not isinstance(end, (int, float))
            ):
                raise AiInvalidOutput("turn misses transcript, startMs or endMs")
            speaker = turn.get("speaker")
            parsed.append(
                (
                    start / 1000,
                    end / 1000,
                    _clean(text),
                    speaker if isinstance(speaker, str) and speaker else None,
                )
            )
        dur = max(0.0, req.duration_s)
        kept: list[tuple[float, float, str, str | None]] = []
        for start, end, text, speaker in parsed:
            start = round(min(max(start, 0.0), dur), 1)
            end = round(min(max(end, 0.0), dur), 1)
            if not text or end - start < 0.1 - 1e-9:
                continue
            kept.append((start, end, text, speaker))
        full = _clean(body["transcript"])
        if not turns and full and dur >= 0.1:
            kept.append((0.0, round(dur, 1), full, None))  # 04 section 3.2 rule 4
        kept.sort(key=lambda s: s[0])
        segments = [
            TranscriptSegmentOut(seq=i, start_s=s, end_s=e, text=t, speaker=sp)
            for i, (s, e, t, sp) in enumerate(kept)
        ]
        full_text = full or " ".join(s.text for s in segments)
        result = TranscriptResult(
            language=detect_language(full_text), segments=segments, full_text=full_text
        )
        audio_ms = body.get("audioDurationMs")
        if (
            isinstance(audio_ms, bool)
            or not isinstance(audio_ms, (int, float))
            or audio_ms < 0
        ):
            audio_ms = req.duration_s * 1000
        audio_ms = round(audio_ms)
        usage = Usage(
            provider=PROVIDER,
            model=self._conn.model,
            audio_s=audio_ms / 1000,
            usd_micros=self._prices.usd_micros(
                PROVIDER, self._conn.model, audio_ms=audio_ms
            ),
            purpose="transcribe",
        )
        return result, [usage]
