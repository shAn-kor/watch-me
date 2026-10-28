"""Q&A limits: the sliding-hour limiter and the daily cost cap (01 section 1.3, 04 section 9.3)."""

from __future__ import annotations

from datetime import UTC, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from app.clock import Clock
from app.errors import QaCostCapReached, RateLimited
from app.repositories.cost_ledger import CostLedgerRepository
from app.repositories.qa_log import QaLogRepository

WINDOW_S = 3600


class QaLimiter(Protocol):
    def check(self, session: Session, ip_hash: str, cookie_id: str) -> None: ...

    def remaining(self, session: Session, ip_hash: str, cookie_id: str) -> int: ...


class QaLogLimiter:
    """Counts `qa_log` rows (outcome other than `error`) of the last hour, per
    IP hash and per visitor cookie. Either limit blocks."""

    def __init__(self, clock: Clock, limit: int) -> None:
        self._clock = clock
        self._limit = limit

    def check(self, session: Session, ip_hash: str, cookie_id: str) -> None:
        now = self._clock.now()
        since = now - timedelta(seconds=WINDOW_S)
        repo = QaLogRepository(session)
        for scope, keys in (("ip", {"ip_hash": ip_hash}), ("cookie", {"cookie_id": cookie_id})):
            times = repo.times_since(since=since, **keys)
            if len(times) >= self._limit:
                expires = times[len(times) - self._limit] + timedelta(seconds=WINDOW_S)
                wait = max(1, int((expires - now).total_seconds() + 0.999))
                raise RateLimited(details={"scope": scope}, retry_after_s=wait)

    def remaining(self, session: Session, ip_hash: str, cookie_id: str) -> int:
        since = self._clock.now() - timedelta(seconds=WINDOW_S)
        repo = QaLogRepository(session)
        used = max(
            repo.count_since(since=since, ip_hash=ip_hash),
            repo.count_since(since=since, cookie_id=cookie_id),
        )
        return max(0, self._limit - used)


class NullLimiter:
    """No limit. For the eval runner only."""

    def check(self, session: Session, ip_hash: str, cookie_id: str) -> None:
        return None

    def remaining(self, session: Session, ip_hash: str, cookie_id: str) -> int:
        return 0


class CostCapGuard:
    """Blocks the selector call once today's (UTC) `qa_select` spend reaches the cap."""

    def __init__(self, clock: Clock, cap_usd: float, purpose: str = "qa_select") -> None:
        self._clock = clock
        self._cap_micros = round(cap_usd * 1_000_000)
        self._purpose = purpose

    def ensure_below_cap(self, session: Session) -> None:
        now = self._clock.now().astimezone(UTC)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        spent = CostLedgerRepository(session).spend_since(self._purpose, midnight)
        if spent >= self._cap_micros:
            wait = int((midnight + timedelta(days=1) - now).total_seconds())
            raise QaCostCapReached(retry_after_s=max(1, wait))


class NullCostCap:
    """No cap. For the eval runner only."""

    def ensure_below_cap(self, session: Session) -> None:
        return None

