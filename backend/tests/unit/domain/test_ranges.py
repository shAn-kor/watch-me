"""UT-RNG-01 to UT-RNG-17: range, grid and frame-plan rules (04 sections 4 and 5)."""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.ranges import (
    Range,
    filter_narration_rows,
    frame_citation_to_range,
    frame_interval,
    frame_times,
    normalize_evidence,
    repair_citations,
    round_half_up,
    segment_ranges,
    segment_windows,
    snap_to_grid,
    union_seconds,
)

EPS = 1e-9


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.5, 1), (1.5, 2), (2.5, 3), (8.49, 8), (8.5, 9)],
)
def test_ut_rng_01_round_half_up(value, expected):
    assert round_half_up(value) == expected


@pytest.mark.parametrize(
    ("duration", "k"),
    [(0.5, 1), (10, 1), (48, 1), (48.1, 2), (96, 2), (97, 3), (120, 3), (120.5, 3)],
)
def test_ut_rng_02_frame_interval(duration, k):
    assert frame_interval(duration) == k
    assert math.ceil(duration / k) <= 48


def test_ut_rng_02_frame_interval_120s_gives_40_frames():
    assert len(frame_times(120)) == 40


def test_ut_rng_03_segment_windows_25s():
    windows = segment_windows(25.0, 2)
    assert [(w.start_s, w.end_s) for w in windows] == [(0, 10), (10, 20), (20, 25)]
    assert [w.ref for w in windows] == ["c2-seg1", "c2-seg2", "c2-seg3"]
    assert windows[-1].end_s == 25.0


def test_ut_rng_03_segment_windows_short_last_window_merges():
    windows = segment_windows(22.0, 1)
    assert [(w.start_s, w.end_s) for w in windows] == [(0, 10), (10, 22)]
    windows = segment_windows(71.0, 1)
    assert len(windows) == 7
    assert (windows[-1].start_s, windows[-1].end_s) == (60, 71.0)


def test_ut_rng_03_segment_windows_tiny_clip_is_one_window():
    windows = segment_windows(2.5, 1)
    assert [(w.start_s, w.end_s) for w in windows] == [(0, 2.5)]
    assert all(w.end_s > w.start_s for w in segment_windows(25.0, 1))


def test_ut_rng_04_snap_and_convert():
    assert snap_to_grid(10.2, 3, 120) == 9
    assert snap_to_grid(19.4, 3, 120) == 18
    assert frame_citation_to_range(10.2, 19.4, 3, 120) == Range(9.0, 21.0)


def test_ut_rng_05_end_past_clip_is_clamped():
    assert snap_to_grid(26.0, 3, 20) == 18
    rng = frame_citation_to_range(15.0, 26.0, 3, 20)
    assert rng == Range(15.0, 20.0)
    assert rng.length == 5.0


def test_ut_rng_06_negative_start():
    assert snap_to_grid(-2.0, 3, 60) == 0
    assert snap_to_grid(4.0, 3, 60) == 3
    assert frame_citation_to_range(-2.0, 4.0, 3, 60) == Range(0.0, 6.0)


def test_ut_rng_07_reversed_or_same_frame():
    reversed_ = frame_citation_to_range(21.0, 12.0, 3, 60)
    same = frame_citation_to_range(9.0, 9.0, 3, 60)
    assert reversed_ == Range(12.0, 24.0)
    assert same == Range(9.0, 12.0)
    assert reversed_.length >= 1.0 and same.length >= 1.0


def test_ut_rng_08_short_range_is_extended_back():
    assert frame_citation_to_range(18.0, 18.0, 3, 18.5) == Range(17.5, 18.5)


def test_ut_rng_08_row_under_1s_is_dropped_and_fact_counted():
    assert frame_citation_to_range(0.0, 0.0, 1, 0.9) is None
    report = repair_citations([[(0.0, 0.0)]], 1, 0.9)
    assert report.rows == ((),)
    assert report.dropped_facts == 1


def test_ut_rng_09_range_over_60s_is_dropped_not_truncated():
    assert frame_citation_to_range(10, 100, 3, 120) is None
    report = repair_citations(
        [[(10, 100)], [(10, 100), (30, 32)]],
        3,
        120,
    )
    assert report.rows[0] == ()
    assert report.rows[1] == (Range(30.0, 35.0),)
    assert report.dropped_facts == 1
    assert report.dropped_rows == 2


