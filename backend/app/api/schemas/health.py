"""`GET /healthz` (01 section 8.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: Literal["ok", "unavailable"]
