"""`GET /api/me`, `POST /api/me/consent` (01 sections 3.3 and 3.4)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api import deps
from app.api.schemas.auth import MemberOut
from app.api.schemas.me import ConsentIn, ConsentOut, MeOut
from app.config import Settings
from app.services.views import Principal

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=MeOut)
def get_me(
    who: Principal = Depends(deps.principal),
    auth: Any = Depends(deps.get_auth_service),
    settings: Settings = Depends(deps.get_settings),
) -> MeOut:
    return MeOut.from_result(auth.me(who), settings)


@router.post("/consent", response_model=ConsentOut)
def accept_consent(
    body: ConsentIn,
    who: Principal = Depends(deps.principal),
    auth: Any = Depends(deps.get_auth_service),
) -> ConsentOut:
    return ConsentOut(member=MemberOut.from_view(auth.accept_consent(who, body.version)))
