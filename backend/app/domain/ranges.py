"""Time ranges, frame grid and evidence repair (04 sections 4 and 5, 02 I-3).

Pure functions, stdlib only. Snap, clamp and drop rules are owned by 04
section 4.2 and section 5 step 4; the unit tests are parameterized on 04's
numbers. `round_half_up` is for 0.1 s display rounding and coverage sums, not
for snapping.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

MAX_FRAMES = 48
MIN_ROW_S = 1.0
MAX_ROW_S = 60.0
MAX_ROWS_PER_FACT = 3
SEGMENT_S = 10
MIN_LAST_SEGMENT_S = 3
MIN_NARRATION_OVERLAP_S = 0.5
_EPS = 1e-9
# Assumed gap between video frames when the stream reports no frame rate.
DEFAULT_FRAME_STEP_S = 0.1


@dataclass(frozen=True)
class Range:
    """One evidence range. `clip_id` is None where the clip is implicit."""

    start_s: float
    end_s: float
    clip_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_s", float(self.start_s))
        object.__setattr__(self, "end_s", float(self.end_s))

    @property
    def length(self) -> float:
        return self.end_s - self.start_s


def round_half_up(value: float) -> int:
    """Round to an integer, .5 always up (not banker's rounding)."""
    return int(Decimal(repr(float(value))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ----------------------------------------------------------------- frame grid
def frame_interval(duration_s: float) -> int:
    """Seconds between sampled frames: k = max(1, ceil(duration / 48))."""
    return max(1, math.ceil(duration_s / MAX_FRAMES))


def frame_times(
    duration_s: float,
    video_duration_s: float | None = None,
    frame_step_s: float = DEFAULT_FRAME_STEP_S,
) -> tuple[int, ...]:
    """Frame times t_i = i * k. A clip under 1 s has no frames (D4).

    `k` and the grid come from `duration_s` (the clip duration the rest of the
    pipeline uses). When the video stream is shorter than the clip (audio runs
    on), `video_duration_s` drops the tail times that have no video frame: a
    time t is kept only while a whole frame still fits, `t + frame_step_s <=
    video_duration_s`. `t = 0` is always kept for a clip of 1 s or more."""
    if duration_s < 1.0:
        return ()
    k = frame_interval(duration_s)
    times = tuple(i * k for i in range(math.ceil(duration_s / k)))
    if video_duration_s is None:
        return times
    limit = video_duration_s - frame_step_s + _EPS
    kept = tuple(t for t in times if t <= limit)
    return kept or times[:1]


def last_frame_t(duration_s: float, grid: int) -> int:
    return max(0, (math.ceil(duration_s / grid) - 1) * grid)


def snap_to_grid(t: float, grid: int, duration_s: float) -> int:
    """Nearest multiple of `grid` (ties go down), clamped to [0, last frame]."""
    index = math.ceil(t / grid - 0.5)
    return min(max(index * grid, 0), last_frame_t(duration_s, grid))


def frame_citation_to_range(
    start_t: float,
    end_t: float,
    grid: int,
    duration_s: float,
    clip_id: str | None = None,
) -> Range | None:
    """Convert a cited frame pair to a range, or None when the row is invalid.

    Snap both times, swap if reversed, convert to
    `[start_t, min(end_t + grid, duration)]`, extend the start back to reach
    1.0 s, drop a row that is still under 1 s or is over 60 s.
    """
    first = snap_to_grid(start_t, grid, duration_s)
    second = snap_to_grid(end_t, grid, duration_s)
    if second < first:
        first, second = second, first
    start_s = float(first)
    end_s = min(float(second + grid), float(duration_s))
    if end_s - start_s < MIN_ROW_S - _EPS:
        start_s = max(0.0, end_s - MIN_ROW_S)
    length = end_s - start_s
    if length < MIN_ROW_S - 1e-6 or length > MAX_ROW_S + 1e-6:
        return None
    return Range(start_s, end_s, clip_id)


# ------------------------------------------------------------ evidence lists
def _group_by_clip(rows: Iterable[Range]) -> dict[str | None, list[Range]]:
    groups: dict[str | None, list[Range]] = {}
    for row in rows:
        groups.setdefault(row.clip_id, []).append(row)
    return groups


def _merge_sorted(rows: list[Range], *, cap_length: bool) -> list[Range]:
    merged: list[Range] = []
    for row in sorted(rows, key=lambda r: (r.start_s, r.end_s)):
        if merged and row.start_s <= merged[-1].end_s + _EPS:
            end_s = max(merged[-1].end_s, row.end_s)
            if not cap_length or end_s - merged[-1].start_s <= MAX_ROW_S + _EPS:
                merged[-1] = Range(merged[-1].start_s, end_s, merged[-1].clip_id)
                continue
        merged.append(row)
    return merged


def normalize_evidence(
    rows: Iterable[Range], max_rows: int | None = MAX_ROWS_PER_FACT
) -> tuple[Range, ...]:
    """Drop exact duplicates, merge overlapping or touching rows of one clip
    (never into a row over 60 s), keep `max_rows`, longest first."""
    unique = list(dict.fromkeys(rows))
    merged: list[Range] = []
    for group in _group_by_clip(unique).values():
        merged.extend(_merge_sorted(group, cap_length=True))
    merged.sort(key=lambda r: (-r.length, r.start_s, r.clip_id or ""))
    if max_rows is not None:
        merged = merged[:max_rows]
    return tuple(merged)


def union_seconds(ranges: Iterable[Range]) -> float:
    """Total seconds covered, overlaps counted once (per clip)."""
    total = 0.0
    for group in _group_by_clip(ranges).values():
        total += sum(r.length for r in _merge_sorted(group, cap_length=False))
    return total


def overlap_seconds(a: Iterable[Range], b: Iterable[Range]) -> float:
    """Seconds shared by two evidence lists (same clip only)."""
    groups_a = {k: _merge_sorted(v, cap_length=False) for k, v in _group_by_clip(a).items()}
    groups_b = {k: _merge_sorted(v, cap_length=False) for k, v in _group_by_clip(b).items()}
    total = 0.0
    for clip_id, rows_a in groups_a.items():
        for x in rows_a:
            for y in groups_b.get(clip_id, ()):
                total += max(0.0, min(x.end_s, y.end_s) - max(x.start_s, y.start_s))
    return total


# ------------------------------------------------------------- repair report
@dataclass(frozen=True)
class RepairReport:
    """`rows[i]` is the repaired evidence of fact i; empty means the fact is
    dropped (never stored without evidence)."""

    rows: tuple[tuple[Range, ...], ...]
    dropped_facts: int
    dropped_rows: int
    snapped_rows: int


def repair_citations(
    facts: Sequence[Sequence[tuple[float, float]]],
    grid: int,
    duration_s: float,
    clip_id: str | None = None,
) -> RepairReport:
    """Frames-mode evidence repair for every fact of one clip (04 section 5 step 4)."""
    out: list[tuple[Range, ...]] = []
    dropped_facts = dropped_rows = snapped_rows = 0
    for citations in facts:
        kept: list[Range] = []
        for start_t, end_t in citations:
            rng = frame_citation_to_range(start_t, end_t, grid, duration_s, clip_id)
            if rng is None:
                dropped_rows += 1
                continue
            if (
                snap_to_grid(start_t, grid, duration_s) != start_t
                or snap_to_grid(end_t, grid, duration_s) != end_t
            ):
                snapped_rows += 1
            kept.append(rng)
        rows = normalize_evidence(kept)
        if not rows:
            dropped_facts += 1
        out.append(rows)
    return RepairReport(tuple(out), dropped_facts, dropped_rows, snapped_rows)


def filter_narration_rows(
    rows: Iterable[Range],
    transcript: Sequence[tuple[float, float]],
    min_overlap_s: float = MIN_NARRATION_OVERLAP_S,
) -> tuple[Range, ...]:
    """Keep rows that overlap at least one transcript segment by `min_overlap_s`."""
    kept = []
    for row in rows:
        best = max(
            (min(row.end_s, end) - max(row.start_s, start) for start, end in transcript),
            default=0.0,
        )
        if best >= min_overlap_s - _EPS:
            kept.append(row)
    return tuple(kept)


# --------------------------------------------------------------- segments mode
@dataclass(frozen=True)
class SegmentWindow:
    ref: str
    index: int
    start_s: float
    end_s: float


def segment_windows(duration_s: float, clip_ordinal: int) -> tuple[SegmentWindow, ...]:
    """Fixed 10 s windows; a last window under 3 s merges into the previous one."""
    bounds: list[list[float]] = []
    start = 0.0
    while start < duration_s - _EPS:
        bounds.append([start, min(start + SEGMENT_S, float(duration_s))])
        start += SEGMENT_S
    if len(bounds) > 1 and bounds[-1][1] - bounds[-1][0] < MIN_LAST_SEGMENT_S:
        last = bounds.pop()
        bounds[-1][1] = last[1]
    return tuple(
        SegmentWindow(f"c{clip_ordinal}-seg{i}", i, s, e) for i, (s, e) in enumerate(bounds, 1)
    )


_SEG_REF = re.compile(r"c(\d+)-seg(\d+)")


def segment_ranges(
    refs: Iterable[str],
    clip_ordinal: int,
    duration_s: float,
    clip_id: str | None = None,
) -> tuple[tuple[Range, ...], int]:
    """Map segment refs to ranges. Returns (rows, dropped_ref_count).

    Refs not in this clip's window list are dropped; adjacent refs merge.
    """
    windows = {w.ref: w for w in segment_windows(duration_s, clip_ordinal)}
    rows: list[Range] = []
    dropped = 0
    for ref in refs:
        window = windows.get(ref.strip()) if _SEG_REF.fullmatch(ref.strip()) else None
        if window is None:
            dropped += 1
        else:
            rows.append(Range(window.start_s, window.end_s, clip_id))
    return normalize_evidence(rows), dropped
