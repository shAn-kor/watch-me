"""`transcript_segment` (02 section 2.6) and `segment` (02 section 2.7)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TranscriptSegment(Base):
    __tablename__ = "transcript_segment"
    __table_args__ = (
        CheckConstraint("start_s >= 0", name="start_nonneg"),
        CheckConstraint("end_s > start_s", name="range"),
        Index("uq_tseg_clip_idx", "clip_id", "idx", unique=True),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clip_id: Mapped[str] = mapped_column(String(32), ForeignKey("clip.id", ondelete="CASCADE"))
    idx: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    lang: Mapped[str | None] = mapped_column(String(8))


class Segment(Base):
    __tablename__ = "segment"
    __table_args__ = (
        CheckConstraint("end_s > start_s", name="range"),
        Index("uq_segment_clip_idx", "clip_id", "idx", unique=True),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clip_id: Mapped[str] = mapped_column(String(32), ForeignKey("clip.id", ondelete="CASCADE"))
    idx: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)

    def label(self, ordinal: int) -> str:
        """Model-facing label `c{ordinal}-seg{idx}`."""
        return f"c{ordinal}-seg{self.idx}"
