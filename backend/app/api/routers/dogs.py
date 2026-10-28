"""`/api/dogs` (01 sections 4.1 to 4.10): CRUD, photo, checklist, publish lifecycle,
delete. Thin: dependencies, a call to one service method, a response model."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile

from app.api import deps
from app.api.schemas.dogs import (
    ChecklistEnvelope,
    ChecklistIn,
    ChecklistOut,
    DeleteOut,
    DogCreateIn,
    DogDetailOut,
    DogEnvelope,
    DogListItemOut,
    DogListOut,
    DogOut,
    DogPatchIn,
    PublishOut,
)
from app.db.uow import UnitOfWork
from app.services.views import Principal

router = APIRouter(prefix="/api/dogs", tags=["dogs"])

_writes = Depends(deps.limit("writes"))


def _dogs(container: Any = Depends(deps.get_container)) -> Any:
    return container.services.dog_service


def _publish(container: Any = Depends(deps.get_container)) -> Any:
    return container.services.publish_service


def _deletion(container: Any = Depends(deps.get_container)) -> Any:
    return container.services.deletion_service


@router.get("", response_model=DogListOut)
def list_dogs(
    who: Principal = Depends(deps.principal),
    uow: UnitOfWork = Depends(deps.uow),
    dogs: Any = Depends(_dogs),
) -> DogListOut:
    return DogListOut(
        dogs=[DogListItemOut.from_view(i) for i in dogs.list_for_org(uow, who)]
    )


@router.post("", response_model=DogEnvelope, status_code=201, dependencies=[_writes])
def create_dog(
    body: DogCreateIn,
    who: Principal = Depends(deps.principal),
    uow: UnitOfWork = Depends(deps.uow),
    dogs: Any = Depends(_dogs),
) -> DogEnvelope:
    view = dogs.create(uow, who, **body.model_dump())
    return DogEnvelope(dog=DogOut.from_view(view))


@router.get("/{dog_id}", response_model=DogDetailOut)
def get_dog(
    dog_id: str,
    who: Principal = Depends(deps.principal),
    uow: UnitOfWork = Depends(deps.uow),
    dogs: Any = Depends(_dogs),
) -> DogDetailOut:
    return DogDetailOut.from_view(dogs.get_detail(uow, who, dog_id))


@router.patch("/{dog_id}", response_model=DogEnvelope, dependencies=[_writes])
def patch_dog(
    dog_id: str,
    body: DogPatchIn,
    who: Principal = Depends(deps.principal),
    uow: UnitOfWork = Depends(deps.uow),
    dogs: Any = Depends(_dogs),
) -> DogEnvelope:
    return DogEnvelope(dog=DogOut.from_view(dogs.update(uow, who, dog_id, body.patch())))


@router.put("/{dog_id}/photo", response_model=DogEnvelope, dependencies=[_writes])
def put_photo(
    dog_id: str,
    photo: UploadFile | None = File(None),
    who: Principal = Depends(deps.principal),
    uow: UnitOfWork = Depends(deps.uow),
    dogs: Any = Depends(_dogs),
    settings: Any = Depends(deps.get_settings),
) -> DogEnvelope:
    # Read one byte past the limit so the service can answer `file_too_large`
    # without holding an arbitrarily large body in memory.
    # A missing field is reported by the service after the org-scoped lookup, so a
    # hidden dog answers `not_found` whatever the body is.
    data = photo.file.read(settings.max_photo_bytes + 1) if photo is not None else None
    view = dogs.set_photo(uow, who, dog_id, data, (photo.filename if photo else "") or "")
    return DogEnvelope(dog=DogOut.from_view(view))


@router.put(
    "/{dog_id}/publish-checklist", response_model=ChecklistEnvelope, dependencies=[_writes]
)
def put_checklist(
    dog_id: str,
    body: ChecklistIn,
    who: Principal = Depends(deps.require_staff),
    uow: UnitOfWork = Depends(deps.uow),
    publish: Any = Depends(_publish),
) -> ChecklistEnvelope:
    view = publish.set_checklist(uow, who, dog_id, **body.model_dump())
    return ChecklistEnvelope(checklist=ChecklistOut.from_view(view))


@router.post("/{dog_id}/publish", response_model=PublishOut, dependencies=[_writes])
def publish_dog(
    dog_id: str,
    who: Principal = Depends(deps.require_staff),
    uow: UnitOfWork = Depends(deps.uow),
    publish: Any = Depends(_publish),
) -> PublishOut:
    return PublishOut.from_result(publish.publish(uow, who, dog_id))


@router.post("/{dog_id}/unpublish", response_model=DogEnvelope, dependencies=[_writes])
def unpublish_dog(
    dog_id: str,
    who: Principal = Depends(deps.require_staff),
    uow: UnitOfWork = Depends(deps.uow),
    publish: Any = Depends(_publish),
) -> DogEnvelope:
    return DogEnvelope(dog=DogOut.from_view(publish.unpublish(uow, who, dog_id)))


@router.post("/{dog_id}/adopted", response_model=DogEnvelope, dependencies=[_writes])
def adopted_dog(
    dog_id: str,
    who: Principal = Depends(deps.require_staff),
    uow: UnitOfWork = Depends(deps.uow),
    publish: Any = Depends(_publish),
) -> DogEnvelope:
    return DogEnvelope(dog=DogOut.from_view(publish.mark_adopted(uow, who, dog_id)))


@router.delete("/{dog_id}", response_model=DeleteOut, status_code=202, dependencies=[_writes])
def delete_dog(
    dog_id: str,
    who: Principal = Depends(deps.require_staff),
    uow: UnitOfWork = Depends(deps.uow),
    deletion: Any = Depends(_deletion),
) -> DeleteOut:
    ticket = deletion.request_dog_delete(uow, who, dog_id)
    return DeleteOut(dog_id=ticket.dog_id, status=ticket.status, purge=ticket.purge)
