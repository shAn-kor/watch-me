"""UT-LBL-01 to UT-LBL-06: server-rendered labels (02 section 4.3, 01 section 4)."""

from __future__ import annotations

from app.domain.labels import clip_length, confirmed_by_label, source_label
from app.domain.ranges import Range


def test_ut_lbl_01_one_clip():
    length = clip_length("clip", [Range(12.0, 21.0, "a")])
    assert (length.clip_count, length.seconds, length.label) == (1, 9, "1 clip, 9 s")


def test_ut_lbl_02_two_clips():
    length = clip_length("clip", [Range(0, 5, "a"), Range(3, 12, "b")])
    assert (length.clip_count, length.seconds, length.label) == (2, 14, "2 clips, 14 s")


def test_ut_lbl_03_overlap_in_one_clip_is_union_not_sum():
    length = clip_length("clip", [Range(0, 5, "a"), Range(3, 8, "a")])
    assert length.label == "1 clip, 8 s"


def test_ut_lbl_04_minimum_one_second():
    length = clip_length("clip", [Range(1.0, 1.4, "a")])
    assert length.seconds == 1
    assert length.label == "1 clip, 1 s"


def test_ut_lbl_05_narration_and_staff_note_labels():
    assert clip_length("narration", [Range(0, 4, "a")]).label == "Narration only, 4 s"
    assert clip_length("staff_note", []).label == "No clip"
    assert source_label("narration") == "Said by volunteer, not in clip"
    assert source_label("staff_note") == "Shelter staff note"
    assert source_label("clip") == "Seen in clip"


def test_ut_lbl_06_confirmed_by_label_has_no_name():
    assert confirmed_by_label("staff") == "Confirmed by staff"
    assert confirmed_by_label("volunteer") == "Confirmed by volunteer"
