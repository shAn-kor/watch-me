"""API entry point: `create_app()` (06 section 1).

Wiring only. Each lane plugs in at its `[slot ...]` marker; the router list is
`app.api.routers.ROUTERS`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routers import ROUTERS
from app.container import Container, build_container
from app.errors import AppError, InternalError, RateLimited
from app.logging import (
    configure_logging,
    get_request_id,
    new_request_id,
    set_request_id,
)


def create_app(container: Container | None = None) -> FastAPI:
    """Build the FastAPI app. Pass a prebuilt `container` (tests) or let it be built
    from the environment."""
    owns_container = container is None
    container = container or build_container()
    configure_logging(container.settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_container:
            container.dispose()

    app = FastAPI(title="Watch Me!", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.container = container

    _install_request_id_middleware(app)
    _install_error_handlers(
        app
    )  # [slot S1] replaced by api.errors.install_error_handlers

    for router in ROUTERS:
        app.include_router(router)

    # [slot S1] security headers middleware, noindex headers
    # [slot S5] media routes are part of ROUTERS
    # [slot S1] SPA shell (api/spa.py): index.html with 200 for non-/api, non-/media paths (D8)
    return app


def _install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # noqa: ANN001, ANN202
        request_id = new_request_id()
        set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            set_request_id(None)
        response.headers["X-Request-Id"] = request_id
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _install_error_handlers(app: FastAPI) -> None:
    """Minimal 01 section 1.1 envelope so the harness works before lane S1.
    Lane S1 replaces this with `api/errors.py` (validation errors, 404/405 shapes)."""

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimited) or hasattr(exc, "retry_after_s"):
            headers["Retry-After"] = str(getattr(exc, "retry_after_s", 1))
        return JSONResponse(
            exc.to_envelope(), status_code=exc.http_status, headers=headers
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(_request: Request, _exc: Exception) -> JSONResponse:
        err = InternalError(details={"request_id": get_request_id()})
        return JSONResponse(err.to_envelope(), status_code=err.http_status)
