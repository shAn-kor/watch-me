"""Coverage and not-observed list (02 sections 4.1 and 4.2, PUB-1, PUB-4, PUB-9).

Pure computation over plain facts and clips; `CoverageService` feeds it rows.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.ranges import Range, round_half_up, union_seconds
from app.domain.situations import (
    SITUATION_LABELS,
    SITUATION_ORDER,
    SITUATIONS_TOTAL,
    STAFF_ONLY,
)


@dataclass(frozen=True)
class CoverageFact:
    situation: str
    source: str
    status: str
    evidence: tuple[Range, ...] = ()
    confirmed_role: str | None = None


@dataclass(frozen=True)
class CoverageClip:
    id: str
    duration_s: float
    status: str = "ready"
    deleted: bool = False


@dataclass(frozen=True)
class SituationCoverage:
    situation: str
    label: str
    covered: bool
    clip_count: int
    filmed_s: int
    confirmed_s: int


@dataclass(frozen=True)
class Coverage:
    entries: tuple[SituationCoverage, ...]
    covered: tuple[str, ...]
    not_observed: tuple[str, ...]
    situations_covered: int
    situations_total: int = SITUATIONS_TOTAL

    def entry(self, situation: str) -> SituationCoverage:
        return next(e for e in self.entries if e.situation == situation)


def compute_coverage(facts: Iterable[CoverageFact], clips: Iterable[CoverageClip]) -> Coverage:
    """A situation is covered by a live, ready clip cited by a confirmed
    `clip` fact. Situations in STAFF_ONLY count only staff-confirmed facts."""
    live = {c.id: c for c in clips if c.status == "ready" and not c.deleted}
    cited: dict[str, dict[str, None]] = {s: {} for s in SITUATION_ORDER}
    ranges: dict[str, list[Range]] = {s: [] for s in SITUATION_ORDER}
    for fact in facts:
        if fact.status != "confirmed" or fact.source != "clip":
            continue
        if fact.situation not in cited:
            continue
        if fact.situation in STAFF_ONLY and fact.confirmed_role != "staff":
            continue
        for row in fact.evidence:
            clip = live.get(row.clip_id) if row.clip_id is not None else None
            if clip is None:
                continue
            cited[fact.situation][clip.id] = None
            ranges[fact.situation].append(
                Range(max(0.0, row.start_s), min(row.end_s, clip.duration_s), clip.id)
            )
    entries = []
    for situation in SITUATION_ORDER:
        ids = list(cited[situation])
        entries.append(
            SituationCoverage(
                situation=situation,
                label=SITUATION_LABELS[situation],
                covered=bool(ids),
                clip_count=len(ids),
                filmed_s=round_half_up(sum(live[i].duration_s for i in ids)),
                confirmed_s=round_half_up(
                    union_seconds(r for r in ranges[situation] if r.length > 0)
                ),
            )
        )
    covered = tuple(e.situation for e in entries if e.covered)
    not_observed = tuple(e.situation for e in entries if not e.covered)
    return Coverage(tuple(entries), covered, not_observed, len(covered))
