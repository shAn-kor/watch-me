"""Settings (06 section 5, 04 section 8.6). Read from environment variables.

The app refuses to start when a required value is missing or invalid. Secrets
have no defaults and never appear in `repr` or logs (`SecretStr`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AiRole = Literal["transcriber", "drafter", "checker", "selector"]

_APP_DIR = Path(__file__).resolve().parent
DEFAULT_TRANSCRIBER_MODEL = "muse-voice-transcribe-1.0"


@dataclass(frozen=True)
class AiConnection:
    """Resolved connection settings of one AI role (shared values + role override)."""

    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # --- runtime
    app_env: Literal["dev", "test", "prod"] = "dev"
    secret_key: SecretStr
    ip_hash_key: SecretStr = Field(min_length=1)
    database_url: str = "sqlite:///./data/watchme.db"
    storage_root: Path = Path("./data/storage")
    public_base_url: str = "http://localhost:8000"
    cookie_secure: bool = True
    session_max_age_s: int = Field(604_800, gt=0)
    trusted_proxy: bool = False
    consent_version: str = "2026-10-28"
    log_level: str = "INFO"

    # --- uploads and media
    max_clip_bytes: int = Field(209_715_200, gt=0)
    max_clip_s: float = Field(120.0, gt=0)
    clip_duration_tolerance_s: float = Field(0.5, ge=0)
    max_clips_per_session: int = Field(3, ge=1, le=3)
    allowed_extensions: Annotated[list[str], NoDecode] = [".mp4", ".mov"]
    max_photo_bytes: int = Field(8_388_608, gt=0)
    photo_max_side_px: int = Field(1600, gt=0)
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    ffprobe_timeout_s: int = Field(10, gt=0)
    keep_originals: bool = False

    # --- job timeouts (02 section 3.5)
    transcode_timeout_s: int = Field(600, gt=0)
    transcribe_timeout_s: int = Field(180, gt=0)
    sample_timeout_s: int = Field(180, gt=0)
    draft_timeout_s: int = Field(180, gt=0)
    check_timeout_s: int = Field(180, gt=0)
    merge_timeout_s: int = Field(60, gt=0)
    purge_clip_timeout_s: int = Field(120, gt=0)
    purge_dog_timeout_s: int = Field(300, gt=0)
    sweep_timeout_s: int = Field(60, gt=0)

    # --- drafting
    draft_mode: Literal["frames", "segments"] = "frames"
    frame_max_count: int = Field(48, ge=1)
    segment_len_s: int = Field(10, ge=1)

    # --- AI adapters
    ai_transcriber: Literal["mock", "local_whisper", "muse_transcribe"] = "mock"
    ai_drafter: Literal["mock", "openai_compat"] = "mock"
    ai_checker: Literal["mock", "rules", "openai_compat"] = "rules"
    ai_selector: Literal["mock", "openai_compat"] = "mock"
    ai_base_url: str = "https://api.meta.ai/v1"
    ai_model: str = "muse-spark-1.3"
    ai_api_key: SecretStr | None = None
    ai_transcriber_base_url: str | None = None
    ai_transcriber_model: str | None = None
    ai_transcriber_api_key: SecretStr | None = None
    ai_drafter_base_url: str | None = None
    ai_drafter_model: str | None = None
    ai_drafter_api_key: SecretStr | None = None
    ai_checker_base_url: str | None = None
    ai_checker_model: str | None = None
    ai_checker_api_key: SecretStr | None = None
    ai_selector_base_url: str | None = None
    ai_selector_model: str | None = None
    ai_selector_api_key: SecretStr | None = None
    ai_timeout_s: int = Field(75, gt=0)
    ai_stream: bool = False
    ai_schema_strict: bool = True
    ai_allow_contributor_model: bool = False
    ai_prices_file: Path = _APP_DIR / "ai" / "prices.json"
    ai_mock_fixtures_dir: Path = Path("fixtures/")
    banned_words_file: Path = _APP_DIR.parent / "config" / "banned_words.txt"
    health_keywords_file: Path = _APP_DIR.parent / "config" / "health_keywords.txt"

    # --- Q&A
    qa_daily_usd_cap: float = Field(3.00, ge=0)
    qa_max_facts: int = Field(5, ge=1)
    qa_question_min_chars: int = Field(3, ge=1)
    qa_question_max_chars: int = Field(300, ge=1)
    qa_limit_per_hour: int = Field(10, ge=1)

    # --- rate limits
    rate_login_per_ip: int = Field(10, ge=1)
    rate_login_per_email: int = Field(5, ge=1)
    rate_writes_per_member_min: int = Field(120, ge=1)
    rate_uploads_per_member_hour: int = Field(20, ge=1)
    rate_public_per_ip_min: int = Field(120, ge=1)
    rate_media_per_ip_min: int = Field(600, ge=1)

    # --- worker and retention
    worker_poll_s: float = Field(2.0, gt=0)
    job_stale_s: int = Field(600, gt=0)
    job_retention_days: int = Field(14, ge=1)
    qa_question_retention_days: int = Field(30, ge=1)
    qa_row_retention_days: int = Field(90, ge=1)
    tmp_max_age_h: int = Field(6, ge=1)

    # --- seed tool only (tools/seed.py, ORG-0)
    seed_org_name: str | None = None
    seed_org_country: str | None = None
    seed_org_location: str | None = None
    seed_org_contact_url: str | None = None
    seed_org_contact_email: str | None = None
    seed_org_contact_phone: str | None = None
    seed_staff_email: str | None = None
    seed_staff_password: SecretStr | None = None
    seed_volunteer_email: str | None = None
    seed_volunteer_password: SecretStr | None = None

    # ------------------------------------------------------------ validators
    @field_validator("secret_key")
    @classmethod
    def _secret_key_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < 32:
            raise ValueError("SECRET_KEY must be at least 32 bytes")
        return value

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def _split_extensions(cls, value: object) -> object:
        if isinstance(value, str):
            value = [part for part in value.split(",")]
        if isinstance(value, (list, tuple)):
            cleaned = []
            for item in value:
                ext = str(item).strip().lower()
                if not ext:
                    continue
                cleaned.append(ext if ext.startswith(".") else f".{ext}")
            return cleaned
        return value

    @model_validator(mode="after")
    def _cross_checks(self) -> Settings:
        if self.app_env == "prod" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true when APP_ENV=prod")
        if self.qa_question_min_chars > self.qa_question_max_chars:
            raise ValueError(
                "QA_QUESTION_MIN_CHARS must not exceed QA_QUESTION_MAX_CHARS"
            )
        if not self.allowed_extensions:
            raise ValueError("ALLOWED_EXTENSIONS must not be empty")
        return self

    # --------------------------------------------------------------- helpers
    @property
    def wording_check(self) -> Literal["rules_only", "model"]:
        """`limits.wording_check` of GET /api/me (01 section 3.3, UT-CFG-04)."""
        return "rules_only" if self.ai_checker == "rules" else "model"

    def ai_connection(self, role: AiRole) -> AiConnection:
        """Shared connection values with the per-role override applied (06 section 5).

        The transcriber model defaults to `muse-voice-transcribe-1.0`, never to `AI_MODEL`.
        """
        base_url = getattr(self, f"ai_{role}_base_url") or self.ai_base_url
        model = getattr(self, f"ai_{role}_model")
        if model is None:
            model = (
                DEFAULT_TRANSCRIBER_MODEL if role == "transcriber" else self.ai_model
            )
        key = getattr(self, f"ai_{role}_api_key") or self.ai_api_key
        return AiConnection(
            base_url=base_url,
            model=model,
            api_key=key.get_secret_value() if key is not None else None,
        )

    def forbidden_contributor_models(self) -> list[str]:
        """Configured model ids ending in `-contributor` while
        `AI_ALLOW_CONTRIBUTOR_MODEL=false` (NFR-5): the shared `AI_MODEL` and every
        per-role override. `AiRegistry.from_settings` (lane C) refuses to start when
        this is non-empty.
        """
        if self.ai_allow_contributor_model:
            return []
        candidates = [self.ai_model] + [
            getattr(self, f"ai_{role}_model")
            for role in ("transcriber", "drafter", "checker", "selector")
        ]
        return [m for m in candidates if m and m.endswith("-contributor")]
