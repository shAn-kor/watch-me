"""Request and response models of the fact review routes (01 sections 2 and 5.8 to 5.12)."""

from __future__ import annotations

import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.api.schemas.auth import iso_z
from app.services.fact_review_service import PlaybackResult
from app.services.views import FactView

SituationCode = Literal[
    "new_person", "handling", "leash_walk", "other_dog",
    "food_toys", "alone_time", "indoors_rest", "children_cats",
]


class PlaybackIn(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=64)
    position_s: float = Field(ge=0, le=100000)
    watched_s: float = Field(ge=0, le=100000)


class PlaybackOut(BaseModel):
    fact_id: str
    evidence_id: str
    completed_at: str
    all_ranges_played: bool

    @classmethod
    def from_result(cls, r: PlaybackResult) -> PlaybackOut:
        return cls(
            fact_id=r.fact_id,
            evidence_id=r.evidence_id,
            completed_at=iso_z(r.completed_at) or "",
            all_ranges_played=r.all_ranges_played,
        )


class ConfirmIn(BaseModel):
    acknowledge_flags: bool = False


class EvidenceIn(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    clip_id: str = Field(min_length=1, max_length=64)
    start_s: float
    end_s: float

    @field_validator("start_s", "end_s")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("not finite")
        return value


class FactPatchIn(BaseModel):
    situation: SituationCode | None = None
    behavior: str | None = Field(default=None, max_length=2000)
    evidence: list[EvidenceIn] | None = Field(default=None, max_length=3)

    @field_validator("situation", "behavior", "evidence", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # A key that is present must carry a value; omit it to leave a field alone.
        if value is None:
            raise ValueError("null is not allowed")
        return value


class FactCreateIn(BaseModel):
    situation: SituationCode
    behavior: str = Field(max_length=2000)
    evidence: list[EvidenceIn] = Field(default_factory=list, max_length=3)
    observed_on: date | None = None


class FlagOut(BaseModel):
    code: str
    severity: str
    source: str
    detail: str


class EvidenceOut(BaseModel):
    id: str
    clip_id: str
    start_s: float
    end_s: float
    played_by_me: bool
    media_url: str | None
    captions_url: str | None


class ClipLengthOut(BaseModel):
    clip_count: int
    seconds: int
    label: str


class ConfirmedOut(BaseModel):
    by_member_id: str
    by_name: str
    role: str
    at: str


class FactOut(BaseModel):
    id: str
    dog_id: str
    session_id: str | None
    situation: str
    behavior: str
    source: str
    origin: str
    status: str
    flags: list[FlagOut]
    observed_on: str
    evidence: list[EvidenceOut]
    clip_length: ClipLengthOut
    confirmed: ConfirmedOut | None
    created_by: str | None
    can_confirm: bool
    blocked_reason: str | None

    @classmethod
    def from_view(cls, v: FactView) -> FactOut:
        return cls(
            id=v.id,
            dog_id=v.dog_id,
            session_id=v.session_id,
            situation=v.situation,
            behavior=v.behavior,
            source=v.source,
            origin=v.origin,
            status=v.status,
            flags=[FlagOut(code=f.code, severity=f.severity, source=f.source, detail=f.detail) for f in v.flags],
            observed_on=v.observed_on.isoformat(),
            evidence=[
                EvidenceOut(
                    id=e.id, clip_id=e.clip_id, start_s=e.start_s, end_s=e.end_s,
                    played_by_me=e.played_by_me, media_url=e.media_url, captions_url=e.captions_url,
                )
                for e in v.evidence
            ],
            clip_length=ClipLengthOut(
                clip_count=v.clip_length.clip_count, seconds=v.clip_length.seconds, label=v.clip_length.label
            ),
            confirmed=(
                ConfirmedOut(
                    by_member_id=v.confirmed.by_member_id, by_name=v.confirmed.by_name,
                    role=v.confirmed.role, at=iso_z(v.confirmed.at) or "",
                )
                if v.confirmed
                else None
            ),
            created_by=v.created_by,
            can_confirm=v.can_confirm,
            blocked_reason=v.blocked_reason,
        )


class FactEnvelope(BaseModel):
    fact: FactOut

    @classmethod
    def from_view(cls, v: FactView) -> FactEnvelope:
        return cls(fact=FactOut.from_view(v))
