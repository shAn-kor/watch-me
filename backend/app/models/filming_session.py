"""`session` table, ORM class `FilmingSession` (02 section 2.4, 06 deviation M2)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, check_in
from app.db.types import UtcDateTime
from app.domain.enums import SESSION_FAIL_CODES, SessionStatus, values
from app.models._cols import created_at_col, id_col


class FilmingSession(Base):
    __tablename__ = "session"
    __table_args__ = (
        CheckConstraint(
            "json_valid(situations) AND json_array_length(situations) BETWEEN 1 AND 8",
            name="situations_count",
        ),
        check_in("status", values(SessionStatus), "status"),
        check_in("fail_code", [c.value for c in SESSION_FAIL_CODES], "fail_code", nullable=True),
        CheckConstraint("fail_code IS NULL OR status = 'failed'", name="fail_code_only_failed"),
        Index("ix_session_dog", "dog_id"),
        Index("ix_session_member", "member_id"),
        Index("ix_session_status", "status"),
    )

    id: Mapped[str] = id_col()
    dog_id: Mapped[str] = mapped_column(String(32), ForeignKey("dog.id", ondelete="CASCADE"))
    member_id: Mapped[str] = mapped_column(String(32), ForeignKey("member.id", ondelete="RESTRICT"))
    situations: Mapped[list[str]] = mapped_column(JSON)
    observed_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="open", server_default="open")
    fail_code: Mapped[str | None] = mapped_column(String(20))
    rules_ack_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = created_at_col()
    submitted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    review_ready_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
