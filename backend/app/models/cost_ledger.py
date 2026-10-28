"""`cost_ledger` (02 section 2.13)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, check_in
from app.domain.enums import CostPurpose, values
from app.models._cols import created_at_col


class CostLedger(Base):
    __tablename__ = "cost_ledger"
    __table_args__ = (
        check_in("purpose", values(CostPurpose), "purpose"),
        Index("ix_cost_purpose_time", "purpose", "created_at"),
        Index("ix_cost_session", "session_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    purpose: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(60))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    audio_s: Mapped[float | None] = mapped_column(Float)
    usd_micros: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    dog_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("dog.id", ondelete="SET NULL"))
    session_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("session.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()
