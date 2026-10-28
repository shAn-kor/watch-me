"""JobRunner: poll, claim, dispatch, timeout, outcome mapping, stale reset
(06 section 3.4, 02 section 3.5, 04 section 8.8).

The runner holds no SQL: every state change goes through `JobQueue`.

Outcome table
- handler returns            -> `queue.complete(next_jobs)` (J3)
- `JobError(retryable=True)` -> requeue with backoff while `attempts < max_attempts` (J4)
- otherwise                  -> `failed`, then `handler.on_final_failure(code)` (J5)
- timeout                    -> `JobError(step code, retryable=True)`
- any other exception        -> `JobError(step code, retryable=False)`, logged with a
  traceback (06 M31, open proposal). The job row stores only the code.

A timed-out handler thread cannot be killed from Python. Handlers that start
processes (ffmpeg) bound them with their own timeout, so the thread ends soon after.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from app.clock import Clock
from app.errors import JobError
from app.pipeline.handlers.base import HandlerContext, HandlerResult, JobHandler
from app.services.job_queue import JobQueue
from app.services.views import JobSpec, JobView

log = logging.getLogger(__name__)

# The fail code a step reports when the handler cannot say (timeout, unknown bug).
STEP_FAIL_CODE: dict[str, str] = {
    "transcode": "transcode_failed",
    "transcribe": "ai_failed",
    "sample": "transcode_failed",
    "draft": "ai_failed",
    "merge": "merge_failed",
    "check": "ai_failed",
    "purge_clip": "purge_failed",
    "purge_dog": "purge_failed",
    "retention_sweep": "purge_failed",
}
STALE_CHECK_EVERY_S = 60.0


class JobRunner:
    def __init__(
        self,
        queue: JobQueue,
        handlers: Iterable[JobHandler] | Mapping[str, JobHandler],
        ctx: HandlerContext,
        clock: Clock,
        *,
        worker_id: str = "worker-1",
        poll_s: float = 2.0,
    ):
        self.queue = queue
        self.handlers: dict[str, JobHandler] = (
            dict(handlers)
            if isinstance(handlers, Mapping)
            else {h.job_type: h for h in handlers}
        )
        self.ctx = ctx
        self.clock = clock
        self.worker_id = worker_id
        self.poll_s = poll_s
        self._last_sweep_date: str | None = None

    # ------------------------------------------------------------- one job

    def run_once(self) -> bool:
        """Claim and run one due job. `False` when nothing is due."""
        job = self.queue.claim(self.worker_id)
        if job is None:
            return False
        self.execute(job)
        return True

    def execute(self, job: JobView) -> None:
        handler = self.handlers.get(job.type)
        if handler is None:
            log.error("no handler registered for job type %s (job %s)", job.type, job.id)
            self.queue.fail(
                job.id, JobError(self._step_code(job.type), False), text="no_handler"
            )
            return
        try:
            result = self._call_with_timeout(handler, job)
        except JobError as error:
            self._map_error(handler, job, error)
        except FutureTimeout:
            log.warning("job %s (%s) timed out after %ss", job.id, job.type, handler.timeout_s)
            self._map_error(
                handler, job, JobError(self._step_code(job.type), True), text="timeout"
            )
        except Exception:
            log.exception("job %s (%s) raised an unexpected error", job.id, job.type)
            self._map_error(
                handler,
                job,
                JobError(self._step_code(job.type), False),
                text="internal_error",
            )
        else:
            self.queue.complete(job.id, result.next_jobs)

    def _call_with_timeout(self, handler: JobHandler, job: JobView) -> HandlerResult:
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"job-{job.id}")
        future = pool.submit(handler.handle, job, self.ctx)
        try:
            return future.result(timeout=handler.timeout_s)
        finally:
            pool.shutdown(wait=False)

    @staticmethod
    def _step_code(job_type: str) -> str:
        return STEP_FAIL_CODE.get(job_type, "internal_error")

    def _map_error(
        self, handler: JobHandler, job: JobView, error: JobError, *, text: str | None = None
    ) -> None:
        self._record_usages(job, error)
        outcome = self.queue.fail(job.id, error, text=text)
        if outcome == "failed":
            self._final_failure(handler, job, error)

    def _record_usages(self, job: JobView, error: JobError) -> None:
        """A failed call is still billed (03 E26, I-20)."""
        if not error.usages:
            return
        cost = getattr(self.ctx.services, "cost_service", None)
        if cost is None:
            return
        try:
            cost.record_usages_independent(error.usages, job.dog_id, job.session_id)
        except Exception:
            log.exception("could not write ledger rows of failed job %s", job.id)

    def _final_failure(self, handler: JobHandler, job: JobView, error: JobError) -> None:
        try:
            handler.on_final_failure(job, error, self.ctx)
        except Exception:
            log.exception("on_final_failure of job %s (%s) raised", job.id, job.type)

    # --------------------------------------------------------------- stale

    def reset_stale(self) -> int:
        """J6: requeue or fail running jobs whose lock is older than the limit."""
        failed = self.queue.reset_stale()
        for job in failed:
            handler = self.handlers.get(job.type)
            if handler is not None:
                error = JobError(self._step_code(job.type), True)
                self._final_failure(handler, job, error)
        return len(failed)

    # ---------------------------------------------------------------- loop

    def _enqueue_daily_sweep(self) -> None:
        if "retention_sweep" not in self.handlers:
            return
        today = self.clock.now().date().isoformat()
        if today == self._last_sweep_date:
            return
        self.queue.enqueue(JobSpec(type="retention_sweep", dedupe_key=f"sweep:{today}"))
        self._last_sweep_date = today

    def run_forever(self, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        last_stale = float("-inf")
        while not stop.is_set():
            now = time.monotonic()
            try:
                if now - last_stale >= STALE_CHECK_EVERY_S:
                    self.reset_stale()
                    self._enqueue_daily_sweep()
                    last_stale = now
                if self.run_once():
                    continue
            except Exception:
                log.exception("job runner loop error")
            stop.wait(self.poll_s)
