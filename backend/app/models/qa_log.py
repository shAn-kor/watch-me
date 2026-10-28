"""`qa_log` (02 section 2.12)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, check_in
from app.domain.enums import QaOutcome, values
from app.models._cols import created_at_col


class QaLog(Base):
    __tablename__ = "qa_log"
    __table_args__ = (
        check_in("outcome", values(QaOutcome), "outcome"),
        Index("ix_qa_ip_time", "ip_hash", "created_at"),
        Index("ix_qa_cookie_time", "cookie_id", "created_at"),
        Index("ix_qa_dog", "dog_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dog_id: Mapped[str] = mapped_column(String(32), ForeignKey("dog.id", ondelete="CASCADE"))
    ip_hash: Mapped[str] = mapped_column(String(64))
    cookie_id: Mapped[str] = mapped_column(String(32))
    question: Mapped[str | None] = mapped_column(String(300))
    outcome: Mapped[str] = mapped_column(String(16))
    fact_ids: Mapped[list[str]] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    dropped_ids: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    ledger_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cost_ledger.id", ondelete="SET NULL"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_col()
