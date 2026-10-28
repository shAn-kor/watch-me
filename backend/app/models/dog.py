"""`dog` (02 section 2.3)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, check_bool, check_in
from app.db.types import UtcDateTime
from app.domain.enums import DogStatus, Sex, Size, values
from app.models._cols import created_at_col, id_col, updated_at_col


class Dog(Base):
    __tablename__ = "dog"
    __table_args__ = (
        check_in("sex", values(Sex), "sex"),
        check_in("size", values(Size), "size"),
        check_in("status", values(DogStatus), "status"),
        check_bool("known_concerns_none"),
        CheckConstraint(
            "NOT (known_concerns_none = 1 AND known_concerns IS NOT NULL "
            "AND length(trim(known_concerns)) > 0)",
            name="concerns_vs_none",
        ),
        CheckConstraint(
            "status <> 'published' OR (public_slug IS NOT NULL AND people_check_at IS NOT NULL "
            "AND (known_concerns_none = 1 OR length(trim(coalesce(known_concerns, ''))) > 0))",
            name="published_checklist",
        ),
        CheckConstraint("status <> 'deleted' OR public_slug IS NULL", name="deleted_no_slug"),
        Index("uq_dog_slug", "public_slug", unique=True),
        Index("ix_dog_org_status", "org_id", "status"),
    )

    id: Mapped[str] = id_col()
    org_id: Mapped[str] = mapped_column(String(32), ForeignKey("org.id", ondelete="RESTRICT"))
    created_by: Mapped[str] = mapped_column(String(32), ForeignKey("member.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(60))
    sex: Mapped[str] = mapped_column(String(8), default="unknown", server_default="unknown")
    age_estimate: Mapped[str] = mapped_column(String(40))
    size: Mapped[str] = mapped_column(String(8))
    photo_path: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(10), default="draft", server_default="draft")
    public_slug: Mapped[str | None] = mapped_column(String(16))
    known_concerns: Mapped[str | None] = mapped_column(Text)
    known_concerns_none: Mapped[bool] = mapped_column(
        Boolean(create_constraint=False), default=False, server_default=text("0")
    )
    people_check_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    people_check_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("member.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    adopted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    @property
    def is_public(self) -> bool:
        return self.status == DogStatus.PUBLISHED

    @property
    def is_hidden(self) -> bool:
        return self.status != DogStatus.PUBLISHED
