"""Duplicate facts: within a clip and across clips (04 sections 5 and 5.6, D3).

Duplicates merge their evidence instead of being hard-deleted. A `clip` fact
beats a `narration` duplicate without merging evidence.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace

from app.domain.ranges import Range, normalize_evidence, overlap_seconds

WITHIN_OVERLAP_RATIO = 0.6
WITHIN_RULE_A_JACCARD = 0.5
JACCARD_DUPLICATE = 0.85
_EPS = 1e-9

STOP_WORDS = frozenset({"a", "an", "the", "of", "to", "and", "at", "on", "in", "for", "with"})
_WORD = re.compile(r"[^\W_]+")


@dataclass(frozen=True)
class FactDraft:
    """A drafted fact as the dedupe rules see it. `ref` is the caller's id."""

    ref: str
    situation: str
    source: str
    text: str
    evidence: tuple[Range, ...]
    clip_id: str | None = None


@dataclass(frozen=True)
class DedupeResult:
    facts: tuple[FactDraft, ...]
    removed: tuple[str, ...]


def _stem(word: str) -> str:
    if word.endswith("ing") and len(word) > 5:
        return word[:-3]
    if word.endswith("ed") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def normalized_tokens(text: str) -> frozenset[str]:
    """Lowercase, no punctuation, no stop words, simple -ed/-ing/-s strip."""
    folded = unicodedata.normalize("NFC", text).lower().replace("'", "").replace("’", "")
    return frozenset(_stem(w) for w in _WORD.findall(folded) if w not in STOP_WORDS)


def jaccard(a: str, b: str) -> float:
    ta, tb = normalized_tokens(a), normalized_tokens(b)
    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


def _total(rows: Sequence[Range]) -> float:
    return sum(r.length for r in normalize_evidence(rows, max_rows=None))


def _overlap_ratio(a: FactDraft, b: FactDraft) -> float:
    shorter = min(_total(a.evidence), _total(b.evidence))
    if shorter <= 0:
        return 0.0
    return overlap_seconds(a.evidence, b.evidence) / shorter


def is_within_clip_duplicate(a: FactDraft, b: FactDraft) -> bool:
    """Same situation and (a) overlap >= 60% of the shorter with Jaccard >= 0.5,
    or (b) Jaccard >= 0.85 whatever the ranges."""
    if a.situation != b.situation:
        return False
    similarity = jaccard(a.text, b.text)
    if similarity >= JACCARD_DUPLICATE - _EPS:
        return True
    return (
        similarity >= WITHIN_RULE_A_JACCARD - _EPS
        and _overlap_ratio(a, b) >= WITHIN_OVERLAP_RATIO - _EPS
    )


def is_cross_clip_duplicate(a: FactDraft, b: FactDraft) -> bool:
    return a.situation == b.situation and jaccard(a.text, b.text) >= JACCARD_DUPLICATE - _EPS


def _earliest(f: FactDraft) -> float:
    return min((r.start_s for r in f.evidence), default=float("inf"))


def _resolve(a: FactDraft, b: FactDraft, *, cross_clip: bool) -> tuple[FactDraft, FactDraft] | None:
    """Return (survivor, removed) for a duplicate pair, None when not mergeable."""
    if a.source != b.source:
        pair = {a.source: a, b.source: b}
        if set(pair) == {"clip", "narration"}:
            return pair["clip"], pair["narration"]
        return None
    if cross_clip:
        key = lambda f: (-len(f.text), -len(f.evidence), _earliest(f))  # noqa: E731
    else:
        key = lambda f: (-len(f.evidence), -len(f.text), _earliest(f))  # noqa: E731
    survivor, removed = sorted((a, b), key=key)
    merged = normalize_evidence((*survivor.evidence, *removed.evidence))
    return replace(survivor, evidence=merged), removed


def _dedupe(facts: Sequence[FactDraft], *, cross_clip: bool) -> DedupeResult:
    current = list(facts)
    removed: list[str] = []
    is_dup = is_cross_clip_duplicate if cross_clip else is_within_clip_duplicate
    changed = True
    while changed:
        changed = False
        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                a, b = current[i], current[j]
                if (a.clip_id != b.clip_id) != cross_clip or not is_dup(a, b):
                    continue
                resolved = _resolve(a, b, cross_clip=cross_clip)
                if resolved is None:
                    continue
                survivor, gone = resolved
                removed.append(gone.ref)
                current[i] = survivor
                del current[j]
                changed = True
                break
            if changed:
                break
    return DedupeResult(tuple(current), tuple(removed))


def dedupe_within_clip(facts: Sequence[FactDraft]) -> DedupeResult:
    """Merge duplicates among facts of the same clip (only same-`clip_id` pairs)."""
    return _dedupe(facts, cross_clip=False)


def merge_across_clips(facts: Sequence[FactDraft]) -> DedupeResult:
    """Merge duplicates among facts of different clips (only different-`clip_id` pairs)."""
    return _dedupe(facts, cross_clip=True)
