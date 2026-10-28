"""Public visibility rule (I-1, I-15). The one SQL reader of this rule is
`repositories/public_facts.py`; this predicate is its executable definition."""

from __future__ import annotations

from app.domain.enums import DogStatus, FactStatus


def is_publicly_visible(fact_status: str, merged: bool, dog_status: str) -> bool:
    """A fact is public only when confirmed, merged, on a published dog."""
    return bool(
        fact_status == FactStatus.CONFIRMED
        and merged
        and dog_status == DogStatus.PUBLISHED
    )
