"""FFmpeg wrapper: probe, transcode, extract_wav, extract_frames (06 section 3.4).

No DB, no storage. Commands are argv lists (never a shell string) and every path
is made absolute, so a file name can neither inject arguments nor be mistaken for
an option. Failures raise `FFmpegError`; `ffmpeg_error_to_job_error` is the one
translation to `JobError` that the handlers share (02 J4/J5, D2).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.errors import JobError

ErrorKind = Literal["timeout", "killed", "disk_full", "exit", "not_found", "bad_output"]

TRANSIENT_KINDS: frozenset[str] = frozenset({"timeout", "killed", "disk_full"})
FRAME_LONG_SIDE_PX = 640
FRAME_QUALITY = "5"
_TAIL = 1500


class FFmpegError(Exception):
    """A failed ffmpeg or ffprobe call. `kind` drives retry (see `transient`)."""

    def __init__(
        self,
        kind: ErrorKind | str,
        detail: str = "",
        *,
        returncode: int | None = None,
    ):
        super().__init__(f"{kind}: {detail}"[:300])
        self.kind = kind
        self.detail = detail
        self.returncode = returncode

    @property
    def transient(self) -> bool:
        """Timeout, kill, and disk full are retried (02 J4); other exits are not."""
        return self.kind in TRANSIENT_KINDS


def ffmpeg_error_to_job_error(error: FFmpegError, code: str = "transcode_failed") -> JobError:
    """06 section 3.4 / UT-JOB-14: transient kinds retry, any other exit does not.

    Only the exit text is dropped: `JobError.code` is all that is stored."""
    return JobError(code, retryable=error.transient)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    duration_s: float
    has_video: bool
    has_audio: bool
    video_codec: str | None
    container: str
    width: int | None = None
    height: int | None = None
    audio_codec: str | None = None
    # Video stream duration and one frame's length; `None` when not reported.
    video_duration_s: float | None = None
    frame_step_s: float | None = None


@dataclass(frozen=True, slots=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str], float], Any]


def run_process(argv: Sequence[str], timeout: float) -> RunResult:
    """Run `argv` without a shell. On timeout the whole process group is killed."""
    try:
        proc = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise FFmpegError("not_found", str(argv[0])) from exc
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        raise FFmpegError("timeout", f"after {timeout}s") from exc
    return RunResult(proc.returncode, out, err)


# ------------------------------------------------------------- argv builders


def _abs(path: Path | str) -> str:
    return str(Path(path).absolute())


_BASE = ("-nostdin", "-hide_banner", "-loglevel", "error", "-y")


def build_transcode_cmd(ffmpeg_bin: str, src: Path, dst: Path) -> list[str]:
    """H.264/AAC MP4, `+faststart`. Re-encoding applies the display rotation."""
    return [
        ffmpeg_bin, *_BASE, "-i", _abs(src),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-sn", "-dn", "-map_metadata", "-1",
        "-movflags", "+faststart",
        _abs(dst),
    ]  # fmt: skip


def build_wav_cmd(ffmpeg_bin: str, src: Path, dst: Path) -> list[str]:
    """16 kHz mono 16-bit PCM WAV for the Transcriber."""
    return [
        ffmpeg_bin, *_BASE, "-i", _abs(src),
        "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        _abs(dst),
    ]  # fmt: skip


def build_frames_cmd(
    ffmpeg_bin: str, src: Path, out_pattern: Path | str, *, k: int, count: int
) -> list[str]:
    """One frame every `k` seconds, long side at most 640 px (never upscaled)."""
    side = FRAME_LONG_SIDE_PX
    vf = (
        f"fps=1/{k}:eof_action=pass,"
        f"scale='min({side},iw)':'min({side},ih)':force_original_aspect_ratio=decrease"
    )
    return [
        ffmpeg_bin, *_BASE, "-i", _abs(src),
        "-an", "-vf", vf, "-frames:v", str(count), "-q:v", FRAME_QUALITY,
        _abs(out_pattern),
    ]  # fmt: skip


def parse_probe(data: dict[str, Any]) -> ProbeResult:
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    def _num(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    duration = _num(fmt.get("duration"))
    if duration is None:
        candidates = [d for s in streams if (d := _num(s.get("duration"))) is not None]
        duration = max(candidates) if candidates else 0.0
    video_duration = _num(video.get("duration")) if video else None
    if video_duration is not None and video_duration <= 0:
        video_duration = None
    frame_step = _frame_step(video) if video else None
    return ProbeResult(
        duration_s=duration,
        has_video=video is not None,
        has_audio=audio is not None,
        video_codec=video.get("codec_name") if video else None,
        container=str(fmt.get("format_name") or ""),
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
        audio_codec=audio.get("codec_name") if audio else None,
        video_duration_s=video_duration,
        frame_step_s=frame_step,
    )


def _frame_step(video: dict[str, Any]) -> float | None:
    """Seconds per video frame from `avg_frame_rate` / `r_frame_rate` ("30/1")."""
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = str(video.get(key) or "")
        num, _, den = raw.partition("/")
        try:
            rate = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            continue
        if rate > 0:
            return 1.0 / rate
    return None


def sanitize_display_name(name: str) -> str:
    """The original file name is display data only: drop control characters."""
    return "".join(ch for ch in name if ch.isprintable() or ch == " ")


# ------------------------------------------------------------------ wrapper


class FFmpeg:
    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
        *,
        probe_timeout_s: float = 10,
        transcode_timeout_s: float = 600,
        wav_timeout_s: float = 180,
        frames_timeout_s: float = 180,
        runner: Runner | None = None,
    ):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.probe_timeout_s = probe_timeout_s
        self.transcode_timeout_s = transcode_timeout_s
        self.wav_timeout_s = wav_timeout_s
        self.frames_timeout_s = frames_timeout_s
        self._run = runner or run_process

    @classmethod
    def from_settings(cls, settings: Any) -> FFmpeg:
        return cls(
            settings.ffmpeg_bin,
            settings.ffprobe_bin,
            probe_timeout_s=settings.ffprobe_timeout_s,
            transcode_timeout_s=settings.transcode_timeout_s,
            frames_timeout_s=settings.sample_timeout_s,
        )

    # -- internals

    def _exec(self, argv: list[str], timeout: float) -> Any:
        result = self._run(argv, timeout)
        if result.returncode != 0:
            tail = (result.stderr or "")[-_TAIL:]
            if "No space left on device" in tail:
                kind = "disk_full"
            elif result.returncode < 0:
                kind = "killed"
            else:
                kind = "exit"
            raise FFmpegError(kind, tail, returncode=result.returncode)
        return result

    # -- public

    def probe(self, path: Path) -> ProbeResult:
        argv = [
            self.ffprobe_bin, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", _abs(path),
        ]  # fmt: skip
        result = self._exec(argv, self.probe_timeout_s)
        try:
            data = json.loads(result.stdout)
        except (TypeError, ValueError) as exc:
            raise FFmpegError("bad_output", "ffprobe did not return JSON") from exc
        if not isinstance(data, dict):
            raise FFmpegError("bad_output", "ffprobe JSON is not an object")
        return parse_probe(data)

    def transcode_playback(self, src: Path, dst: Path) -> None:
        self._exec(build_transcode_cmd(self.ffmpeg_bin, src, dst), self.transcode_timeout_s)

    def extract_wav(self, src: Path, dst: Path) -> None:
        self._exec(build_wav_cmd(self.ffmpeg_bin, src, dst), self.wav_timeout_s)

    def extract_frames(self, src: Path, times: Sequence[int], out_dir: Path) -> list[Path]:
        """Write `t{seconds}.jpg` for each of `times` (`i * k`, one ffmpeg pass).

        Returns the files in `times` order. Temp names are renamed away; on any
        failure the partial output is removed."""
        if not times:
            return []
        k = int(times[1] - times[0]) if len(times) > 1 else 1
        out_dir.mkdir(parents=True, exist_ok=True)
        pattern = out_dir / "_f%05d.jpg"
        try:
            self._exec(
                build_frames_cmd(self.ffmpeg_bin, src, pattern, k=k, count=len(times)),
                self.frames_timeout_s,
            )
            files: list[Path] = []
            for i, t in enumerate(times, start=1):
                tmp = out_dir / f"_f{i:05d}.jpg"
                if not tmp.exists():
                    raise FFmpegError(
                        "bad_output", f"expected {len(times)} frames, got {i - 1}"
                    )
                final = out_dir / f"t{int(t)}.jpg"
                tmp.replace(final)
                files.append(final)
            return files
        except BaseException:
            for stray in out_dir.glob("_f*.jpg"):
                stray.unlink(missing_ok=True)
            for done in out_dir.glob("t*.jpg"):
                done.unlink(missing_ok=True)
            raise
