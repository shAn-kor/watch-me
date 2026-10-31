"""Exception handlers: the 01 section 1.1 error envelope for every failure.

- `AppError` -> its code, status, and details (`Retry-After` for rate limits).
- Request validation -> 422 `validation_error` with `details.fields`
  (`path`, `problem`, `limit`), or 400 `malformed_request` for a body that is not JSON.
- Unknown route or method -> 404 `not_found`. A GET of a non-API path is the SPA shell
  (D8), so the hidden-profile page needs no server-rendered 404.
- Anything else -> 500 `internal_error` with the request id; the stack trace stays in
  the log.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler as _plain_http_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import (
    AppError,
    InternalError,
    MalformedRequest,
    NotFound,
    ServiceBusy,
    ValidationFailed,
)

log = logging.getLogger("app.errors")

NO_STORE = {"Cache-Control": "no-store"}

# pydantic error type -> 01 `details.fields[].problem`
_PROBLEMS = {
    "missing": "required",
    "string_too_short": "too_short",
    "too_short": "too_short",
    "string_too_long": "too_long",
    "too_long": "too_long",
}
_LIMIT_CTX = {
    "string_too_short": "min_length",
    "too_short": "min_length",
    "string_too_long": "max_length",
    "too_long": "max_length",
}


def _field(error: dict[str, Any]) -> dict[str, Any]:
    kind = str(error.get("type", ""))
    out: dict[str, Any] = {
        "path": ".".join(str(part) for part in error.get("loc", ())),
        "problem": _PROBLEMS.get(kind, "invalid_value"),
    }
    ctx_key = _LIMIT_CTX.get(kind)
    ctx = error.get("ctx") or {}
    if ctx_key and isinstance(ctx.get(ctx_key), int):
        out["limit"] = ctx[ctx_key]
    return out


def _error_response(
    err: AppError, *, headers: dict[str, str] | None = None
) -> JSONResponse:
    all_headers = dict(headers or {})
    retry_after = getattr(err, "retry_after_s", None)
    if retry_after is not None:
        all_headers["Retry-After"] = str(max(1, int(retry_after)))
    return JSONResponse(
        err.to_envelope(), status_code=err.http_status, headers=all_headers
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        if any(e.get("type") == "json_invalid" for e in errors):
            return _error_response(MalformedRequest())
        fields = [_field(e) for e in errors]
        return _error_response(ValidationFailed(details={"fields": fields}))

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code in (404, 405):
            shell = getattr(request.app.state, "spa_shell", None)
            if shell is not None:
                page = shell.respond(request)
                if page is not None:
                    return page
            return _error_response(NotFound())
        if exc.status_code == 400:
            return _error_response(MalformedRequest())
        # 304, 416 and similar protocol answers keep their plain form (01 section 7).
        return await _plain_http_handler(request, exc)

    @app.exception_handler(OperationalError)
    async def db_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
        if "database is locked" not in str(exc):
            return await unexpected_handler(request, exc)
        # A write could not get the SQLite lock in time: retryable, not a bug.
        log.warning("database is locked on %s %s", request.method, request.url.path)
        return _error_response(ServiceBusy(), headers=dict(NO_STORE))

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        log.error(
            "unhandled error on %s %s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        err = InternalError(details={"request_id": request_id})
        headers = dict(NO_STORE)
        if request_id:
            headers["X-Request-Id"] = request_id
        return _error_response(err, headers=headers)
