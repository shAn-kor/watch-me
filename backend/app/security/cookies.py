"""Session cookie codec (itsdangerous) and visitor cookie helpers (01 section 1).

The payload carries its own issue time so the age check uses the injected
`Clock` (tests never sleep). itsdangerous only signs.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any

from itsdangerous import BadData, URLSafeSerializer

from app.clock import Clock
from app.errors import Unauthenticated

SESSION_COOKIE = "wm_session"
VISITOR_COOKIE = "wm_visitor"
SESSION_MAX_AGE_S = 7 * 24 * 3600
VISITOR_MAX_AGE_S = 365 * 24 * 3600

_VISITOR_RE = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class CookiePayload:
    member_id: str
    issued_at: int
    session_epoch: int
    sid: str


@dataclass(frozen=True)
class IssuedCookie:
    value: str
    payload: CookiePayload
    max_age_s: int


class SessionCookieCodec:
    def __init__(self, secret_key: str, clock: Clock, max_age_s: int = SESSION_MAX_AGE_S):
        self._ser = URLSafeSerializer(secret_key, salt="wm_session")
        self._clock = clock
        self.max_age_s = max_age_s

    def issue(self, member_id: str, session_epoch: int) -> IssuedCookie:
        payload = CookiePayload(
            member_id=member_id,
            issued_at=int(self._clock.now().timestamp()),
            session_epoch=session_epoch,
            sid=secrets.token_hex(16),
        )
        value = self._ser.dumps(
            {"m": payload.member_id, "i": payload.issued_at, "e": payload.session_epoch, "s": payload.sid}
        )
        return IssuedCookie(value=value, payload=payload, max_age_s=self.max_age_s)

    def parse(self, value: str) -> CookiePayload:
        if not value:
            raise Unauthenticated()
        try:
            data: Any = self._ser.loads(value)
            payload = CookiePayload(
                member_id=str(data["m"]),
                issued_at=int(data["i"]),
                session_epoch=int(data["e"]),
                sid=str(data["s"]),
            )
        except (BadData, KeyError, TypeError, ValueError):
            raise Unauthenticated() from None
        age = int(self._clock.now().timestamp()) - payload.issued_at
        if age > self.max_age_s:
            raise Unauthenticated()
        return payload


def new_visitor_id() -> str:
    return secrets.token_hex(16)


def is_valid_visitor_id(value: str | None) -> bool:
    return bool(value) and _VISITOR_RE.fullmatch(value) is not None
