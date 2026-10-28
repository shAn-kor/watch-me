"""Whole-word, phrase and stem matching shared by the banned-word and health
matchers (04 section 6.2).

List format: entries separated by whitespace, `"quoted phrases"`, an entry
ending in `*` is a stem, `#` starts a comment. Text and entries are lowercased,
NFC-normalized and split on non-letters, so "Well-Behaved" matches
`well-behaved` and "class" never matches "ass".
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

_WORD = re.compile(r"[^\W\d_]+")
_ENTRY_TOKEN = re.compile(r'#.*|"([^"]*)"|(\S+)')


def split_words(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(unicodedata.normalize("NFC", text).lower()))


@dataclass(frozen=True)
class Term:
    words: tuple[str, ...]
    stem: bool = False

    def matches_at(self, tokens: tuple[str, ...], i: int) -> bool:
        n = len(self.words)
        if i + n > len(tokens):
            return False
        if tokens[i : i + n - 1] != self.words[:-1]:
            return False
        last = tokens[i + n - 1]
        return last.startswith(self.words[-1]) if self.stem else last == self.words[-1]


@dataclass(frozen=True)
class Match:
    term: Term
    position: int
    text: str


def parse_terms(source: str) -> tuple[Term, ...]:
    terms: dict[Term, None] = {}
    for line in source.splitlines():
        for m in _ENTRY_TOKEN.finditer(line):
            if m.group(0).startswith("#"):
                break
            raw = m.group(1) if m.group(1) is not None else m.group(2)
            stem = raw.endswith("*")
            words = split_words(raw.rstrip("*"))
            if words:
                terms[Term(words, stem)] = None
    return tuple(terms)


class TermMatcher:
    def __init__(self, terms: Iterable[Term]) -> None:
        self._terms = tuple(terms)

    @classmethod
    def from_text(cls, source: str):
        return cls(parse_terms(source))

    def find(self, text: str) -> tuple[Match, ...]:
        """First occurrence of each distinct term, in text order."""
        tokens = split_words(text)
        found: list[Match] = []
        for term in self._terms:
            for i in range(len(tokens)):
                if term.matches_at(tokens, i):
                    found.append(Match(term, i, " ".join(tokens[i : i + len(term.words)])))
                    break
        found.sort(key=lambda m: m.position)
        return tuple(found)
