"""UT-SLG-01, UT-HLT-01, UT-SAF-01, UT-VIS-01."""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from app.domain.enums import DogStatus, FactStatus
from app.domain.health import HealthQuestionMatcher
from app.domain.situations import (
    SITUATION_LABELS,
    SITUATION_ORDER,
    SITUATIONS_TOTAL,
    STAFF_ONLY,
)
from app.domain.slugs import generate_slug
from app.domain.visibility import is_publicly_visible


def test_ut_slg_01_slug_generator():
    slugs = [generate_slug() for _ in range(1000)]
    assert all(len(s) == 12 for s in slugs)
    assert all(re.fullmatch(r"[a-z2-9]{12}", s) for s in slugs)
    assert not any(set(s) & set("01lo") for s in slugs)
    assert len(set(slugs)) == 1000


KEYWORDS = """
# health keyword list (stems end with *)
vaccin*
medic*
sick
ill
"""


def test_ut_hlt_01_health_matcher():
    matcher = HealthQuestionMatcher.from_text(KEYWORDS)
    assert matcher.matches("Is he vaccinated?")
    assert matcher.matches("any medical issues")
    assert matcher.matches("does he need medication")
    assert matcher.matches("IS HE SICK")
    assert not matcher.matches("does he walk well")


def test_ut_saf_01_situation_order():
    assert SITUATION_ORDER == (
        "new_person",
        "handling",
        "leash_walk",
        "other_dog",
        "food_toys",
        "alone_time",
        "indoors_rest",
        "children_cats",
    )
    assert SITUATIONS_TOTAL == 8
    assert [SITUATION_LABELS[c] for c in SITUATION_ORDER] == [
        "Meeting a new person",
        "Handling",
        "Leash walk",
        "Meeting another dog",
        "Food and toys",
        "Alone time",
        "Indoors and rest",
        "Children or cats",
    ]
    assert "children_cats" in STAFF_ONLY


@given(
    st.sampled_from(list(FactStatus)),
    st.booleans(),
    st.sampled_from(list(DogStatus)),
)
def test_ut_vis_01_property_public_fact_visibility(fact_status, merged, dog_status):
    expected = (
        fact_status == FactStatus.CONFIRMED
        and merged is True
        and dog_status == DogStatus.PUBLISHED
    )
    assert is_publicly_visible(fact_status, merged, dog_status) is expected
