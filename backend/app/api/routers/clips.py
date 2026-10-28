"""Clip routes: upload, status, retry, delete (01 sections 5.3, 5.5 to 5.7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api import deps
from app.api.schemas.clips import ClipDeleteOut, ClipEnvelope, UploadOut
from app.api.upload import UploadReceiver
from app.db.uow import UnitOfWork
from app.services.views import Principal

router = APIRouter(tags=["clips"])


def _services(request: Request) -> Any:
    return deps.get_container(request).services


@router.post("/api/sessions/{session_id}/clips", response_model=UploadOut)
async def upload_clip(
    session_id: str,
    request: Request,
    response: Response,
    who: Principal = Depends(deps.require_consent),
    _uploads: None = Depends(deps.limit("uploads")),
    unit: UnitOfWork = Depends(deps.uow),
) -> UploadOut:
    container = deps.get_container(request)
    service = container.services.clip_upload_service
    # checks that need no body run first, so a refused request reads nothing
    service.precheck(who, session_id, uow=unit)
    receiver = UploadReceiver(container.settings.max_clip_bytes, container.storage.new_tmp_path)
    received = await receiver.receive(request)
    result = await run_in_threadpool(service.accept, who, session_id, received, uow=unit)
    response.status_code = 201 if result.created else 200
    return UploadOut.from_result(result)


@router.get("/api/clips/{clip_id}", response_model=ClipEnvelope)
def get_clip(
    clip_id: str,
    request: Request,
    who: Principal = Depends(deps.principal),
    unit: UnitOfWork = Depends(deps.uow),
) -> ClipEnvelope:
    return ClipEnvelope.from_view(_services(request).clip_service.get(who, clip_id, uow=unit))


@router.post("/api/clips/{clip_id}/retry", response_model=ClipEnvelope)
def retry_clip(
    clip_id: str,
    request: Request,
    who: Principal = Depends(deps.require_consent),
    _writes: None = Depends(deps.limit("writes")),
    unit: UnitOfWork = Depends(deps.uow),
) -> ClipEnvelope:
    return ClipEnvelope.from_view(_services(request).clip_service.retry(who, clip_id, uow=unit))


@router.delete("/api/clips/{clip_id}", status_code=202, response_model=ClipDeleteOut)
def delete_clip(
    clip_id: str,
    request: Request,
    who: Principal = Depends(deps.require_consent),
    _writes: None = Depends(deps.limit("writes")),
    unit: UnitOfWork = Depends(deps.uow),
) -> ClipDeleteOut:
    return ClipDeleteOut.from_result(
        _services(request).clip_service.delete(who, clip_id, uow=unit)
    )
