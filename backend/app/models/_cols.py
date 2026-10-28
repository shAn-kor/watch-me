"""Column helpers shared by the model files."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import new_id, utcnow
from app.db.types import UtcDateTime

NOW = text("CURRENT_TIMESTAMP")


def id_col() -> Mapped[str]:
    """`String(32)` primary key, uuid4 hex generated in Python."""
    return mapped_column(String(32), primary_key=True, default=new_id)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(UtcDateTime, nullable=False, default=utcnow, server_default=NOW)


def updated_at_col() -> Mapped[datetime]:
    return mapped_column(
        UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=NOW
    )
