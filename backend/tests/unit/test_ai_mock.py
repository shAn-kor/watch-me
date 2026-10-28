"""UT-AI-11, UT-AI-12: the mock adapter (04 section 8.1, 07 section 2.3)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.ai.adapters.mock import MockAdapter, MockFixtureError
from app.ai.errors import AiInvalidOutput, AiPermanentError, AiTransientError
from app.ai.protocols import FactDrafter, FactSelector, Transcriber, WordingChecker
from app.ai.types import (
    CheckItem,
    CheckRequest,
    DraftRequest,
    FactRef,
    SelectRequest,
    TranscribeRequest,
)
from app.errors import JobError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ai"


def transcribe_req(key: str | None) -> TranscribeRequest:
    return TranscribeRequest(audio_path="a.wav", duration_s=5.0, fixture_key=key)


def draft_req(key: str | None, allowed=("leash_walk", "new_person")) -> DraftRequest:
    return DraftRequest(
        mode="frames", clip_ord=1, duration_s=5.0, k=1,
        frames=[{"t": i, "path": f"t{i}.jpg"} for i in range(5)],
        transcript=[], allowed_situations=list(allowed), dog_name=None,
        observed_on=date(2026, 10, 27), fixture_key=key,
    )  # type: ignore[arg-type]


def write(dir_: Path, name: str, body: dict) -> None:
    (dir_ / f"{name}.json").write_text(json.dumps(body))


# --------------------------------------------------------------------- AI-11


def test_ut_ai_11_protocols_and_determinism():
    m = MockAdapter(FIXTURES)
    assert all(isinstance(m, p) for p in (Transcriber, FactDrafter, WordingChecker, FactSelector))
    a1, u1 = m.transcribe(transcribe_req("h264_5s"))
    a2, u2 = m.transcribe(transcribe_req("h264_5s"))
    assert a1 == a2 and u1 == u2
    d1, _ = m.draft(draft_req("h264_5s"))
    d2, _ = m.draft(draft_req("h264_5s"))
    assert d1 == d2 and len(d1.facts) == 2
    assert a1.language == "en" and (a1.segments[0].start_s, a1.segments[0].end_s) == (0.5, 2.0)
    assert [s.seq for s in a1.segments] == list(range(len(a1.segments)))
    assert a1.full_text == " ".join(s.text for s in a1.segments)


def test_ut_ai_11_unknown_key_is_a_clear_test_error(tmp_path: Path):
    with pytest.raises(MockFixtureError) as exc:
        MockAdapter(tmp_path).draft(draft_req("nope"))
    assert "nope" in str(exc.value) and "default" in str(exc.value)


def test_ut_ai_11_mock_usage_is_synthetic_and_free():
    m = MockAdapter(FIXTURES)
    _, usages = m.draft(draft_req("h264_5s"))
    (u,) = usages
    assert (u.provider, u.usd_micros, u.purpose) == ("mock", 0, "draft")
    assert u.tokens_in > 0 and u.tokens_out > 0
    _, tu = m.transcribe(transcribe_req("h264_5s"))
    assert tu[0].purpose == "transcribe" and tu[0].audio_s == 5.0


def test_mock_filters_situations_and_max_facts():
    m = MockAdapter(FIXTURES)
    out, _ = m.draft(draft_req("h264_5s", allowed=("leash_walk",)))
    assert [f.situation for f in out.facts] == ["leash_walk"]
    req = draft_req("h264_5s")
    req.max_facts = 1
    assert len(m.draft(req)[0].facts) == 1


def test_mock_check_rules():
    m = MockAdapter(FIXTURES)
    req = CheckRequest(
        items=[
            CheckItem(ref="C1", situation="new_person", behavior="She was a bit SHY at first.", source="clip"),
            CheckItem(ref="C2", situation="leash_walk", behavior="Pulled on the leash.", source="clip"),
        ],
        fixture_key=None,
    )
    results, usages = m.check(req)
    assert [(r.ref, r.kind) for r in results] == [("C1", "trait_label"), ("C2", "none")]
    assert results[0].phrase and results[1].phrase is None
    assert usages[0].purpose == "check"


def test_mock_select_rules_return_refs_even_outside_the_set(tmp_path: Path):
    write(tmp_path, "default", {"select": [
        {"question_contains": ["kid", "child"], "refs": ["F3"]},
        {"question_contains": ["bark"], "refs": ["F1", "F99"]},
    ]})
    m = MockAdapter(tmp_path)
    facts = [FactRef(ref="F1", situation="new_person", behavior="Walked up.")]
    sel = lambda q: m.select(SelectRequest(question=q, facts=facts))[0].refs
    assert sel("Is she good with KIDS?") == ["F3"]
    assert sel("Does she bark?") == ["F1", "F99"]
    assert sel("What colour is she?") == []


@pytest.mark.parametrize(
    "name,refs",
    [
        ("in_set", ["F2", "F5"]),
        ("out_of_set_alias", ["F2", "F99"]),
        ("duplicates", ["F1", "F1", "F2"]),
        ("empty", []),
        ("lowercase_ref", ["f3"]),
    ],
)
def test_mock_selector_fixtures(name, refs):
    m = MockAdapter(FIXTURES)
    req = SelectRequest(
        question="anything at all",
        facts=[FactRef(ref="F1", situation="new_person", behavior="Walked up.")],
        fixture_key=f"selector_{name}",
    )
    assert m.select(req)[0].refs == refs


def test_mock_selector_fixture_set_is_complete():
    names = {p.stem for p in FIXTURES.glob("selector_*.json")}
    assert names >= {
        "selector_in_set", "selector_out_of_set_alias", "selector_other_dog_hex_id",
        "selector_prose", "selector_too_many", "selector_duplicates",
        "selector_empty", "selector_lowercase_ref",
    }


def test_all_07_fixture_files_exist_and_parse():
    expected = [
        "default", "h264_5s", "hevc_8s", "silent_5s", "dup_pair_a", "dup_pair_b", "dup_five",
        "dup_narr_clip", "zero_facts", "short_0_8s", "bad_ranges", "trait_words", "inject_narration",
    ]
    m = MockAdapter(FIXTURES)
    for name in expected:
        assert (FIXTURES / f"{name}.json").is_file(), name
        m.draft(draft_req(name, allowed=tuple(__import__("app.domain.situations", fromlist=["SITUATION_ORDER"]).SITUATION_ORDER)))
    ko, _ = m.transcribe(transcribe_req("hevc_8s"))
    assert ko.language == "ko"
    assert m.transcribe(transcribe_req("silent_5s"))[0].segments == []


# --------------------------------------------------------------------- AI-12


def faulty(tmp_path: Path, faults, **kw) -> MockAdapter:
    base = {"transcript": {"language": "en", "segments": []}, "facts": []}
    write(tmp_path, "default", base)
    write(tmp_path, "flaky", {**base, "faults": faults})
    return MockAdapter(tmp_path, **kw)


def test_ut_ai_12_transient_then_success(tmp_path: Path):
    m = faulty(tmp_path, [{"kind": "transient", "fail_times": 2, "retry_after_s": 4}], raise_ai_errors=True)
    for _ in range(2):
        with pytest.raises(AiTransientError) as exc:
            m.transcribe(transcribe_req("flaky"))
        assert exc.value.retry_after_s == 4
    result, usages = m.transcribe(transcribe_req("flaky"))
    assert result.segments == [] and usages[0].usd_micros == 0


def test_ut_ai_12_invalid_output_per_fail_times(tmp_path: Path):
    m = faulty(tmp_path, [{"kind": "invalid_output", "fail_times": 2}], raise_ai_errors=True)
    for _ in range(2):
        with pytest.raises(AiInvalidOutput):
            m.draft(draft_req("flaky"))
    assert m.draft(draft_req("flaky"))[0].facts == []


def test_ut_ai_12_permanent(tmp_path: Path):
    m = faulty(tmp_path, [{"kind": "permanent", "fail_times": 1}], raise_ai_errors=True)
    with pytest.raises(AiPermanentError):
        m.draft(draft_req("flaky"))
    assert m.draft(draft_req("flaky"))[0].facts == []


def test_ut_ai_12_counted_per_fixture(tmp_path: Path):
    m = faulty(tmp_path, [{"kind": "transient", "fail_times": 1}], raise_ai_errors=True)
    write(tmp_path, "flaky2", {"faults": [{"kind": "transient", "fail_times": 1}]})
    with pytest.raises(AiTransientError):
        m.draft(draft_req("flaky"))
    with pytest.raises(AiTransientError):  # flaky2 has its own counter
        m.draft(draft_req("flaky2"))
    m.draft(draft_req("flaky"))
    m.draft(draft_req("flaky2"))


def test_ut_ai_12_04_form_faults_by_method(tmp_path: Path):
    m = faulty(
        tmp_path,
        {"transcribe": {"kind": "transient", "fail_times": 1, "retry_after_s": None},
         "draft": {"kind": "invalid_output", "fail_times": 2}, "check": None, "select": None},
        raise_ai_errors=True,
    )
    with pytest.raises(AiTransientError):
        m.transcribe(transcribe_req("flaky"))
    m.transcribe(transcribe_req("flaky"))
    with pytest.raises(AiInvalidOutput):
        m.draft(draft_req("flaky"))
    check = CheckRequest(
        items=[CheckItem(ref="C1", situation="leash_walk", behavior="Pulled on the leash.", source="clip")],
        fixture_key="flaky",
    )
    assert m.check(check)[0][0].kind == "none"  # not faulted


def test_ut_ai_12_default_converts_to_job_error(tmp_path: Path):
    """04 8.1: the mock converts like a real adapter. 07 expects the raw AiError
    classes, which `raise_ai_errors=True` provides (see above)."""
    m = faulty(tmp_path, [{"kind": "transient", "fail_times": 1, "retry_after_s": 9}])
    with pytest.raises(JobError) as exc:
        m.transcribe(transcribe_req("flaky"))
    assert (exc.value.code, exc.value.retryable, exc.value.retry_after_s) == ("ai_failed", True, 9)
    # list-form faults count calls of every method; a new adapter starts its own counters
    with pytest.raises(JobError) as exc:
        MockAdapter(tmp_path).draft(draft_req("flaky"))
    assert exc.value.code == "ai_failed" and exc.value.retryable


def test_ut_ai_12_invalid_output_code_by_purpose(tmp_path: Path):
    m = faulty(tmp_path, {"draft": {"kind": "invalid_output", "fail_times": 1},
                          "transcribe": {"kind": "invalid_output", "fail_times": 1}})
    with pytest.raises(JobError) as exc:
        m.draft(draft_req("flaky"))
    assert (exc.value.code, exc.value.retryable) == ("ai_invalid_output", False)
    with pytest.raises(JobError) as exc:
        m.transcribe(transcribe_req("flaky"))
    assert exc.value.code == "ai_failed"


def test_ut_ai_12_fallback_to_default_and_missing_both(tmp_path: Path):
    write(tmp_path, "default", {"facts": [{
        "situation": "leash_walk", "behavior": "Pulled on the leash for a minute.",
        "source": "clip", "evidence": [{"start_t": 0, "end_t": 2}]}]})
    m = MockAdapter(tmp_path)
    assert len(m.draft(draft_req("not_there"))[0].facts) == 1
    assert len(m.draft(draft_req(None))[0].facts) == 1
    with pytest.raises(MockFixtureError):
        MockAdapter(tmp_path / "empty").draft(draft_req("x"))
