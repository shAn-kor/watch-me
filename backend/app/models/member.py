"""`member` (02 section 2.2)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, check_in
from app.db.types import UtcDateTime
from app.domain.enums import Role, values
from app.models._cols import created_at_col, id_col


class Member(Base):
    __tablename__ = "member"
    __table_args__ = (
        check_in("role", values(Role), "role"),
        CheckConstraint("(consented_at IS NULL) = (consent_version IS NULL)", name="consent_pair"),
        CheckConstraint("email = lower(email)", name="email_lower"),
        Index("uq_member_email", "email", unique=True),
        Index("ix_member_org", "org_id"),
    )

    id: Mapped[str] = id_col()
    org_id: Mapped[str] = mapped_column(String(32), ForeignKey("org.id", ondelete="RESTRICT"))
    email: Mapped[str] = mapped_column(String(254))
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(12))
    consented_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    consent_version: Mapped[str | None] = mapped_column(String(20))
    session_epoch: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = created_at_col()

    @property
    def is_staff(self) -> bool:
        return self.role == Role.STAFF

    @property
    def has_consented(self) -> bool:
        return self.consented_at is not None
