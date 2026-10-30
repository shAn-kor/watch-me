"""Frame and segment plans for the `sample` step (04 section 4.1, 4.6).

Thin views over `app.domain.ranges`, the one place that owns the grid rules
(UT-RNG-02, UT-RNG-03). The draft ingest step maps the model's citations back
with the same functions, so the two sides cannot drift.
"""

from __future__ import annotations

from app.domain import ranges
from app.domain.ranges import SegmentWindow

frame_interval = ranges.frame_interval


def frame_times(
    duration_s: float,
    video_duration_s: float | None = None,
    frame_step_s: float | None = None,
) -> list[int]:
    """`t_i = i * k` for `i = 0 .. ceil(duration / k) - 1`; empty under 1 s (D4).

    Pass the probed video stream duration (and frame step) so times past the last
    video frame are dropped when the audio is longer than the video."""
    step = frame_step_s if frame_step_s else ranges.DEFAULT_FRAME_STEP_S
    return list(ranges.frame_times(duration_s, video_duration_s, step))


def segment_windows(duration_s: float) -> list[tuple[float, float]]:
    """Fixed 10 s windows (0-based list of `(start_s, end_s)`); a last window under
    3 s merges into the previous one. The last `end_s` is the clip duration."""
    if duration_s <= 0:
        return []
    return [(w.start_s, w.end_s) for w in ranges.segment_windows(duration_s, 1)]


def segment_plan(duration_s: float, clip_ordinal: int) -> tuple[SegmentWindow, ...]:
    """The labelled windows (`c{ordinal}-seg{n}`, 1-based) the model and the
    `segment` rows use."""
    if duration_s <= 0:
        return ()
    return ranges.segment_windows(duration_s, clip_ordinal)
