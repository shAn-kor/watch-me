"""SQL for the `job` table (02 section 2.11). No business rules: `JobQueue` decides."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Dog, Job

LIVE = ("queued", "running")


def find_live_by_dedupe(session: Session, dedupe_key: str) -> Job | None:
    return session.scalars(
        select(Job).where(Job.dedupe_key == dedupe_key, Job.status.in_(LIVE))
    ).first()


def insert(session: Session, **fields: object) -> Job:
    """Insert a `queued` job. A concurrent insert of the same live `dedupe_key`
    loses to the partial unique index; the caller gets the winner back."""
    job = Job(**fields)
    key = fields.get("dedupe_key")
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError:
        if isinstance(key, str):
            existing = find_live_by_dedupe(session, key)
            if existing is not None:
                return existing
        raise
    return job


def claim_next(session: Session, *, now: datetime, worker_id: str) -> Job | None:
    """Atomic claim (02 2.11): one UPDATE picks the oldest due job."""
    due = (
        select(Job.id)
        .where(Job.status == "queued", Job.run_after <= now)
        .order_by(Job.run_after, Job.id)
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        update(Job)
        .where(Job.id == due, Job.status == "queued")
        .values(
            status="running",
            attempts=Job.attempts + 1,
            locked_at=now,
            locked_by=worker_id,
            updated_at=now,
        )
        .returning(Job)
        .execution_options(synchronize_session=False)
    )
    return session.execute(stmt).scalars().first()


def get(session: Session, job_id: int) -> Job | None:
    return session.get(Job, job_id)


def dog_is_deleted(session: Session, dog_id: str) -> bool:
    status = session.scalar(select(Dog.status).where(Dog.id == dog_id))
    return status == "deleted"


def cancel_queued(
    session: Session, *, now: datetime, dog_id: str | None = None, clip_id: str | None = None
) -> int:
    stmt = update(Job).where(Job.status == "queued")
    if dog_id is not None:
        stmt = stmt.where(Job.dog_id == dog_id)
    if clip_id is not None:
        stmt = stmt.where(Job.clip_id == clip_id)
    result = session.execute(
        stmt.values(status="cancelled", updated_at=now).execution_options(
            synchronize_session=False
        )
    )
    return result.rowcount or 0


def stale_running(session: Session, *, locked_before: datetime) -> list[Job]:
    return list(
        session.scalars(
            select(Job)
            .where(Job.status == "running", Job.locked_at < locked_before)
            .order_by(Job.id)
        )
    )
