"""Frame and segment plans for the `sample` step (04 section 4.1, 4.6).

TODO(lane-a): use domain.ranges `frame_interval` and `segment_windows` once lane A
merges. These private copies follow 07 UT-RNG-02 and UT-RNG-03 and have the same
signatures in spirit, so the swap is an import change.
"""

from __future__ import annotations

import math

FRAME_MAX_COUNT = 48
SEGMENT_LEN_S = 10
SEGMENT_MIN_LAST_S = 3.0
MIN_FRAME_CLIP_S = 1.0


def frame_interval(duration_s: float, max_frames: int = FRAME_MAX_COUNT) -> int:
    """`k = max(1, ceil(duration / max_frames))` seconds."""
    return max(1, math.ceil(duration_s / max_frames))


def frame_times(duration_s: float, max_frames: int = FRAME_MAX_COUNT) -> list[int]:
    """`t_i = i * k` for `i = 0 .. ceil(duration / k) - 1`; empty under 1 s (D4)."""
    if duration_s < MIN_FRAME_CLIP_S:
        return []
    k = frame_interval(duration_s, max_frames)
    count = min(max_frames, math.ceil(duration_s / k))
    return [i * k for i in range(count)]


def segment_windows(
    duration_s: float,
    seg_len_s: float = SEGMENT_LEN_S,
    min_last_s: float = SEGMENT_MIN_LAST_S,
) -> list[tuple[float, float]]:
    """Fixed windows of `seg_len_s`; a last window under `min_last_s` merges into the
    previous one. The last `end_s` is the clip duration."""
    if duration_s <= 0:
        return []
    windows: list[tuple[float, float]] = []
    start = 0.0
    while start < duration_s:
        end = min(start + seg_len_s, duration_s)
        windows.append((start, end))
        start = end
    if len(windows) > 1 and windows[-1][1] - windows[-1][0] < min_last_s:
        last = windows.pop()
        windows[-1] = (windows[-1][0], last[1])
    return windows
