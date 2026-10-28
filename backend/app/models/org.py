"""`org` (02 section 2.1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._cols import created_at_col, id_col


class Org(Base):
    __tablename__ = "org"
    __table_args__ = (
        CheckConstraint(
            "contact_url IS NOT NULL OR contact_email IS NOT NULL OR contact_phone IS NOT NULL",
            name="has_contact",
        ),
    )

    id: Mapped[str] = id_col()
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2))
    location: Mapped[str] = mapped_column(String(120))
    contact_url: Mapped[str | None] = mapped_column(String(300))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = created_at_col()
