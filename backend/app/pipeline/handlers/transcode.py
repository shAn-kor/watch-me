"""`transcode`: probe the upload, build the playback MP4 and the 16 kHz WAV
(03 section 2.2 step T, 04 section 3, D1).

Failure mapping (the `unsupported_file` decision, see the lane P report):
- the source cannot be probed, has no video stream, or ffmpeg fails with a decode
  error, or the output is much shorter than the source (ffmpeg exits 0 on a
  truncated file): `unsupported_file`, not retryable;
- timeout, kill, disk full: `transcode_failed`, retryable;
- any other ffmpeg exit: `transcode_failed`, not retryable (retry by hand);
- playback longer than `max_clip_s + tolerance`: `too_long`, not retryable.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.config import Settings
from app.errors import JobError
from app.pipeline.ffmpeg import FFmpegError, ffmpeg_error_to_job_error
from app.pipeline.handlers._util import clip_id_of, fail_clip, step_job
from app.pipeline.handlers.base import HandlerContext, HandlerResult
from app.services.views import JobView
from app.storage.base import StorageError, StorageFull

log = logging.getLogger(__name__)

DECODE_MARKERS = (
    "invalid data found",
    "error while decoding",
    "moov atom not found",
    "decoding error",
    "could not find codec parameters",
    "invalid nal unit",
    "no such file or directory",
)
MIN_SHORTFALL_S = 1.0
SHORTFALL_RATIO = 0.10


def _fail(code: str, retryable: bool, detail: str = "") -> JobError:
    err = JobError(code, retryable)
    err.detail = detail[-280:]  # type: ignore[attr-defined]
    return err


def _is_decode_error(error: FFmpegError) -> bool:
    text = (error.detail or "").lower()
    return error.kind == "exit" and any(m in text for m in DECODE_MARKERS)


class TranscodeHandler:
    job_type = "transcode"

    def __init__(self, settings: Settings | None = None, timeout_s: int | None = None):
        self.timeout_s = timeout_s or (settings.transcode_timeout_s if settings else 600)

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        svc = ctx.services.clip_pipeline_service
        info = svc.begin_step(clip_id_of(job), "transcode")
        if info is None or not info.original_path:
            return HandlerResult()
        storage, ffmpeg, cfg = ctx.storage, ctx.ffmpeg, ctx.settings
        src = storage.open_path(info.original_path)
        playback_key = f"{info.prefix}playback.mp4"
        wav_key = f"{info.prefix}audio.wav"

        try:
            source = ffmpeg.probe(src)
        except FFmpegError as exc:
            if exc.kind in ("exit", "bad_output"):
                raise _fail("unsupported_file", False, exc.detail) from exc
            raise self._map(exc) from exc
        if not source.has_video:
            raise _fail("unsupported_file", False, "no video stream")

        work = storage.new_tmp_path()
        work.mkdir(parents=True, exist_ok=True)
        stored: list[str] = []
        try:
            playback = work / "playback.mp4"
            wav = work / "audio.wav"
            try:
                ffmpeg.transcode_playback(src, playback)
                result = ffmpeg.probe(playback)
                if source.has_audio:
                    ffmpeg.extract_wav(src, wav)
            except FFmpegError as exc:
                if _is_decode_error(exc):
                    raise _fail("unsupported_file", False, exc.detail) from exc
                raise self._map(exc) from exc

            limit = cfg.max_clip_s + cfg.clip_duration_tolerance_s
            if result.duration_s > limit + 1e-9:
                raise _fail("too_long", False, f"{result.duration_s:.1f} s")
            shortfall = max(MIN_SHORTFALL_S, SHORTFALL_RATIO * source.duration_s)
            if result.duration_s < source.duration_s - shortfall:
                raise _fail(
                    "unsupported_file",
                    False,
                    f"output {result.duration_s:.1f} s of {source.duration_s:.1f} s",
                )

            try:
                storage.put_file(playback_key, playback)
                stored.append(playback_key)
                if source.has_audio:
                    storage.put_file(wav_key, wav)
                    stored.append(wav_key)
                else:
                    storage.delete(wav_key)
            except StorageFull as exc:
                raise _fail("transcode_failed", True, "storage full") from exc
            except StorageError as exc:
                raise _fail("transcode_failed", True, str(exc)) from exc
        except BaseException:
            for key in stored:
                try:
                    storage.delete(key)
                except StorageError:
                    log.warning("could not remove partial output %s", key)
            raise
        finally:
            shutil.rmtree(Path(work), ignore_errors=True)

        svc.complete_transcode(
            info.id,
            playback_path=playback_key,
            duration_s=result.duration_s,
            container=source.container,
            codec=source.video_codec,
        )
        return HandlerResult((step_job("transcribe", job),))

    @staticmethod
    def _map(exc: FFmpegError) -> JobError:
        err = ffmpeg_error_to_job_error(exc, "transcode_failed")
        err.detail = (exc.detail or "")[-280:]  # type: ignore[attr-defined]
        return err

    def on_final_failure(self, job: JobView, error: JobError, ctx: HandlerContext) -> None:
        fail_clip(job, error, ctx)
