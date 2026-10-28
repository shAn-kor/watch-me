"""`check`: model wording check, then the session becomes `review_ready`
(03 section 2.2 step W, 04 section 6.3). A check never fails a session (D2)."""

from __future__ import annotations

from app.config import Settings
from app.errors import JobError
from app.pipeline.handlers._util import session_id_of
from app.pipeline.handlers.base import HandlerContext, HandlerResult
from app.services.views import JobView


class CheckHandler:
    job_type = "check"

    def __init__(self, settings: Settings | None = None, timeout_s: int | None = None):
        self.timeout_s = timeout_s or (settings.check_timeout_s if settings else 180)

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        sid = session_id_of(job)
        fact_ids = list(job.payload.get("fact_ids") or [])
        ctx.services.wording_service.apply_model_flags(sid, fact_ids, ctx.ai.checker)
        ctx.services.session_service.mark_review_ready(sid)
        return HandlerResult()

    def on_final_failure(self, job: JobView, error: JobError, ctx: HandlerContext) -> None:
        sid = session_id_of(job)
        ctx.services.wording_service.mark_check_unavailable(
            sid, list(job.payload.get("fact_ids") or [])
        )
        ctx.services.session_service.mark_review_ready(sid)
