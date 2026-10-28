"""UT-AI-13, UT-AI-14 (the part that belongs to the ai layer), UT-CFG-02 helpers,
registry wiring and the rules adapter."""

from __future__ import annotations

import pytest

from app.ai.adapters.mock import MockAdapter
from app.ai.adapters.openai_compat import (
    OpenAICompatChecker,
    OpenAICompatDrafter,
    OpenAICompatSelector,
)
from app.ai.adapters.rules import RulesChecker
from app.ai.errors import (
    AiError,
    AiInvalidOutput,
    AiPermanentError,
    AiTransientError,
    to_job_error,
)
from app.ai.registry import AiConfigError, AiRegistry
from app.ai.types import CheckItem, CheckRequest, Flag, Usage
from app.config import Settings
from app.errors import JobError

USAGES = [Usage(provider="muse", model="m", tokens_in=1, tokens_out=1, purpose="draft")]


def settings(**kw) -> Settings:
    return Settings(_env_file=None, secret_key="k" * 32, ip_hash_key="i" * 16, **kw)


# --------------------------------------------------------------------- AI-13


def test_ut_ai_13_transient_is_retryable_with_retry_after():
    e = AiTransientError("503", retry_after_s=12.5, usages=USAGES)
    for purpose in ("transcribe", "draft", "check", "qa_select", "spike"):
        j = to_job_error(e, purpose)  # type: ignore[arg-type]
        assert (j.code, j.retryable, j.retry_after_s) == ("ai_failed", True, 12.5)
        assert list(j.usages) == USAGES


def test_ut_ai_13_permanent_is_not_retryable():
    j = to_job_error(AiPermanentError("401", usages=USAGES), "draft")
    assert (j.code, j.retryable, j.retry_after_s) == ("ai_failed", False, None)
    assert list(j.usages) == USAGES


@pytest.mark.parametrize(
    "purpose,code",
    [("draft", "ai_invalid_output"), ("transcribe", "ai_failed"), ("check", "ai_failed"),
     ("qa_select", "ai_failed")],
)
def test_ut_ai_13_invalid_output_by_purpose(purpose, code):
    j = to_job_error(AiInvalidOutput("bad", usages=USAGES), purpose)  # type: ignore[arg-type]
    assert (j.code, j.retryable) == (code, False)
    assert len(j.usages) == 1


def test_ut_ai_13_base_ai_error_is_permanent():
    j = to_job_error(AiError("?"), "check")
    assert (j.code, j.retryable) == ("ai_failed", False)


def test_ut_ai_13_ffmpeg_cases_map_to_transcode_failed():
    from app.pipeline.ffmpeg import FFmpegError, ffmpeg_error_to_job_error

    for kind in ("timeout", "killed", "disk_full"):
        err = ffmpeg_error_to_job_error(FFmpegError(kind, "x"))
        assert (err.code, err.retryable) == ("transcode_failed", True), kind
    err = ffmpeg_error_to_job_error(FFmpegError("exit", "bad", returncode=1))
    assert (err.code, err.retryable) == ("transcode_failed", False)


# --------------------------------------------------------------------- AI-14


@pytest.mark.parametrize("err", [AiTransientError, AiPermanentError, AiInvalidOutput])
def test_ut_ai_14_every_check_error_is_one_catchable_job_error(err):
    """ai part of UT-AI-14: any `AiError` of a check call leaves the checker as a
    `JobError` (ai_failed), so the handler can catch it and set `check_unavailable`."""
    j = to_job_error(err("x"), "check")
    assert isinstance(j, JobError) and j.code == "ai_failed"
    flag = Flag(code="check_unavailable", severity="info", source="system",
                detail="The wording check did not run. Read the sentence yourself.")
    assert flag.severity == "info"


