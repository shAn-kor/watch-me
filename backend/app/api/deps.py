"""FastAPI dependencies (06 section 3.5). Other lanes build their routes from these.

Names to use in routers:

- `principal`          cookie, then CSRF on POST/PUT/PATCH/DELETE. Use on every creator route.
- `require_staff`      `principal` plus role `staff` (`forbidden_role`).
- `require_consent`    `principal` plus the face and voice consent (`consent_required`).
- `current_principal`  cookie only, no CSRF (media reads; `principal` builds on it).
- `require_csrf`       the CSRF check alone (already inside `principal`).
- `uow`                one `UnitOfWork` per request; commits after the route returns.
- `limit(scope)`       rate limit factory: "writes", "uploads" (per member), "public", "media" (per IP).
- `get_container`, `get_settings`, `client_ip` plumbing.

Check order for a creator route: cookie (401), CSRF (403), role (403); consent and
org scope follow in the service, in the order 01 lists for that endpoint.
`api` may not import `app.container`, so the container is read from `app.state`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import Depends, Request

from app.config import Settings
from app.db.uow import UnitOfWork
from app.errors import (
    ConsentRequired,
    CsrfFailed,
    ForbiddenRole,
    RateLimited,
    UnsupportedMediaType,
)
from app.security.cookies import SESSION_COOKIE
from app.services.views import Principal

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"

# ----------------------------------------------------------------- plumbing


def get_container(request: Request) -> Any:
    return request.app.state.container


def get_settings(request: Request) -> Settings:
    return get_container(request).settings


def get_auth_service(request: Request) -> Any:
    return get_container(request).services.auth_service


def client_ip(request: Request) -> str:
    return get_container(request).security["ip_resolver"].resolve(request)


def _request_uow(request: Request) -> Iterator[UnitOfWork]:
    with get_container(request).uow() as unit:
        yield unit
        unit.commit()


def uow(unit: UnitOfWork = Depends(_request_uow, scope="function")) -> UnitOfWork:
    """A unit of work for the request. It commits when the route returns normally
    and rolls back when the route (or a dependency) raises. `scope="function"` ends
    it before the response is sent, so the client never sees a result that is not
    committed yet."""
    return unit


# ------------------------------------------------------------ content type


async def require_json_content_type(request: Request) -> None:
    """01 section 1: a JSON request body must be `application/json`
    (`unsupported_media_type` 415). Multipart uploads are exempt. It runs first on
    every route (app-level dependency), so a cross-site form post gets 415 whatever
    the route is. A request without a body passes."""
    if request.method not in ("POST", "PUT", "PATCH"):
        return
    if not request.url.path.startswith("/api/"):
        return
    headers = request.headers
    has_body = headers.get("content-length", "0").strip() not in ("", "0") or (
        "transfer-encoding" in headers
    )
    if not has_body:
        return
    content_type = headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ("application/json", "multipart/form-data"):
        raise UnsupportedMediaType()


# ----------------------------------------------------------------- identity


def current_principal(request: Request) -> Principal:
    cookie = request.cookies.get(SESSION_COOKIE)
    return get_auth_service(request).principal_from_cookie(cookie)


def require_csrf(request: Request, who: Principal = Depends(current_principal)) -> None:
    if request.method in SAFE_METHODS:
        return
    csrf = get_container(request).security["csrf"]
    if not csrf.verify(who.sid, request.headers.get(CSRF_HEADER)):
        raise CsrfFailed()


def principal(
    who: Principal = Depends(current_principal), _csrf: None = Depends(require_csrf)
) -> Principal:
    """The signed-in member, CSRF-checked on unsafe methods."""
    return who


def require_staff(who: Principal = Depends(principal)) -> Principal:
    if not who.is_staff:
        raise ForbiddenRole()
    return who


def require_consent(who: Principal = Depends(principal)) -> Principal:
    if not who.consented:
        raise ConsentRequired()
    return who


# ------------------------------------------------------------- rate limits

_MEMBER_SCOPES = {
    "writes": ("rate_writes_per_member_min", 60),
    "uploads": ("rate_uploads_per_member_hour", 3600),
}
_IP_SCOPES = {
    "public": ("rate_public_per_ip_min", 60),
    "media": ("rate_media_per_ip_min", 60),
}


def limit(scope: str) -> Callable[..., None]:
    """Dependency factory for the limits of 01 section 1.3 that are not login or Q&A.
    `details.scope` is `member` for the per-member scopes and `ip` for the others."""
    if scope in _MEMBER_SCOPES:
        setting, window_s = _MEMBER_SCOPES[scope]

        def member_limit(
            request: Request, who: Principal = Depends(current_principal)
        ) -> None:
            container = get_container(request)
            allowed = getattr(container.settings, setting)
            decision = container.security["rate_limiter"].hit(
                scope, who.member_id, allowed, window_s
            )
            if not decision.allowed:
                raise RateLimited(
                    details={"scope": "member"}, retry_after_s=decision.retry_after_s
                )

        return member_limit

    if scope in _IP_SCOPES:
        setting, window_s = _IP_SCOPES[scope]

        def ip_limit(request: Request) -> None:
            container = get_container(request)
            ip = container.security["ip_resolver"].resolve(request)
            key = container.security["ip_hasher"].hash(ip, container.clock.now().date())
            allowed = getattr(container.settings, setting)
            decision = container.security["rate_limiter"].hit(scope, key, allowed, window_s)
            if not decision.allowed:
                raise RateLimited(
                    details={"scope": "ip"}, retry_after_s=decision.retry_after_s
                )

        return ip_limit

    raise ValueError(f"unknown rate limit scope: {scope}")
