"""`job` (02 section 2.11)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, check_in, utcnow
from app.db.types import UtcDateTime
from app.domain.enums import JobStatus, JobType, values
from app.models._cols import NOW, created_at_col, updated_at_col


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (
        check_in("type", values(JobType), "type"),
        check_in("status", values(JobStatus), "status"),
        Index("ix_job_claim", "status", "run_after"),
        Index("ix_job_dog", "dog_id"),
        Index("ix_job_clip", "clip_id"),
        Index(
            "uq_job_dedupe",
            "dedupe_key",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    dog_id: Mapped[str | None] = mapped_column(String(32))
    session_id: Mapped[str | None] = mapped_column(String(32))
    clip_id: Mapped[str | None] = mapped_column(String(32))
    dedupe_key: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(10), default="queued", server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, default=2, server_default=text("2"))
    error: Mapped[str | None] = mapped_column(Text)
    run_after: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, server_default=NOW)
    locked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    locked_by: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
