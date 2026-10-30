"""Health question matcher (QA-4). Keyword list format: see `textmatch`.

A line that starts with `!` lists place phrases ("at the vet*", "vet visit*"):
a question about how the dog behaves at a place is not a health question, so
those phrases are removed from the question before the keywords are matched.
Any other health keyword in the same question still redirects.
"""

from __future__ import annotations

from app.domain.textmatch import Term, TermMatcher, parse_terms, split_words

_EXEMPT_PREFIX = "!"


class HealthQuestionMatcher:
    def __init__(self, matcher: TermMatcher, exempt: tuple[Term, ...] = ()) -> None:
        self._matcher = matcher
        self._exempt = exempt

    @classmethod
    def from_text(cls, source: str) -> HealthQuestionMatcher:
        keywords: list[str] = []
        exempt: list[str] = []
        for line in source.splitlines():
            if line.lstrip().startswith(_EXEMPT_PREFIX):
                exempt.append(line.lstrip()[len(_EXEMPT_PREFIX) :])
            else:
                keywords.append(line)
        return cls(
            TermMatcher.from_text("\n".join(keywords)),
            parse_terms("\n".join(exempt)),
        )

    def matches(self, question: str) -> bool:
        tokens = split_words(question)
        masked: set[int] = set()
        for term in self._exempt:
            for i in range(len(tokens)):
                if term.matches_at(tokens, i):
                    masked.update(range(i, i + len(term.words)))
        kept = " ".join(t for i, t in enumerate(tokens) if i not in masked)
        return bool(self._matcher.find(kept))
