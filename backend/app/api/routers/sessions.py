"""Filming session routes (01 sections 5.1, 5.2, 5.4, 5.4a)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.api import deps
from app.api.schemas.sessions import (
    SessionCreateIn,
    SessionDetailOut,
    SessionEnvelope,
    bundle_body,
)
from app.db.uow import UnitOfWork
from app.services.views import Principal

router = APIRouter(tags=["sessions"])


def _service(request: Request) -> Any:
    return deps.get_container(request).services.session_service


@router.post("/api/dogs/{dog_id}/sessions", status_code=201, response_model=SessionEnvelope)
def create_session(
    dog_id: str,
    body: SessionCreateIn,
    request: Request,
    who: Principal = Depends(deps.require_consent),
    _writes: None = Depends(deps.limit("writes")),
    unit: UnitOfWork = Depends(deps.uow),
) -> SessionEnvelope:
    view = _service(request).create(
        who,
        dog_id,
        situations=body.situations,
        observed_on=body.observed_on,
        capture_rules_ack=body.capture_rules_ack is True,
        uow=unit,
    )
    return SessionEnvelope.from_view(view)


@router.get(
    "/api/sessions/{session_id}",
    response_model=SessionDetailOut,
    responses={304: {"description": "Not modified (`If-None-Match` matched)"}},
)
def get_session(
    session_id: str,
    request: Request,
    include: str | None = None,
    who: Principal = Depends(deps.principal),
    unit: UnitOfWork = Depends(deps.uow),
) -> Response:
    bundle = _service(request).get(
        who, session_id, include_facts=include != "none", uow=unit
    )
    body = bundle_body(bundle)
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    etag = 'W/"' + hashlib.sha1(payload.encode()).hexdigest()[:24] + '"'
    sent = request.headers.get("if-none-match", "")
    if etag in [part.strip() for part in sent.split(",")] or sent.strip() == "*":
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(body, headers={"ETag": etag})


@router.post("/api/sessions/{session_id}/submit", response_model=SessionEnvelope)
def submit_session(
    session_id: str,
    request: Request,
    who: Principal = Depends(deps.require_consent),
    _writes: None = Depends(deps.limit("writes")),
    unit: UnitOfWork = Depends(deps.uow),
) -> SessionEnvelope:
    return SessionEnvelope.from_view(_service(request).submit(who, session_id, uow=unit))


@router.post("/api/sessions/{session_id}/retry-merge", response_model=SessionEnvelope)
def retry_merge(
    session_id: str,
    request: Request,
    who: Principal = Depends(deps.require_consent),
    _writes: None = Depends(deps.limit("writes")),
    unit: UnitOfWork = Depends(deps.uow),
) -> SessionEnvelope:
    return SessionEnvelope.from_view(_service(request).retry_merge(who, session_id, uow=unit))
