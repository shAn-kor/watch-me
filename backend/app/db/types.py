"""Column types: `UtcDateTime` (02 section 0)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Always UTC. Stored naive (ISO text in SQLite), returned aware.

    Writing a naive datetime is a bug and raises, so a local-time value can never
    be stored by accident. Offsets are converted to UTC before storing (DB-TYP-01).
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UtcDateTime needs an aware datetime (got a naive one)")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


def json_list(value: Any) -> list[Any]:
    """Defensive read of a JSON list column (None -> [])."""
    return list(value) if value else []
