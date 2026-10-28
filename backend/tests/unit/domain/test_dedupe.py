"""UT-DUP-01 to UT-DUP-06: within-clip and cross-clip duplicate handling (D3)."""

from __future__ import annotations

from app.domain.dedupe import (
    FactDraft,
    dedupe_within_clip,
    jaccard,
    merge_across_clips,
)
from app.domain.ranges import Range

# Tokens that survive normalization unchanged (no stop word, no -s/-ed/-ing).
POOL = [f"x{chr(97 + i)}x" for i in range(26)]


def words(*idx: int) -> str:
    return " ".join(POOL[i] for i in idx)


def fact(ref, text, rows, *, clip="c1", situation="leash_walk", source="clip"):
    return FactDraft(
        ref=ref,
        situation=situation,
        source=source,
        text=text,
        evidence=tuple(Range(s, e, clip) for s, e in rows),
        clip_id=clip,
    )


def test_jaccard_helper_uses_normalized_tokens():
    assert jaccard(words(0, 1, 2), words(0, 1, 3)) == 0.5
    assert jaccard("The dog walks, calmly!", "dog walk calmly") == 1.0


def test_ut_dup_01_rule_a_merges_with_union_of_evidence():
    a = fact("a", words(0, 1, 2), [(0, 10)])
    b = fact("b", words(0, 1, 3), [(4, 14), (30, 35)])  # 60% overlap, Jaccard 0.5
    result = dedupe_within_clip([a, b])
    assert [f.ref for f in result.facts] == ["b"]
    assert result.removed == ("a",)
    # a's range was merged into b, not lost (D3)
    assert result.facts[0].evidence == (Range(0, 14, "c1"), Range(30, 35, "c1"))


def test_ut_dup_01_below_overlap_is_not_a_rule_a_duplicate():
    a = fact("a", words(0, 1, 2), [(0, 10)])
    b = fact("b", words(0, 1, 3), [(5.5, 15)])  # 4.5/10 = 45% overlap
    assert dedupe_within_clip([a, b]).removed == ()


def test_ut_dup_01_tie_breaks_longer_text_then_earlier_start():
    a = fact("a", words(0, 1, 2), [(0, 10)])
    b = fact("b", "the " + words(0, 1, 2), [(2, 12)])  # same tokens, longer string
    assert [f.ref for f in dedupe_within_clip([a, b]).facts] == ["b"]
    c = fact("c", words(0, 1, 2), [(8, 18)])
    assert [f.ref for f in dedupe_within_clip([c, a]).facts] == ["a"]


def test_ut_dup_02_rule_b_text_similarity_ignores_ranges():
    shared = list(range(17))
    a = fact("a", words(*shared, 17), [(0, 5)])
    b = fact("b", words(*shared, 18, 19), [(50, 55)])  # 17/20 = 0.85
    assert jaccard(a.text, b.text) == 0.85
    result = dedupe_within_clip([a, b])
    assert len(result.facts) == 1 and len(result.removed) == 1


def test_ut_dup_02_jaccard_084_with_distant_ranges_is_not_duplicate():
    shared = list(range(21))
    a = fact("a", words(*shared, 21, 22), [(0, 5)])
    b = fact("b", words(*shared, 23, 24), [(50, 55)])  # 21/25 = 0.84
    result = dedupe_within_clip([a, b])
    assert len(result.facts) == 2 and result.removed == ()


def test_ut_dup_03_clip_beats_narration():
    shared = list(range(17))
    clip = fact("clip", words(*shared, 17), [(0, 5)])
    narr = fact("narr", words(*shared, 18, 19), [(50, 55)], source="narration")
    result = dedupe_within_clip([narr, clip])
    assert [f.ref for f in result.facts] == ["clip"]
    assert result.removed == ("narr",)
    assert result.facts[0].evidence == (Range(0, 5, "c1"),)


def test_ut_dup_04_cross_clip_same_source_merges_into_longer_text():
    shared = list(range(17))
    a = fact("a", words(*shared, 17), [(0, 5)], clip="c1")
    b = fact("b", words(*shared, 18, 19), [(10, 15)], clip="c2")
    result = merge_across_clips([a, b])
    assert [f.ref for f in result.facts] == ["b"]
    assert result.removed == ("a",)
    assert set(result.facts[0].evidence) == {Range(10, 15, "c2"), Range(0, 5, "c1")}


def test_ut_dup_04_jaccard_084_keeps_both():
    shared = list(range(21))
    a = fact("a", words(*shared, 21, 22), [(0, 5)], clip="c1")
    b = fact("b", words(*shared, 23, 24), [(0, 5)], clip="c2")
    result = merge_across_clips([a, b])
    assert len(result.facts) == 2 and result.removed == ()


def test_ut_dup_04_same_situation_required():
    a = fact("a", words(0, 1, 2), [(0, 5)], clip="c1", situation="handling")
    b = fact("b", words(0, 1, 2), [(0, 5)], clip="c2", situation="leash_walk")
    assert merge_across_clips([a, b]).removed == ()


def test_ut_dup_05_cross_clip_merge_caps_evidence_at_three_longest_first():
    a = fact("a", words(0, 1, 2), [(0, 5), (10, 12)], clip="c1")
    b = fact("b", "the " + words(0, 1, 2), [(0, 20), (30, 33)], clip="c2")
    merged = merge_across_clips([a, b]).facts[0]
    assert merged.ref == "b"
    assert merged.evidence == (
        Range(0, 20, "c2"),
        Range(0, 5, "c1"),
        Range(30, 33, "c2"),
    )


def test_ut_dup_05_touching_ranges_merge_before_the_cap():
    a = fact("a", words(0, 1, 2), [(0, 5), (5, 10)], clip="c1")
    b = fact("b", "the " + words(0, 1, 2), [(0, 3), (20, 22)], clip="c2")
    merged = merge_across_clips([a, b]).facts[0]
    assert merged.evidence == (
        Range(0, 10, "c1"),
        Range(0, 3, "c2"),
        Range(20, 22, "c2"),
    )


def test_ut_dup_06_clip_beats_narration_across_clips_without_merge():
    clip = fact("clip", words(0, 1, 2, 3, 4, 5, 6, 7, 8, 9), [(0, 5)], clip="c1")
    narr = fact(
        "narr", words(0, 1, 2, 3, 4, 5, 6, 7, 8), [(2, 6)], clip="c2", source="narration"
    )
    result = merge_across_clips([clip, narr])  # Jaccard 0.9
    assert [f.ref for f in result.facts] == ["clip"]
    assert result.removed == ("narr",)
    assert result.facts[0].evidence == (Range(0, 5, "c1"),)


def test_ut_dup_06_low_similarity_clip_and_narration_both_stay():
    clip = fact("clip", words(0, 1, 2), [(0, 5)], clip="c1")
    narr = fact("narr", words(0, 1, 3), [(2, 6)], clip="c2", source="narration")
    result = merge_across_clips([clip, narr])  # Jaccard 0.5
    assert len(result.facts) == 2 and result.removed == ()
