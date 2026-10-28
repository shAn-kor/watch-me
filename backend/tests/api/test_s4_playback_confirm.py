"""API-PBK and API-CFM (07 section 3.10)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.api._s1_support import csrf
from tests.api._s4_support import (  # noqa: F401
    code,
    confirm,
    events,
    fresh_fact,
    patch,
    play,
    play_all,
    rv,
    world,
)

# ------------------------------------------------------------------ API-PBK


def test_api_pbk_01_playback_complete_ok(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    ev = rv.f_clip1.evidence[0]
    length = ev.end_s - ev.start_s
    r = play(client, token, rv.f_clip1, ev, position_s=ev.end_s, watched_s=0.9 * length)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fact_id"] == rv.f_clip1.id
    assert body["evidence_id"] == ev.id
    assert body["all_ranges_played"] is True
    assert body["completed_at"].endswith("Z")
    rows = events(db, rv.f_clip1.id)
    assert len(rows) == 1
    assert rows[0].member_id == world.vol1.id
    assert (rows[0].start_s, rows[0].end_s) == (ev.start_s, ev.end_s)
    assert rows[0].watched_s == pytest.approx(0.9 * length)


def test_api_pbk_02_playback_thresholds(client, rv, world, login_as):
    token = login_as(world.vol1)
    ev = rv.f_clip1.evidence[0]
    length = ev.end_s - ev.start_s

    r = play(client, token, rv.f_clip1, ev, position_s=ev.end_s - 0.6)
    assert r.status_code == 422
    assert code(r) == "validation_error"
    assert r.json()["error"]["details"]["fields"][0]["problem"] == "range_not_completed"

    assert play(client, token, rv.f_clip1, ev, position_s=ev.end_s - 0.5).status_code == 200

    r = play(client, token, rv.f_clip1, ev, watched_s=0.79 * length)
    assert r.status_code == 422
    assert r.json()["error"]["details"]["fields"][0]["problem"] == "range_not_completed"

    assert play(client, token, rv.f_clip1, ev, watched_s=0.8 * length).status_code == 200


def test_api_pbk_03_playback_upsert(client, db, rv, world, clock, login_as):
    token = login_as(world.vol1)
    ev = rv.f_clip1.evidence[0]
    first = play(client, token, rv.f_clip1, ev)
    assert first.status_code == 200
    clock.advance(60)
    second = play(client, token, rv.f_clip1, ev)
    assert second.status_code == 200
    assert len(events(db, rv.f_clip1.id)) == 1
    assert second.json()["completed_at"] > first.json()["completed_at"]


def test_api_pbk_04_partial_ranges(client, rv, world, login_as):
    token = login_as(world.vol1)
    first, second = rv.f_two.evidence
    r = play(client, token, rv.f_two, first)
    assert r.status_code == 200
    assert r.json()["all_ranges_played"] is False
    r = play(client, token, rv.f_two, second)
    assert r.json()["all_ranges_played"] is True


def test_api_pbk_05_playback_guards(client, seed, rv, world, login_as):
    token = login_as(world.vol1)
    other_fact_evidence = rv.f_flag.evidence[0]
    r = play(client, token, rv.f_clip1, other_fact_evidence)
    assert (r.status_code, code(r)) == (404, "not_found")

    confirmed = seed.fact(
        rv.dog, status="confirmed", session=world.session_review, clip=rv.clip, confirmed_by=world.vol1
    )
    r = play(client, token, confirmed, confirmed.evidence[0])
    assert (r.status_code, code(r)) == (409, "invalid_state")

    deleted = seed.fact(rv.dog, status="deleted", session=world.session_review, clip=rv.clip)
    r = play(client, token, deleted, deleted.evidence[0])
    assert (r.status_code, code(r)) == (404, "not_found")

    unmerged = seed.fact(
        rv.dog, merged=False, session=world.session_review, clip=rv.clip
    )
    r = play(client, token, unmerged, unmerged.evidence[0])
    assert (r.status_code, code(r)) == (404, "not_found")

    token2 = login_as(world.vol2)
    r = play(client, token2, rv.f_clip1, rv.f_clip1.evidence[0])
    assert (r.status_code, code(r)) == (403, "not_own_session")

    # staff may play any fact; another org gets not_found
    token_s = login_as(world.staff1)
    assert play(client, token_s, rv.f_clip1, rv.f_clip1.evidence[0]).status_code == 200
    token_b = login_as(world.staff_b)
    r = play(client, token_b, rv.f_clip1, rv.f_clip1.evidence[0])
    assert (r.status_code, code(r)) == (404, "not_found")


# ------------------------------------------------------------------ API-CFM


def test_api_cfm_01_confirm_after_playback(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    play_all(client, token, rv.f_clip1)
    r = confirm(client, token, rv.f_clip1)
    assert r.status_code == 200, r.text
    fact = r.json()["fact"]
    assert fact["status"] == "confirmed"
    assert fact["confirmed"]["role"] == "volunteer"
    assert fact["confirmed"]["by_member_id"] == world.vol1.id
    assert fact["confirmed"]["by_name"] == world.vol1.display_name
    assert fact["confirmed"]["at"].endswith("Z")
    row = fresh_fact(db, rv.f_clip1.id)
    assert (row.status, row.confirmed_role, row.confirmed_by) == (
        "confirmed",
        "volunteer",
        world.vol1.id,
    )
    assert row.confirmed_at is not None


def test_api_cfm_02_confirm_without_playback(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    r = confirm(client, token, rv.f_clip1)
    assert (r.status_code, code(r)) == (409, "playback_required")
    assert r.json()["error"]["details"]["missing_evidence_ids"] == [
        e.id for e in rv.f_clip1.evidence
    ]
    assert fresh_fact(db, rv.f_clip1.id).status == "draft"


def test_api_cfm_03_partial_playback(client, rv, world, login_as):
    token = login_as(world.vol1)
    first, second = rv.f_two.evidence
    play(client, token, rv.f_two, first)
    r = confirm(client, token, rv.f_two)
    assert (r.status_code, code(r)) == (409, "playback_required")
    assert r.json()["error"]["details"]["missing_evidence_ids"] == [second.id]


def test_api_cfm_04_playback_by_another_member(client, rv, world, login_as):
    token_s = login_as(world.staff1)
    play_all(client, token_s, rv.f_clip1)
    token = login_as(world.vol1)
    r = confirm(client, token, rv.f_clip1)
    assert (r.status_code, code(r)) == (409, "playback_required")


def test_api_cfm_05_range_changed_after_playback(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    ev = rv.f_clip1.evidence[0]
    play_all(client, token, rv.f_clip1)
    r = patch(
        client,
        token,
        rv.f_clip1,
        evidence=[
            {"clip_id": rv.clip.id, "start_s": ev.start_s, "end_s": ev.end_s + 1.0},
        ],
    )
    assert r.status_code == 200, r.text
    assert events(db, rv.f_clip1.id) == []
    r = confirm(client, token, rv.f_clip1)
    assert (r.status_code, code(r)) == (409, "playback_required")


def test_api_cfm_06_flags_need_acknowledgement(client, rv, world, login_as):
    token = login_as(world.vol1)
    play_all(client, token, rv.f_flag)
    r = confirm(client, token, rv.f_flag)
    assert (r.status_code, code(r)) == (409, "flags_unacknowledged")
    r = confirm(client, token, rv.f_flag, acknowledge_flags=True)
    assert r.status_code == 200, r.text


def test_api_cfm_07_situation_8_staff_only(client, rv, world, login_as):
    token = login_as(world.vol1)
    play_all(client, token, rv.f_c8)
    r = confirm(client, token, rv.f_c8, acknowledge_flags=True)
    assert (r.status_code, code(r)) == (403, "staff_only_situation")

    token_s = login_as(world.staff1)
    play_all(client, token_s, rv.f_c8)
    r = confirm(client, token_s, rv.f_c8, acknowledge_flags=True)
    assert r.status_code == 200, r.text
    assert r.json()["fact"]["confirmed"]["role"] == "staff"


def test_api_cfm_08_own_session_rule(client, rv, world, login_as):
    token = login_as(world.vol1)
    play(client, token, rv.f_other, rv.f_other.evidence[0])  # attempt; may be refused
    r = confirm(client, token, rv.f_other)
    assert (r.status_code, code(r)) == (403, "not_own_session")

    token_s = login_as(world.staff1)
    play_all(client, token_s, rv.f_other)
    r = confirm(client, token_s, rv.f_other)
    assert r.status_code == 200, r.text
    assert r.json()["fact"]["confirmed"]["role"] == "staff"


def test_api_cfm_09_staff_note(client, rv, world, login_as):
    token = login_as(world.vol1)
    r = confirm(client, token, rv.f_note)
    assert (r.status_code, code(r)) == (403, "forbidden_role")
    token_s = login_as(world.staff1)
    r = confirm(client, token_s, rv.f_note)
    assert r.status_code == 200, r.text
    assert r.json()["fact"]["confirmed"]["role"] == "staff"


def test_api_cfm_10_state_guards(client, seed, rv, world, login_as):
    token = login_as(world.vol1)
    confirmed = seed.fact(
        rv.dog, status="confirmed", session=world.session_review, clip=rv.clip, confirmed_by=world.vol1
    )
    r = confirm(client, token, confirmed)
    assert (r.status_code, code(r)) == (409, "invalid_state")
    deleted = seed.fact(rv.dog, status="deleted", session=world.session_review, clip=rv.clip)
    r = confirm(client, token, deleted)
    assert (r.status_code, code(r)) == (404, "not_found")
    unmerged = seed.fact(rv.dog, merged=False, session=world.session_review, clip=rv.clip)
    r = confirm(client, token, unmerged)
    assert (r.status_code, code(r)) == (404, "not_found")


def test_api_cfm_11_consent_before_state(client, rv, world, login_as):
    token = login_as(world.vol_new)
    r = confirm(client, token, rv.f_clip1)
    assert (r.status_code, code(r)) == (403, "consent_required")
    # consent also comes before the state guard
    r = confirm(client, token, rv.f_two)
    assert code(r) == "consent_required"


def test_api_cfm_12_published_dog_safety_net(db, world):
    """A published dog cannot lack a people check: the database refuses it, so the
    service guard is a safety net only (policy covered by UT-CNF-06)."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE dog SET status='published', people_check_at=NULL, public_slug='x' WHERE id=:i"),
            {"i": world.dog_empty.id},
        )
        db.flush()
    db.rollback()


