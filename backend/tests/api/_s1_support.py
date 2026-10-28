"""Shared helpers of the lane S1 API tests (07 section 3.7).

`build_probe_router` is a test-only router that stands in for the creator routes of
other lanes: it uses the real S1 dependencies (`principal`, `require_staff`,
`require_consent`, `uow`) and a tiny org-scope rule on the real `dog` and
`filming_session` tables. Nothing here is imported by the app.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.errors import NotFound
from app.models import Dog, FilmingSession

UNSAFE = ("POST", "PUT", "PATCH", "DELETE")


class _Body(BaseModel):
    x: str


def csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def build_probe_router() -> APIRouter:
    from app.api import deps

    router = APIRouter(prefix="/api/_t")

    @router.get("/whoami")
    def whoami(p=Depends(deps.principal)) -> dict[str, Any]:
        return {"member_id": p.member_id, "role": p.role, "org_id": p.org_id}

    def _ok(p) -> dict[str, bool]:
        return {"ok": True}

    @router.post("/write")
    def write_post(p=Depends(deps.principal)):
        return _ok(p)

    @router.put("/write")
    def write_put(p=Depends(deps.principal)):
        return _ok(p)

    @router.patch("/write")
    def write_patch(p=Depends(deps.principal)):
        return _ok(p)

    @router.delete("/write")
    def write_delete(p=Depends(deps.principal)):
        return _ok(p)

    @router.post("/staff")
    def staff_only(p=Depends(deps.require_staff)):
        return _ok(p)

    @router.post("/gated")
    def consent_gated(p=Depends(deps.require_consent)):
        return _ok(p)

    @router.get("/open-read")
    def open_read(p=Depends(deps.principal)):
        return _ok(p)

    def _dog(uow, p, dog_id: str) -> Dog:
        dog = uow.session.get(Dog, dog_id)
        if dog is None or dog.org_id != p.org_id:
            raise NotFound()
        return dog

    @router.get("/dogs/{dog_id}")
    def dog_get(dog_id: str, p=Depends(deps.principal), uow=Depends(deps.uow)):
        return {"id": _dog(uow, p, dog_id).id}

    @router.patch("/dogs/{dog_id}")
    def dog_patch(dog_id: str, p=Depends(deps.principal), uow=Depends(deps.uow)):
        return {"id": _dog(uow, p, dog_id).id}

    @router.put("/dogs/{dog_id}")
    def dog_put(dog_id: str, p=Depends(deps.principal), uow=Depends(deps.uow)):
        return {"id": _dog(uow, p, dog_id).id}

    @router.post("/dogs/{dog_id}")
    def dog_post(dog_id: str, p=Depends(deps.principal), uow=Depends(deps.uow)):
        return {"id": _dog(uow, p, dog_id).id}

    @router.delete("/dogs/{dog_id}")
    def dog_delete(dog_id: str, p=Depends(deps.principal), uow=Depends(deps.uow)):
        return {"id": _dog(uow, p, dog_id).id}

    @router.post("/sessions/{session_id}/clips")
    def upload_like(
        session_id: str,
        p=Depends(deps.require_consent),
        uow=Depends(deps.uow),
    ):
        # Service order of 06 section 3.5: consent (dependency) first, then org scope.
        sess = uow.session.scalar(
            select(FilmingSession)
            .join(Dog, Dog.id == FilmingSession.dog_id)
            .where(FilmingSession.id == session_id, Dog.org_id == p.org_id)
        )
        if sess is None:
            raise NotFound()
        return {"id": sess.id}

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    @router.post("/public")
    def public_post(body: _Body):
        return {"x": body.x}

    @router.get("/limited-writes")
    def limited(_=Depends(deps.limit("writes"))):
        return {"ok": True}

    return router


def iter_api_routes(router: Any, prefix: str = ""):
    """Yield (full_path, APIRoute) for every route, also through include_router
    wrappers (FastAPI includes routers lazily)."""
    from fastapi.routing import APIRoute

    for route in router.routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif hasattr(route, "original_router"):
            inner = prefix + getattr(route.include_context, "prefix", "")
            yield from iter_api_routes(route.original_router, inner)


def uses_principal(dependant: Any) -> bool:
    from app.api import deps

    return any(
        sub.call is deps.current_principal or uses_principal(sub)
        for sub in dependant.dependencies
    )


def creator_unsafe_routes(app: Any) -> list[tuple[str, str]]:
    """(method, path with dummy ids) of every unsafe route under /api that uses the
    creator principal dependency. This is the "route table" of API-CSRF-03."""
    found: list[tuple[str, str]] = []
    for full_path, route in iter_api_routes(app.router):
        if not full_path.startswith("/api/") or not uses_principal(route.dependant):
            continue
        path = full_path
        for name in route.param_convertors:
            path = path.replace("{" + name + "}", "x" * 32)
        for method in sorted(route.methods & set(UNSAFE)):
            found.append((method, path))
    return found
