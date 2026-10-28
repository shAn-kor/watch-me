"""ClientIpResolver (TRUSTED_PROXY aware) and IpHasher (01 section 1.3, I-18)."""

from __future__ import annotations

import hashlib
import hmac
from datetime import date
from typing import Any


class ClientIpResolver:
    def __init__(self, trusted_proxy: bool = False):
        self._trusted = trusted_proxy

    def resolve(self, request: Any) -> str:
        if self._trusted:
            header = request.headers.get("x-forwarded-for")
            if header:
                last = header.split(",")[-1].strip()
                if last:
                    return last
        client = getattr(request, "client", None)
        host = getattr(client, "host", None)
        return host or "unknown"


class IpHasher:
    def __init__(self, key: str):
        self._key = key.encode()

    def hash(self, ip: str, utc_date: date) -> str:
        msg = (ip + utc_date.isoformat()).encode()
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()
