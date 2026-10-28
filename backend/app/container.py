"""Composition root (06 section 1). The only place that chooses concrete classes.

Tests build the same container with fakes (`overrides`). Each lane plugs its
objects into its own `[slot ...]` block below and nowhere else, so merges stay
trivial. A lane needing another change asks the lead (08 section 1, rule 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.protocols import FactDrafter, FactSelector, Transcriber, WordingChecker
from app.ai.registry import AiRegistry
from app.clock import Clock, SystemClock
from app.config import Settings
from app.db.engine import make_engine, make_session_factory
from app.db.uow import UnitOfWork, UowFactory, make_uow_factory
from app.domain.health import HealthQuestionMatcher
from app.domain.wording import BannedWordMatcher
from app.pipeline.ffmpeg import FFmpeg
from app.security.client_ip import ClientIpResolver, IpHasher
from app.security.cookies import SessionCookieCodec
from app.security.csrf import CsrfTokenService
from app.security.passwords import PasswordHasher
from app.security.ratelimit import InMemorySlidingWindow
from app.services.auth_service import AuthService
from app.services.clip_service import ClipService
from app.services.clip_upload_service import ClipUploadService
from app.services.coverage_service import CoverageService
from app.services.deletion_service import DeletionService
from app.services.dog_service import DogService
from app.services.evidence_validator import EvidenceValidator
from app.services.fact_review_service import FactReviewService
from app.services.job_queue import JobQueue
from app.services.media_access_service import MediaAccessService
from app.services.public_profile_service import PublicProfileService
from app.services.publish_service import PublishService
from app.services.qa_limits import CostCapGuard, QaLogLimiter
from app.services.qa_service import QAService
from app.services.session_service import SessionService
from app.services.views import MediaUrls
from app.storage.base import Storage
from app.storage.local import LocalStorage


@dataclass
class AiSlots:
    """The four AI roles. Production fills them from `AiRegistry.from_settings`
    (lane C); tests put scripted fakes here. A role that is `None` was not wired."""

    transcriber: Transcriber | None = None
    drafter: FactDrafter | None = None
    checker: WordingChecker | None = None
    selector: FactSelector | None = None


@dataclass
class Services:
    """One attribute per service, `None` until its lane wires it.

    Names follow 06 section 1. Handlers and routers read what they need from here.
    """

    # [slot S1] auth
    auth_service: Any = None
    # [slot S2] dogs and publish
    dog_service: Any = None
    publish_service: Any = None
    coverage_service: Any = None
    deletion_service: Any = None
    # [slot S3] sessions and upload
    session_service: Any = None
    clip_upload_service: Any = None
    clip_service: Any = None
    # [slot S4] review
    fact_review_service: Any = None
    evidence_validator: Any = None
    # [slot S5] public and media
    public_profile_service: Any = None
    media_access_service: Any = None
    # [slot S6] Q&A
    qa_service: Any = None
    # [slot D] jobs
    job_queue: Any = None
    # [slot P] pipeline
    draft_ingest_service: Any = None
    merge_service: Any = None
    wording_service: Any = None
    clip_pipeline_service: Any = None
    cost_service: Any = None
    # [slot I] integration (phase 3)
    metrics_service: Any = None


@dataclass
class Container:
    settings: Settings
    clock: Clock
    engine: Engine
    session_factory: sessionmaker[Session]
    uow_factory: UowFactory
    media_urls: MediaUrls
    storage: Storage | None = None
    ai: AiSlots = field(default_factory=AiSlots)
    services: Services = field(default_factory=Services)
    # [slot B] security objects (cookie codec, csrf, rate limiters, ip resolver)
    security: dict[str, Any] = field(default_factory=dict)
    # [slot D] pipeline objects (ffmpeg wrapper, job runner)
    pipeline: dict[str, Any] = field(default_factory=dict)

    def uow(self) -> UnitOfWork:
        return self.uow_factory()

    def dispose(self) -> None:
        self.engine.dispose()


def build_container(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    engine: Engine | None = None,
    storage: Storage | None = None,
    ai: AiSlots | None = None,
    **service_overrides: Any,
) -> Container:
    """Build the object graph.

    `settings` defaults to `Settings()` (environment). Tests pass fakes for
    `clock`, `storage`, `ai`, and any service by name in `service_overrides`
    (applied last, so they win over a lane's real wiring).
    """
    settings = settings or Settings()  # type: ignore[call-arg]
    clock = clock or SystemClock()
    engine = engine or make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    container = Container(
        settings=settings,
        clock=clock,
        engine=engine,
        session_factory=session_factory,
        uow_factory=make_uow_factory(session_factory),
        media_urls=MediaUrls(),
        storage=storage,
        ai=ai or AiSlots(),
    )

    # [slot B] storage
    if container.storage is None:
        container.storage = LocalStorage(settings.storage_root)
    # [slot B] security: built in the S1 block below
    # [slot C] ai (tests pass scripted slots)
    if ai is None:
        registry = AiRegistry.from_settings(settings)
        container.ai = AiSlots(
            transcriber=registry.transcriber(),
            drafter=registry.drafter(),
            checker=registry.checker(),
            selector=registry.selector(),
        )
    # [slot D] jobs; the JobRunner is built by the worker (lane P)
    container.services.job_queue = JobQueue(
        container.uow_factory, clock, stale_s=settings.job_stale_s
    )
    container.pipeline.setdefault("ffmpeg", FFmpeg.from_settings(settings))
    # [slot S1] AuthService. The lane B primitives are not wired anywhere else yet,
    # so this slot builds them into `container.security` (setdefault: a later
    # slot B wiring wins).
    sec = container.security
    sec.setdefault("password_hasher", PasswordHasher())
    sec.setdefault(
        "cookie_codec",
        SessionCookieCodec(
            settings.secret_key.get_secret_value(), clock, settings.session_max_age_s
        ),
    )
    sec.setdefault("csrf", CsrfTokenService(settings.secret_key.get_secret_value()))
    sec.setdefault("rate_limiter", InMemorySlidingWindow(clock))
    sec.setdefault("ip_resolver", ClientIpResolver(settings.trusted_proxy))
    sec.setdefault("ip_hasher", IpHasher(settings.ip_hash_key.get_secret_value()))
    container.services.auth_service = AuthService(
        uow_factory=container.uow_factory,
        clock=clock,
        settings=settings,
        hasher=sec["password_hasher"],
        codec=sec["cookie_codec"],
        csrf=sec["csrf"],
        limiter=sec["rate_limiter"],
        ip_hasher=sec["ip_hasher"],
    )
    # [slot S2] DogService, PublishService, CoverageService, DeletionService
    container.services.coverage_service = CoverageService()
    container.services.publish_service = PublishService(
        clock=clock, settings=settings, media_urls=container.media_urls
    )
    container.services.dog_service = DogService(
        clock=clock,
        settings=settings,
        storage=container.storage,
        media_urls=container.media_urls,
        coverage=container.services.coverage_service,
        publish=container.services.publish_service,
    )
    container.services.deletion_service = DeletionService(
        clock=clock, job_queue=container.services.job_queue
    )
    # [slot S3] SessionService, ClipUploadService, ClipService
    container.services.session_service = SessionService(
        uow_factory=container.uow_factory,
        clock=clock,
        settings=settings,
        job_queue=container.services.job_queue,
        media_urls=container.media_urls,
    )
    container.services.clip_upload_service = ClipUploadService(
        clock=clock,
        settings=settings,
        job_queue=container.services.job_queue,
        storage=container.storage,
        ffmpeg=container.pipeline["ffmpeg"],
        media_urls=container.media_urls,
    )
    container.services.clip_service = ClipService(
        clock=clock,
        job_queue=container.services.job_queue,
        session_service=container.services.session_service,
        media_urls=container.media_urls,
    )
    # [slot S4] FactReviewService, EvidenceValidator
    container.services.evidence_validator = EvidenceValidator()
    container.services.fact_review_service = FactReviewService(
        clock=clock,
        media_urls=container.media_urls,
        banned=BannedWordMatcher.from_text(
            settings.banned_words_file.read_text(encoding="utf-8")
        ),
        validator=container.services.evidence_validator,
    )
    # [slot S5] PublicProfileService, MediaAccessService
    container.services.public_profile_service = PublicProfileService(
        settings=settings,
        media_urls=container.media_urls,
        coverage=container.services.coverage_service,
    )
    container.services.media_access_service = MediaAccessService(storage=container.storage)
    # [slot S6] QAService (+ QaLogLimiter, CostCapGuard, AliasMapper, AnswerRenderer)
    container.services.qa_service = QAService(
        uow_factory=container.uow_factory,
        clock=clock,
        selector=container.ai.selector,
        health=HealthQuestionMatcher.from_text(
            settings.health_keywords_file.read_text(encoding="utf-8")
        ),
        ip_hasher=sec["ip_hasher"],
        media_urls=container.media_urls,
        limiter=QaLogLimiter(clock, settings.qa_limit_per_hour),
        cap_guard=CostCapGuard(clock, settings.qa_daily_usd_cap),
        max_facts=settings.qa_max_facts,
        min_chars=settings.qa_question_min_chars,
        max_chars=settings.qa_question_max_chars,
    )
    # [slot P] DraftIngestService, MergeService, WordingService, ClipPipelineService, CostService
    # [slot I] MetricsService

    for name, value in service_overrides.items():
        if not hasattr(container.services, name):
            raise TypeError(f"unknown service override: {name}")
        setattr(container.services, name, value)
    return container
