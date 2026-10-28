"""UT-CNF-01 to UT-CNF-07: ConfirmPolicy guard order (02 section 3.4, F5)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain.confirm_policy import (
    ActorInfo,
    ConfirmContext,
    ConfirmPolicy,
    DogInfo,
    EvidenceInfo,
    FactInfo,
    PlaybackSnapshot,
    missing_playback_evidence_ids,
)

POLICY = ConfirmPolicy()
WARN = {"code": "banned_word", "severity": "warn", "source": "rules", "detail": "x"}
INFO = {"code": "check_unavailable", "severity": "info", "source": "system", "detail": "x"}


def make_ctx(**over) -> ConfirmContext:
    evidence = (EvidenceInfo("e1", 12.0, 21.0), EvidenceInfo("e2", 30.0, 35.0))
    ctx = ConfirmContext(
        fact=FactInfo(
            id="f1",
            org_id="org",
            status="draft",
            merged=True,
            situation="leash_walk",
            source="clip",
            session_id="s1",
            session_owner_id="vol1",
            flags=(),
        ),
        dog=DogInfo(status="draft", people_check_at=None),
        actor=ActorInfo(id="vol1", org_id="org", role="volunteer", consent_accepted=True),
        evidence=evidence,
        events=(
            PlaybackSnapshot("e1", "vol1", 12.0, 21.0),
            PlaybackSnapshot("e2", "vol1", 30.0, 35.0),
        ),
        acknowledge_flags=False,
    )
    return replace(ctx, **over)


def with_fact(ctx, **over):
    return replace(ctx, fact=replace(ctx.fact, **over))


def with_actor(ctx, **over):
    return replace(ctx, actor=replace(ctx.actor, **over))


def test_ut_cnf_02_allowed_row():
    assert POLICY.evaluate(make_ctx()) is None


def _violate_all() -> ConfirmContext:
    ctx = make_ctx()
    ctx = with_fact(
        ctx, situation="children_cats", status="confirmed", flags=(WARN,), session_owner_id="other"
    )
    ctx = with_actor(ctx, consent_accepted=False)
    return replace(ctx, dog=DogInfo("published", None), events=())


def test_ut_cnf_01_guard_order():
    # Each step removes the earliest remaining violation; the code must follow
    # the documented order: not_found, consent_required, invalid_state,
    # staff_only_situation, not_own_session, playback_required,
    # flags_unacknowledged, publish_checklist_incomplete.
    ctx = _violate_all()
    assert POLICY.evaluate(replace(ctx, fact=None)) == "not_found"
    assert POLICY.evaluate(with_actor(ctx, org_id="elsewhere")) == "not_found"
    assert POLICY.evaluate(ctx) == "consent_required"
    ctx = with_actor(ctx, consent_accepted=True)
    assert POLICY.evaluate(ctx) == "invalid_state"
    ctx = with_fact(ctx, status="draft")
    assert POLICY.evaluate(with_fact(ctx, merged=False)) == "invalid_state"
    assert POLICY.evaluate(ctx) == "staff_only_situation"
    ctx = with_fact(ctx, situation="leash_walk")
    assert POLICY.evaluate(ctx) == "not_own_session"
    ctx = with_fact(ctx, session_owner_id="vol1")
    assert POLICY.evaluate(ctx) == "playback_required"
    ctx = replace(
        ctx,
        events=(PlaybackSnapshot("e1", "vol1", 12.0, 21.0), PlaybackSnapshot("e2", "vol1", 30.0, 35.0)),
    )
    assert POLICY.evaluate(ctx) == "flags_unacknowledged"
    ctx = replace(ctx, acknowledge_flags=True)
    assert POLICY.evaluate(ctx) == "publish_checklist_incomplete"
    ctx = replace(ctx, dog=DogInfo("published", "2026-10-28"))
    assert POLICY.evaluate(ctx) is None


def test_ut_cnf_01_volunteer_without_session_gets_forbidden_role():
    ctx = with_fact(make_ctx(), session_id=None, session_owner_id=None)
    assert POLICY.evaluate(ctx) == "forbidden_role"


def test_ut_cnf_03_snapshot_must_match_current_range():
    ctx = replace(
        make_ctx(),
        events=(PlaybackSnapshot("e1", "vol1", 12.0, 22.0), PlaybackSnapshot("e2", "vol1", 30.0, 35.0)),
    )
    assert POLICY.evaluate(ctx) == "playback_required"
    assert missing_playback_evidence_ids(ctx) == ("e1",)


def test_ut_cnf_04_event_of_another_member_does_not_count():
    ctx = replace(
        make_ctx(),
        events=(PlaybackSnapshot("e1", "vol2", 12.0, 21.0), PlaybackSnapshot("e2", "vol2", 30.0, 35.0)),
    )
    assert POLICY.evaluate(ctx) == "playback_required"
    assert missing_playback_evidence_ids(ctx) == ("e1", "e2")


def test_ut_cnf_05_staff_note():
    note = with_fact(
        make_ctx(),
        source="staff_note",
        session_id=None,
        session_owner_id=None,
    )
    note = replace(note, evidence=(), events=())
    assert POLICY.evaluate(note) == "forbidden_role"
    staff = with_actor(note, id="staff1", role="staff")
    assert POLICY.evaluate(staff) is None


def test_ut_cnf_05_staff_confirms_children_cats_volunteer_may_not():
    ctx = with_fact(make_ctx(), situation="children_cats")
    assert POLICY.evaluate(ctx) == "staff_only_situation"
    staff = with_actor(ctx, id="staff1", role="staff")
    staff = replace(
        staff,
        events=(PlaybackSnapshot("e1", "staff1", 12.0, 21.0), PlaybackSnapshot("e2", "staff1", 30.0, 35.0)),
    )
    assert POLICY.evaluate(staff) is None


def test_ut_cnf_06_published_dog_safety_net():
    ctx = replace(make_ctx(), dog=DogInfo(status="published", people_check_at=None))
    assert POLICY.evaluate(ctx) == "publish_checklist_incomplete"
    ok = replace(make_ctx(), dog=DogInfo(status="published", people_check_at="2026-10-28"))
    assert POLICY.evaluate(ok) is None


@pytest.mark.parametrize(
    ("flags", "acknowledged", "expected"),
    [
        ((WARN,), False, "flags_unacknowledged"),
        ((WARN,), True, None),
        ((INFO,), False, None),
    ],
)
def test_ut_cnf_07_flags_acknowledged(flags, acknowledged, expected):
    ctx = with_fact(make_ctx(), flags=flags)
    ctx = replace(ctx, acknowledge_flags=acknowledged)
    assert POLICY.evaluate(ctx) == expected
