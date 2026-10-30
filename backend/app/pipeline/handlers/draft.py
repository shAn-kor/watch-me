"""`draft`: ask the model for facts and store them as unmerged drafts
(03 section 2.2 step D, 04 sections 4 and 5).

A clip under 1 s has no frames: no model call, the clip becomes `ready` with zero
facts. After a stored draft the original, WAV and frames are removed (I-17).
"""

from __future__ import annotations

from app.ai.errors import AiError, to_job_error
from app.ai.prompts import PROMPT_VERSION
from app.ai.types import (
    DraftFrame,
    DraftOutput,
    DraftRequest,
    DraftSegment,
    TranscriptSegmentOut,
)
from app.config import Settings
from app.errors import JobError
from app.pipeline import sampling
from app.pipeline.handlers._util import clip_id_of, fail_clip
from app.pipeline.handlers.base import HandlerContext, HandlerResult
from app.services.views import JobView


class DraftHandler:
    job_type = "draft"

    def __init__(self, settings: Settings | None = None, timeout_s: int | None = None):
        self.timeout_s = timeout_s or (settings.draft_timeout_s if settings else 180)

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        svc = ctx.services.clip_pipeline_service
        pipeline_ctx = svc.draft_context(clip_id_of(job))
        if pipeline_ctx is None:
            return HandlerResult()
        info = pipeline_ctx.info
        if svc.begin_step(info.id, "draft") is None:
            return HandlerResult()
        mode = ctx.settings.draft_mode
        grid = sampling.frame_times(info.duration_s)
        k = sampling.frame_interval(info.duration_s)
        ingest = ctx.services.draft_ingest_service

        if not grid:
            ingest.store_drafts(
                clip_id=info.id,
                output=DraftOutput(facts=[]),
                usages=[],
                mode=mode,
                k=k,
                ai_model=f"none@{PROMPT_VERSION}",
            )
            svc.cleanup_derivatives(info.id)
            return HandlerResult()

        frames_prefix = f"{info.prefix}frames"
        # `sample` drops grid times past the last video frame (audio longer than
        # video), so the frames to use are the leading grid times that exist.
        times = []
        for t in grid:
            if not ctx.storage.exists(f"{frames_prefix}/t{t}.jpg"):
                break
            times.append(t)
        if not times or any(
            ctx.storage.exists(f"{frames_prefix}/t{t}.jpg") for t in grid[len(times) :]
        ):
            raise JobError("transcode_failed", False)
        windows = pipeline_ctx.segments
        frames = []
        for t in times:
            ref = None
            if mode == "segments":
                for idx, start, end in windows:
                    if start <= t < end or (t >= end and idx == windows[-1][0]):
                        ref = f"c{info.ordinal}-seg{idx}"
                        break
            frames.append(
                DraftFrame(
                    t=t,
                    path=str(ctx.storage.open_path(f"{frames_prefix}/t{t}.jpg")),
                    segment_ref=ref,
                )
            )
        segments = []
        if mode == "segments":
            for idx, start, end in windows:
                ref = f"c{info.ordinal}-seg{idx}"
                segments.append(
                    DraftSegment(
                        ref=ref,
                        start_s=start,
                        end_s=end,
                        frame_ts=[f.t for f in frames if f.segment_ref == ref],
                    )
                )
        req = DraftRequest(
            mode=mode,
            clip_ord=info.ordinal,
            duration_s=info.duration_s,
            k=k,
            frames=frames,
            segments=segments,
            transcript=[
                TranscriptSegmentOut(seq=seq, start_s=s, end_s=e, text=text)
                for seq, s, e, text in pipeline_ctx.transcript
            ],
            allowed_situations=list(info.situations),
            dog_name=info.dog_name,
            observed_on=info.observed_on,
            max_facts=8,
            fixture_key=info.fixture_key,
        )
        try:
            output, usages = ctx.ai.drafter.draft(req)
        except AiError as exc:
            raise to_job_error(exc, "draft") from exc
        model = usages[0].model if usages else "unknown"
        ingest.store_drafts(
            clip_id=info.id,
            output=output,
            usages=usages,
            mode=mode,
            k=k,
            ai_model=f"{model}@{PROMPT_VERSION}",
        )
        svc.cleanup_derivatives(info.id)
        return HandlerResult()

    def on_final_failure(self, job: JobView, error: JobError, ctx: HandlerContext) -> None:
        fail_clip(job, error, ctx)
