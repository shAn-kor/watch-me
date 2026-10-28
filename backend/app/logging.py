"""Structured logs, request id, and the IP hash helper (never a raw IP, I-18)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging as _logging
import uuid
from contextvars import ContextVar
from datetime import date

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def ip_hash(key: str, ip: str, utc_date: date) -> str:
    """`HMAC-SHA256(key, ip + utc_date)` as hex (02 section 2.12).

    The date is part of the message, so the per-IP counters restart at 00:00 UTC.
    """
    message = f"{ip}{utc_date.isoformat()}".encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()


class JsonFormatter(_logging.Formatter):
    def format(self, record: _logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Install one JSON handler on the `app` logger. Safe to call repeatedly."""
    logger = _logging.getLogger("app")
    logger.setLevel(level.upper())
    if not any(getattr(h, "_wm_handler", False) for h in logger.handlers):
        handler = _logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._wm_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
