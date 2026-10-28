"""`purge_clip`, `purge_dog` and `retention_sweep` handlers (02 section 6, 03 section 3.3).

Files go first, then rows. Every failure is a retryable `purge_failed`."""

from __future__ import annotations

import logging

from app.config import Settings
from app.errors import JobError
from app.pipeline.handlers.base import HandlerContext, HandlerResult
from app.services.views import JobView

log = logging.getLogger(__name__)


class _PurgeBase:
    job_type = ""

    def __init__(self, settings: Settings | None = None, timeout_s: int | None = None):
        self.timeout_s = timeout_s or self._default(settings)

    def _default(self, settings: Settings | None) -> int:
        raise NotImplementedError

    def on_final_failure(self, job: JobView, error: JobError, ctx: HandlerContext) -> None:
        log.error("%s job %s failed for good: %s", self.job_type, job.id, error.code)

    def _run(self, fn, *args):
        try:
            return fn(*args)
        except JobError:
            raise
        except Exception as exc:
            log.exception("%s failed", self.job_type)
            raise JobError("purge_failed", True) from exc


class PurgeClipHandler(_PurgeBase):
    job_type = "purge_clip"

    def _default(self, settings):
        return settings.purge_clip_timeout_s if settings else 120

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        self._run(
            ctx.services.deletion_service.run_purge_clip,
            str(job.payload.get("clip_id") or job.clip_id),
            job.payload.get("dog_id") or job.dog_id,
        )
        return HandlerResult()


class PurgeDogHandler(_PurgeBase):
    job_type = "purge_dog"

    def _default(self, settings):
        return settings.purge_dog_timeout_s if settings else 300

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        self._run(
            ctx.services.deletion_service.run_purge_dog,
            str(job.payload.get("dog_id") or job.dog_id),
            job.id,
        )
        return HandlerResult()


class RetentionSweepHandler(_PurgeBase):
    job_type = "retention_sweep"

    def _default(self, settings):
        return settings.sweep_timeout_s if settings else 60

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        self._run(ctx.services.deletion_service.run_retention_sweep)
        return HandlerResult()