def test_api_cfm_13_guard_order(client, seed, rv, world, login_as):
    """Volunteer, children_cats, other session, no playback, flags: errors come in
    the order of 02 section 3.4."""
    fact = seed.fact(
        rv.dog,
        situation="children_cats",
        behavior="Stays calm near a friendly cat.",
        session=rv.session_vol2,
        clip=rv.clip_vol2,
        flags=[{"code": "trait_claim", "severity": "warn", "source": "model", "detail": "x"}],
    )
    token = login_as(world.vol1)
    r = confirm(client, token, fact)
    assert code(r) == "staff_only_situation"

    token_s = login_as(world.staff1)  # staff: no ownership needed
    r = confirm(client, token_s, fact)
    assert code(r) == "playback_required"
    play_all(client, token_s, fact)
    r = confirm(client, token_s, fact)
    assert code(r) == "flags_unacknowledged"
    assert confirm(client, token_s, fact, acknowledge_flags=True).status_code == 200

    # volunteer on a normal fact of another session: ownership before playback
    other = seed.fact(
        rv.dog, session=rv.session_vol2, clip=rv.clip_vol2,
        flags=[{"code": "trait_claim", "severity": "warn", "source": "model", "detail": "x"}],
    )
    token = login_as(world.vol1)
    assert code(confirm(client, token, other)) == "not_own_session"


