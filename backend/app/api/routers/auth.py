"""`POST /api/auth/login`, `POST /api/auth/logout` (01 sections 3.1 and 3.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from app.api import deps
from app.api.schemas.auth import LoginIn, LoginOut
from app.config import Settings
from app.security.cookies import SESSION_COOKIE
from app.services.views import Principal

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    auth: Any = Depends(deps.get_auth_service),
    settings: Settings = Depends(deps.get_settings),
) -> LoginOut:
    result = auth.login(body.email, body.password, deps.client_ip(request))
    response.set_cookie(
        SESSION_COOKIE,
        result.cookie.value,
        max_age=result.cookie.max_age_s,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return LoginOut.from_result(result)


@router.post("/logout", status_code=204)
def logout(
    who: Principal = Depends(deps.principal),
    auth: Any = Depends(deps.get_auth_service),
    settings: Settings = Depends(deps.get_settings),
) -> Response:
    auth.logout(who)
    response = Response(status_code=204)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response
