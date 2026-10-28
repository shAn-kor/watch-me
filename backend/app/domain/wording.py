"""Wording rules: banned-word rules layer and behavior text rules (04 section 6, 01 section 2)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.domain.textmatch import TermMatcher

MAX_FLAGS_PER_FACT = 3
BEHAVIOR_MIN = 3
BEHAVIOR_MAX = 280


@dataclass(frozen=True)
class RuleFlag:
    code: str
    severity: str
    source: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "source": self.source,
            "detail": self.detail,
        }


class BannedWordMatcher:
    """Rules checker core. Build it from the banned list text; a reload is a
    new instance, no code change needed (PRD 5.3)."""

    def __init__(self, matcher: TermMatcher) -> None:
        self._matcher = matcher

    @classmethod
    def from_text(cls, source: str) -> BannedWordMatcher:
        return cls(TermMatcher.from_text(source))

    def check(self, text: str) -> tuple[RuleFlag, ...]:
        """One `banned_word` flag per distinct matched entry, at most 3."""
        matches = self._matcher.find(text)[:MAX_FLAGS_PER_FACT]
        return tuple(
            RuleFlag("banned_word", "warn", "rules", f'Banned wording: "{m.text}"')
            for m in matches
        )


def _severity(flag: Any) -> str | None:
    if isinstance(flag, Mapping):
        return flag.get("severity")
    return getattr(flag, "severity", None)


def needs_acknowledgement(flags: Iterable[Any]) -> bool:
    """True when any flag needs `acknowledge_flags`: every severity except
    `info`, so an unknown severity fails safe as `warn`."""
    return any(_severity(f) != "info" for f in flags)


def normalize_behavior(text: str) -> str:
    """NFC and trim (01 section 2)."""
    return unicodedata.normalize("NFC", text).strip()


def behavior_problem(text: str) -> str | None:
    """`contains_newline`, `too_short`, `too_long`, or None when valid."""
    value = normalize_behavior(text)
    if "\n" in value or "\r" in value:
        return "contains_newline"
    if len(value) < BEHAVIOR_MIN:
        return "too_short"
    if len(value) > BEHAVIOR_MAX:
        return "too_long"
    return None


def normalize_ai_behavior(text: str) -> str | None:
    """Lenient normalization of model text (04 section 5 step 2): NFC, collapse
    whitespace and newlines, strip a trailing period, truncate at 280. None when
    shorter than 3 characters."""
    value = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()
    value = value.removesuffix(".").rstrip()[:BEHAVIOR_MAX].rstrip()
    return value if len(value) >= BEHAVIOR_MIN else None
