"""UT-AI-01 to UT-AI-07 (07 section 3.4): structured calls over a fake HTTP
boundary. The real `openai` SDK runs against `httpx.MockTransport`."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.ai.adapters.openai_compat import (
    OpenAICompatChecker,
    OpenAICompatDrafter,
    OpenAICompatSelector,
)
from app.ai.cost import PriceTable
from app.ai.errors import AiInvalidOutput, AiPermanentError, AiTransientError
from app.ai.structured import RawCompletion, StructuredCaller
from app.ai.types import (
    CheckItem,
    CheckRequest,
    DraftOutput,
    FactRef,
    SelectOutput,
    SelectRequest,
)
from app.config import Settings
from app.errors import JobError
from tests.unit.ai_helpers import (
    MODEL,
    VALID_DRAFT,
    FakeHttp,
    completion_body,
    draft_request,
    ok,
)

PRICES = PriceTable.from_file(Settings.model_fields["ai_prices_file"].default)
VALID = json.dumps(VALID_DRAFT)


def drafter(http: FakeHttp, **kw) -> OpenAICompatDrafter:
    return OpenAICompatDrafter(http.chat(), PRICES, **kw)


def caller(http: FakeHttp, purpose_model: str = MODEL):
    return StructuredCaller(PRICES, provider="muse", model=purpose_model), http.chat()


def run_structured(http: FakeHttp, schema=DraftOutput, purpose="draft"):
    sc, chat = caller(http)
    messages = [{"role": "user", "content": "hi"}]
    return sc.call(
        lambda msgs: chat.complete(msgs, {"type": "json_object"}, temperature=0, max_tokens=50),
        messages,
        schema,
        purpose,
    )


# ------------------------------------------------------------------ AI-01..03


def test_ut_ai_01_valid_first_try(tmp_path: Path):
    http = FakeHttp(ok(VALID, prompt_tokens=100, completion_tokens=10))
    out, usages = drafter(http).draft(draft_request(tmp_path))
    assert http.calls == 1
    assert isinstance(out, DraftOutput) and out.facts[0].situation == "new_person"
    assert len(usages) == 1
    u = usages[0]
    assert (u.provider, u.model, u.purpose) == ("muse", MODEL, "draft")
    assert (u.tokens_in, u.tokens_out) == (100, 10)
    assert u.usd_micros == (100 * 1_250_000 + 10 * 4_250_000 + 500_000) // 1_000_000


def test_ut_ai_02_invalid_once_then_valid(tmp_path: Path):
    http = FakeHttp(ok("this is not json"), ok(VALID))
    out, usages = drafter(http).draft(draft_request(tmp_path))
    assert http.calls == 2
    assert len(out.facts) == 1 and len(usages) == 2
    retry = http.requests[1]["messages"]
    # same request again, plus the bad answer and the error summary
    assert retry[: len(http.requests[0]["messages"])] == http.requests[0]["messages"]
    assert retry[-2] == {"role": "assistant", "content": "this is not json"}
    assert retry[-1]["role"] == "user"
    assert "Your last answer was not valid" in retry[-1]["content"]
    assert "json" in retry[-1]["content"].lower()


def test_ut_ai_02_error_summary_has_no_input_values(tmp_path: Path):
    bad = json.dumps({"facts": [{"situation": "grumpy-secret-value"}]})
    http = FakeHttp(ok(bad), ok(VALID))
    drafter(http).draft(draft_request(tmp_path))
    summary = http.requests[1]["messages"][-1]["content"]
    assert "grumpy-secret-value" not in summary
    assert summary.count("situation") >= 1  # loc is listed


@pytest.mark.parametrize(
    "bad",
    [
        dict(content="nope"),
        dict(content=VALID, finish="length"),
        dict(content=None, refusal="I cannot help with that"),
        dict(content=VALID, finish="content_filter"),
    ],
    ids=["not-json", "length", "refusal", "content-filter"],
)
def test_ut_ai_03_invalid_twice(bad):
    http = FakeHttp(ok(**bad), ok(**bad))
    with pytest.raises(AiInvalidOutput) as exc:
        run_structured(http)
    assert http.calls == 2  # no third call
    assert len(exc.value.usages) == 2  # failed calls are billed


def test_ut_ai_03_public_method_raises_job_error(tmp_path: Path):
    http = FakeHttp(ok("nope"), ok("nope"))
    with pytest.raises(JobError) as exc:
        drafter(http).draft(draft_request(tmp_path))
    assert (exc.value.code, exc.value.retryable) == ("ai_invalid_output", False)
    assert len(exc.value.usages) == 2
    assert isinstance(exc.value.__cause__, AiInvalidOutput)


def test_ut_ai_03_checker_and_selector_invalid_output_is_ai_failed():
    http = FakeHttp(ok("x"), ok("x"))
    chk = OpenAICompatChecker(http.chat(), PRICES)
    req = CheckRequest(
        items=[CheckItem(ref="C1", situation="leash_walk", behavior="Pulled on the leash.", source="clip")]
    )
    with pytest.raises(JobError) as exc:
        chk.check(req)
    assert (exc.value.code, exc.value.retryable) == ("ai_failed", False)
    http = FakeHttp(ok("x"), ok("x"))
    sel = OpenAICompatSelector(http.chat(), PRICES)
    sreq = SelectRequest(
        question="Does she bark?",
        facts=[FactRef(ref="F1", situation="leash_walk", behavior="Pulled on the leash.")],
    )
    with pytest.raises(JobError) as exc:
        sel.select(sreq)
    assert exc.value.code == "ai_failed" and len(exc.value.usages) == 2


# --------------------------------------------------------------------- AI-04


def test_ut_ai_04_transient_not_retried():
    http = FakeHttp(
        httpx.Response(
            503,
            headers={"Retry-After": "7"},
            json={"error": {"message": "overloaded", "code": "service_overloaded"}},
        )
    )
    with pytest.raises(AiTransientError) as exc:
        run_structured(http)
    assert http.calls == 1
    assert exc.value.retry_after_s == 7.0
    assert exc.value.usages == []


def test_ut_ai_04_public_method_maps_to_retryable_job_error(tmp_path: Path):
    http = FakeHttp(httpx.Response(503, headers={"Retry-After": "7"}, json={"error": {}}))
    with pytest.raises(JobError) as exc:
        drafter(http).draft(draft_request(tmp_path))
    e = exc.value
    assert (e.code, e.retryable, e.retry_after_s) == ("ai_failed", True, 7.0)
    assert e.usages == ()


def test_ut_ai_04_transient_after_invalid_first_try_keeps_first_usage():
    http = FakeHttp(ok("nope"), httpx.Response(503, json={"error": {}}))
    with pytest.raises(AiTransientError) as exc:
        run_structured(http)
    assert http.calls == 2 and len(exc.value.usages) == 1


# --------------------------------------------------------------------- AI-05

REQ = httpx.Request("POST", "https://ai.invalid/v1/chat/completions")


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_ut_ai_05_transient_statuses(status):
    http = FakeHttp(httpx.Response(status, json={"error": {"message": "BODY-TEXT", "code": "x"}}))
    with pytest.raises(AiTransientError) as exc:
        http.chat().complete([{"role": "user", "content": "x"}], {}, temperature=0, max_tokens=10)
    assert f"{status}" in str(exc.value) and "BODY-TEXT" not in str(exc.value)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404])
def test_ut_ai_05_permanent_statuses(status):
    http = FakeHttp(
        httpx.Response(status, json={"error": {"message": "BODY-TEXT", "code": "invalid_thing"}})
    )
    with pytest.raises(AiPermanentError) as exc:
        http.chat().complete([{"role": "user", "content": "x"}], {}, temperature=0, max_tokens=10)
    text = str(exc.value)
    assert str(status) in text and "invalid_thing" in text and "BODY-TEXT" not in text


def test_ut_ai_05_content_policy_is_permanent():
    http = FakeHttp(
        httpx.Response(400, json={"error": {"message": "no", "code": "content_policy_violation"}})
    )
    with pytest.raises(AiPermanentError) as exc:
        http.chat().complete([{"role": "user", "content": "x"}], {}, temperature=0, max_tokens=10)
    assert "content_policy_violation" in str(exc.value)


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("t", request=REQ), httpx.ConnectError("reset", request=REQ)],
    ids=["timeout", "connection-reset"],
)
def test_ut_ai_05_network_is_transient(error):
    http = FakeHttp(error)
    with pytest.raises(AiTransientError):
        http.chat().complete([{"role": "user", "content": "x"}], {}, temperature=0, max_tokens=10)
    assert http.calls == 1


# --------------------------------------------------------------------- AI-06

LONG = "x" * 300
CASES = {
    "not-json": "{not json",
    "missing-field": {"facts": [{"situation": "new_person", "behavior": "Walked up to the visitor.", "source": "clip"}]},
    "extra-field": {"facts": [], "comment": "she is friendly"},
    "wrong-type": {"facts": "none"},
    "situation-grumpy": {"facts": [{"situation": "grumpy", "behavior": "Walked up to the visitor.", "source": "clip", "evidence": [{"start_t": 0, "end_t": 3}]}]},
    "behavior-1-char": {"facts": [{"situation": "new_person", "behavior": "x", "source": "clip", "evidence": [{"start_t": 0, "end_t": 3}]}]},
    "behavior-300-chars": {"facts": [{"situation": "new_person", "behavior": LONG, "source": "clip", "evidence": [{"start_t": 0, "end_t": 3}]}]},
    "nine-facts": {"facts": [VALID_DRAFT["facts"][0]] * 9},
    "empty-evidence": {"facts": [{"situation": "new_person", "behavior": "Walked up to the visitor.", "source": "clip", "evidence": []}]},
    # 07 lists the next three, but 04 section 4.3/5 and 06 section 3.3 say they are
    # repaired after validation (newline stripped, reversed times swapped, rows capped
    # at 3), and the frozen `ai/types.py` does not reject them. 04 wins.
    "behavior-newline": {"facts": [{"situation": "new_person", "behavior": "Walked up\nto the visitor.", "source": "clip", "evidence": [{"start_t": 0, "end_t": 3}]}]},
    "start-after-end": {"facts": [{"situation": "new_person", "behavior": "Walked up to the visitor.", "source": "clip", "evidence": [{"start_t": 9, "end_t": 3}]}]},
    "four-evidence-items": {"facts": [{"situation": "new_person", "behavior": "Walked up to the visitor.", "source": "clip", "evidence": [{"start_t": 0, "end_t": 3}] * 4}]},
}
AMBIGUOUS = {"behavior-newline", "start-after-end", "four-evidence-items"}
XFAIL_REASON = "07 UT-AI-06 vs 04 4.3/5 + 06 3.3: repaired after validation, not schema-invalid; 04 wins"


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(n, marks=pytest.mark.xfail(reason=XFAIL_REASON, strict=True))
        if n in AMBIGUOUS
        else n
        for n in CASES
    ],
)
def test_ut_ai_06_schema_invalid_triggers_retry(name):
    payload = CASES[name]
    text = payload if isinstance(payload, str) else json.dumps(payload)
    http = FakeHttp(ok(text), ok(VALID))
    out, usages = run_structured(http)
    assert http.calls == 2 and len(usages) == 2  # the retry path ran
    assert out.facts[0].situation == "new_person"


# --------------------------------------------------------------------- AI-07


@pytest.mark.parametrize(
    "evidence",
    [
        [{"start_t": 0, "end_t": 9999}],  # past the clip
        [{"start_t": 7, "end_t": 8}],  # off-grid for k=3
        [{"start_t": -5, "end_t": 3}],  # negative
        ["c9-seg1"],  # unknown ref
    ],
    ids=["past-clip", "off-grid", "negative", "unknown-ref"],
)
def test_ut_ai_07_content_problems_are_schema_valid(evidence):
    payload = {"facts": [{**VALID_DRAFT["facts"][0], "evidence": evidence}]}
    http = FakeHttp(ok(json.dumps(payload)))
    out, usages = run_structured(http)
    assert http.calls == 1 and len(usages) == 1
    assert isinstance(out, DraftOutput)


def test_structured_caller_accepts_scripted_send():
    """The caller needs nothing but a `send` callable (06 section 3.3)."""
    sc = StructuredCaller(PRICES, provider="muse", model=MODEL)
    seen = []

    def send(msgs):
        seen.append(len(msgs))
        return RawCompletion(content='{"refs": ["F1"]}', finish_reason="stop", tokens_in=5, tokens_out=2)

    res = sc.call(send, [{"role": "user", "content": "q"}], SelectOutput, "qa_select")
    assert res.value.refs == ["F1"] and seen == [1]
    assert res.usages[0].purpose == "qa_select"


def test_completion_without_usage_still_yields_one_usage_row():
    http = FakeHttp(httpx.Response(200, json=completion_body(VALID, usage=False)))
    out, usages = run_structured(http)
    assert len(usages) == 1 and usages[0].tokens_in == 0
