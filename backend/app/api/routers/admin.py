"""`GET /api/admin/metrics` (01 section 8.1). Staff only; thin."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api import deps
from app.api.schemas.admin import MetricsOut
from app.services.views import Principal

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/metrics", response_model=MetricsOut)
def metrics(
    who: Principal = Depends(deps.require_staff),
    container: Any = Depends(deps.get_container),
) -> MetricsOut:
    return MetricsOut.from_view(container.services.metrics_service.admin_metrics(who))
