"""Generated media for tests (07 section 2.1). No binaries are committed.

Clips come from ffmpeg `lavfi` sources into a content-hashed cache directory
(`backend/.cache/fixtures/<hash>/<key>`, or `$WATCHME_FIXTURE_CACHE`). Each build is
verified with `ffprobe`; a clip off by more than 0.05 s fails the build. The hash
covers every recipe, so a changed recipe rebuilds. Photos (Pillow) are lane S3's.

    python -m tools.make_fixtures            # build everything
    python -m tools.make_fixtures h264_5s.mp4
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

DURATION_TOLERANCE_S = 0.05
BACKEND = Path(__file__).resolve().parents[1]
FFMPEG = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"
_COMMON = ["-hide_banner", "-loglevel", "error", "-nostdin", "-y"]


def _video_src(size: str, rate: int) -> list[str]:
    return ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}"]


_SINE = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
_H264 = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]


def _mp4(seconds: float, size: str, rate: int, audio: bool = True, crf: int = 30) -> list[str]:
    args = _video_src(size, rate)
    if audio:
        args += _SINE
    args += ["-t", f"{seconds}", *_H264, "-crf", str(crf)]
    args += ["-c:a", "aac", "-b:a", "64k"] if audio else ["-an"]
    return [*args, "-movflags", "+faststart"]


# key -> (duration to verify, container format, ffmpeg args before the output path)
RECIPES: dict[str, tuple[float, str, list[str]]] = {
    "h264_5s.mp4": (5.0, "mp4", _mp4(5.0, "640x360", 25)),
    "silent_5s.mp4": (5.0, "mp4", _mp4(5.0, "640x360", 25, audio=False)),
    "len_25s.mp4": (25.0, "mp4", _mp4(25.0, "1280x720", 10, crf=42)),
    "len_30s.mp4": (30.0, "mp4", _mp4(30.0, "1280x720", 10, crf=42)),
    "len_60s.mp4": (60.0, "mp4", _mp4(60.0, "1280x720", 10, crf=42)),
    "len_120_0s.mp4": (120.0, "mp4", _mp4(120.0, "1280x720", 10, crf=42)),
    "len_120_4s.mp4": (120.4, "mp4", _mp4(120.4, "1280x720", 10, crf=42)),
    "len_120_5s.mp4": (120.5, "mp4", _mp4(120.5, "1280x720", 10, crf=42)),
    "len_120_6s.mp4": (120.6, "mp4", _mp4(120.6, "1280x720", 10, crf=42)),
    "audio_only.mp4": (
        5.0, "mp4", [*_SINE, "-t", "5.0", "-vn", "-c:a", "aac", "-b:a", "64k"],
    ),
    "legacy.avi": (
        2.0, "avi", [*_video_src("160x120", 10), "-t", "2.0", "-c:v", "mpeg4", "-an"],
    ),
}  # fmt: skip
# built by code, not by one ffmpeg call
SPECIAL = ("hevc_8s.mov", "not_video.mp4", "corrupt_trunc.mp4")
ALL_KEYS = (*RECIPES, *SPECIAL)


class FixtureError(RuntimeError):
    pass


def cache_root() -> Path:
    env = os.environ.get("WATCHME_FIXTURE_CACHE")
    return Path(env) if env else BACKEND / ".cache" / "fixtures"


def _recipe_hash() -> str:
    blob = json.dumps(
        {"recipes": dict(sorted(RECIPES.items())), "special": SPECIAL, "v": 1},
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def cache_dir() -> Path:
    return cache_root() / _recipe_hash()


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, check=False, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise FixtureError(f"{Path(args[0]).name} failed: {proc.stderr[-800:]}")


def _duration(path: Path) -> float:
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", str(path)],
        check=False, capture_output=True, text=True, timeout=30,
    )  # fmt: skip
    if proc.returncode != 0:
        raise FixtureError(f"ffprobe failed on {path.name}: {proc.stderr[-300:]}")
    return float(json.loads(proc.stdout)["format"]["duration"])


def _verify(path: Path, name: str, expected: float | None) -> None:
    if expected is None:
        return
    got = _duration(path)
    if abs(got - expected) > DURATION_TOLERANCE_S:
        raise FixtureError(f"{name}: duration {got:.3f} s, wanted {expected} s")


def _build_hevc(dst: Path) -> None:
    """360x640 portrait: a 640x360 HEVC stream with display-matrix rotation 90."""
    flat = dst.with_name(dst.name + ".flat")
    try:
        _run([
            FFMPEG, *_COMMON, *_video_src("640x360", 25), *_SINE, "-t", "8.0",
            "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-tag:v", "hvc1", "-x265-params", "log-level=error",
            "-c:a", "aac", "-b:a", "64k", "-f", "mov", str(flat),
        ])  # fmt: skip
        _run([
            FFMPEG, *_COMMON, "-display_rotation", "90", "-f", "mov", "-i", str(flat),
            "-c", "copy", "-tag:v", "hvc1", "-f", "mov", str(dst),
        ])  # fmt: skip
    finally:
        flat.unlink(missing_ok=True)


def _build_not_video(dst: Path) -> None:
    dst.write_text(("This is not a video file.\n" * 80)[:2048])


def _build_truncated(dst: Path) -> None:
    data = get("h264_5s.mp4").read_bytes()
    dst.write_bytes(data[: int(len(data) * 0.3)])


_SPECIAL_BUILDERS: dict[str, tuple[float | None, Callable[[Path], None]]] = {
    "hevc_8s.mov": (8.0, _build_hevc),
    "not_video.mp4": (None, _build_not_video),
    "corrupt_trunc.mp4": (None, _build_truncated),
}


def get(key: str) -> Path:
    """Return the cached fixture `key`, building it first when missing."""
    if key not in ALL_KEYS:
        raise KeyError(f"unknown fixture: {key}")
    out_dir = cache_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    # the cache must never be committed: it ignores itself
    guard = cache_root() / ".gitignore"
    if not guard.exists():
        guard.write_text("*\n")
    final = out_dir / key
    if final.exists():
        return final
    tmp = out_dir / f".{os.getpid()}.{key}"  # same volume, so the rename is atomic
    try:
        if key in RECIPES:
            expected, fmt, args = RECIPES[key]
            _run([FFMPEG, *_COMMON, *args, "-f", fmt, str(tmp)])
        else:
            expected, builder = _SPECIAL_BUILDERS[key]
            builder(tmp)
        _verify(tmp, key, expected)
        tmp.replace(final)
    finally:
        tmp.unlink(missing_ok=True)
    return final


build_fixture = get


def build_all() -> dict[str, Path]:
    return {key: get(key) for key in ALL_KEYS}


def main(argv: list[str]) -> int:
    for key in argv or list(ALL_KEYS):
        print(get(key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
