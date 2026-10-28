"""Health question matcher (QA-4). Keyword list format: see `textmatch`."""

from __future__ import annotations

from app.domain.textmatch import TermMatcher


class HealthQuestionMatcher:
    def __init__(self, matcher: TermMatcher) -> None:
        self._matcher = matcher

    @classmethod
    def from_text(cls, source: str) -> HealthQuestionMatcher:
        return cls(TermMatcher.from_text(source))

    def matches(self, question: str) -> bool:
        return bool(self._matcher.find(question))
