"""`playback_event` (02 section 2.10)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.db.types import UtcDateTime
from app.models._cols import NOW


class PlaybackEvent(Base):
    __tablename__ = "playback_event"
    __table_args__ = (
        UniqueConstraint("evidence_id", "member_id", name="uq_playback_event_evidence_member"),
        Index("ix_pbe_fact_member", "fact_id", "member_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fact_id: Mapped[str] = mapped_column(String(32), ForeignKey("fact.id", ondelete="CASCADE"))
    evidence_id: Mapped[str] = mapped_column(String(32), ForeignKey("fact_evidence.id", ondelete="CASCADE"))
    member_id: Mapped[str] = mapped_column(String(32), ForeignKey("member.id", ondelete="RESTRICT"))
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    watched_s: Mapped[float] = mapped_column(Float)
    completed_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, server_default=NOW
    )
