"""`merge`: session-level merge of the clip drafts (03 section 2.2 step M, 04 section 5.6)."""

from __future__ import annotations

from app.config import Settings
from app.errors import JobError
from app.pipeline.handlers._util import session_id_of
from app.pipeline.handlers.base import HandlerContext, HandlerResult
from app.services.views import JobSpec, JobView


class MergeHandler:
    job_type = "merge"

    def __init__(self, settings: Settings | None = None, timeout_s: int | None = None):
        self.timeout_s = timeout_s or (settings.merge_timeout_s if settings else 60)

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        sid = session_id_of(job)
        report = ctx.services.merge_service.merge_session(sid)
        if report.failed:
            return HandlerResult()
        return HandlerResult(
            (
                JobSpec(
                    type="check",
                    payload={"session_id": sid, "fact_ids": list(report.fact_ids)},
                    dog_id=job.dog_id,
                    session_id=sid,
                    dedupe_key=f"check:{sid}:{job.id}",
                ),
            )
        )

    def on_final_failure(self, job: JobView, error: JobError, ctx: HandlerContext) -> None:
        ctx.services.session_service.mark_failed(session_id_of(job), "merge_failed")
