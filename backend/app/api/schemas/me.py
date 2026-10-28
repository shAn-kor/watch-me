"""`GET /api/me` and `POST /api/me/consent` (01 sections 3.3 and 3.4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas.auth import MemberOut, OrgOut
from app.config import Settings
from app.services.auth_service import MeResult


class LimitsOut(BaseModel):
    max_clip_bytes: int
    max_clip_s: int | float
    max_clips_per_session: int
    allowed_extensions: list[str]
    wording_check: Literal["model", "rules_only"]

    @classmethod
    def from_settings(cls, settings: Settings) -> LimitsOut:
        max_s = settings.max_clip_s
        return cls(
            max_clip_bytes=settings.max_clip_bytes,
            max_clip_s=int(max_s) if float(max_s).is_integer() else max_s,
            max_clips_per_session=settings.max_clips_per_session,
            allowed_extensions=list(settings.allowed_extensions),
            wording_check=settings.wording_check,
        )


class MeOut(BaseModel):
    member: MemberOut
    org: OrgOut
    csrf_token: str
    limits: LimitsOut

    @classmethod
    def from_result(cls, result: MeResult, settings: Settings) -> MeOut:
        return cls(
            member=MemberOut.from_view(result.member),
            org=OrgOut.from_view(result.org),
            csrf_token=result.csrf_token,
            limits=LimitsOut.from_settings(settings),
        )


class ConsentIn(BaseModel):
    accepted: Literal[True]
    version: str = Field(min_length=1, max_length=40)


class ConsentOut(BaseModel):
    member: MemberOut
