"""Public routes. S6 owns the ask route; lane S5 adds the profile route to this router.

`POST /api/public/dogs/{slug}/ask` (01 section 6.2): no sign-in, no CSRF. The limit
is the `qa_log` sliding hour inside the service, not the per-minute `public` limit.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api import deps
from app.api.schemas.public import AskIn, AskOut, ProfileOut
from app.config import Settings
from app.db.uow import UnitOfWork
from app.security.cookies import (
    VISITOR_COOKIE,
    VISITOR_MAX_AGE_S,
    is_valid_visitor_id,
    new_visitor_id,
)
from app.services.qa_service import Visitor

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/dogs/{slug}", dependencies=[Depends(deps.limit("public"))])
def profile(
    slug: str,
    unit: UnitOfWork = Depends(deps.uow),
    container: Any = Depends(deps.get_container),
) -> JSONResponse:
    """01 section 6.1: the public profile. Hidden and unknown slugs are one 404."""
    view = container.services.public_profile_service.get_profile(unit, slug)
    return JSONResponse(
        ProfileOut.from_profile(view).model_dump(mode="json"),
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )


@router.post("/dogs/{slug}/ask")
def ask(
    slug: str,
    body: AskIn,
    request: Request,
    ip: str = Depends(deps.client_ip),
    container: Any = Depends(deps.get_container),
    settings: Settings = Depends(deps.get_settings),
) -> JSONResponse:
    cookie = request.cookies.get(VISITOR_COOKIE)
    fresh = not is_valid_visitor_id(cookie)
    visitor_id = new_visitor_id() if fresh else str(cookie)
    answer = container.services.qa_service.ask(slug, body.question, Visitor(ip, visitor_id))
    out = AskOut.from_answer(answer)
    response = JSONResponse(
        out.model_dump(mode="json", exclude_unset=True),
        headers={
            "X-RateLimit-Remaining": str(out.limits.remaining_this_hour),
            "Cache-Control": "no-store",
        },
    )
    if fresh:
        response.set_cookie(
            VISITOR_COOKIE,
            visitor_id,
            max_age=VISITOR_MAX_AGE_S,
            path="/",
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
        )
    return response
