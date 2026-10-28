"""Situation constants (01 section 2, PRD 5.2). Constants only: rule functions
(coverage, not-observed, ...) belong to lane A.
"""

from __future__ import annotations

from typing import Literal

from app.domain.enums import Situation

SituationCode = Literal[
    "new_person",
    "handling",
    "leash_walk",
    "other_dog",
    "food_toys",
    "alone_time",
    "indoors_rest",
    "children_cats",
]

# Fixed PRD order; numbers 1 to 8 follow this order.
SITUATION_ORDER: tuple[str, ...] = tuple(s.value for s in Situation)

SITUATION_LABELS: dict[str, str] = {
    "new_person": "Meeting a new person",
    "handling": "Handling",
    "leash_walk": "Leash walk",
    "other_dog": "Meeting another dog",
    "food_toys": "Food and toys",
    "alone_time": "Alone time",
    "indoors_rest": "Indoors and rest",
    "children_cats": "Children or cats",
}

# Only staff may confirm facts of these situations (PUB-9, I-6).
STAFF_ONLY: frozenset[str] = frozenset({"children_cats"})

SITUATIONS_TOTAL: int = len(SITUATION_ORDER)
