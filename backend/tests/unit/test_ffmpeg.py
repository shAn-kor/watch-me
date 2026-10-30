"""UT-FFM-01..04: FFmpeg argument building and probe parsing (07 section 3.3).

No ffmpeg process runs here: a recording runner stands in for subprocess.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.pipeline.ffmpeg import (
    FFmpeg,
    FFmpegError,
    ProbeResult,
    build_frames_cmd,
    build_transcode_cmd,
    build_wav_cmd,
    parse_probe,
    sanitize_display_name,
)
from app.pipeline.sampling import frame_times


class RecordingRunner:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = ""):
        self.calls: list[tuple[list[str], float]] = []
        self.result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        self.on_call = None

    def __call__(self, argv, timeout):
        self.calls.append((list(argv), timeout))
        if self.on_call:
            self.on_call(argv)
        return self.result


def _ff(runner: RecordingRunner) -> FFmpeg:
    return FFmpeg(
        "ffmpeg",
        "ffprobe",
        probe_timeout_s=10,
        transcode_timeout_s=600,
        wav_timeout_s=180,
        frames_timeout_s=180,
        runner=runner,
    )


# ---------------------------------------------------------------- UT-FFM-01


def test_ut_ffm_01_transcode_command():
    cmd = build_transcode_cmd("ffmpeg", Path("/s/original.mov"), Path("/s/playback.mp4"))
    assert cmd[0] == "ffmpeg"
    assert "-nostdin" in cmd
    assert all(isinstance(a, str) for a in cmd)
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert cmd[cmd.index("-i") + 1] == "/s/original.mov"
    assert cmd[-1] == "/s/playback.mp4"


def test_ut_ffm_01_wav_command():
    cmd = build_wav_cmd("ffmpeg", Path("/s/original.mov"), Path("/s/audio.wav"))
    assert "-nostdin" in cmd
    assert "-vn" in cmd
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[cmd.index("-c:a") + 1] == "pcm_s16le"
    assert cmd[-1] == "/s/audio.wav"


def test_ut_ffm_01_frame_command_has_nostdin():
    cmd = build_frames_cmd("ffmpeg", Path("/s/p.mp4"), Path("/s/f/_f%05d.jpg"), k=3, count=40)
    assert "-nostdin" in cmd


def test_ut_ffm_01_timeouts_are_passed_and_argv_is_a_list():
    runner = RecordingRunner()
    ff = _ff(runner)
    ff.transcode_playback(Path("/s/o.mov"), Path("/s/p.mp4"))
    ff.extract_wav(Path("/s/o.mov"), Path("/s/a.wav"))
    (t_argv, t_timeout), (w_argv, w_timeout) = runner.calls
    assert t_timeout == 600
    assert w_timeout == 180
    assert isinstance(t_argv, list) and isinstance(w_argv, list)


def test_ut_ffm_01_failures_become_ffmpeg_errors():
    ff = _ff(RecordingRunner(returncode=1, stderr="Invalid data found"))
    with pytest.raises(FFmpegError) as exc:
        ff.transcode_playback(Path("/s/o.mov"), Path("/s/p.mp4"))
    assert exc.value.kind == "exit"
    assert exc.value.returncode == 1

    ff = _ff(RecordingRunner(returncode=-9))
    with pytest.raises(FFmpegError) as exc:
        ff.transcode_playback(Path("/s/o.mov"), Path("/s/p.mp4"))
    assert exc.value.kind == "killed"

    ff = _ff(RecordingRunner(returncode=1, stderr="x: No space left on device"))
    with pytest.raises(FFmpegError) as exc:
        ff.extract_wav(Path("/s/o.mov"), Path("/s/a.wav"))
    assert exc.value.kind == "disk_full"


# ---------------------------------------------------------------- UT-FFM-02

HEVC_JSON = {
    "streams": [
        {"codec_type": "video", "codec_name": "hevc", "width": 1080, "height": 1920,
         "duration": "8.000000"},
        {"codec_type": "audio", "codec_name": "aac", "duration": "8.020000"},
    ],
    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "8.021000"},
}
AUDIO_ONLY_JSON = {
    "streams": [{"codec_type": "audio", "codec_name": "aac", "duration": "5.0"}],
    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "5.01"},
}
NO_STREAMS_JSON = {"streams": [], "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"}}


def test_ut_ffm_02_probe_parsing_hevc():
    p = parse_probe(HEVC_JSON)
    assert isinstance(p, ProbeResult)
    assert p.video_codec == "hevc"
    assert p.has_video is True
    assert p.has_audio is True
    assert p.duration_s == pytest.approx(8.021)
    assert p.container.startswith("mov")


def test_ut_ffm_02_audio_only_has_no_video():
    p = parse_probe(AUDIO_ONLY_JSON)
    assert p.has_video is False
    assert p.has_audio is True
    assert p.video_codec is None
    assert p.duration_s == pytest.approx(5.01)


def test_ut_ffm_02_no_streams():
    p = parse_probe(NO_STREAMS_JSON)
    assert p.has_video is False
    assert p.has_audio is False
    assert p.duration_s == 0.0


def test_ut_ffm_02_probe_runs_ffprobe_with_json_output():
    import json

    runner = RecordingRunner(stdout=json.dumps(HEVC_JSON))
    p = _ff(runner).probe(Path("/s/original.mov"))
    argv, timeout = runner.calls[0]
    assert argv[0] == "ffprobe"
    assert "json" in argv
    assert argv[-1] == "/s/original.mov"
    assert timeout == 10
    assert p.has_video


def test_ut_ffm_02_probe_failure_and_garbage_raise():
    with pytest.raises(FFmpegError):
        _ff(RecordingRunner(returncode=1, stderr="Invalid data")).probe(Path("/s/x.mp4"))
    with pytest.raises(FFmpegError):
        _ff(RecordingRunner(stdout="not json")).probe(Path("/s/x.mp4"))


# ---------------------------------------------------------------- UT-FFM-03


@pytest.mark.parametrize("hostile", ["a b'; rm -rf.mov", "../../x.mov", "-i evil.mov"])
def test_ut_ffm_03_filenames_never_reach_argv(hostile: str):
    """Paths come from generated storage keys. A hostile original name is display
    data only; commands take absolute path arguments, one argv item each."""
    src = Path("/store/dogs/d1/clips/c1/original.mov")
    for cmd in (
        build_transcode_cmd("ffmpeg", src, src.with_name("playback.mp4")),
        build_wav_cmd("ffmpeg", src, src.with_name("audio.wav")),
        build_frames_cmd("ffmpeg", src, src.with_name("_f%05d.jpg"), k=1, count=5),
    ):
        assert not any(hostile in part for part in cmd)
        assert cmd[cmd.index("-i") + 1] == str(src)


def test_ut_ffm_03_relative_paths_are_made_absolute():
    cmd = build_wav_cmd("ffmpeg", Path("-weird.mov"), Path("out.wav"))
    assert not cmd[cmd.index("-i") + 1].startswith("-")
    assert Path(cmd[-1]).is_absolute()


def test_ut_ffm_03_display_name_strips_control_chars():
    assert sanitize_display_name("a b'; rm -rf.mov") == "a b'; rm -rf.mov"
    assert sanitize_display_name("bad\x00na\nme\t\x1b[0m.mov") == "badname[0m.mov"
    assert sanitize_display_name("../../x.mov") == "../../x.mov"
    assert sanitize_display_name("\x00\x01") == ""


# ---------------------------------------------------------------- UT-FFM-04


def test_ut_ffm_04_frame_command_arguments():
    cmd = build_frames_cmd("ffmpeg", Path("/s/p.mp4"), Path("/s/f/_f%05d.jpg"), k=3, count=40)
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.startswith("fps=1/3")
    assert "min(640,iw)" in vf and "min(640,ih)" in vf
    assert "force_original_aspect_ratio=decrease" in vf
    assert cmd[cmd.index("-q:v") + 1] == "5"
    assert cmd[cmd.index("-frames:v") + 1] == "40"
    assert cmd[-1] == "/s/f/_f%05d.jpg"


@pytest.mark.parametrize(("duration", "count"), [(120.0, 40), (120.5, 41)])
def test_ut_ffm_04_plan_caps_frames(duration: float, count: int):
    times = frame_times(duration)
    assert len(times) == count <= 48
    assert times[:3] == [0, 3, 6]


def test_ut_ffm_04_extract_frames_names_files_by_second_with_3_min_timeout(tmp_path: Path):
    runner = RecordingRunner()

    def make_files(argv):
        pattern = argv[-1]
        n = int(argv[argv.index("-frames:v") + 1])
        for i in range(1, n + 1):
            Path(pattern % i).write_bytes(b"\xff\xd8jpg")

    runner.on_call = make_files
    times = frame_times(120.0)
    out = tmp_path / "frames"
    files = _ff(runner).extract_frames(Path("/s/p.mp4"), times, out)
    assert [f.name for f in files][:3] == ["t0.jpg", "t3.jpg", "t6.jpg"]
    assert files[-1].name == "t117.jpg"
    assert len(files) == 40
    assert all(f.exists() for f in files)
    assert list(out.glob("_f*")) == []  # temp names are gone
    assert runner.calls[0][1] == 180


LONG_AUDIO_JSON = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920,
         "duration": "10.001667", "avg_frame_rate": "30/1", "r_frame_rate": "30/1"},
        {"codec_type": "audio", "codec_name": "aac", "duration": "10.033991"},
    ],
    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "10.033991"},
}


def test_probe_exposes_video_duration_and_frame_step():
    p = parse_probe(LONG_AUDIO_JSON)
    assert p.duration_s == pytest.approx(10.033991)  # clip duration is unchanged
    assert p.video_duration_s == pytest.approx(10.001667)
    assert p.frame_step_s == pytest.approx(1 / 30)


def test_probe_video_without_duration_or_rate_falls_back_to_none():
    p = parse_probe({
        "streams": [{"codec_type": "video", "codec_name": "h264", "avg_frame_rate": "0/0"}],
        "format": {"format_name": "mp4", "duration": "10.0"},
    })
    assert p.video_duration_s is None
    assert p.frame_step_s is None


def test_frame_times_skip_times_without_a_video_frame():
    p = parse_probe(LONG_AUDIO_JSON)
    assert len(frame_times(p.duration_s)) == 11  # old behavior asks for t=10
    times = frame_times(p.duration_s, p.video_duration_s, p.frame_step_s)
    assert times == list(range(10))


def test_frame_times_video_ending_exactly_on_a_grid_second():
    assert frame_times(10.0, 10.0, 1 / 30) == list(range(10))
    assert frame_times(10.0, None, None) == list(range(10))
    # fps unknown: a conservative default step still drops the t=10 slot
    assert frame_times(10.03, 10.0, None) == list(range(10))


def test_frame_times_keep_t0_when_video_is_very_short():
    assert frame_times(2.0, 0.5, 1 / 30) == [0]
