"""Handler contract (06 section 3.4). The one error type is `JobError` (app/errors.py).

`JobRunner` (lane D) claims a job, builds a `HandlerContext`, calls
`handle`, and maps the outcome: a `HandlerResult` enqueues `next_jobs` in the
same transaction as the handler's service writes; a `JobError` is retried when
`retryable` and `attempts < max_attempts`, otherwise `on_final_failure` runs
(J5, 02 section 3.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.clock import Clock
from app.config import Settings
from app.errors import JobError
from app.services.views import JobSpec, JobView
from app.storage.base import Storage


@dataclass(frozen=True, slots=True)
class HandlerResult:
    """What a successful handler hands back: the jobs to enqueue next."""

    next_jobs: tuple[JobSpec, ...] = ()


@dataclass(slots=True)
class HandlerContext:
    """Everything a handler may touch. Handlers hold no SQL: all DB work goes
    through `services` (a `Services` bundle built by the container).

    `ffmpeg` is `pipeline.ffmpeg.FFmpeg` (lane D) and `ai` is `ai.registry.AiRegistry`
    (lane C); both are typed `Any` here so Phase 0 does not depend on them.
    """

    settings: Settings
    storage: Storage
    ffmpeg: Any
    ai: Any
    services: Any
    clock: Clock
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class JobHandler(Protocol):
    job_type: str
    timeout_s: int

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        """Do the step. Raise `JobError(code, retryable)` on failure; nothing else."""
        ...

    def on_final_failure(
        self, job: JobView, error: JobError, ctx: HandlerContext
    ) -> None:
        """Final-failure hook (J5): set the clip or session fail code, and enqueue
        `merge` when the session is waiting."""
        ...
