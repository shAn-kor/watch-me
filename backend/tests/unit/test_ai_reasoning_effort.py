"""reasoning_effort per role, max_tokens budget and the length-cutoff error detail."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ai.adapters.openai_compat import MAX_TOKENS, OpenAICompatDrafter
from app.ai.cost import PriceTable
from app.ai.registry import AiRegistry
from app.config import Settings
from app.errors import JobError
from tests.unit.ai_helpers import VALID_DRAFT, FakeHttp, draft_request, ok

PRICES = PriceTable.from_file(Settings.model_fields["ai_prices_file"].default)


def settings(**kw) -> Settings:
    return Settings(_env_file=None, secret_key="k" * 32, ip_hash_key="i" * 16, **kw)


def send(http: FakeHttp, **kw) -> None:
    http.chat(**kw).complete([{"role": "user", "content": "x"}], {}, temperature=0, max_tokens=10)


def test_effort_is_sent_when_set():
    http = FakeHttp(ok("{}"))
    send(http, reasoning_effort="minimal")
    assert http.requests[0]["reasoning_effort"] == "minimal"


@pytest.mark.parametrize("value", [None, ""])
def test_effort_is_omitted_when_unset(value):
    http = FakeHttp(ok("{}"))
    send(http, reasoning_effort=value)
    assert "reasoning_effort" not in http.requests[0]


def test_settings_defaults_per_role():
    s = settings()
    assert s.ai_connection("drafter").reasoning_effort == "low"
    assert s.ai_connection("selector").reasoning_effort == "minimal"
    assert s.ai_connection("checker").reasoning_effort == "minimal"
    assert s.ai_connection("transcriber").reasoning_effort is None


def test_settings_accepts_override_and_blank():
    s = settings(ai_drafter_reasoning_effort="high", ai_selector_reasoning_effort="")
    assert s.ai_connection("drafter").reasoning_effort == "high"
    assert s.ai_connection("selector").reasoning_effort is None


def test_settings_blank_from_environment(monkeypatch):
    monkeypatch.setenv("AI_CHECKER_REASONING_EFFORT", "")
    assert settings().ai_connection("checker").reasoning_effort is None


@pytest.mark.parametrize("bad", ["none", "fast", "LOWEST"])
def test_settings_rejects_unsupported_effort(bad):
    for field in (
        "ai_drafter_reasoning_effort",
        "ai_checker_reasoning_effort",
        "ai_selector_reasoning_effort",
    ):
        with pytest.raises(ValidationError):
            settings(**{field: bad})


def test_registry_plumbs_effort_per_role():
    s = settings(
        ai_api_key="key",
        ai_drafter="openai_compat",
        ai_checker="openai_compat",
        ai_selector="openai_compat",
        ai_drafter_reasoning_effort="medium",
        ai_selector_reasoning_effort="",
    )
    reg = AiRegistry.from_settings(s)
    assert reg.drafter()._chat._reasoning_effort == "medium"  # type: ignore[attr-defined]
    assert reg.checker()._chat._reasoning_effort == "minimal"  # type: ignore[attr-defined]
    assert reg.selector()._chat._reasoning_effort is None  # type: ignore[attr-defined]


def test_max_tokens_cover_reasoning_and_answer():
    assert MAX_TOKENS == {"draft": 6000, "check": 2000, "qa_select": 1500}


def test_drafter_sends_role_budget_and_effort(tmp_path: Path):
    http = FakeHttp(ok(json.dumps(VALID_DRAFT)))
    OpenAICompatDrafter(http.chat(reasoning_effort="low"), PRICES).draft(draft_request(tmp_path))
    assert http.requests[0]["max_tokens"] == 6000
    assert http.requests[0]["reasoning_effort"] == "low"


def test_length_cutoff_is_an_error_and_says_so(tmp_path: Path):
    http = FakeHttp(ok(None, finish="length"), ok(None, finish="length"))
    with pytest.raises(JobError) as exc:
        OpenAICompatDrafter(http.chat(), PRICES).draft(draft_request(tmp_path))
    assert exc.value.code == "ai_invalid_output" and not exc.value.retryable
    assert "finish_reason=length" in exc.value.detail  # type: ignore[attr-defined]
