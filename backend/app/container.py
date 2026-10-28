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
from app.clock import Clock, SystemClock
from app.config import Settings
from app.db.engine import make_engine, make_session_factory
from app.db.uow import UnitOfWork, UowFactory, make_uow_factory
from app.services.views import MediaUrls
from app.storage.base import Storage


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

    # [slot B] storage: LocalStorage(settings.storage_root) when `storage` is None
    # [slot B] security: SessionCookieCodec, CsrfTokenService, RateLimiter, ClientIpResolver
    # [slot C] ai: AiRegistry.from_settings(settings) when `ai` is None (mock adapters in tests)
    # [slot D] pipeline: FFmpeg wrapper, JobQueue, JobRunner
    # [slot S1] AuthService
    # [slot S2] DogService, PublishService, CoverageService, DeletionService
    # [slot S3] SessionService, ClipUploadService, ClipService
    # [slot S4] FactReviewService, EvidenceValidator
    # [slot S5] PublicProfileService, MediaAccessService
    # [slot S6] QaService (+ QaLimiter, CostCapGuard, AliasMapper, AnswerRenderer)
    # [slot P] DraftIngestService, MergeService, WordingService, ClipPipelineService, CostService
    # [slot I] MetricsService

    for name, value in service_overrides.items():
        if not hasattr(container.services, name):
            raise TypeError(f"unknown service override: {name}")
        setattr(container.services, name, value)
    return container
