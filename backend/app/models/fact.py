"""`fact` (02 section 2.8) and `fact_evidence` (02 section 2.9)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, check_bool, check_in
from app.db.types import UtcDateTime
from app.domain.enums import FactStatus, Origin, Role, Situation, Source, values
from app.models._cols import created_at_col, id_col, updated_at_col


class Fact(Base):
    __tablename__ = "fact"
    __table_args__ = (
        check_in("situation", values(Situation), "situation"),
        check_in("source", values(Source), "source"),
        check_in("origin", values(Origin), "origin"),
        check_in("status", values(FactStatus), "status"),
        check_in("confirmed_role", values(Role), "confirmed_role", nullable=True),
        check_bool("merged"),
        CheckConstraint(
            "(status = 'confirmed') = (confirmed_at IS NOT NULL AND confirmed_role IS NOT NULL)",
            name="confirmed_triplet",
        ),
        CheckConstraint("(status = 'deleted') = (deleted_at IS NOT NULL)", name="deleted_pair"),
        CheckConstraint(
            "situation <> 'children_cats' OR status <> 'confirmed' OR confirmed_role = 'staff'",
            name="situation8_staff_only",
        ),
        CheckConstraint(
            "source <> 'staff_note' OR origin = 'human_added'", name="staff_note_origin"
        ),
        CheckConstraint(
            "merged = 1 OR (origin = 'ai_unchanged' AND status = 'draft')",
            name="unmerged_only_ai_drafts",
        ),
        Index("ix_fact_dog_status_sit", "dog_id", "status", "situation"),
        Index("ix_fact_session", "session_id"),
        Index("ix_fact_created_by", "created_by"),
    )

    id: Mapped[str] = id_col()
    dog_id: Mapped[str] = mapped_column(String(32), ForeignKey("dog.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("session.id", ondelete="CASCADE"))
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("member.id", ondelete="SET NULL"))
    situation: Mapped[str] = mapped_column(String(14))
    behavior: Mapped[str] = mapped_column(String(280))
    source: Mapped[str] = mapped_column(String(10))
    origin: Mapped[str] = mapped_column(String(14))
    status: Mapped[str] = mapped_column(String(10), default="draft", server_default="draft")
    merged: Mapped[bool] = mapped_column(
        Boolean(create_constraint=False), default=True, server_default=text("1")
    )
    flags: Mapped[list[dict]] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    observed_on: Mapped[date] = mapped_column(Date)
    ai_model: Mapped[str | None] = mapped_column(String(60))
    confirmed_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("member.id", ondelete="SET NULL"))
    confirmed_role: Mapped[str | None] = mapped_column(String(10))
    confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    deleted_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("member.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    evidence: Mapped[list[FactEvidence]] = relationship(
        back_populates="fact",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FactEvidence.id",
    )


class FactEvidence(Base):
    __tablename__ = "fact_evidence"
    __table_args__ = (
        CheckConstraint("start_s >= 0", name="start_nonneg"),
        # Lengths are compared after rounding so that 0.1 s grid values such as
        # (2.3, 3.3) are not rejected by binary floating point noise.
        CheckConstraint(
            "end_s > start_s AND round(end_s - start_s, 6) >= 1.0 "
            "AND round(end_s - start_s, 6) <= 60.0",
            name="length",
        ),
        Index("ix_evidence_fact", "fact_id"),
        Index("ix_evidence_clip", "clip_id"),
    )

    id: Mapped[str] = id_col()
    fact_id: Mapped[str] = mapped_column(String(32), ForeignKey("fact.id", ondelete="CASCADE"))
    clip_id: Mapped[str] = mapped_column(String(32), ForeignKey("clip.id", ondelete="CASCADE"))
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)

    fact: Mapped[Fact] = relationship(back_populates="evidence")

    @property
    def length_s(self) -> float:
        return round(self.end_s - self.start_s, 6)
