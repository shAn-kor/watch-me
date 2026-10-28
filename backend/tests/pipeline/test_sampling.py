"""PIPE-SMP-01..03: frame plan, segment rows, sample failure (07 section 3.15).

Real ffmpeg on generated clips (tools/make_fixtures.py, no binaries committed).
`SampleHandler` itself belongs to lane P; these tests drive the same pieces it
uses (`sampling` plan, `FFmpeg.extract_frames`, error translation) and run the
failure cases through the real `JobRunner`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.clock import FakeClock
from app.container import Container
from app.errors import JobError
from app.models import Job
from app.pipeline.ffmpeg import FFmpeg, FFmpegError, ffmpeg_error_to_job_error
from app.pipeline.handlers.base import HandlerContext, HandlerResult
from app.pipeline.runner import JobRunner
from app.pipeline.sampling import frame_times, segment_windows
from app.services.job_queue import JobQueue
from app.services.views import JobSpec, JobView
from tools.make_fixtures import build_fixture

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="needs ffmpeg and ffprobe",
)


def _real_ffmpeg() -> FFmpeg:
    return FFmpeg(shutil.which("ffmpeg"), shutil.which("ffprobe"))


def _image_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"]


# ---------------------------------------------------------------- PIPE-SMP-01


@pytest.mark.parametrize(
    ("fixture", "k", "count"),
    [
        ("len_30s.mp4", 1, 30),
        ("len_60s.mp4", 2, 30),
        ("len_120_0s.mp4", 3, 40),
        ("len_120_5s.mp4", 3, 41),
    ],
)
def test_pipe_smp_01_frame_plan(tmp_path: Path, fixture: str, k: int, count: int):
    ff = _real_ffmpeg()
    clip = build_fixture(fixture)
    duration = ff.probe(clip).duration_s
    times = frame_times(duration)
    assert len(times) == count <= 48
    assert times == [i * k for i in range(count)]

    out = tmp_path / "frames"
    files = ff.extract_frames(clip, times, out)
    assert [f.name for f in files] == [f"t{t}.jpg" for t in times]
    assert sorted(p.name for p in out.iterdir()) == sorted(f.name for f in files)
    for f in files:
        w, h = _image_size(f)
        assert max(w, h) == 640, f.name
    digests = {hashlib.sha1(f.read_bytes()).hexdigest() for f in files}
    assert len(digests) == len(files)  # each label points at a different moment


def test_pipe_smp_01_portrait_long_side_is_640(tmp_path: Path):
    ff = _real_ffmpeg()
    clip = build_fixture("hevc_8s.mov")
    times = frame_times(ff.probe(clip).duration_s)
    files = ff.extract_frames(clip, times, tmp_path / "frames")
    w, h = _image_size(files[0])
    assert h == 640 and w < h  # upright, rotation applied


# ---------------------------------------------------------------- PIPE-SMP-02


def test_pipe_smp_02_segment_rows():
    ff = _real_ffmpeg()
    clip = build_fixture("len_25s.mp4")
    duration = ff.probe(clip).duration_s
    windows = segment_windows(duration)
    assert [(w[0], w[1]) for w in windows] == [(0.0, 10.0), (10.0, 20.0), (20.0, duration)]
    assert all(end > start for start, end in windows)
    assert windows[-1][1] == pytest.approx(25.0, abs=0.05)


# ---------------------------------------------------------------- PIPE-SMP-03


def _script(path: Path, body: str) -> str:
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


class SampleStub:
    """What `SampleHandler` does with ffmpeg, minus the clip service."""

    job_type = "sample"
    timeout_s = 30

    def __init__(self, ffmpeg: FFmpeg, out: Path):
        self.ffmpeg, self.out = ffmpeg, out
        self.finals: list[JobError] = []

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        try:
            self.ffmpeg.extract_frames(Path("/nonexistent/p.mp4"), frame_times(10.0), self.out)
        except FFmpegError as exc:
            raise ffmpeg_error_to_job_error(exc) from exc
        return HandlerResult()

    def on_final_failure(self, job, error, ctx) -> None:
        self.finals.append(error)


def _run(container: Container, clock: FakeClock, engine, handler) -> tuple[JobQueue, JobRunner, int]:
    queue = JobQueue(container.uow_factory, clock)
    ctx = HandlerContext(
        settings=container.settings, storage=None, ffmpeg=None, ai=None,  # type: ignore[arg-type]
        services=container.services, clock=clock,
    )
    runner = JobRunner(queue, [handler], ctx, clock, worker_id="w1", poll_s=0.01)
    jid = queue.enqueue(JobSpec(type="sample", clip_id="c1"))
    return queue, runner, jid


def _row(engine, jid: int) -> Job:
    with Session(engine) as s:
        job = s.get(Job, jid)
        s.expunge(job)
        return job


def test_pipe_smp_03_nonzero_exit_fails_at_attempt_1(tmp_path, container, clock, engine):
    fake = _script(tmp_path / "ffmpeg", "echo boom >&2; exit 1")
    handler = SampleStub(FFmpeg(fake, "ffprobe", frames_timeout_s=5), tmp_path / "frames")
    _, runner, jid = _run(container, clock, engine, handler)
    runner.run_once()
    row = _row(engine, jid)
    assert (row.status, row.attempts) == ("failed", 1)
    assert [e.code for e in handler.finals] == ["transcode_failed"]
    assert handler.finals[0].retryable is False


def test_pipe_smp_03_timeout_is_retried_then_fails(tmp_path, container, clock, engine):
    fake = _script(tmp_path / "ffmpeg", "exec sleep 30")
    handler = SampleStub(FFmpeg(fake, "ffprobe", frames_timeout_s=1), tmp_path / "frames")
    _, runner, jid = _run(container, clock, engine, handler)
    t0 = clock.now()
    runner.run_once()
    row = _row(engine, jid)
    assert (row.status, row.attempts) == ("queued", 1)
    assert row.run_after == t0 + timedelta(seconds=30)
    clock.advance(30)
    runner.run_once()
    row = _row(engine, jid)
    assert (row.status, row.attempts) == ("failed", 2)
    assert [e.code for e in handler.finals] == ["transcode_failed"]
    # no orphan: the fake's sleep is gone
    leftover = subprocess.run(["pgrep", "-f", str(tmp_path / "ffmpeg")], check=False, capture_output=True)
    assert leftover.returncode == 1
