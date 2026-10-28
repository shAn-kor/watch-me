"""API-EDT, API-DLF, API-ADD (07 section 3.10)."""

from __future__ import annotations

import unicodedata
from datetime import date

from tests.api._s4_support import (  # noqa: F401
    add,
    code,
    confirm,
    delete,
    events,
    evidence_rows,
    fresh_fact,
    patch,
    play,
    play_all,
    rv,
    world,
)

# ------------------------------------------------------------------ API-EDT


def test_api_edt_01_edit_behavior(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    r = patch(client, token, rv.f_clip1, behavior="Walked beside the handler on a loose leash.")
    assert r.status_code == 200, r.text
    fact = r.json()["fact"]
    assert fact["origin"] == "human_edited"
    assert fact["behavior"] == "Walked beside the handler on a loose leash."
    assert fact["flags"] == []

    # rule flags are recomputed on the new text
    r = patch(client, token, rv.f_clip1, behavior="A friendly dog that walks well.")
    assert r.status_code == 200
    flags = r.json()["fact"]["flags"]
    assert [(f["code"], f["severity"], f["source"]) for f in flags] == [("banned_word", "warn", "rules")]
    assert "friendly" in flags[0]["detail"]
    assert fresh_fact(db, rv.f_clip1.id).flags[0]["code"] == "banned_word"


def test_api_edt_02_edit_keeps_human_added(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    r = add(client, token, rv.dog, situation="food_toys", behavior="Dropped the toy when asked.", evidence=[
        {"clip_id": rv.clip.id, "start_s": 2.0, "end_s": 6.0}
    ])
    assert r.status_code == 201, r.text
    fid = r.json()["fact"]["id"]
    r = client.patch(
        f"/api/facts/{fid}", json={"behavior": "Dropped the toy twice when asked."},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200, r.text
    assert r.json()["fact"]["origin"] == "human_added"


def test_api_edt_03_edit_demotes_confirmed(client, db, seed, rv, world, login_as):
    confirmed = seed.fact(
        rv.dog, status="confirmed", session=world.session_review, clip=rv.clip, confirmed_by=world.vol1
    )
    token = login_as(world.vol1)
    r = patch(client, token, confirmed, behavior="Walks calmly next to the handler.")
    assert r.status_code == 200, r.text
    fact = r.json()["fact"]
    assert fact["status"] == "draft"
    assert fact["confirmed"] is None
    row = fresh_fact(db, confirmed.id)
    assert (row.status, row.confirmed_by, row.confirmed_role, row.confirmed_at) == ("draft", None, None, None)
    # nothing confirmed remains for the dog's public set (I-1)
    from sqlalchemy import select

    from app.models import Fact

    remaining = db.scalars(
        select(Fact.id).where(Fact.dog_id == rv.dog.id, Fact.status == "confirmed")
    ).all()
    assert confirmed.id not in remaining


def test_api_edt_04_edit_evidence_replaces_rows(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    first, second = rv.f_two.evidence
    play_all(client, token, rv.f_two)
    assert len(events(db, rv.f_two.id)) == 2
    r = patch(
        client,
        token,
        rv.f_two,
        evidence=[
            {"id": first.id, "clip_id": first.clip_id, "start_s": first.start_s, "end_s": first.end_s},
            {"clip_id": rv.clip.id, "start_s": second.start_s, "end_s": second.end_s + 2.0},
        ],
    )
    assert r.status_code == 200, r.text
    ids = [e["id"] for e in r.json()["fact"]["evidence"]]
    assert first.id in ids
    assert second.id not in ids
    new_id = next(i for i in ids if i != first.id)
    remaining = events(db, rv.f_two.id)
    assert [e.evidence_id for e in remaining] == [first.id]
    assert {row.id for row in evidence_rows(db, rv.f_two.id)} == {first.id, new_id}
    r = confirm(client, token, rv.f_two)
    assert (r.status_code, code(r)) == (409, "playback_required")
    assert r.json()["error"]["details"]["missing_evidence_ids"] == [new_id]


def test_api_edt_05_evidence_limits(client, seed, rv, world, login_as):
    token = login_as(world.vol1)
    clip = rv.clip  # 20 s
    long_clip = seed.clip(seed.session(rv.dog, world.vol1, status="review"), 1, duration_s=100.0)
    other_dog = seed.dog(world.org_a, world.staff1, name="Other")
    other_clip = seed.clip(seed.session(other_dog, world.vol1, status="review"), 1)

    def ev(clip_id, a, b):
        return {"clip_id": clip_id, "start_s": a, "end_s": b}

    # 4 ranges
    r = patch(client, token, rv.f_clip1, evidence=[ev(clip.id, i * 4.0, i * 4.0 + 2.0) for i in range(4)])
    assert (r.status_code, code(r)) == (422, "validation_error")
    field = r.json()["error"]["details"]["fields"][0]
    assert field["problem"] == "too_long" and field["limit"] == 3  # exact problem value: verify
    # empty list on a clip fact
    r = patch(client, token, rv.f_clip1, evidence=[])
    assert (r.status_code, code(r)) == (422, "validation_error")
    assert r.json()["error"]["details"]["fields"][0]["problem"] == "evidence_required"
    # out of range: past clip end, 0.9 s, 61 s, other dog's clip
    for bad in (
        ev(clip.id, 15.0, 21.0),
        ev(clip.id, 2.0, 2.9),
        ev(long_clip.id, 0.0, 61.0),
        ev(other_clip.id, 1.0, 4.0),
    ):
        r = patch(client, token, rv.f_clip1, evidence=[bad])
        assert (r.status_code, code(r)) == (422, "evidence_out_of_range"), bad
    # a clip that is not ready
    sess2 = seed.session(rv.dog, world.vol1, status="review")
    pending = seed.clip(sess2, 1, status="processing")
    r = patch(client, token, rv.f_clip1, evidence=[ev(pending.id, 1.0, 4.0)])
    assert (r.status_code, code(r)) == (409, "clip_not_ready")
    # boundaries are valid: exactly 1.0 s and exactly 60 s
    assert patch(client, token, rv.f_clip1, evidence=[ev(clip.id, 2.0, 3.0)]).status_code == 200
    assert patch(client, token, rv.f_clip1, evidence=[ev(long_clip.id, 10.0, 70.0)]).status_code == 200


def test_api_edt_06_text_validation(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    for bad in ("ab", "x" * 281, "Walks\nslowly"):
        r = patch(client, token, rv.f_clip1, behavior=bad)
        assert (r.status_code, code(r)) == (422, "validation_error"), bad
    problems = {
        "ab": "too_short",
        "x" * 281: "too_long",
    }
    for bad, problem in problems.items():
        r = patch(client, token, rv.f_clip1, behavior=bad)
        assert r.json()["error"]["details"]["fields"][0]["problem"] == problem
    nfd = unicodedata.normalize("NFD", "Café visitor greeted calmly")
    assert nfd != unicodedata.normalize("NFC", nfd)
    r = patch(client, token, rv.f_clip1, behavior="  " + nfd + "  ")
    assert r.status_code == 200, r.text
    assert fresh_fact(db, rv.f_clip1.id).behavior == unicodedata.normalize("NFC", nfd)


def test_api_edt_07_edit_situation(client, db, seed, rv, world, login_as):
    confirmed = seed.fact(
        rv.dog, status="confirmed", session=world.session_review, clip=rv.clip, confirmed_by=world.vol1
    )
    token = login_as(world.vol1)
    r = patch(client, token, confirmed, situation="children_cats")
    assert r.status_code == 200, r.text
    assert r.json()["fact"]["status"] == "draft"
    assert r.json()["fact"]["situation"] == "children_cats"
    play_all(client, token, confirmed)
    r = confirm(client, token, confirmed)
    assert (r.status_code, code(r)) == (403, "staff_only_situation")
    r = patch(client, token, confirmed, situation="not_a_situation")
    assert (r.status_code, code(r)) == (422, "validation_error")


def test_api_edt_08_edit_guards(client, seed, rv, world, login_as):
    token2 = login_as(world.vol2)
    r = patch(client, token2, rv.f_clip1, behavior="Walks beside the handler.")
    assert (r.status_code, code(r)) == (403, "not_own_session")
    token = login_as(world.vol1)
    unmerged = seed.fact(rv.dog, merged=False, session=world.session_review, clip=rv.clip)
    deleted = seed.fact(rv.dog, status="deleted", session=world.session_review, clip=rv.clip)
    for fact in (unmerged, deleted):
        r = patch(client, token, fact, behavior="Walks beside the handler.")
        assert (r.status_code, code(r)) == (404, "not_found")
    # staff may edit any fact; a deleted dog hides its facts
    token_s = login_as(world.staff1)
    assert patch(client, token_s, rv.f_other, behavior="Waits at the door.").status_code == 200
    gone = seed.fact(world.dog_deleted, session=seed.session(world.dog_deleted, world.vol1), clip=None)
    r = patch(client, token_s, gone, behavior="Waits at the door.")
    assert (r.status_code, code(r)) == (404, "not_found")


def test_api_edt_09_unchanged_patch_keeps_origin(client, db, seed, rv, world, login_as):
    token = login_as(world.vol1)
    r = patch(client, token, rv.f_clip1, behavior=rv.f_clip1.behavior)
    assert r.status_code == 200
    assert r.json()["fact"]["origin"] == "ai_unchanged"
    confirmed = seed.fact(
        rv.dog, status="confirmed", session=world.session_review, clip=rv.clip, confirmed_by=world.vol1
    )
    ev = confirmed.evidence[0]
    r = patch(
        client, token, confirmed,
        behavior=confirmed.behavior, situation=confirmed.situation,
        evidence=[{"id": ev.id, "clip_id": ev.clip_id, "start_s": ev.start_s, "end_s": ev.end_s}],
    )
    assert r.status_code == 200, r.text
    assert r.json()["fact"]["status"] == "confirmed"
    assert r.json()["fact"]["origin"] == "ai_unchanged"
    assert fresh_fact(db, confirmed.id).status == "confirmed"


# ------------------------------------------------------------------ API-DLF


def test_api_dlf_01_delete_fact(client, db, seed, rv, world, login_as):
    token = login_as(world.vol1)
    play_all(client, token, rv.f_clip1)
    confirmed = seed.fact(
        rv.dog, status="confirmed", session=world.session_review, clip=rv.clip, confirmed_by=world.vol1
    )
    for fact in (rv.f_clip1, confirmed):
        r = delete(client, token, fact)
        assert r.status_code == 204, r.text
        assert r.content == b""
        row = fresh_fact(db, fact.id)
        assert row.status == "deleted"
        assert row.deleted_at is not None
        assert row.deleted_by == world.vol1.id
        assert (row.confirmed_at, row.confirmed_role, row.confirmed_by) == (None, None, None)
        assert evidence_rows(db, fact.id) == []
        assert events(db, fact.id) == []
        # the fact is gone from every route
        assert code(patch(client, token, fact, behavior="Anything at all.")) == "not_found"
        assert code(confirm(client, token, fact)) == "not_found"
        assert code(delete(client, token, fact)) == "not_found"


def test_api_dlf_02_delete_guards(client, rv, world, login_as):
    token2 = login_as(world.vol2)
    r = delete(client, token2, rv.f_clip1)
    assert (r.status_code, code(r)) == (403, "not_own_session")
    token_s = login_as(world.staff1)
    assert delete(client, token_s, rv.f_clip1).status_code == 204
    token_b = login_as(world.staff_b)
    r = delete(client, token_b, rv.f_two)
    assert (r.status_code, code(r)) == (404, "not_found")


def test_api_dlf_03_deleted_drafts_count_in_metric(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    assert delete(client, token, rv.f_clip1).status_code == 204
    assert fresh_fact(db, rv.f_clip1.id).origin == "ai_unchanged"  # row kept for REV-10
    login_as(world.staff1)
    r = client.get("/api/admin/metrics")
    assert r.status_code == 200
    assert r.json()["draft_acceptance"]["all_drafts"] >= 1


# ------------------------------------------------------------------ API-ADD


def test_api_add_01_add_fact_with_evidence(client, db, rv, world, login_as):
    token = login_as(world.vol1)
    r = add(
        client, token, rv.dog,
        situation="food_toys",
        behavior="Dropped the toy when asked, twice.",
        evidence=[{"clip_id": rv.clip.id, "start_s": 4.0, "end_s": 9.0}],
    )
    assert r.status_code == 201, r.text
    fact = r.json()["fact"]
    assert (fact["source"], fact["origin"], fact["status"]) == ("clip", "human_added", "draft")
    assert fact["session_id"] == world.session_review.id
    assert fact["created_by"] == world.vol1.id
    assert fact["flags"] == []
    assert fact["evidence"][0]["media_url"] == f"/media/{rv.clip.id}.mp4"
    row = fresh_fact(db, fact["id"])
    assert row.merged is True and row.dog_id == rv.dog.id
    # rule flags run on add
    r = add(
        client, token, rv.dog,
        situation="food_toys", behavior="A friendly dog.",
        evidence=[{"clip_id": rv.clip.id, "start_s": 4.0, "end_s": 9.0}],
    )
    assert [f["code"] for f in r.json()["fact"]["flags"]] == ["banned_word"]


def test_api_add_02_add_without_evidence(client, rv, world, login_as):
    token = login_as(world.staff1)
    r = add(
        client, token, rv.dog,
        situation="handling", behavior="Staff note: lets staff check the paws.",
        evidence=[], observed_on="2026-10-01",
    )
    assert r.status_code == 201, r.text
    fact = r.json()["fact"]
    assert (fact["source"], fact["origin"], fact["status"]) == ("staff_note", "human_added", "draft")
    assert fact["session_id"] is None
    assert fact["observed_on"] == "2026-10-01"
    assert fact["evidence"] == []
    assert fact["clip_length"]["label"] == "No clip"
    # default observed_on is today
    r = add(client, token, rv.dog, situation="handling", behavior="Another staff note here.")
    assert r.json()["fact"]["observed_on"] == "2026-10-28"


def test_api_add_03_add_guards(client, seed, rv, world, login_as):
    def ev(clip_id, a=2.0, b=6.0):
        return [{"clip_id": clip_id, "start_s": a, "end_s": b}]

    base = {"situation": "food_toys", "behavior": "Dropped the toy when asked."}
    token = login_as(world.vol1)
    r = add(client, token, rv.dog, evidence=ev(rv.clip_vol2.id), **base)
    assert (r.status_code, code(r)) == (403, "not_own_session")

    token_s = login_as(world.staff1)
    assert add(client, token_s, rv.dog, evidence=ev(rv.clip_vol2.id), **base).status_code == 201

    token = login_as(world.vol1)
    pending = seed.clip(seed.session(rv.dog, world.vol1, status="review"), 1, status="processing")
    r = add(client, token, rv.dog, evidence=ev(pending.id), **base)
    assert (r.status_code, code(r)) == (409, "clip_not_ready")

    r = add(client, token, rv.dog, evidence=ev(rv.clip.id, 15.0, 25.0), **base)
    assert (r.status_code, code(r)) == (422, "evidence_out_of_range")

    r = add(client, token, world.dog_deleted, evidence=[], **base)
    assert (r.status_code, code(r)) == (404, "not_found")

    r = add(client, token, world.dog_b, evidence=[], **base)
    assert (r.status_code, code(r)) == (404, "not_found")

    token_new = login_as(world.vol_new)
    r = add(client, token_new, rv.dog, evidence=[], **base)
    assert (r.status_code, code(r)) == (403, "consent_required")


def test_api_add_04_evidence_ignores_observed_on(client, seed, rv, world, login_as):
    sess = seed.session(rv.dog, world.vol1, status="review", observed_on=date(2026, 10, 20))
    clip = seed.clip(sess, 1)
    token = login_as(world.vol1)
    r = add(
        client, token, rv.dog,
        situation="food_toys", behavior="Dropped the toy when asked.",
        evidence=[{"clip_id": clip.id, "start_s": 2.0, "end_s": 6.0}],
        observed_on="2026-01-01",
    )
    assert r.status_code == 201, r.text
    assert r.json()["fact"]["observed_on"] == "2026-10-20"
    assert r.json()["fact"]["session_id"] == sess.id


def test_api_add_05_add_then_confirm_clip_fact(client, rv, world, login_as):
    token = login_as(world.vol1)
    r = add(
        client, token, rv.dog,
        situation="food_toys", behavior="Dropped the toy when asked, twice.",
        evidence=[{"clip_id": rv.clip.id, "start_s": 4.0, "end_s": 9.0}],
    )
    assert r.status_code == 201, r.text
    fact = r.json()["fact"]
    ev = fact["evidence"][0]
    assert play_raw(client, token, fact["id"], ev).status_code == 200
    r = client.post(f"/api/facts/{fact['id']}/confirm", json={}, headers={"X-CSRF-Token": token})
    assert r.status_code == 200, r.text
    assert r.json()["fact"]["status"] == "confirmed"


def play_raw(client, token, fact_id, ev):
    return client.post(
        f"/api/facts/{fact_id}/playback-complete",
        json={"evidence_id": ev["id"], "position_s": ev["end_s"], "watched_s": ev["end_s"] - ev["start_s"]},
        headers={"X-CSRF-Token": token},
    )
