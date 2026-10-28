"""CsrfTokenService: token = HMAC-SHA256(SECRET_KEY, "csrf:" + sid), hex (01 section 1)."""

from __future__ import annotations

import hashlib
import hmac


class CsrfTokenService:
    def __init__(self, secret_key: str):
        self._key = secret_key.encode()

    def token_for(self, sid: str) -> str:
        return hmac.new(self._key, f"csrf:{sid}".encode(), hashlib.sha256).hexdigest()

    def verify(self, sid: str, presented: str | None) -> bool:
        if not presented:
            return False
        return hmac.compare_digest(self.token_for(sid).encode(), presented.encode())
