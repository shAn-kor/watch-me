"""`transcribe`: speech to text for clips that have audio (03 section 2.2 step A, 04 section 3).

A clip without a WAV (silent video) skips the call and writes no ledger row.
"""

from __future__ import annotations

from app.ai.errors import AiError, to_job_error
from app.ai.types import TranscribeRequest
from app.config import Settings
from app.errors import JobError
from app.pipeline.handlers._util import clip_id_of, fail_clip, step_job
from app.pipeline.handlers.base import HandlerContext, HandlerResult
from app.services.views import JobView


class TranscribeHandler:
    job_type = "transcribe"

    def __init__(self, settings: Settings | None = None, timeout_s: int | None = None):
        self.timeout_s = timeout_s or (settings.transcribe_timeout_s if settings else 180)

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        svc = ctx.services.clip_pipeline_service
        info = svc.begin_step(clip_id_of(job), "transcribe")
        if info is None:
            return HandlerResult()
        wav_key = f"{info.prefix}audio.wav"
        if info.has_audio and ctx.storage.exists(wav_key):
            req = TranscribeRequest(
                audio_path=str(ctx.storage.open_path(wav_key)),
                duration_s=info.duration_s,
                lang_hint="auto",
                keywords=[info.dog_name] if info.dog_name else [],
                fixture_key=info.fixture_key,
            )
            try:
                result, usages = ctx.ai.transcriber.transcribe(req)
            except AiError as exc:
                raise to_job_error(exc, "transcribe") from exc
            svc.save_transcript(info.id, result, usages, info.dog_id, info.session_id)
        return HandlerResult((step_job("sample", job),))

    def on_final_failure(self, job: JobView, error: JobError, ctx: HandlerContext) -> None:
        fail_clip(job, error, ctx)
