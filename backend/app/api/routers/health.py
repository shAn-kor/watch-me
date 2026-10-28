"""`GET /healthz` (01 section 8.2): 200 while the database answers. No AI dependency."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import deps
from app.api.schemas.health import HealthOut

log = logging.getLogger("app.health")

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthOut)
def healthz(container=Depends(deps.get_container)):  # noqa: ANN001, ANN201
    try:
        with container.uow() as unit:
            unit.session.execute(text("SELECT 1"))
    except Exception:  # any DB failure means "not healthy"
        log.warning("health check: database unavailable", exc_info=True)
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return HealthOut(status="ok")
