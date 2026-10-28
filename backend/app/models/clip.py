"""`clip` (02 section 2.5)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, check_bool, check_in
from app.db.types import UtcDateTime
from app.domain.enums import CLIP_FAIL_CODES, ClipStatus, ClipStep, values
from app.models._cols import created_at_col, id_col


class Clip(Base):
    __tablename__ = "clip"
    __table_args__ = (
        CheckConstraint("ordinal BETWEEN 1 AND 3", name="ordinal"),
        CheckConstraint("original_size_bytes <= 209715200", name="size_limit"),
        CheckConstraint("duration_s > 0 AND duration_s <= 120.5", name="duration"),
        check_bool("has_audio"),
        check_in("status", values(ClipStatus), "status"),
        check_in("step", values(ClipStep), "step", nullable=True),
        check_in("fail_code", [c.value for c in CLIP_FAIL_CODES], "fail_code", nullable=True),
        CheckConstraint("(status = 'failed') = (fail_code IS NOT NULL)", name="failed_has_code"),
        Index(
            "uq_clip_session_ordinal",
            "session_id",
            "ordinal",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_clip_session_req",
            "session_id",
            "client_request_id",
            unique=True,
            sqlite_where=text("client_request_id IS NOT NULL"),
        ),
        Index("ix_clip_dog", "dog_id"),
        Index("ix_clip_status", "status"),
    )

    id: Mapped[str] = id_col()
    session_id: Mapped[str] = mapped_column(String(32), ForeignKey("session.id", ondelete="CASCADE"))
    dog_id: Mapped[str] = mapped_column(String(32), ForeignKey("dog.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    client_request_id: Mapped[str | None] = mapped_column(String(40))
    original_filename: Mapped[str] = mapped_column(String(200))
    original_path: Mapped[str | None] = mapped_column(String(300))
    original_size_bytes: Mapped[int] = mapped_column(Integer)
    source_container: Mapped[str | None] = mapped_column(String(40))
    source_codec: Mapped[str | None] = mapped_column(String(20))
    has_audio: Mapped[bool] = mapped_column(Boolean(create_constraint=False))
    playback_path: Mapped[str | None] = mapped_column(String(300))
    duration_s: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), default="uploaded", server_default="uploaded")
    step: Mapped[str | None] = mapped_column(String(12))
    fail_code: Mapped[str | None] = mapped_column(String(20))
    fail_detail: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_at_col()
    ready_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    @property
    def is_live(self) -> bool:
        return self.deleted_at is None

    @property
    def is_ready(self) -> bool:
        return self.status == ClipStatus.READY and self.deleted_at is None