def test_api_cfm_14_can_confirm_and_blocked_reason(client, db, container, rv, world, login_as):
    """The Fact view carries `can_confirm` and `blocked_reason` (the same ConfirmPolicy).
    Read through the playback-then-confirm flow and the edit response, because the
    session GET belongs to lane S3."""
    token = login_as(world.vol1)

    def view(fact):
        r = patch(client, token, fact)  # an empty patch returns the current view
        assert r.status_code == 200, r.text
        return r.json()["fact"]

    v = view(rv.f_clip1)
    assert (v["can_confirm"], v["blocked_reason"]) == (False, "playback_required")
    play_all(client, token, rv.f_clip1)
    v = view(rv.f_clip1)
    assert (v["can_confirm"], v["blocked_reason"]) == (True, None)
    assert [e["played_by_me"] for e in v["evidence"]] == [True]

    v = view(rv.f_c8)
    assert (v["can_confirm"], v["blocked_reason"]) == (False, "staff_only_situation")
    # f_other belongs to vol2: vol1 may not even edit it, so read it as staff-less via vol2's
    # own view and check vol1's rule through the service
    from app.services.views import Principal

    svc = container.services.fact_review_service
    with container.uow() as uow:
        p = Principal(world.vol1.id, world.org_a.id, "volunteer", True, "sid")
        fv = svc.get_view(uow, p, rv.f_other.id)
    assert (fv.can_confirm, fv.blocked_reason) == (False, "not_own_session")


def test_api_cfm_15_rate_limit_on_writes(client, rv, world, login_as):
    token = login_as(world.vol1)
    for _ in range(120):
        assert patch(client, token, rv.f_clip1, behavior="Walks beside the handler.").status_code == 200
    r = patch(client, token, rv.f_clip1, behavior="Walks beside the handler.")
    assert (r.status_code, code(r)) == (429, "rate_limited")
    assert r.json()["error"]["details"]["scope"] == "member"
    assert "Retry-After" in r.headers


def test_api_cfm_16_flag_severities_and_acknowledgement(client, seed, rv, world, login_as):
    def flagged(*flags):
        return seed.fact(
            rv.dog,
            session=world.session_review,
            clip=rv.clip,
            flags=list(flags),
        )

    banned = flagged(
        {"code": "banned_word", "severity": "warn", "source": "rules", "detail": 'Banned wording: "friendly"'}
    )
    trait = flagged(
        {"code": "trait_claim", "severity": "warn", "source": "model", "detail": "Possible trait wording"}
    )
    info = flagged(
        {"code": "check_unavailable", "severity": "info", "source": "system", "detail": "The wording check did not run."}
    )
    token = login_as(world.vol1)
    for fact in (banned, trait, info):
        play_all(client, token, fact)
    assert code(confirm(client, token, banned)) == "flags_unacknowledged"
    assert code(confirm(client, token, trait)) == "flags_unacknowledged"
    r = confirm(client, token, info)
    assert r.status_code == 200, r.text
    flags = r.json()["fact"]["flags"]
    assert flags == [
        {
            "code": "check_unavailable",
            "severity": "info",
            "source": "system",
            "detail": "The wording check did not run.",
        }
    ]
