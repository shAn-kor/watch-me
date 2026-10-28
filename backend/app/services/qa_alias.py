"""Alias table for the selector call (04 section 7, I-19).

The model sees "F1".."Fn" and the fact text, never a fact id. Its answer is a
list of refs. `resolve` keeps only refs that are in this request's table, so a
made-up ref, a hex id, a prose string, or an id of another dog resolves to nothing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.types import FactRef
from app.repositories.public_facts import PublicFact

MAX_ALIASES = 100
_REF = re.compile(r"F[1-9][0-9]*")


@dataclass(frozen=True, slots=True)
class AliasTable:
    fact_refs: list[FactRef]
    by_ref: dict[str, str]  # "F3" -> fact id
    order: dict[str, int]  # fact id -> index in profile order


@dataclass(frozen=True, slots=True)
class ResolvedSelection:
    fact_ids: tuple[str, ...]  # in the model's order, deduplicated, capped
    dropped: int  # refs that were not in the table
    in_profile_order: tuple[str, ...]


class AliasMapper:
    def __init__(self, max_facts: int = 5) -> None:
        self._max_facts = max_facts

    def build(self, facts: Sequence[PublicFact]) -> AliasTable:
        used = list(facts)[:MAX_ALIASES]
        refs = [
            FactRef(ref=f"F{i}", situation=f.situation, behavior=f.behavior)  # type: ignore[arg-type]
            for i, f in enumerate(used, start=1)
        ]
        return AliasTable(
            fact_refs=refs,
            by_ref={r.ref: f.id for r, f in zip(refs, used, strict=True)},
            order={f.id: i for i, f in enumerate(used)},
        )

    def resolve(self, table: AliasTable, refs: Sequence[str]) -> ResolvedSelection:
        """Normalize (drop all whitespace, upper-case), drop unknown refs and count
        them, deduplicate, keep the first `max_facts`. Duplicates and overflow are
        not counted as dropped."""
        kept: list[str] = []
        dropped = 0
        for raw in refs:
            ref = "".join(str(raw).split()).upper()
            fact_id = table.by_ref.get(ref) if _REF.fullmatch(ref) else None
            if fact_id is None:
                dropped += 1
            elif fact_id not in kept:
                kept.append(fact_id)
        kept = kept[: self._max_facts]
        ordered = tuple(sorted(kept, key=table.order.__getitem__))
        return ResolvedSelection(fact_ids=tuple(kept), dropped=dropped, in_profile_order=ordered)
