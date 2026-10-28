"""SPA shell and response security headers (06 section 1, D8).

The shell is `index.html` served with HTTP 200 for every GET that is not under
`/api` or `/media` (and is not `/healthz`), so it never reveals whether a profile
slug exists, is hidden, or never was. The frontend asks the public API and shows the
"not available" page on 404. Real files of the build (assets, favicon) are served as
themselves. Unknown `/api` and `/media` paths stay JSON 404.

It hooks into the 404 handler of `api/errors.py` instead of a catch-all route, so
routers added after `create_app` (tests, later lanes) are never shadowed.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

_NOT_BUILT = (
    "<!doctype html><meta charset=utf-8><title>Watch Me!</title>"
    "<p>The Watch Me! frontend is not built. Run the Vite build, or open the dev server.</p>"
)
_API_PREFIXES = ("/api", "/media", "/healthz")
NOINDEX_PREFIXES = ("/d/", "/api/public/")


def default_spa_dir() -> Path:
    """The `SPA_DIR` environment variable, else `<repo>/frontend/dist`."""
    configured = os.environ.get("SPA_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


def _is_reserved(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _API_PREFIXES)


class SpaShell:
    def __init__(self, directory: Path):
        self._dir = directory.resolve()

    def respond(self, request: Request) -> Response | None:
        """The shell or a build file for a GET/HEAD, else `None` (caller answers JSON 404)."""
        path = request.url.path
        if request.method not in ("GET", "HEAD") or _is_reserved(path):
            return None
        candidate = self._static_file(path)
        if candidate is not None:
            return FileResponse(candidate)
        index = self._dir / "index.html"
        if index.is_file():
            return FileResponse(
                index,
                media_type="text/html; charset=utf-8",
                headers={"Cache-Control": "no-cache"},
            )
        return HTMLResponse(_NOT_BUILT, headers={"Cache-Control": "no-cache"})

    def _static_file(self, path: str) -> Path | None:
        relative = path.lstrip("/")
        if not relative or relative == "index.html":
            return None
        target = (self._dir / relative).resolve()
        if self._dir in target.parents and target.is_file():
            return target
        return None


def install_spa(app: FastAPI, directory: Path | None = None) -> SpaShell:
    shell = SpaShell(directory or default_spa_dir())
    app.state.spa_shell = shell
    return shell


def install_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # noqa: ANN001, ANN202
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "same-origin")
        headers.setdefault("X-Frame-Options", "DENY")
        path = request.url.path
        if any(path.startswith(prefix) for prefix in NOINDEX_PREFIXES):
            headers.setdefault("X-Robots-Tag", "noindex")
        return response
