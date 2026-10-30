"""`sample`: frames on the 1-per-k-seconds grid and the fixed 10 s segment rows
(03 section 2.2 step S, 04 sections 4.1 and 4.6).

The step clears its own earlier output first, so a manual retry leaves no stale
frame behind (C6) and the segment rows are replaced, not duplicated.
"""

from __future__ import annotations

from app.config import Settings
from app.errors import JobError
from app.pipeline import sampling
from app.pipeline.ffmpeg import FFmpegError, ffmpeg_error_to_job_error
from app.pipeline.handlers._util import (
    clip_frame_times,
    clip_id_of,
    fail_clip,
    step_job,
)
from app.pipeline.handlers.base import HandlerContext, HandlerResult
from app.services.views import JobView


class SampleHandler:
    job_type = "sample"

    def __init__(self, settings: Settings | None = None, timeout_s: int | None = None):
        self.timeout_s = timeout_s or (settings.sample_timeout_s if settings else 180)

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        svc = ctx.services.clip_pipeline_service
        info = svc.begin_step(clip_id_of(job), "sample")
        if info is None:
            return HandlerResult()
        source_key = info.playback_path or info.original_path
        if not source_key or not ctx.storage.exists(source_key):
            raise JobError("transcode_failed", False)
        frames_prefix = f"{info.prefix}frames"
        ctx.storage.delete_prefix(f"{frames_prefix}/")
        times = clip_frame_times(ctx, info)
        if times:
            try:
                ctx.ffmpeg.extract_frames(
                    ctx.storage.open_path(source_key), times, ctx.storage.open_path(frames_prefix)
                )
            except FFmpegError as exc:
                err = ffmpeg_error_to_job_error(exc, "transcode_failed")
                err.detail = (exc.detail or "")[-280:]  # type: ignore[attr-defined]
                raise err from exc
        svc.save_segments(info.id, sampling.segment_plan(info.duration_s, info.ordinal))
        return HandlerResult((step_job("draft", job),))

    def on_final_failure(self, job: JobView, error: JobError, ctx: HandlerContext) -> None:
        fail_clip(job, error, ctx)
