"""Adapter-internal exceptions and the boundary conversion to `JobError`
(04 sections 2, 8.7, 8.8; 06 section 3.3).

The classes are frozen in Phase 0. `to_job_error` is implemented by lane C.
"""

from __future__ import annotations

from typing import Literal

from app.ai.types import Usage
from app.errors import JobError

Purpose = Literal["transcribe", "draft", "check", "qa_select", "spike"]


class AiError(Exception):
    """Base of adapter-internal errors. Never leaves the adapter: public methods
    convert it with `to_job_error`."""

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_s: float | None = None,
        usages: list[Usage] | None = None,
    ):
        super().__init__(message)
        self.retry_after_s: float | None = retry_after_s
        self.usages: list[Usage] = list(usages or [])


class AiTransientError(AiError):
    """Network, timeout, HTTP 429, 5xx."""


class AiPermanentError(AiError):
    """HTTP 400, 401, 402, 403, 404, content policy, malformed ASR body."""


class AiInvalidOutput(AiError):
    """Schema-invalid output after the one in-adapter retry, length, refusal."""


def to_job_error(error: AiError, purpose: Purpose) -> JobError:
    """Map an `AiError` to the worker-facing `JobError` (D2):

    - `AiTransientError` -> `JobError("ai_failed", retryable=True, retry_after_s=...)`
    - `AiPermanentError` -> `JobError("ai_failed", retryable=False)`
    - `AiInvalidOutput` -> `JobError("ai_invalid_output", False)` for `draft`,
      `JobError("ai_failed", False)` for `transcribe`, `check`, `select`.

    `JobError.usages` carries `error.usages`.
    """
    # AiInvalidOutput text is `error_summary` output: locs and reasons such as
    # "finish_reason=length", never input values. A length cutoff stays diagnosable.
    detail = (
        str(error)[:200]
        if isinstance(error, (AiTransientError, AiPermanentError, AiInvalidOutput))
        else ""
    )
    job_error = _to_job_error(error, purpose)
    if detail:
        # Status and provider code ("HTTP 401 invalid_api_key") or the invalid-output reason; the failure
        # hook stores it in `clip.fail_detail`, and the metrics alert reads it.
        job_error.detail = detail  # type: ignore[attr-defined]
    return job_error


def _to_job_error(error: AiError, purpose: Purpose) -> JobError:
    if isinstance(error, AiTransientError):
        return JobError("ai_failed", True, error.retry_after_s, error.usages)
    if isinstance(error, AiInvalidOutput) and purpose == "draft":
        return JobError("ai_invalid_output", False, None, error.usages)
    # AiPermanentError, AiInvalidOutput for the other purposes, and a bare AiError
    return JobError("ai_failed", False, None, error.usages)
