"""Fact review routes (01 sections 5.8 to 5.12; lane S4).

The add-fact route lives under `/api/dogs/{dog_id}/facts` but belongs here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Request, Response

from app.api import deps
from app.api.schemas.facts import (
    ConfirmIn,
    FactCreateIn,
    FactEnvelope,
    FactPatchIn,
    PlaybackIn,
    PlaybackOut,
)
from app.db.uow import UnitOfWork
from app.services.evidence_validator import EvidenceInput
from app.services.fact_review_service import FactPatch, NewFact
from app.services.views import Principal

router = APIRouter(prefix="/api", tags=["facts"])


def get_service(request: Request) -> Any:
    return deps.get_container(request).services.fact_review_service


def fact_visible(
    fact_id: str,
    who: Principal = Depends(deps.principal),
    unit: UnitOfWork = Depends(deps.uow),
    service: Any = Depends(get_service),
) -> None:
    """Runs before the body is validated: another org's fact is `not_found`."""
    service.ensure_visible(unit, who, fact_id)


def dog_visible(
    dog_id: str,
    who: Principal = Depends(deps.require_consent),
    unit: UnitOfWork = Depends(deps.uow),
    service: Any = Depends(get_service),
) -> None:
    service.ensure_dog_visible(unit, who, dog_id)


@router.post(
    "/facts/{fact_id}/playback-complete",
    response_model=PlaybackOut,
    dependencies=[Depends(deps.limit("writes")), Depends(fact_visible)],
)
def playback_complete(
    fact_id: str,
    body: PlaybackIn,
    who: Principal = Depends(deps.principal),
    unit: UnitOfWork = Depends(deps.uow),
    service: Any = Depends(get_service),
) -> PlaybackOut:
    result = service.record_playback(
        unit, who, fact_id, body.evidence_id, body.position_s, body.watched_s
    )
    return PlaybackOut.from_result(result)


@router.post(
    "/facts/{fact_id}/confirm",
    response_model=FactEnvelope,
    dependencies=[Depends(deps.limit("writes")), Depends(fact_visible)],
)
def confirm_fact(
    fact_id: str,
    body: ConfirmIn | None = Body(default=None),
    who: Principal = Depends(deps.principal),
    unit: UnitOfWork = Depends(deps.uow),
    service: Any = Depends(get_service),
) -> FactEnvelope:
    ack = body.acknowledge_flags if body else False
    return FactEnvelope.from_view(service.confirm(unit, who, fact_id, ack))


@router.patch(
    "/facts/{fact_id}",
    response_model=FactEnvelope,
    dependencies=[Depends(deps.limit("writes")), Depends(fact_visible)],
)
def edit_fact(
    fact_id: str,
    body: FactPatchIn,
    who: Principal = Depends(deps.principal),
    unit: UnitOfWork = Depends(deps.uow),
    service: Any = Depends(get_service),
) -> FactEnvelope:
    patch = FactPatch(
        situation=body.situation,
        behavior=body.behavior,
        evidence=_evidence(body.evidence) if body.evidence is not None else None,
    )
    return FactEnvelope.from_view(service.edit(unit, who, fact_id, patch))


@router.delete(
    "/facts/{fact_id}",
    status_code=204,
    dependencies=[Depends(deps.limit("writes")), Depends(fact_visible)],
)
def delete_fact(
    fact_id: str,
    who: Principal = Depends(deps.principal),
    unit: UnitOfWork = Depends(deps.uow),
    service: Any = Depends(get_service),
) -> Response:
    service.delete(unit, who, fact_id)
    return Response(status_code=204)


@router.post(
    "/dogs/{dog_id}/facts",
    status_code=201,
    response_model=FactEnvelope,
    dependencies=[Depends(deps.limit("writes")), Depends(dog_visible)],
)
def add_fact(
    dog_id: str,
    body: FactCreateIn,
    who: Principal = Depends(deps.require_consent),
    unit: UnitOfWork = Depends(deps.uow),
    service: Any = Depends(get_service),
) -> FactEnvelope:
    data = NewFact(
        situation=body.situation,
        behavior=body.behavior,
        evidence=_evidence(body.evidence),
        observed_on=body.observed_on,
    )
    return FactEnvelope.from_view(service.add_manual(unit, who, dog_id, data))


def _evidence(items: list[Any]) -> list[EvidenceInput]:
    return [EvidenceInput(clip_id=i.clip_id, start_s=i.start_s, end_s=i.end_s, id=i.id) for i in items]
