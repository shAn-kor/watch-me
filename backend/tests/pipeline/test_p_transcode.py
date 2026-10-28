"""PIPE-TRC-01..09 and the handler half of PIPE-SMP-01..03 (07 section 3.15).

Real ffmpeg, mock AI. The runner is the real worker (`app.worker.build_runner`).
"""

from __future__ import annotations

import json
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest

from tests.pipeline.pipe_support import (
    FFMPEG_BIN,
    FFPROBE_BIN,
    FaultyStorage,
    csrf,
    count_running,
    write_script,
)
from app.pipeline.ffmpeg import FFmpeg
from app.storage.local import LocalStorage


def _ffprobe(path: Path) -> dict:
    out = subprocess.run(
        [FFPROBE_BIN, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return json.loads(out)


def _one_clip(env, media, **kw):
    _, _, vol, dog = env.world()
    sess = env.session(dog, vol)
    return env.add_clip(sess, media, **kw), sess


def _run_steps(env, n):
    for _ in range(n):
        assert env.run_step()


# ---------------------------------------------------------------- PIPE-TRC-01


def test_pipe_trc_01_hevc_mov_becomes_upright_h264(env):
    clip, _ = _one_clip(env, "hevc_8s.mov")
    _run_steps(env, 1)  # transcode only
    row = env.clip(clip.id)
    assert row.status == "processing" and row.step == "transcode"
    assert row.playback_path == f"dogs/{clip.dog_id}/clips/{clip.id}/playback.mp4"
    path = env.storage.open_path(row.playback_path)
    info = _ffprobe(path)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
    assert audio["codec_name"] == "aac"
    assert video["width"] < video["height"]  # display rotation applied
    data = path.read_bytes()
    assert 0 <= data.find(b"moov") < data.find(b"mdat")  # faststart
    assert float(info["format"]["duration"]) == pytest.approx(8.0, abs=0.2)
    assert row.duration_s == pytest.approx(8.0, abs=0.2)


# ---------------------------------------------------------------- PIPE-TRC-02


def test_pipe_trc_02_h264_playback_and_16k_mono_wav(env):
    clip, _ = _one_clip(env, "h264_5s.mp4")
    _run_steps(env, 1)
    row = env.clip(clip.id)
    info = _ffprobe(env.storage.open_path(row.playback_path))
    assert {s["codec_name"] for s in info["streams"]} == {"h264", "aac"}
    wav = _ffprobe(env.storage.open_path(f"{env.clip_prefix(clip)}audio.wav"))
    stream = wav["streams"][0]
    assert (stream["sample_rate"], stream["channels"], stream["codec_name"]) == (
        "16000",
        1,
        "pcm_s16le",
    )
    assert [j.type for j in env.jobs(status="queued")] == ["transcribe"]


# ---------------------------------------------------------------- PIPE-TRC-03


def test_pipe_trc_03_silent_clip_has_no_wav_and_no_transcript(env):
    clip, _ = _one_clip(env, "silent_5s.mp4")
    _run_steps(env, 2)  # transcode, transcribe
    assert not env.storage.exists(f"{env.clip_prefix(clip)}audio.wav")
    assert env.transcript(clip.id) == []
    assert env.spy("transcriber").calls["transcribe"] == []
    assert env.ledger("transcribe") == []
    assert [j.type for j in env.jobs(status="queued")] == ["sample"]
    assert env.clip(clip.id).status == "processing"


# ---------------------------------------------------------------- PIPE-TRC-04


def test_pipe_trc_04_truncated_media_is_unsupported_file(env):
    clip, _ = _one_clip(env, "corrupt_trunc.mp4")
    _run_steps(env, 1)
    row = env.clip(clip.id)
    assert (row.status, row.fail_code, row.step) == (
        "failed",
        "unsupported_file",
        "transcode",
    )
    job = env.jobs("transcode")[0]
    assert (job.status, job.attempts) == ("failed", 1)
    assert not env.run_step()  # no second attempt
    # not retryable: the API answers 409 invalid_state
    with env.api(env.seed_member) as (client, token):
        r = client.post(f"/api/clips/{clip.id}/retry", json={}, headers=csrf(token))
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"


def test_pipe_trc_04_error_view_is_not_retryable(env):
    clip, sess = _one_clip(env, "corrupt_trunc.mp4")
    _run_steps(env, 1)
    with env.api(env.seed_member) as (client, _):
        body = client.get(f"/api/sessions/{sess.id}?include=none").json()
    errors = [c["error"] for c in body["clips"] if c["id"] == clip.id]
    assert errors[0]["retryable"] is False


# ---------------------------------------------------------------- PIPE-TRC-05


def _real_wrapper(tmp_path: Path, body: str) -> str:
    return write_script(tmp_path / "ffmpeg", body.replace("REAL", FFMPEG_BIN))


def test_pipe_trc_05_encoder_exit_one_fails_at_once_but_is_retryable_by_hand(
    tmp_path, make_env
):
    fake = _real_wrapper(tmp_path, "echo 'boom: encoder crashed' >&2; exit 1")
    env = make_env(ffmpeg=FFmpeg(fake, FFPROBE_BIN))
    clip, _ = _one_clip(env, "h264_5s.mp4")
    _run_steps(env, 1)
    row = env.clip(clip.id)
    assert (row.status, row.fail_code) == ("failed", "transcode_failed")
    job = env.jobs("transcode")[0]
    assert (job.status, job.attempts) == ("failed", 1)
    with env.api(env.seed_member) as (client, token):
        # manual retry is allowed for transcode_failed
        r = client.post(f"/api/clips/{clip.id}/retry", json={}, headers=csrf(token))
    assert r.status_code == 200


def test_pipe_trc_05_sigkill_is_transient_and_retried(tmp_path, make_env):
    counter = tmp_path / "count"
    fake = _real_wrapper(
        tmp_path,
        f'if [ ! -f "{counter}" ]; then echo 1 > "{counter}"; kill -9 $$; fi\nexec REAL "$@"',
    )
    env = make_env(ffmpeg=FFmpeg(fake, FFPROBE_BIN))
    clip, _ = _one_clip(env, "h264_5s.mp4")
    t0 = env.clock.now()
    _run_steps(env, 1)
    job = env.jobs("transcode")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    assert job.run_after == t0 + timedelta(seconds=30)
    assert not env.run_step()
    env.advance(30)
    _run_steps(env, 1)
    assert env.jobs("transcode")[0].status == "succeeded"
    assert env.clip(clip.id).playback_path is not None


def test_pipe_trc_05_killed_twice_fails_after_two_attempts(tmp_path, make_env):
    fake = _real_wrapper(tmp_path, "kill -9 $$")
    env = make_env(ffmpeg=FFmpeg(fake, FFPROBE_BIN))
    clip, _ = _one_clip(env, "h264_5s.mp4")
    _run_steps(env, 1)
    env.advance(30)
    _run_steps(env, 1)
    job = env.jobs("transcode")[0]
    assert (job.status, job.attempts) == ("failed", 2)
    assert (env.clip(clip.id).status, env.clip(clip.id).fail_code) == (
        "failed",
        "transcode_failed",
    )


# ---------------------------------------------------------------- PIPE-TRC-06


def test_pipe_trc_06_timeout_retried_once_then_failed_no_orphan(tmp_path, make_env):
    fake = write_script(tmp_path / "ffmpeg", "exec sleep 30")
    env = make_env(
        ffmpeg=FFmpeg(fake, FFPROBE_BIN, transcode_timeout_s=1), transcode_timeout_s=60
    )
    clip, _ = _one_clip(env, "h264_5s.mp4")
    _run_steps(env, 1)
    job = env.jobs("transcode")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    env.advance(30)
    _run_steps(env, 1)
    job = env.jobs("transcode")[0]
    assert (job.status, job.attempts) == ("failed", 2)
    assert env.clip(clip.id).fail_code == "transcode_failed"
    assert count_running(str(tmp_path / "ffmpeg")) == 0


# ---------------------------------------------------------------- PIPE-TRC-07


def test_pipe_trc_07_disk_full_is_transient_then_transcode_failed(settings, make_env):
    storage = FaultyStorage(LocalStorage(settings.storage_root))
    env = make_env(storage=storage)
    clip, _ = _one_clip(env, "h264_5s.mp4")
    storage.full_on_put_suffix = "playback.mp4"
    _run_steps(env, 1)
    job = env.jobs("transcode")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    env.advance(30)
    _run_steps(env, 1)
    job = env.jobs("transcode")[0]
    assert (job.status, job.attempts) == ("failed", 2)
    row = env.clip(clip.id)
    assert (row.status, row.fail_code, row.playback_path) == (
        "failed",
        "transcode_failed",
        None,
    )
    assert not any(
        k.endswith("playback.mp4") for k in env.clip_keys(clip)
    )  # partial output removed
    assert env.storage.list_prefix("tmp") == []


# ---------------------------------------------------------------- PIPE-TRC-08


def test_pipe_trc_08_too_long_after_reprobe(tmp_path, make_env):
    counter = tmp_path / "n"
    code = (
        "import json,sys;d=json.load(sys.stdin);"
        "d['format']['duration']='120.8';"
        "[s.__setitem__('duration','120.8') for s in d['streams']];"
        "print(json.dumps(d))"
    )
    fake = write_script(
        tmp_path / "ffprobe",
        f'n=$(cat "{counter}" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "{counter}"\n'
        f'if [ "$n" -ge 2 ]; then {FFPROBE_BIN} "$@" | "{__import__("sys").executable}" -c "{code}"; '
        f'else exec {FFPROBE_BIN} "$@"; fi',
    )
    env = make_env(ffmpeg=FFmpeg(FFMPEG_BIN, fake))
    clip, _ = _one_clip(env, "len_120_4s.mp4")
    _run_steps(env, 1)
    row = env.clip(clip.id)
    assert (row.status, row.fail_code) == ("failed", "too_long")
    job = env.jobs("transcode")[0]
    assert (job.status, job.attempts) == ("failed", 1)


# ---------------------------------------------------------------- PIPE-TRC-09


@pytest.mark.xfail(
    reason="the media route (Range, 206) is lane S5 and is not in this branch",
    strict=False,
)
def test_pipe_trc_09_playback_served_with_range(env):
    clip, _ = _one_clip(env, "h264_5s.mp4")
    _run_steps(env, 1)
    with env.api(env.seed_member) as (client, _):
        r = client.get(f"/media/clips/{clip.id}", headers={"Range": "bytes=0-99"})
        assert r.status_code == 206 and len(r.content) == 100
        r = client.get(f"/media/clips/{clip.id}", headers={"Range": "bytes=1000-1099"})
        assert r.status_code == 206


# ----------------------------------------------------------- PIPE-SMP (handler)


@pytest.mark.parametrize(
    ("media", "k", "count"),
    [
        ("len_30s.mp4", 1, 30),
        ("len_60s.mp4", 2, 30),
        ("len_120_0s.mp4", 3, 40),
        ("len_120_5s.mp4", 3, 41),
    ],
)
def test_pipe_smp_01_sample_handler_writes_frames(env, media, k, count):
    clip, _ = _one_clip(env, media)
    for _ in range(3):  # transcode, transcribe, sample
        assert env.run_step()
    keys = [x for x in env.clip_keys(clip) if "/frames/" in x]
    assert len(keys) == count <= 48
    prefix = f"{env.clip_prefix(clip)}frames/"
    assert sorted(keys) == sorted(f"{prefix}t{i * k}.jpg" for i in range(count))
    long_side = max(
        _ffprobe(env.storage.open_path(keys[0]))["streams"][0][d]
        for d in ("width", "height")
    )
    assert long_side == 640
    assert [j.type for j in env.jobs(status="queued")] == ["draft"]


def test_pipe_smp_02_sample_handler_writes_segment_rows(env):
    clip, _ = _one_clip(env, "len_25s.mp4")
    for _ in range(3):
        assert env.run_step()
    rows = [(s.idx, s.start_s, s.end_s) for s in env.segments(clip.id)]
    duration = env.clip(clip.id).duration_s
    assert [(r[1], r[2]) for r in rows[:2]] == [(0.0, 10.0), (10.0, 20.0)]
    assert rows[2][1] == 20.0 and rows[2][2] == pytest.approx(duration, abs=0.05)
    assert all(end > start for _, start, end in rows)
    assert [r[0] for r in rows] == [1, 2, 3]


def _seed_at_sample(env, tmp_path: Path):
    """A clip whose transcode is done: playback stored, `sample` queued."""
    _, _, vol, dog = env.world()
    sess = env.session(dog, vol)
    clip = env.add_clip(sess, "h264_5s.mp4", enqueue=False)
    key = f"{env.clip_prefix(clip)}playback.mp4"
    env.storage.put_file(
        key, __import__("tools.make_fixtures", fromlist=["get"]).get("h264_5s.mp4")
    )
    from sqlalchemy import update

    from app.models import Clip

    with env.db() as s:
        s.execute(
            update(Clip)
            .where(Clip.id == clip.id)
            .values(playback_path=key, status="processing", step="transcribe")
        )
        s.commit()
    env.enqueue_step(clip, "sample")
    return clip


def test_pipe_smp_03_nonzero_exit_fails_at_attempt_one(tmp_path, make_env):
    fake = write_script(tmp_path / "ffmpeg", "echo boom >&2; exit 1")
    env = make_env(ffmpeg=FFmpeg(fake, FFPROBE_BIN))
    clip = _seed_at_sample(env, tmp_path)
    assert env.run_step()
    job = env.jobs("sample")[0]
    assert (job.status, job.attempts) == ("failed", 1)
    row = env.clip(clip.id)
    assert (row.status, row.fail_code, row.step) == (
        "failed",
        "transcode_failed",
        "sample",
    )


def test_pipe_smp_03_timeout_is_retried_then_fails(tmp_path, make_env):
    fake = write_script(tmp_path / "ffmpeg", "exec sleep 30")
    env = make_env(
        ffmpeg=FFmpeg(fake, FFPROBE_BIN, frames_timeout_s=1), sample_timeout_s=60
    )
    clip = _seed_at_sample(env, tmp_path)
    assert env.run_step()
    job = env.jobs("sample")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    env.advance(30)
    assert env.run_step()
    job = env.jobs("sample")[0]
    assert (job.status, job.attempts) == ("failed", 2)
    assert env.clip(clip.id).fail_code == "transcode_failed"
    assert count_running(str(tmp_path / "ffmpeg")) == 0
