"""Read-only SQL for the admin metrics (01 section 8.1). No business rules.

Facts and sessions of a dog tombstone (`dog.status = 'deleted'`) are left out of
every count (API-MET-07); the cost ledger is not filtered, so its total survives
a dog delete (NFR-2, 02 section 6.1).
"""

from __future__ import annotations

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import Clip, CostLedger, Dog, Fact, FactEvidence, FilmingSession, Job

_LIVE_DOG = Dog.status != "deleted"
AI_JOB_TYPES = ("transcribe", "draft", "check")
AUTH_DETAIL_PREFIXES = ("HTTP 401", "HTTP 402", "HTTP 403")


class MetricsRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    # ---------------------------------------------------------------- facts

    def draft_counts(self) -> tuple[int, int]:
        """(confirmed and unchanged AI drafts, all AI drafts). All drafts are the
        merged facts that did not start as a human addition, in any status."""
        base = (
            select(func.count())
            .select_from(Fact)
            .join(Dog, Dog.id == Fact.dog_id)
            .where(_LIVE_DOG, Fact.merged.is_(True), Fact.origin != "human_added")
        )
        all_drafts = self._s.scalar(base) or 0
        unchanged = (
            self._s.scalar(
                base.where(Fact.status == "confirmed", Fact.origin == "ai_unchanged")
            )
            or 0
        )
        return int(unchanged), int(all_drafts)

    def confirmed_counts(self) -> tuple[int, int]:
        """(confirmed facts, confirmed facts with at least one evidence row)."""
        base = (
            select(func.count())
            .select_from(Fact)
            .join(Dog, Dog.id == Fact.dog_id)
            .where(_LIVE_DOG, Fact.status == "confirmed")
        )
        total = self._s.scalar(base) or 0
        with_clip = (
            self._s.scalar(
                base.where(exists().where(FactEvidence.fact_id == Fact.id))
            )
            or 0
        )
        return int(total), int(with_clip)

    def published_dog_count(self) -> int:
        return int(
            self._s.scalar(
                select(func.count()).select_from(Dog).where(Dog.status == "published")
            )
            or 0
        )

    # ----------------------------------------------------------------- time

    def review_durations_s(self) -> list[float]:
        """Seconds from the original `submitted_at` to `review_ready_at`, for
        sessions in `review`. A retry clears `review_ready_at` but never
        `submitted_at`, so the retry time is included."""
        rows = self._s.execute(
            select(FilmingSession.submitted_at, FilmingSession.review_ready_at)
            .join(Dog, Dog.id == FilmingSession.dog_id)
            .where(
                _LIVE_DOG,
                FilmingSession.status == "review",
                FilmingSession.submitted_at.is_not(None),
                FilmingSession.review_ready_at.is_not(None),
            )
        ).all()
        return [(done - start).total_seconds() for start, done in rows]

    def publish_durations_s(self) -> list[float]:
        """Seconds from the first session's `created_at` to `published_at`."""
        first = (
            select(
                FilmingSession.dog_id.label("dog_id"),
                func.min(FilmingSession.created_at).label("first_at"),
            )
            .group_by(FilmingSession.dog_id)
            .subquery()
        )
        rows = self._s.execute(
            select(first.c.first_at, Dog.published_at)
            .join(Dog, Dog.id == first.c.dog_id)
            .where(Dog.status.in_(("published", "adopted")), Dog.published_at.is_not(None))
        ).all()
        return [(done - start).total_seconds() for start, done in rows]

    # ----------------------------------------------------------------- cost

    def total_usd_micros(self) -> int:
        return int(self._s.scalar(select(func.coalesce(func.sum(CostLedger.usd_micros), 0))) or 0)

    def per_dog_usd_micros(self) -> list[tuple[str, int]]:
        rows = self._s.execute(
            select(CostLedger.dog_id, func.sum(CostLedger.usd_micros))
            .join(Dog, Dog.id == CostLedger.dog_id)
            .where(_LIVE_DOG)
            .group_by(CostLedger.dog_id)
        ).all()
        return [(dog_id, int(micros or 0)) for dog_id, micros in rows]

    # ------------------------------------------------------- purge, alerts

    def purge_pending_dog_ids(self) -> list[str]:
        """Dog tombstones: the purge job has not finished (it is queued, running or
        failed after all attempts)."""
        return list(
            self._s.scalars(
                select(Dog.id).where(Dog.status == "deleted").order_by(Dog.deleted_at, Dog.id)
            )
        )

    def last_ai_auth_failure_job(self) -> int | None:
        """Id of the newest failed job whose clip still carries a provider 401, 402
        or 403 in `fail_detail` (written by the failure hook). A manual retry or a
        clip delete removes the detail, so it also ends the alert."""
        return self._s.scalar(
            select(func.max(Job.id))
            .join(Clip, Clip.id == Job.clip_id)
            .where(
                Job.status == "failed",
                Job.type.in_(AI_JOB_TYPES),
                Clip.status == "failed",
                Clip.fail_code == "ai_failed",
                Clip.deleted_at.is_(None),
                or_(*(Clip.fail_detail.like(f"{p}%") for p in AUTH_DETAIL_PREFIXES)),
            )
        )

    def ai_job_succeeded_after(self, job_id: int) -> bool:
        """True when a provider-calling job created after `job_id` has succeeded:
        the provider answered, so the credentials work. Job ids are ordered by
        creation, which needs no clock (the job table mixes clock sources)."""
        return bool(
            self._s.scalar(
                select(
                    exists().where(
                        and_(
                            Job.id > job_id,
                            Job.status == "succeeded",
                            Job.type.in_(AI_JOB_TYPES),
                        )
                    )
                )
            )
        )
