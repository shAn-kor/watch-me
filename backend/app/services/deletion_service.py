"""DeletionService, dog part (06 section 4.6; 02 section 6.1 step 1).

`request_dog_delete` hides the dog in one transaction and queues `purge_dog`. The
purge itself (`run_purge_dog`, the retention sweep, clip deletion) belongs to lane P.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select, update

from app.clock import Clock
from app.config import Settings
from app.db.uow import UnitOfWork, UowFactory
from app.errors import ForbiddenRole, JobError
from app.models import (
    Clip,
    CostLedger,
    Dog,
    Fact,
    FactEvidence,
    FilmingSession,
    Job,
    PlaybackEvent,
    QaLog,
    Segment,
    TranscriptSegment,
)
from app.repositories.dogs import DogRepository
from app.repositories.qa_log import QaLogRepository
from app.services._write_lock import lock_for_write
from app.services.dog_service import load_dog
from app.services.job_queue import JobQueue
from app.services.views import JobSpec, Principal
from app.storage.base import Storage, StorageError

log = logging.getLogger(__name__)

PURGE_DOG_MAX_ATTEMPTS = 8


@dataclass(frozen=True, slots=True)
class PurgeTicket:
    dog_id: str
    status: str  # "deleted"
    purge: str  # "queued"


class DeletionService:
    def __init__(
        self,
        *,
        clock: Clock,
        job_queue: JobQueue,
        uow_factory: UowFactory | None = None,
        storage: Storage | None = None,
        settings: Settings | None = None,
    ):
        self._clock = clock
        self._jobs = job_queue
        self._uow_factory = uow_factory
        self._storage = storage
        self._settings = settings

    def request_dog_delete(
        self, uow: UnitOfWork, principal: Principal, dog_id: str
    ) -> PurgeTicket:
        if not principal.is_staff:
            raise ForbiddenRole()
        dog = load_dog(uow, principal, dog_id)  # not_found also for an already deleted dog
        now = self._clock.now()
        dog.status = "deleted"
        dog.deleted_at = now
        dog.public_slug = None
        uow.flush()
        # Cancel first, so the purge job enqueued next is not cancelled with the rest.
        DogRepository(uow.session).cancel_queued_jobs(dog.id, now=now)
        self._jobs.enqueue(
            JobSpec(
                type="purge_dog",
                dog_id=dog.id,
                dedupe_key=f"purge_dog:{dog.id}",
                max_attempts=PURGE_DOG_MAX_ATTEMPTS,
            ),
            uow=uow,
        )
        return PurgeTicket(dog_id=dog.id, status="deleted", purge="queued")

    # ------------------------------------------------------------ lane P
    # The purge side (02 sections 6.1 and 6.2, 03 section 3.3). Called by the
    # `purge_dog`, `purge_clip` and `retention_sweep` handlers.

    def run_purge_dog(self, dog_id: str, current_job_id: int) -> str:
        """Files first, verification, then rows. Returns `purged`, `gone` (no such
        dog), `rescheduled` (another job of the dog is still running) or
        `refused` (the dog is not deleted: nothing is touched)."""
        assert self._uow_factory is not None and self._storage is not None
        now = self._clock.now()
        with self._uow_factory() as uow:
            lock_for_write(uow)
            dog = uow.session.get(Dog, dog_id)
            if dog is None:
                return "gone"
            if dog.status != "deleted":
                log.error("purge_dog refused: dog %s is not deleted", dog_id)
                return "refused"
            running = uow.session.scalar(
                select(Job.id)
                .where(Job.dog_id == dog_id, Job.status == "running", Job.id != current_job_id)
                .limit(1)
            )
            if running is not None:
                job = uow.session.get(Job, current_job_id)
                if job is not None:
                    job.status = "queued"
                    job.attempts = max(0, job.attempts - 1)  # waiting is not an attempt
                    job.run_after = now + timedelta(seconds=30)
                    job.locked_at = None
                    job.locked_by = None
                uow.commit()
                return "rescheduled"
        self._purge_files(f"dogs/{dog_id}/")
        with self._uow_factory() as uow:
            lock_for_write(uow)
            clip_ids = select(Clip.id).where(Clip.dog_id == dog_id)
            fact_ids = select(Fact.id).where(Fact.dog_id == dog_id)
            session_ids = select(FilmingSession.id).where(FilmingSession.dog_id == dog_id)
            uow.session.execute(
                update(CostLedger)
                .where((CostLedger.dog_id == dog_id) | (CostLedger.session_id.in_(session_ids)))
                .values(dog_id=None, session_id=None)
            )
            uow.session.execute(delete(PlaybackEvent).where(PlaybackEvent.fact_id.in_(fact_ids)))
            uow.session.execute(delete(FactEvidence).where(FactEvidence.fact_id.in_(fact_ids)))
            uow.session.execute(delete(Fact).where(Fact.dog_id == dog_id))
            uow.session.execute(
                delete(TranscriptSegment).where(TranscriptSegment.clip_id.in_(clip_ids))
            )
            uow.session.execute(delete(Segment).where(Segment.clip_id.in_(clip_ids)))
            uow.session.execute(delete(Clip).where(Clip.dog_id == dog_id))
            uow.session.execute(delete(FilmingSession).where(FilmingSession.dog_id == dog_id))
            uow.session.execute(delete(QaLog).where(QaLog.dog_id == dog_id))
            uow.session.execute(delete(Job).where(Job.dog_id == dog_id))
            uow.session.execute(delete(Dog).where(Dog.id == dog_id))
            uow.commit()
        return "purged"

    def run_purge_clip(self, clip_id: str, dog_id: str | None = None) -> str:
        """Delete the clip's files, verify, then its leftover rows. Only a clip that
        was deleted (hidden) first is purged."""
        assert self._uow_factory is not None and self._storage is not None
        with self._uow_factory() as uow:
            lock_for_write(uow)
            clip = uow.session.get(Clip, clip_id)
            if clip is not None:
                if clip.deleted_at is None:
                    log.error("purge_clip refused: clip %s is live", clip_id)
                    return "refused"
                dog_id = clip.dog_id
        if dog_id is None:
            return "gone"
        self._purge_files(f"dogs/{dog_id}/clips/{clip_id}/")
        with self._uow_factory() as uow:
            lock_for_write(uow)
            evidence_ids = select(FactEvidence.id).where(FactEvidence.clip_id == clip_id)
            uow.session.execute(
                delete(PlaybackEvent).where(PlaybackEvent.evidence_id.in_(evidence_ids))
            )
            uow.session.execute(delete(FactEvidence).where(FactEvidence.clip_id == clip_id))
            uow.session.execute(
                delete(TranscriptSegment).where(TranscriptSegment.clip_id == clip_id)
            )
            uow.session.execute(delete(Segment).where(Segment.clip_id == clip_id))
            uow.session.execute(delete(Clip).where(Clip.id == clip_id))
            uow.commit()
        return "purged"

    def run_retention_sweep(self) -> dict[str, int]:
        """I-18: question text 30 days, QA rows 90 days, finished jobs 14 days,
        stale tmp files 6 hours. The cost ledger is never touched."""
        assert self._uow_factory is not None and self._settings is not None
        cfg = self._settings
        now = self._clock.now()
        with self._uow_factory() as uow:
            lock_for_write(uow)
            qa = QaLogRepository(uow.session)
            nulled = qa.null_questions_before(now - timedelta(days=cfg.qa_question_retention_days))
            qa_deleted = qa.delete_before(now - timedelta(days=cfg.qa_row_retention_days))
            jobs = uow.session.execute(
                delete(Job).where(
                    Job.status.in_(("succeeded", "failed", "cancelled")),
                    Job.updated_at < now - timedelta(days=cfg.job_retention_days),
                )
            ).rowcount or 0
            uow.commit()
        tmp = self._sweep_tmp(now.timestamp() - cfg.tmp_max_age_h * 3600)
        return {"qa_nulled": nulled, "qa_deleted": qa_deleted, "jobs": jobs, "tmp": tmp}

    # -------------------------------------------------------------- helpers

    def _purge_files(self, prefix: str) -> None:
        """Delete everything under `prefix` and prove it is gone. A failure is a
        retryable `purge_failed`; no row is touched before this returns."""
        assert self._storage is not None
        try:
            self._storage.delete_prefix(prefix)
            left = self._storage.list_prefix(prefix)
        except StorageError as exc:
            raise JobError("purge_failed", True) from exc
        if left:
            log.error("purge verification found %d files under %s", len(left), prefix)
            raise JobError("purge_failed", True)

    def _sweep_tmp(self, cutoff_ts: float) -> int:
        assert self._storage is not None
        removed = 0
        try:
            keys = self._storage.list_prefix("tmp")
        except StorageError:
            return 0
        for key in keys:
            try:
                if self._storage.open_path(key).stat().st_mtime < cutoff_ts:
                    self._storage.delete(key)
                    removed += 1
            except (OSError, StorageError):
                continue
        return removed
