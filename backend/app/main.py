"""API entry point: `create_app()` (06 section 1).

Wiring only. Each lane plugs in at its `[slot ...]` marker; the router list is
`app.api.routers.ROUTERS`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request

from app.api.deps import require_json_content_type
from app.api.errors import install_error_handlers
from app.api.routers import ROUTERS
from app.api.spa import install_security_headers, install_spa
from app.container import Container, build_container
from app.logging import (
    configure_logging,
    new_request_id,
    set_request_id,
)


def create_app(
    container: Container | None = None, *, spa_dir: Path | None = None
) -> FastAPI:
    """Build the FastAPI app. Pass a prebuilt `container` (tests) or let it be built
    from the environment. `spa_dir` is the built frontend (default `SPA_DIR` or
    `frontend/dist`)."""
    owns_container = container is None
    container = container or build_container()
    configure_logging(container.settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_container:
            container.dispose()

    app = FastAPI(
        title="Watch Me!",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        dependencies=[Depends(require_json_content_type)],  # [slot S1] 415 rule
    )
    app.state.container = container

    _install_request_id_middleware(app)
    install_error_handlers(app)  # [slot S1]

    for router in ROUTERS:
        app.include_router(router)

    install_security_headers(app)  # [slot S1] security and noindex headers
    # [slot S5] media routes are part of ROUTERS
    install_spa(app, spa_dir)  # [slot S1] SPA shell: 200 for non-/api, non-/media paths (D8)
    return app


def _install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = new_request_id()
        request.state.request_id = request_id  # read by the 500 handler (api/errors.py)
        set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            set_request_id(None)
        response.headers["X-Request-Id"] = request_id
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response
