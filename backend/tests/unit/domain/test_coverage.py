"""UT-COV-01 to UT-COV-08: coverage and not-observed (02 sections 4.1 and 4.2)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.coverage import CoverageClip, CoverageFact, compute_coverage
from app.domain.ranges import Range
from app.domain.situations import SITUATION_ORDER


def cf(situation, clip_id, start, end, *, source="clip", status="confirmed", role="staff"):
    evidence = (Range(start, end, clip_id),) if clip_id else ()
    return CoverageFact(
        situation=situation,
        source=source,
        status=status,
        evidence=evidence,
        confirmed_role=role if status == "confirmed" else None,
    )


def clip(clip_id, duration, *, status="ready", deleted=False):
    return CoverageClip(id=clip_id, duration_s=duration, status=status, deleted=deleted)


def test_ut_cov_01_empty_dog():
    cov = compute_coverage([], [])
    assert [e.situation for e in cov.entries] == list(SITUATION_ORDER)
    assert cov.situations_covered == 0
    assert cov.covered == ()
    assert cov.not_observed == tuple(SITUATION_ORDER)
    assert all(not e.covered and e.clip_count == 0 for e in cov.entries)


def test_ut_cov_02_source_rules():
    facts = [
        cf("leash_walk", "a", 0, 5),
        cf("alone_time", "a", 0, 5, source="narration"),
        cf("handling", None, 0, 0, source="staff_note"),
        cf("other_dog", "a", 0, 5, status="draft"),
    ]
    cov = compute_coverage(facts, [clip("a", 20)])
    assert cov.covered == ("leash_walk",)


def test_ut_cov_03_only_ready_live_clips_count():
    facts = [
        cf("new_person", "ready", 0, 5),
        cf("handling", "gone", 0, 5),
        cf("leash_walk", "failed", 0, 5),
        cf("other_dog", "up", 0, 5),
    ]
    clips = [
        clip("ready", 20),
        clip("gone", 20, deleted=True),
        clip("failed", 20, status="failed"),
        clip("up", 20, status="uploaded"),
    ]
    assert compute_coverage(facts, clips).covered == ("new_person",)


def test_ut_cov_04_filmed_and_confirmed_seconds():
    facts = [cf("leash_walk", "a", 0, 8), cf("leash_walk", "a", 5, 10)]
    cov = compute_coverage(facts, [clip("a", 74)])
    entry = cov.entry("leash_walk")
    assert (entry.clip_count, entry.filmed_s, entry.confirmed_s) == (1, 74, 10)
    assert entry.confirmed_s <= entry.filmed_s


def test_ut_cov_05_clip_in_two_situations_counts_in_both():
    facts = [cf("leash_walk", "a", 0, 5), cf("handling", "a", 6, 9)]
    cov = compute_coverage(facts, [clip("a", 30)])
    assert cov.entry("leash_walk").clip_count == 1
    assert cov.entry("handling").clip_count == 1
    assert cov.situations_covered == 2


def test_ut_cov_06_rounding_of_sums():
    facts = [cf("leash_walk", "a", 0, 5), cf("leash_walk", "b", 0, 5)]
    cov = compute_coverage(facts, [clip("a", 10.4), clip("b", 20.5)])
    assert cov.entry("leash_walk").filmed_s == 31
    assert cov.entry("leash_walk").clip_count == 2


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from(SITUATION_ORDER),
            st.sampled_from(["clip", "narration", "staff_note"]),
            st.sampled_from(["draft", "confirmed", "deleted"]),
            st.sampled_from(["a", "b", "c"]),
            st.floats(min_value=0, max_value=40, allow_nan=False),
            st.floats(min_value=1, max_value=20, allow_nan=False),
            st.sampled_from(["staff", "volunteer"]),
        ),
        max_size=12,
    ),
    st.dictionaries(
        st.sampled_from(["a", "b", "c"]),
        st.tuples(
            st.floats(min_value=60, max_value=120, allow_nan=False),
            st.sampled_from(["ready", "failed", "uploaded", "processing"]),
            st.booleans(),
        ),
    ),
)
def test_ut_cov_07_property_not_observed_is_eight_minus_covered(rows, clip_rows):
    facts = [
        CoverageFact(
            situation=sit,
            source=src,
            status=status,
            evidence=(Range(start, start + length, cid),),
            confirmed_role=role if status == "confirmed" else None,
        )
        for sit, src, status, cid, start, length, role in rows
    ]
    clips = [CoverageClip(i, d, s, deleted) for i, (d, s, deleted) in clip_rows.items()]
    cov = compute_coverage(facts, clips)
    assert len(cov.covered) + len(cov.not_observed) == 8
    assert not set(cov.covered) & set(cov.not_observed)
    order = {s: i for i, s in enumerate(SITUATION_ORDER)}
    assert list(cov.covered) == sorted(cov.covered, key=order.get)
    assert list(cov.not_observed) == sorted(cov.not_observed, key=order.get)
    assert cov.situations_covered == len(cov.covered)
    for entry in cov.entries:
        assert entry.confirmed_s <= entry.filmed_s


def test_ut_cov_08_children_cats_needs_a_staff_confirmed_clip_fact():
    volunteer_fact = cf("children_cats", "a", 0, 5, role="volunteer")
    staff_fact = cf("children_cats", "a", 0, 5, role="staff")
    clips = [clip("a", 20)]
    assert "children_cats" not in compute_coverage([volunteer_fact], clips).covered
    assert "children_cats" in compute_coverage([staff_fact], clips).covered
