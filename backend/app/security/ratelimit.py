"""RateLimiter protocol, in-memory sliding window, and a no-op limiter (01 section 1.3)."""

from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.clock import Clock


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    scope: str
    retry_after_s: int = 0
    remaining: int = 0


@runtime_checkable
class RateLimiter(Protocol):
    def hit(self, scope: str, key: str, limit: int, window_s: int) -> RateDecision: ...


class InMemorySlidingWindow:
    """Counts hits per (scope, key) inside the last `window_s` seconds. A denied
    hit is not recorded. Counters reset on restart (accepted for R1)."""

    def __init__(self, clock: Clock):
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, scope: str, key: str, limit: int, window_s: int) -> RateDecision:
        now = self._clock.now().timestamp()
        with self._lock:
            q = self._hits.setdefault((scope, key), deque())
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                retry = max(1, math.ceil(q[0] + window_s - now))
                return RateDecision(False, scope, retry_after_s=retry, remaining=0)
            q.append(now)
            return RateDecision(True, scope, remaining=limit - len(q))


class NullLimiter:
    def hit(self, scope: str, key: str, limit: int, window_s: int) -> RateDecision:
        return RateDecision(True, scope, remaining=limit)
