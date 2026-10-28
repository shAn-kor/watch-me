"""UT-WRD-01 to UT-WRD-06: banned-word rules layer and behavior text rules (04 section 6)."""

from __future__ import annotations

import unicodedata

import pytest

from app.domain.wording import (
    BannedWordMatcher,
    behavior_problem,
    needs_acknowledgement,
    normalize_behavior,
)

# Starter list of 04 section 6.2 (one entry per whitespace-separated token,
# quoted phrases, `*` stems, `#` comments).
STARTER = """
# trait labels
aggressive* anxious* nervous* fearful* shy timid friendly* sweet gentle
playful calm* happy* sad lazy stubborn dominant* submissive protective
territorial reactive loyal affectionate* cuddly* needy independent obedient
well-behaved good-natured even-tempered easygoing laid-back mellow
# judgments and safety claims
dangerous safe harmless vicious mean bad good-dog perfect
"good with kids" "good with children" "good with cats" "good with dogs"
"great with" "loves people" "loves kids" "hates" "afraid of" "scared of"
# mental states
seemed* appeared* "wanted to" "wants to" "loves to" "likes to" "enjoys"
excited happy* comfortable relaxed
# paraphrased claims
"doesn't mind" "does not mind" "never bites" "won't bite" "never barks"
"no issues" "no problems" "family dog" "ideal"
"""


@pytest.fixture(scope="module")
def matcher() -> BannedWordMatcher:
    return BannedWordMatcher.from_text(STARTER)


def test_ut_wrd_01_banned_word_matcher(matcher):
    for text in ("He is a friendly dog", "Friendly!"):
        flags = matcher.check(text)
        assert len(flags) == 1
        flag = flags[0]
        assert (flag.code, flag.severity, flag.source) == ("banned_word", "warn", "rules")
    assert matcher.check("unfriendly") == ()
    assert matcher.check("He barked 3 times") == ()
    assert len(matcher.check("He acted aggressively")) == 1


def test_ut_wrd_02_trait_phrases(matcher):
    for text in (
        "He is GOOD with kids!",
        "Good with children.",
        "Well-Behaved, quiet",
        "Great with other dogs",
    ):
        flags = matcher.check(text)
        assert flags, text
        assert all(f.code == "banned_word" and f.severity == "warn" for f in flags)
    flag = matcher.check("He is good with kids")[0]
    assert flag.detail == 'Banned wording: "good with kids"'


def test_ut_wrd_02_at_most_three_flags_one_per_entry(matcher):
    text = "friendly friendly calm sweet gentle playful lazy"
    flags = matcher.check(text)
    assert len(flags) == 3
    assert len({f.detail for f in flags}) == 3


def test_ut_wrd_02_whole_word_not_substring():
    ass = BannedWordMatcher.from_text("ass")
    assert ass.check("A class of dogs") == ()
    assert len(ass.check("an ass")) == 1


def test_ut_wrd_03_paraphrase_on_the_list_vs_not(matcher):
    assert len(matcher.check("doesn't mind being grabbed")) == 1
    assert matcher.check("tolerates being grabbed") == ()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (unicodedata.normalize("NFD", "café walk"), "café walk"),
        ("   sits quietly   ", "sits quietly"),
    ],
)
def test_ut_wrd_04_normalization(raw, expected):
    assert normalize_behavior(raw) == expected
    assert behavior_problem(normalize_behavior(raw)) is None


def test_ut_wrd_04_length_and_newline_rules():
    assert behavior_problem("ab") == "too_short"
    assert behavior_problem("abc") is None
    assert behavior_problem("a" * 280) is None
    assert behavior_problem("a" * 281) == "too_long"
    assert behavior_problem("line one\nline two") == "contains_newline"


def test_ut_wrd_05_list_reload_flags_new_word_without_code_change():
    before = BannedWordMatcher.from_text("calm*")
    assert before.check("He is wobbly") == ()
    after = BannedWordMatcher.from_text("calm*\nwobbly")
    assert len(after.check("He is wobbly")) == 1


def test_ut_wrd_06_acknowledgement_set():
    banned = {"code": "banned_word", "severity": "warn", "source": "rules", "detail": "x"}
    trait = {"code": "trait_claim", "severity": "warn", "source": "model", "detail": "x"}
    unavailable = {
        "code": "check_unavailable",
        "severity": "info",
        "source": "system",
        "detail": "x",
    }
    assert needs_acknowledgement([banned])
    assert needs_acknowledgement([trait])
    assert not needs_acknowledgement([unavailable])
    assert not needs_acknowledgement([])
    assert needs_acknowledgement([unavailable, banned])
    # unknown severity is treated as warn (fail safe)
    assert needs_acknowledgement([{"code": "x", "severity": "weird"}])


def test_ut_wrd_04_ai_text_is_normalized_leniently():
    from app.domain.wording import normalize_ai_behavior

    assert normalize_ai_behavior("  He sits\n quietly. ") == "He sits quietly"
    assert normalize_ai_behavior("ab") is None
    assert len(normalize_ai_behavior("a" * 400)) == 280
