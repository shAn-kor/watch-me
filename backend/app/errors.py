"""Error types: `AppError` hierarchy (01 section 1.2) and `JobError` (D2, 04 8.8).

One `AppError` subclass per code of the 01 catalog. `JobError` is the only
error handlers and AI adapters raise inside the worker. It lives here so that
`ai` does not import `pipeline`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:  # type-only; keeps this module free of an `ai` dependency
    from app.ai.types import Usage


class AppError(Exception):
    """Base of every HTTP-visible error. Subclasses fix `code` and `http_status`."""

    code: ClassVar[str] = "internal_error"
    http_status: ClassVar[int] = 500
    default_message: ClassVar[str] = "Something went wrong."

    def __init__(
        self, message: str | None = None, *, details: dict[str, Any] | None = None
    ):
        self.message: str = message or self.default_message
        self.details: dict[str, Any] = dict(details) if details else {}
        super().__init__(self.message)

    def to_envelope(self) -> dict[str, Any]:
        """The 01 section 1.1 error envelope."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


ERROR_CLASSES: dict[str, type[AppError]] = {}


def _register(cls: type[AppError]) -> type[AppError]:
    ERROR_CLASSES[cls.code] = cls
    return cls


def _make(name: str, code: str, status: int, message: str) -> type[AppError]:
    cls = type(
        name,
        (AppError,),
        {
            "code": code,
            "http_status": status,
            "default_message": message,
            "__module__": __name__,
            "__doc__": f"{status} `{code}` (01 section 1.2).",
        },
    )
    return _register(cls)


# 400
MalformedRequest = _make(
    "MalformedRequest", "malformed_request", 400, "The request body is not valid."
)
UploadIncomplete = _make(
    "UploadIncomplete",
    "upload_incomplete",
    400,
    "The upload ended before the whole file arrived.",
)
# 401
Unauthenticated = _make(
    "Unauthenticated", "unauthenticated", 401, "Sign in to continue."
)
InvalidCredentials = _make(
    "InvalidCredentials", "invalid_credentials", 401, "Wrong email or password."
)
# 403
CsrfFailed = _make(
    "CsrfFailed",
    "csrf_failed",
    403,
    "The request could not be verified. Reload and try again.",
)
ForbiddenRole = _make(
    "ForbiddenRole", "forbidden_role", 403, "Your role cannot do this."
)
ConsentRequired = _make(
    "ConsentRequired",
    "consent_required",
    403,
    "Accept the face and voice notice first.",
)
NotOwnSession = _make(
    "NotOwnSession",
    "not_own_session",
    403,
    "This belongs to another volunteer's session.",
)
StaffOnlySituation = _make(
    "StaffOnlySituation",
    "staff_only_situation",
    403,
    "Only staff can confirm this situation.",
)
# 404
NotFound = _make("NotFound", "not_found", 404, "Not found.")
# 409
InvalidState = _make(
    "InvalidState",
    "invalid_state",
    409,
    "This action is not allowed in the current state.",
)
ClipLimitReached = _make(
    "ClipLimitReached", "clip_limit_reached", 409, "This session already has 3 clips."
)
ClipNotReady = _make(
    "ClipNotReady", "clip_not_ready", 409, "The clip is not ready yet."
)
PlaybackRequired = _make(
    "PlaybackRequired",
    "playback_required",
    409,
    "Watch the whole clip range before you confirm this fact.",
)
FlagsUnacknowledged = _make(
    "FlagsUnacknowledged",
    "flags_unacknowledged",
    409,
    "Acknowledge the wording flags before you confirm.",
)
PublishChecklistIncomplete = _make(
    "PublishChecklistIncomplete",
    "publish_checklist_incomplete",
    409,
    "Finish the publish checklist first.",
)
# 413 / 415
FileTooLarge = _make(
    "FileTooLarge", "file_too_large", 413, "The file is larger than 200 MiB."
)
UnsupportedFileType = _make(
    "UnsupportedFileType",
    "unsupported_file_type",
    415,
    "This file type is not supported.",
)
UnsupportedMediaType = _make(
    "UnsupportedMediaType",
    "unsupported_media_type",
    415,
    "Send the request as application/json.",
)
# 422
ValidationFailed = _make(
    "ValidationFailed", "validation_error", 422, "Some fields are not valid."
)
ClipTooLong = _make(
    "ClipTooLong", "clip_too_long", 422, "The clip is longer than 2 minutes."
)
EvidenceOutOfRange = _make(
    "EvidenceOutOfRange",
    "evidence_out_of_range",
    422,
    "The evidence range is not valid for this clip.",
)
QuestionTooShort = _make(
    "QuestionTooShort", "question_too_short", 422, "The question is too short."
)


@_register
class RateLimited(AppError):
    """429 `rate_limited` (01 section 1.2). `retry_after_s` feeds the Retry-After header."""

    code = "rate_limited"
    http_status = 429
    default_message = "Too many requests. Try again later."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        retry_after_s: int = 1,
    ):
        super().__init__(message, details=details)
        self.retry_after_s = retry_after_s


# 500 / 503
InternalError = _make(
    "InternalError", "internal_error", 500, "Something went wrong on our side."
)


@_register
class QaCostCapReached(AppError):
    """503 `qa_cost_cap_reached`. `retry_after_s` runs until 00:00 UTC."""

    code = "qa_cost_cap_reached"
    http_status = 503
    default_message = "Questions are paused for today. Try again tomorrow."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        retry_after_s: int = 1,
    ):
        super().__init__(message, details=details)
        self.retry_after_s = retry_after_s


QaUnavailable = _make(
    "QaUnavailable", "qa_unavailable", 503, "Questions are unavailable right now."
)
StorageUnavailable = _make(
    "StorageUnavailable",
    "storage_unavailable",
    503,
    "Storage is unavailable right now.",
)


class JobError(Exception):
    """The single worker-facing error (D2, 04 section 8.8).

    `code` is what the failure hook stores as the clip or session fail code
    (`ai_failed`, `ai_invalid_output`, `transcode_failed`, ...). There is no
    separate `fail_code` field. `usages` carries the `Usage` rows of calls
    already made, so a failed call still reaches the ledger (I-20).
    """

    def __init__(
        self,
        code: str,
        retryable: bool,
        retry_after_s: float | None = None,
        usages: Sequence[Usage] = (),
    ):
        super().__init__(code)
        self.code: str = code
        self.retryable: bool = retryable
        self.retry_after_s: float | None = retry_after_s
        self.usages: tuple[Usage, ...] = tuple(usages)

    def __repr__(self) -> str:
        return (
            f"JobError(code={self.code!r}, retryable={self.retryable!r}, "
            f"retry_after_s={self.retry_after_s!r}, usages={len(self.usages)})"
        )
