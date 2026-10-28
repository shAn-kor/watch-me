"""Small helpers shared by the lane P handlers."""

from __future__ import annotations

from app.services.views import JobSpec, JobView


def clip_id_of(job: JobView) -> str:
    return str(job.payload.get("clip_id") or job.clip_id or "")


def session_id_of(job: JobView) -> str:
    return str(job.payload.get("session_id") or job.session_id or "")


def step_job(step: str, job: JobView) -> JobSpec:
    """The next clip step: same clip, session and dog as the current job."""
    return JobSpec(
        type=step,
        payload={
            "clip_id": clip_id_of(job),
            "session_id": job.payload.get("session_id") or job.session_id,
            "dog_id": job.payload.get("dog_id") or job.dog_id,
        },
        dog_id=job.dog_id or job.payload.get("dog_id"),
        session_id=job.session_id or job.payload.get("session_id"),
        clip_id=clip_id_of(job),
    )


def fail_clip(job: JobView, error: Exception, ctx) -> None:  # noqa: ANN001
    """`on_final_failure` of every clip step: the clip is `failed` with the code."""
    code = getattr(error, "code", "transcode_failed")
    detail = getattr(error, "detail", None)
    ctx.services.clip_pipeline_service.mark_failed(clip_id_of(job), code, detail)
