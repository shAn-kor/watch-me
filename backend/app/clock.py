"""Clock protocol: services never read the wall clock directly (no test sleeps)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current time as an aware UTC datetime."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Test clock. Starts at 2026-10-28T12:00:00Z (07 section 2.2) and only moves
    when told to."""

    DEFAULT_START = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)

    def __init__(self, start: datetime | None = None):
        start = start or self.DEFAULT_START
        if start.tzinfo is None:
            raise ValueError("FakeClock needs an aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("FakeClock needs an aware datetime")
        self._now = value.astimezone(UTC)

    def advance(self, seconds: float = 0, **kwargs: float) -> datetime:
        """Move forward by `seconds` and/or timedelta keywords (minutes=, hours=, days=)."""
        self._now = self._now + timedelta(seconds=seconds, **kwargs)
        return self._now