def test_ut_ai_14_check_handler_sets_check_unavailable():
    """The handler half: a checker failure never fails the session. The wording
    service sets `check_unavailable` and the handler still marks `review_ready`;
    after the retries are used up the final-failure hook does the same."""
    from types import SimpleNamespace

    from app.pipeline.handlers.check import CheckHandler
    from app.services.views import JobView

    calls: list[tuple] = []
    wording = SimpleNamespace(
        apply_model_flags=lambda sid, ids, checker: calls.append(("flags", sid, list(ids))),
        mark_check_unavailable=lambda sid, ids: calls.append(("unavailable", sid, list(ids))),
    )
    sessions = SimpleNamespace(
        mark_review_ready=lambda sid: calls.append(("ready", sid)),
        mark_failed=lambda *a, **k: calls.append(("failed", a)),
    )
    ctx = SimpleNamespace(
        services=SimpleNamespace(wording_service=wording, session_service=sessions),
        ai=SimpleNamespace(checker=object()),
    )
    job = JobView(
        id=1, type="check", payload={"session_id": "s1", "fact_ids": ["f1", "f2"]},
        dog_id="d1", session_id="s1", clip_id=None, dedupe_key=None, attempts=1, max_attempts=2,
    )
    handler = CheckHandler()
    handler.handle(job, ctx)
    assert calls == [("flags", "s1", ["f1", "f2"]), ("ready", "s1")]
    calls.clear()
    handler.on_final_failure(job, JobError("ai_failed", False), ctx)
    assert calls == [("unavailable", "s1", ["f1", "f2"]), ("ready", "s1")]
    assert not any(c[0] == "failed" for c in calls)


# ---------------------------------------------------------------- registry


def test_registry_builds_mock_and_rules_by_default():
    reg = AiRegistry.from_settings(settings())
    assert isinstance(reg.transcriber(), MockAdapter)
    assert isinstance(reg.drafter(), MockAdapter)
    assert isinstance(reg.selector(), MockAdapter)
    assert isinstance(reg.checker(), RulesChecker)
    assert reg.drafter() is reg.selector()  # one mock instance: faults are counted once


def test_registry_builds_openai_compat_roles():
    s = settings(
        ai_drafter="openai_compat", ai_checker="openai_compat", ai_selector="openai_compat",
        ai_api_key="shared-key", ai_selector_model="muse-small",
    )
    reg = AiRegistry.from_settings(s)
    assert isinstance(reg.drafter(), OpenAICompatDrafter)
    assert isinstance(reg.checker(), OpenAICompatChecker)
    sel = reg.selector()
    assert isinstance(sel, OpenAICompatSelector)
    assert sel._chat.model == "muse-small"  # per-role override
    assert reg.drafter()._chat.model == "muse-spark-1.3"


def test_registry_openai_compat_without_key_is_a_config_error():
    with pytest.raises(AiConfigError) as exc:
        AiRegistry.from_settings(settings(ai_drafter="openai_compat"))
    assert "AI_API_KEY" in str(exc.value) and "DRAFTER" in str(exc.value)


def test_registry_refuses_contributor_model():
    with pytest.raises(AiConfigError) as exc:
        AiRegistry.from_settings(settings(ai_model="muse-spark-1.3-contributor"))
    assert "contributor" in str(exc.value)
    with pytest.raises(AiConfigError):
        AiRegistry.from_settings(settings(ai_selector_model="x-contributor"))
    # allowed only by the explicit switch
    AiRegistry.from_settings(
        settings(ai_model="muse-spark-1.3-contributor", ai_allow_contributor_model=True)
    )


def test_registry_real_transcribers_wait_for_phase_3():
    with pytest.raises(AiConfigError):
        AiRegistry.from_settings(settings(ai_transcriber="muse_transcribe", ai_api_key="k"))


# ------------------------------------------------------------------- rules


def test_rules_checker_returns_none_for_everything_without_usage():
    req = CheckRequest(items=[
        CheckItem(ref="C1", situation="new_person", behavior="Seemed nervous.", source="clip"),
        CheckItem(ref="C2", situation="leash_walk", behavior="Pulled on the leash.", source="clip"),
    ])
    results, usages = RulesChecker().check(req)
    assert [(r.ref, r.kind, r.phrase) for r in results] == [("C1", "none", None), ("C2", "none", None)]
    assert usages == []
