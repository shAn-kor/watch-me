"""Session schemas (01 section 2 `Session`, sections 5.1 to 5.4a)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.clips import ClipOut, UtcZ, UtcZRequired
from app.api.schemas.facts import FactOut
from app.api.schemas.vocab import SessionFailCode, SessionStatus, SituationCode
from app.services.session_service import SessionBundle, SessionView


class SessionCreateIn(BaseModel):
    # Validation of the values lives in SessionService so every error is one
    # `validation_error` with `details.fields`; this model only types the body.
    situations: list[str] = Field(default_factory=list)
    observed_on: date | None = None
    capture_rules_ack: bool | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dog_id: str
    member_id: str
    owner_name: str
    situations: list[SituationCode]
    observed_on: date
    status: SessionStatus
    fail_code: SessionFailCode | None
    created_at: UtcZRequired
    submitted_at: UtcZ
    review_ready_at: UtcZ

    @classmethod
    def from_view(cls, view: SessionView) -> SessionOut:
        return cls.model_validate(view)


class SessionEnvelope(BaseModel):
    session: SessionOut

    @classmethod
    def from_view(cls, view: SessionView) -> SessionEnvelope:
        return cls(session=SessionOut.from_view(view))


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clips_total: int
    clips_ready: int
    clips_failed: int


class SessionDetailOut(BaseModel):
    """Body of `GET /api/sessions/{id}`. `facts` is absent (not empty) for `include=none`;
    the route sends `bundle_body` as is, so this model only describes it."""

    session: SessionOut
    clips: list[ClipOut]
    facts: list[FactOut] = Field(default_factory=list)
    progress: ProgressOut


def bundle_body(bundle: SessionBundle) -> dict[str, Any]:
    """The JSON body of `GET /api/sessions/{id}` (`facts` absent for `include=none`)."""
    body: dict[str, Any] = {
        "session": SessionOut.from_view(bundle.session).model_dump(mode="json"),
        "clips": [ClipOut.from_view(c).model_dump(mode="json") for c in bundle.clips],
    }
    if bundle.facts is not None:
        body["facts"] = [FactOut.from_view(f).model_dump(mode="json") for f in bundle.facts]
    body["progress"] = ProgressOut.model_validate(bundle.progress).model_dump(mode="json")
    return body


