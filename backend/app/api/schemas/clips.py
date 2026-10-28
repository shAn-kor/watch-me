"""Clip schemas (01 section 2 `Clip`, sections 5.3, 5.5 to 5.7)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.api.schemas.auth import iso_z
from app.services.clip_service import ClipDeleteResult
from app.services.clip_upload_service import UploadResult
from app.services.views import ClipView

UtcZ = Annotated[
    datetime | None,
    PlainSerializer(iso_z, return_type=str | None, when_used="always"),
]


class ClipErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cause: str
    retryable: bool


class ClipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    ordinal: int
    original_filename: str
    original_size_bytes: int
    duration_s: float
    has_audio: bool
    status: str
    step: str | None
    fail_code: str | None
    error: ClipErrorOut | None
    media_url: str | None
    captions_url: str | None
    created_at: UtcZ
    ready_at: UtcZ

    @classmethod
    def from_view(cls, view: ClipView) -> ClipOut:
        return cls.model_validate(view)


class ClipEnvelope(BaseModel):
    clip: ClipOut

    @classmethod
    def from_view(cls, view: ClipView) -> ClipEnvelope:
        return cls(clip=ClipOut.from_view(view))


class UploadOut(BaseModel):
    clip: ClipOut
    warnings: list[str]

    @classmethod
    def from_result(cls, result: UploadResult) -> UploadOut:
        return cls(clip=ClipOut.from_view(result.clip), warnings=list(result.warnings))


class ClipDeleteOut(BaseModel):
    clip_id: str
    purge: str
    facts_deleted: int
    facts_demoted: int

    @classmethod
    def from_result(cls, result: ClipDeleteResult) -> ClipDeleteOut:
        return cls(
            clip_id=result.clip_id,
            purge=result.purge,
            facts_deleted=result.facts_deleted,
            facts_demoted=result.facts_demoted,
        )