def test_ut_rng_10_segment_id_mapping():
    one, dropped = segment_ranges(["c2-seg2"], 2, 25.0)
    assert one == (Range(10.0, 20.0),) and dropped == 0
    last, _ = segment_ranges(["c2-seg3"], 2, 25.0)
    assert last == (Range(20.0, 25.0),)
    for bad in ("c2-seg9", "c1-seg1"):
        rows, dropped = segment_ranges([bad], 2, 25.0)
        assert rows == () and dropped == 1


def test_ut_rng_10_adjacent_segment_refs_merge():
    rows, dropped = segment_ranges(["c2-seg2", "c2-seg3"], 2, 25.0)
    assert rows == (Range(10.0, 25.0),)
    assert dropped == 0


@st.composite
def _citations(draw):
    duration = draw(st.floats(min_value=1.0, max_value=120.0, allow_nan=False))
    grid = draw(st.integers(min_value=1, max_value=6))
    raw = st.floats(min_value=-30.0, max_value=160.0, allow_nan=False)
    cites = draw(st.lists(st.tuples(raw, raw), min_size=1, max_size=6))
    return duration, grid, cites


@settings(max_examples=300, deadline=None)
@given(_citations())
def test_ut_rng_11_property_converted_output_always_valid(data):
    duration, grid, cites = data
    kept = []
    for start_t, end_t in cites:
        rng = frame_citation_to_range(start_t, end_t, grid, duration)
        if rng is None:
            continue
        assert 0 <= rng.start_s < rng.end_s <= duration + EPS
        assert 1.0 - 1e-6 <= rng.length <= 60.0 + 1e-6
        on_grid = abs(rng.start_s / grid - round(rng.start_s / grid)) < 1e-9
        assert on_grid or abs(rng.start_s - (rng.end_s - 1.0)) < 1e-9
        end_ok = abs(rng.end_s / grid - round(rng.end_s / grid)) < 1e-9
        assert end_ok or abs(rng.end_s - duration) < 1e-9
        kept.append(rng)
    assert len(normalize_evidence(kept)) <= 3
    report = repair_citations([cites], grid, duration)
    assert len(report.rows[0]) <= 3


def test_ut_rng_12_union_seconds():
    ranges = [Range(2, 6), Range(4, 8), Range(10, 11)]
    assert union_seconds(ranges) == 7.0


@pytest.mark.parametrize(("raw", "expected"), [(1.5, 0), (4.5, 3), (1.6, 3)])
def test_ut_rng_13_snap_ties_go_down(raw, expected):
    assert snap_to_grid(raw, 3, 60) == expected


def test_ut_rng_14_frames_to_range_formula():
    assert frame_citation_to_range(12, 18, 3, 120) == Range(12.0, 21.0)


def test_ut_rng_15_narration_overlap_rule():
    transcript = [(2.0, 4.0)]
    keep = Range(3.5, 6.0)
    assert filter_narration_rows([keep], transcript) == (keep,)
    assert filter_narration_rows([Range(3.6, 6.0)], transcript) == ()
    assert filter_narration_rows([Range(5.0, 8.0)], transcript) == ()


def test_ut_rng_16_row_limits_per_fact():
    five = [Range(i * 10.0, i * 10.0 + 2.0) for i in range(5)]
    assert len(normalize_evidence(five)) == 3
    dup = normalize_evidence([Range(0, 5), Range(0, 5)])
    assert dup == (Range(0, 5),)
    touching = normalize_evidence([Range(0, 5), Range(5, 9)])
    assert touching == (Range(0, 9),)
    overlapping = normalize_evidence([Range(0, 5), Range(3, 9)])
    assert overlapping == (Range(0, 9),)


def test_ut_rng_16_rows_of_different_clips_never_merge():
    rows = normalize_evidence([Range(0, 5, "a"), Range(0, 5, "b")])
    assert len(rows) == 2


def test_ut_rng_17_clip_under_1s_has_no_frames():
    assert frame_times(0.8) == ()
    assert frame_times(1.0) == (0,)
