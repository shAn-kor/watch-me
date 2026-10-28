"""Server-rendered labels (01 section 4, 02 section 4.3)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.ranges import Range, round_half_up, union_seconds

_SOURCE_LABELS = {
    "clip": "Seen in clip",
    "narration": "Said by volunteer, not in clip",
    "staff_note": "Shelter staff note",
}
_CONFIRMED_BY = {"staff": "Confirmed by staff", "volunteer": "Confirmed by volunteer"}


@dataclass(frozen=True)
class ClipLength:
    clip_count: int
    seconds: int
    label: str


def clip_length(source: str, evidence: Iterable[Range]) -> ClipLength:
    """Clip length of a fact: union per clip, summed, at least 1 s."""
    rows = list(evidence)
    if source == "staff_note" or not rows:
        return ClipLength(0, 0, "No clip")
    clips = len({r.clip_id for r in rows})
    seconds = max(1, round_half_up(union_seconds(rows)))
    if source == "narration":
        return ClipLength(clips, seconds, f"Narration only, {seconds} s")
    return ClipLength(clips, seconds, f"{clips} clip{'' if clips == 1 else 's'}, {seconds} s")


def source_label(source: str) -> str:
    return _SOURCE_LABELS[source]


def confirmed_by_label(role: str) -> str:
    """Role only, never a name."""
    return _CONFIRMED_BY[role]
