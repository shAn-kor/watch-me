"""Lane S6: UT-QA-01..10 (07 section 3.4): AliasMapper, selector output shape,
AnswerRenderer, render templates, CostCapGuard."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

import pytest

from app.ai.adapters.openai_compat import OpenAICompatSelector
from app.ai.cost import PriceTable
from app.ai.types import SelectRequest
from app.errors import QaCostCapReached
from app.repositories.public_facts import PublicEvidence, PublicFact
from app.services.qa_alias import AliasMapper
from app.services.qa_limits import CostCapGuard
from app.services.qa_render import AnswerRenderer, QaContact
from app.services.views import MediaUrls
from tests.unit.ai_helpers import FakeHttp, ok

HEX32 = re.compile(r"[0-9a-f]{32}")
SITUATIONS = [
    "new_person", "handling", "leash_walk", "other_dog", "food_toys", "alone_time",
    "indoors_rest", "children_cats",
]


def pfact(i: int, behavior: str | None = None, *, situation: str | None = None, **kw) -> PublicFact:
    base = dict(
        id=f"{i:032x}",
        dog_id="d" * 32,
        situation=situation or SITUATIONS[i % 8],
        behavior=behavior or f"Behavior number {i}.",
        source="clip",
        observed_on=date(2026, 10, 28),
        confirmed_at=datetime(2026, 10, 28, 12, tzinfo=UTC),
        confirmed_role="volunteer",
        created_at=datetime(2026, 10, 28, 11, tzinfo=UTC),
        evidence=(PublicEvidence(clip_id="c" * 32, start_s=1.0, end_s=4.0, has_transcript=True),),
    )
    base.update(kw)
    return PublicFact(**base)


@pytest.fixture
def facts7() -> list[PublicFact]:
    return [pfact(i) for i in range(1, 8)]


# ---------------------------------------------------------------- AliasMapper


def test_ut_qa_01_alias_build(facts7):
    table = AliasMapper(max_facts=5).build(facts7)
    assert [f.ref for f in table.fact_refs] == [f"F{i}" for i in range(1, 8)]
    assert [f.behavior for f in table.fact_refs] == [f.behavior for f in facts7]
    assert not HEX32.search(repr([f.model_dump() for f in table.fact_refs]))
    again = AliasMapper(max_facts=5).build(list(reversed(facts7)))
    assert again.fact_refs[0].behavior == facts7[-1].behavior  # per-request, by input order


def test_ut_qa_01_alias_build_cuts_at_100():
    table = AliasMapper(max_facts=5).build([pfact(i) for i in range(1, 131)])
    assert len(table.fact_refs) == 100 and table.fact_refs[-1].ref == "F100"


def test_ut_qa_02_resolve_in_set_refs(facts7):
    mapper = AliasMapper(max_facts=5)
    sel = mapper.resolve(mapper.build(facts7), ["F2", "F5"])
    assert sel.fact_ids == (facts7[1].id, facts7[4].id) and sel.dropped == 0


def test_ut_qa_03_resolve_unknown_ref(facts7):
    mapper = AliasMapper(max_facts=5)
    sel = mapper.resolve(mapper.build(facts7), ["F2", "F99", "", "F-3", "F3x"])
    assert sel.fact_ids == (facts7[1].id,) and sel.dropped == 4


def test_ut_qa_04_resolve_raw_id(facts7):
    mapper = AliasMapper(max_facts=5)
    sel = mapper.resolve(mapper.build(facts7), [facts7[0].id, "0123456789abcdef0123456789abcdef"])
    assert sel.fact_ids == () and sel.dropped == 2


def test_ut_qa_05_resolve_duplicates_and_cap(facts7):
    mapper = AliasMapper(max_facts=5)
    sel = mapper.resolve(mapper.build(facts7), ["F1", "F1", "F2", "F3", "F4", "F5", "F6", "F7"])
    assert sel.fact_ids == tuple(f.id for f in facts7[:5]) and sel.dropped == 0


def test_ut_qa_10_resolve_normalization(facts7):
    mapper = AliasMapper(max_facts=5)
    sel = mapper.resolve(mapper.build(facts7), ["f3", " F5 ", "F 7"])
    assert sel.dropped == 0
    assert set(sel.fact_ids) == {facts7[2].id, facts7[4].id, facts7[6].id}
    sel = mapper.resolve(mapper.build(facts7), ["F5", "f3"])
    assert sel.fact_ids == (facts7[4].id, facts7[2].id)  # the model's order is kept here ...
    assert sel.in_profile_order == (facts7[2].id, facts7[4].id)  # ... and re-sorted for rendering


# ------------------------------------------------------- selector output shape


@pytest.mark.parametrize(
    "bad", ['{"refs": {"a": 1}}', '"F1"', "[1, 2]", '{"refs": [1, 2]}', '{"refs": "F1"}'],
    ids=["object", "string", "list-of-numbers", "numbers-in-refs", "refs-string"],
)
def test_ut_qa_06_selector_output_shape_is_never_coerced(bad):
    http = FakeHttp(ok(bad), ok('{"refs": ["F1"]}'))
    selector = OpenAICompatSelector(http.chat(), PriceTable.from_dict({}), strict=True)
    req = SelectRequest(question="Does he like walks?", facts=AliasMapper(5).build([pfact(1)]).fact_refs)
    out, usages = selector.select(req)
    assert out.refs == ["F1"]
    assert http.calls == 2 and len(usages) == 2  # the invalid shape went to the retry path


# ------------------------------------------------------------- AnswerRenderer


def test_ut_qa_07_answer_renderer_text_is_the_fact_text():
    evil = "<img src=x onerror=alert(1)>"
    render = AnswerRenderer(MediaUrls())
    answer = render.answered([pfact(1, evil), pfact(2)])
    assert answer.outcome == "answered"
    assert answer.heading == "Here is what has been filmed:"
    assert answer.lines[0].text == evil and answer.lines[1].text == "Behavior number 2."
    assert answer.cited_fact_ids == (pfact(1).id, pfact(2).id)
    assert answer.hint is None and answer.contact is None
    line = answer.lines[0]
    assert line.situation == "handling" and line.situation_label == "Handling"
    assert line.source_label == "Seen in clip" and line.confirmed_by_label == "Confirmed by volunteer"
    assert line.clip_length.label == "1 clip, 3 s"
    assert line.evidence[0].media_url == "/media/" + "c" * 32 + ".mp4"
    assert line.evidence[0].captions_url == "/media/" + "c" * 32 + ".vtt"


def test_ut_qa_07_children_cats_line_carries_the_notice():
    render = AnswerRenderer(MediaUrls())
    line = render.answered([pfact(8, situation="children_cats", confirmed_role="staff")]).lines[0]
    assert line.notice.code == "ask_shelter_in_person_meeting"
    assert line.notice.text == "Ask the shelter about an in-person meeting."
    assert line.confirmed_by_label == "Confirmed by staff"
    assert render.answered([pfact(1)]).lines[0].notice is None


def test_ut_qa_07_staff_note_and_narration_labels():
    render = AnswerRenderer(MediaUrls())
    note = render.answered([pfact(1, source="staff_note", evidence=())]).lines[0]
    assert note.source_label == "Shelter staff note" and note.clip_length.label == "No clip"
    assert note.evidence == ()
    narr = render.answered([pfact(2, source="narration")]).lines[0]
    assert narr.source_label == "Said by volunteer, not in clip"
    assert narr.clip_length.label == "Narration only, 3 s"


def test_ut_qa_08_render_templates():
    render = AnswerRenderer(MediaUrls())
    none = render.not_observed()
    assert (none.outcome, none.heading) == ("not_observed", "Not observed yet.")
    assert none.hint == "Check the list of situations that have not been filmed, or ask the shelter."
    assert none.lines == () and none.cited_fact_ids == () and none.contact is None
    health = render.health_redirect(QaContact(url=None, email="adopt@example.org", phone=None))
    assert (health.outcome, health.heading) == ("health_redirect", "Ask the shelter's vet.")
    assert health.hint == "Health information comes from the shelter, not from these clips."
    assert health.contact == QaContact(url=None, email="adopt@example.org", phone=None)
    assert health.lines == ()


# ---------------------------------------------------------------- CostCapGuard


def test_ut_qa_09_cost_cap_guard(seed, db, clock, settings):
    assert settings.qa_daily_usd_cap == 3.00
    guard = CostCapGuard(clock, settings.qa_daily_usd_cap)
    now = clock.now()
    seed.ledger("qa_select", usd_micros=2_999_999, created_at=now)
    seed.ledger("draft", usd_micros=9_000_000, created_at=now)
    seed.ledger("transcribe", usd_micros=9_000_000, created_at=now)
    seed.ledger("qa_select", usd_micros=9_000_000, created_at=now - timedelta(days=1))
    guard.ensure_below_cap(db)  # 2,999,999 passes
    seed.ledger("qa_select", usd_micros=1, created_at=now)
    db.expire_all()
    with pytest.raises(QaCostCapReached) as err:
        guard.ensure_below_cap(db)  # exactly 3,000,000 is at the cap
    assert err.value.retry_after_s == 12 * 3600  # 12:00 UTC to the next 00:00 UTC


def test_ut_qa_09_the_day_starts_at_utc_midnight(seed, db, clock):
    guard = CostCapGuard(clock, 3.00)
    midnight = clock.now().replace(hour=0, minute=0, second=0)
    seed.ledger("qa_select", usd_micros=3_000_000, created_at=midnight - timedelta(seconds=1))
    guard.ensure_below_cap(db)  # yesterday's spend is ignored
    seed.ledger("qa_select", usd_micros=3_000_000, created_at=midnight)
    db.expire_all()
    with pytest.raises(QaCostCapReached):
        guard.ensure_below_cap(db)  # a row at exactly 00:00:00 UTC counts


def test_ut_qa_09_cap_scales_with_the_setting(seed, db, clock):
    seed.ledger("qa_select", usd_micros=500_000, created_at=clock.now())
    with pytest.raises(QaCostCapReached):
        CostCapGuard(clock, 0.50).ensure_below_cap(db)
    CostCapGuard(clock, 0.51).ensure_below_cap(db)
