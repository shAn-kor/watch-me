"""UT-CFG-01..04: Settings validation (06 section 5, 04 section 8.6)."""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

GOOD = {"secret_key": "k" * 32, "ip_hash_key": "ip-hash-key-for-tests"}


def make(monkeypatch, **overrides):
    from app.config import Settings

    # Isolate from the developer's environment.
    names = {f.upper() for f in Settings.model_fields}
    for name in list(os.environ):
        if name.upper() in names or name.upper().startswith(("AI_", "SEED_")):
            monkeypatch.delenv(name, raising=False)
    return Settings(_env_file=None, **{**GOOD, **overrides})


def test_ut_cfg_01_missing_secret_key_fails(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, ip_hash_key="x")
    assert "secret_key" in str(exc.value)


def test_ut_cfg_01_short_secret_key_fails(monkeypatch):
    with pytest.raises(ValidationError) as exc:
        make(monkeypatch, secret_key="12345678")
    assert "32" in str(exc.value)


def test_ut_cfg_01_env_var_is_read(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("SECRET_KEY", "e" * 40)
    monkeypatch.setenv("IP_HASH_KEY", "abc")
    s = Settings(_env_file=None)
    assert s.secret_key.get_secret_value() == "e" * 40


def test_ut_cfg_01_defaults_match_the_spec(monkeypatch):
    s = make(monkeypatch)
    assert s.qa_daily_usd_cap == 3.00
    assert s.qa_max_facts == 5
    assert s.ai_timeout_s == 75
    assert s.draft_mode == "frames"
    assert s.ai_allow_contributor_model is False
    assert s.app_env == "dev"
    assert s.cookie_secure is True
    assert s.database_url == "sqlite:///./data/watchme.db"
    assert s.max_clip_bytes == 209_715_200
    assert s.max_clip_s == 120.0
    assert s.clip_duration_tolerance_s == 0.5
    assert s.max_clips_per_session == 3
    assert s.allowed_extensions == [".mp4", ".mov"]
    assert s.session_max_age_s == 604_800
    assert s.frame_max_count == 48
    assert s.segment_len_s == 10
    assert (s.ai_transcriber, s.ai_drafter, s.ai_checker, s.ai_selector) == (
        "mock",
        "mock",
        "rules",
        "mock",
    )
    assert s.ai_base_url == "https://api.meta.ai/v1"
    assert s.ai_model == "muse-spark-1.3"
    assert s.ai_stream is False and s.ai_schema_strict is True
    assert (s.qa_question_min_chars, s.qa_question_max_chars) == (3, 300)
    assert s.qa_limit_per_hour == 10
    assert (s.rate_login_per_ip, s.rate_login_per_email) == (10, 5)
    assert (
        s.worker_poll_s == 2.0 and s.job_stale_s == 600 and s.job_retention_days == 14
    )
    assert (s.qa_question_retention_days, s.qa_row_retention_days) == (30, 90)
    assert s.tmp_max_age_h == 6
    assert s.transcode_timeout_s == 600
    assert (
        s.transcribe_timeout_s,
        s.sample_timeout_s,
        s.draft_timeout_s,
        s.check_timeout_s,
    ) == (
        180,
        180,
        180,
        180,
    )
    assert (s.purge_clip_timeout_s, s.purge_dog_timeout_s, s.sweep_timeout_s) == (
        120,
        300,
        60,
    )
    assert s.log_level == "INFO"


def test_ut_cfg_01_secrets_do_not_leak_in_repr(monkeypatch):
    s = make(monkeypatch, ai_api_key="provider-token-123")
    text = repr(s) + str(s.model_dump())
    assert "k" * 32 not in text and "provider-token-123" not in text


def test_ut_cfg_01_invalid_values_rejected(monkeypatch):
    for bad in (
        {"draft_mode": "native_video"},
        {"ai_drafter": "local_whisper"},
        {"max_clip_s": 0},
        {"qa_daily_usd_cap": -1},
        {"qa_question_min_chars": 10, "qa_question_max_chars": 5},
    ):
        with pytest.raises(ValidationError):
            make(monkeypatch, **bad)


def test_ut_cfg_01_per_role_ai_connection_falls_back(monkeypatch):
    s = make(monkeypatch, ai_api_key="shared", ai_drafter_model="muse-x")
    drafter = s.ai_connection("drafter")
    assert (drafter.base_url, drafter.model, drafter.api_key) == (
        "https://api.meta.ai/v1",
        "muse-x",
        "shared",
    )
    # The transcriber never defaults to AI_MODEL.
    assert s.ai_connection("transcriber").model == "muse-voice-transcribe-1.0"
    assert s.ai_connection("checker").model == "muse-spark-1.3"


def test_ut_cfg_02_contributor_model_guard(monkeypatch):
    """UT-CFG-02: Settings reports contributor models; AiRegistry (lane C) refuses on it."""
    s = make(monkeypatch, ai_model="muse-spark-1.3-contributor")
    assert s.forbidden_contributor_models()  # non-empty
    allowed = make(
        monkeypatch,
        ai_model="muse-spark-1.3-contributor",
        ai_allow_contributor_model=True,
    )
    assert allowed.forbidden_contributor_models() == []
    per_role = make(monkeypatch, ai_selector_model="x-contributor")
    assert per_role.forbidden_contributor_models() == ["x-contributor"]
    assert make(monkeypatch).forbidden_contributor_models() == []


@pytest.mark.xfail(
    reason="AiRegistry.from_settings is lane C (ai/registry.py); the Settings-side guard is tested above",
    strict=False,
)
def test_ut_cfg_02_registry_refuses_contributor_model(monkeypatch):
    from app.ai.registry import AiRegistry  # noqa: F401  (does not exist before lane C)

    raise AssertionError(
        "lane C must assert AiRegistry.from_settings raises a config error"
    )


def test_ut_cfg_03_prod_requires_secure_cookie(monkeypatch):
    with pytest.raises(ValidationError) as exc:
        make(monkeypatch, app_env="prod", cookie_secure=False)
    assert "COOKIE_SECURE" in str(exc.value)
    assert make(monkeypatch, app_env="prod", cookie_secure=True).app_env == "prod"
    assert make(monkeypatch, app_env="dev", cookie_secure=False).cookie_secure is False


def test_ut_cfg_04_wording_check_hint(monkeypatch):
    assert make(monkeypatch, ai_checker="rules").wording_check == "rules_only"
    assert make(monkeypatch, ai_checker="openai_compat").wording_check == "model"
    assert make(monkeypatch, ai_checker="mock").wording_check == "model"
