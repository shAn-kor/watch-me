"""MetricsService: the read model behind `GET /api/admin/metrics` (01 section 8.1).

Alerts are derived from the database, because the worker and the API run in
different processes. `ai_auth_error` is active while the newest provider 401,
402 or 403 (kept in the failed clip's `fail_detail`, 04 section 8.7) has no
later provider-calling job (`transcribe`, `draft`, `check`) that succeeded. A
call the provider answers proves the credentials work, so the alert clears on
the next successful AI call. A manual clip retry or a clip delete also removes
the failure it came from. Job ids give the order, because `job.updated_at` mixes
clock sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import median

from app.clock import Clock
from app.config import Settings
from app.db.uow import UnitOfWork, UowFactory
from app.errors import ForbiddenRole
from app.repositories.metrics import MetricsRepository
from app.services.cost_service import CostService
from app.services.views import Principal

AI_AUTH_ERROR = "ai_auth_error"


@dataclass(frozen=True, slots=True)
class MetricsView:
    as_of: datetime
    confirmed_ai_unchanged: int
    all_drafts: int
    rate: float
    published_dogs: int
    confirmed: int
    with_clip_evidence: int
    clip_evidence_share: float
    median_session_to_review_s: int | None
    median_dog_first_session_to_publish_s: int | None
    total_usd: float
    per_dog_usd: list[tuple[str, float]] = field(default_factory=list)
    qa_today_usd: float = 0.0
    qa_daily_cap_usd: float = 0.0
    alerts: list[str] = field(default_factory=list)
    purge_pending: list[str] = field(default_factory=list)


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def _median_s(values: list[float]) -> int | None:
    return round(median(values)) if values else None


def _usd(micros: int) -> float:
    return round(micros / 1_000_000, 6)


class MetricsService:
    def __init__(
        self,
        *,
        uow_factory: UowFactory,
        clock: Clock,
        settings: Settings,
        cost_service: CostService,
    ):
        self._uow_factory = uow_factory
        self._clock = clock
        self._settings = settings
        self._cost = cost_service

    def admin_metrics(self, principal: Principal, uow: UnitOfWork | None = None) -> MetricsView:
        if not principal.is_staff:
            raise ForbiddenRole()
        if uow is not None:
            return self._build(uow)
        with self._uow_factory() as own:
            return self._build(own)

    def _build(self, uow: UnitOfWork) -> MetricsView:
        repo = MetricsRepository(uow.session)
        unchanged, all_drafts = repo.draft_counts()
        confirmed, with_clip = repo.confirmed_counts()
        per_dog = sorted(repo.per_dog_usd_micros(), key=lambda r: (-r[1], r[0]))
        return MetricsView(
            as_of=self._clock.now(),
            confirmed_ai_unchanged=unchanged,
            all_drafts=all_drafts,
            rate=_ratio(unchanged, all_drafts),
            published_dogs=repo.published_dog_count(),
            confirmed=confirmed,
            with_clip_evidence=with_clip,
            clip_evidence_share=_ratio(with_clip, confirmed),
            median_session_to_review_s=_median_s(repo.review_durations_s()),
            median_dog_first_session_to_publish_s=_median_s(repo.publish_durations_s()),
            total_usd=_usd(repo.total_usd_micros()),
            per_dog_usd=[(dog_id, _usd(m)) for dog_id, m in per_dog],
            qa_today_usd=_usd(self._cost.qa_spend_today_micros()),
            qa_daily_cap_usd=float(self._settings.qa_daily_usd_cap),
            alerts=self._alerts(repo),
            purge_pending=repo.purge_pending_dog_ids(),
        )

    @staticmethod
    def _alerts(repo: MetricsRepository) -> list[str]:
        failed = repo.last_ai_auth_failure_job()
        if failed is not None and not repo.ai_job_succeeded_after(failed):
            return [AI_AUTH_ERROR]
        return []


__all__ = ["AI_AUTH_ERROR", "MetricsService", "MetricsView"]
