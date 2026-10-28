"""JobQueue: enqueue (dedupe), claim, complete, fail, cancel, reset stale
(02 sections 2.11 and 3.5, 06 section 4.6).

Every method is a transaction boundary unless a `uow` is passed (the api and other
services enqueue inside their own transaction and commit it themselves).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Literal

from app.clock import Clock
from app.db.uow import UnitOfWork, UowFactory
from app.errors import JobError
from app.models import Job
from app.repositories import jobs as repo
from app.services.views import JobSpec, JobView

PIPELINE_BACKOFF_S: tuple[int, ...] = (30, 120)
PURGE_BACKOFF_S: tuple[int, ...] = (60, 300, 900, 3600, 10_800, 21_600, 43_200)
PURGE_TYPES = frozenset({"purge_clip", "purge_dog"})
# Jobs whose own target is a deleted dog: J3 must not discard them.
KEEP_ON_DELETED_DOG = frozenset({"purge_dog"})
ERROR_MAX_CHARS = 2000

Outcome = Literal["requeued", "failed", "gone"]


def default_max_attempts(job_type: str) -> int:
    if job_type in PURGE_TYPES:
        return 8
    if job_type == "retention_sweep":
        return 1
    return 2


def backoff_seconds(job_type: str, attempts: int) -> int:
    table = PURGE_BACKOFF_S if job_type in PURGE_TYPES else PIPELINE_BACKOFF_S
    return table[min(max(attempts, 1), len(table)) - 1]


def _view(job: Job) -> JobView:
    return JobView(
        id=job.id,
        type=job.type,
        payload=dict(job.payload or {}),
        dog_id=job.dog_id,
        session_id=job.session_id,
        clip_id=job.clip_id,
        dedupe_key=job.dedupe_key,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
    )


class JobQueue:
    def __init__(self, uow_factory: UowFactory, clock: Clock, *, stale_s: int = 600):
        self._uow_factory = uow_factory
        self._clock = clock
        self._stale_s = stale_s

    # ------------------------------------------------------------- enqueue

    def _insert(self, uow: UnitOfWork, spec: JobSpec) -> int:
        session = uow.session
        if spec.dedupe_key is not None:
            existing = repo.find_live_by_dedupe(session, spec.dedupe_key)
            if existing is not None:
                return existing.id
        now = self._clock.now()
        job = repo.insert(
            session,
            type=spec.type,
            payload=dict(spec.payload),
            dog_id=spec.dog_id,
            session_id=spec.session_id,
            clip_id=spec.clip_id,
            dedupe_key=spec.dedupe_key,
            status="queued",
            attempts=0,
            max_attempts=spec.max_attempts or default_max_attempts(spec.type),
            run_after=spec.run_after or now,
            created_at=now,
            updated_at=now,
        )
        session.flush()
        return job.id

    def enqueue(self, spec: JobSpec, *, uow: UnitOfWork | None = None) -> int:
        """Insert a `queued` job; a live `dedupe_key` returns the existing id (J1)."""
        if uow is not None:
            return self._insert(uow, spec)
        with self._uow_factory() as own:
            job_id = self._insert(own, spec)
            own.commit()
            return job_id

    # --------------------------------------------------------------- claim

    def claim(self, worker_id: str) -> JobView | None:
        """J2: the oldest due job (`run_after`, then `id`); `None` when idle."""
        with self._uow_factory() as uow:
            job = repo.claim_next(uow.session, now=self._clock.now(), worker_id=worker_id)
            view = _view(job) if job is not None else None
            uow.commit()
            return view

    # ------------------------------------------------------------ complete

    def complete(
        self, job_id: int, next_jobs: Sequence[JobSpec] = ()
    ) -> Literal["succeeded", "cancelled", "gone"]:
        """J3: succeed and enqueue `next_jobs` in one transaction. When the target
        dog is `deleted` the result is discarded and the job is `cancelled`."""
        now = self._clock.now()
        with self._uow_factory() as uow:
            job = repo.get(uow.session, job_id)
            if job is None or job.status != "running":
                return "gone"
            if (
                job.dog_id
                and job.type not in KEEP_ON_DELETED_DOG
                and repo.dog_is_deleted(uow.session, job.dog_id)
            ):
                job.status, job.updated_at = "cancelled", now
                uow.commit()
                return "cancelled"
            job.status, job.updated_at = "succeeded", now
            for spec in next_jobs:
                self._insert(uow, spec)
            uow.commit()
            return "succeeded"

    # ---------------------------------------------------------------- fail

    def _apply_failure(
        self, job: Job, error: JobError, *, text: str | None = None
    ) -> Outcome:
        now = self._clock.now()
        job.error = (text or error.code)[:ERROR_MAX_CHARS]
        job.updated_at = now
        if error.retryable and job.attempts < job.max_attempts:
            wait = max(
                backoff_seconds(job.type, job.attempts), error.retry_after_s or 0
            )
            job.status = "queued"
            job.run_after = now + timedelta(seconds=wait)
            job.locked_at = None
            job.locked_by = None
            return "requeued"
        job.status = "failed"
        return "failed"

    def fail(self, job_id: int, error: JobError, *, text: str | None = None) -> Outcome:
        """J4/J5: requeue with backoff, or fail now. The caller runs the failure
        hook when this returns `failed`."""
        with self._uow_factory() as uow:
            job = repo.get(uow.session, job_id)
            if job is None or job.status != "running":
                return "gone"
            outcome = self._apply_failure(job, error, text=text)
            uow.commit()
            return outcome

    # -------------------------------------------------------------- cancel

    def cancel_for_dog(self, dog_id: str, *, uow: UnitOfWork | None = None) -> int:
        """J7: cancel `queued` jobs of a dog; a `running` job is left to J3."""
        return self._cancel(uow, dog_id=dog_id)

    def cancel_for_clip(self, clip_id: str, *, uow: UnitOfWork | None = None) -> int:
        return self._cancel(uow, clip_id=clip_id)

    def _cancel(self, uow: UnitOfWork | None, **where: str) -> int:
        now = self._clock.now()
        if uow is not None:
            return repo.cancel_queued(uow.session, now=now, **where)
        with self._uow_factory() as own:
            count = repo.cancel_queued(own.session, now=now, **where)
            own.commit()
            return count

    # --------------------------------------------------------- stale reset

    def reset_stale(self) -> list[JobView]:
        """J6: running jobs locked longer than `stale_s` go back to `queued` or to
        `failed` as J4/J5 (the attempt was already counted). Returns the jobs that
        failed, so the runner can run their failure hooks."""
        now = self._clock.now()
        failed: list[JobView] = []
        with self._uow_factory() as uow:
            stale = repo.stale_running(
                uow.session, locked_before=now - timedelta(seconds=self._stale_s)
            )
            for job in stale:
                error = JobError("job_stale", retryable=True)
                if self._apply_failure(job, error, text="stale lock") == "failed":
                    failed.append(_view(job))
            uow.commit()
        return failed
