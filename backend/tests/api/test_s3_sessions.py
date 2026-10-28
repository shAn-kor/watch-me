"""API-SES and API-RMG (07 section 3.9): create, read, submit, retry-merge."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import FilmingSession
from tests.api._s3_support import (  # noqa: F401
    csrf,
    jobs,
    open_session,
    session_row,
    world,
)

SITS = ["leash_walk", "new_person"]


def _create(client, token, dog_id, **body):
    payload = {"situations": SITS, "capture_rules_ack": True}
    payload.update(body)
    payload = {k: v for k, v in payload.items() if v is not None}
    return client.post(
        f"/api/dogs/{dog_id}/sessions", json=payload, headers=csrf(token)
    )


def _count_sessions(db, dog_id) -> int:
    db.expire_all()
    return db.scalar(
        select(func.count())
        .select_from(FilmingSession)
        .where(FilmingSession.dog_id == dog_id)
    )


def _code(r) -> str:
    return r.json()["error"]["code"]


# ------------------------------------------------------------------ create


def test_api_ses_01_create_session(client, db, world, login_as):
    token = login_as(world.vol1)
    r = _create(client, token, world.dog_empty.id)
    assert r.status_code == 201, r.text
    s = r.json()["session"]
    assert s["status"] == "open"
    assert s["observed_on"] == "2026-10-28"
    assert s["situations"] == SITS
    assert s["dog_id"] == world.dog_empty.id
    assert s["member_id"] == world.vol1.id
    assert s["owner_name"] == "Vol One"
    assert (
        s["fail_code"] is None
        and s["submitted_at"] is None
        and s["review_ready_at"] is None
    )
    row = session_row(db, s["id"])
    assert row.rules_ack_at is not None


@pytest.mark.parametrize("ack", [False, None])
def test_api_ses_02_rules_ack_required(client, db, world, login_as, ack):
    token = login_as(world.vol1)
    r = _create(client, token, world.dog_empty.id, capture_rules_ack=ack)
    assert r.status_code == 422 and _code(r) == "validation_error"
    assert _count_sessions(db, world.dog_empty.id) == 0


@pytest.mark.parametrize(
    "situations",
    [
        [],
        ["leash_walk", "leash_walk"],
        ["leash_walk", "unknown_code"],
        [
            "new_person",
            "handling",
            "leash_walk",
            "other_dog",
            "food_toys",
            "alone_time",
            "indoors_rest",
            "children_cats",
            "new_person",
        ],
    ],
    ids=["empty", "duplicate", "unknown", "nine"],
)
def test_api_ses_03_situations_validation(client, db, world, login_as, situations):
    token = login_as(world.vol1)
    r = _create(client, token, world.dog_empty.id, situations=situations)
    assert r.status_code == 422 and _code(r) == "validation_error"
    assert _count_sessions(db, world.dog_empty.id) == 0


def test_api_ses_04_observed_on_bounds(client, world, login_as):
    token = login_as(world.vol1)
    ok = _create(client, token, world.dog_empty.id, observed_on="2026-10-29")
    assert ok.status_code == 201 and ok.json()["session"]["observed_on"] == "2026-10-29"
    too_far = _create(client, token, world.dog_empty.id, observed_on="2026-10-30")
    assert too_far.status_code == 422 and _code(too_far) == "validation_error"


def test_api_ses_05_new_session_blocked_for_non_draft_dogs(client, db, world, login_as):
    token = login_as(world.vol1)
    for dog, status, code in (
        (world.dog_pub, 409, "invalid_state"),
        (world.dog_adopted, 409, "invalid_state"),
        (world.dog_deleted, 404, "not_found"),
    ):
        r = _create(client, token, dog.id)
        assert (r.status_code, _code(r)) == (status, code), dog.name
        assert _count_sessions(db, dog.id) == 0 if dog is not world.dog_pub else True
    assert _create(client, token, world.dog_ready.id).status_code == 201
    # published dog got no new session row beyond the seeded ones
    db.expire_all()
    n = db.scalar(
        select(func.count())
        .select_from(FilmingSession)
        .where(FilmingSession.dog_id == world.dog_pub.id)
    )
    assert n == 2  # the two sessions of the standard world


def test_api_ses_06_capture_rules_per_session(client, db, world, login_as, clock):
    token = login_as(world.vol1)
    first = _create(client, token, world.dog_empty.id)
    assert first.status_code == 201
    clock.advance(60)
    # a second session needs its own ack
    refused = _create(client, token, world.dog_empty.id, capture_rules_ack=False)
    assert refused.status_code == 422
    second = _create(client, token, world.dog_empty.id)
    assert second.status_code == 201
    a = session_row(db, first.json()["session"]["id"]).rules_ack_at
    b = session_row(db, second.json()["session"]["id"]).rules_ack_at
    assert b - a == timedelta(seconds=60)


def test_api_ses_create_other_org_dog_is_404(client, world, login_as):
    token = login_as(world.vol1)
    r = _create(client, token, world.dog_b.id)
    assert r.status_code == 404 and _code(r) == "not_found"


# -------------------------------------------------------------------- read


def _fact_session(world):
    return world.facts_pub["one_range"].session_id


def test_api_ses_07_get_session_and_polling(client, db, seed, world, login_as):
    token = login_as(world.vol1)
    sid = _fact_session(world)
    r = client.get(f"/api/sessions/{sid}")
    assert r.status_code == 200, r.text
    etag = r.headers["ETag"]
    assert etag.startswith('W/"')
    body = r.json()
    assert set(body) == {"session", "clips", "facts", "progress"}
    ids = {f["id"] for f in body["facts"]}
    fp = world.facts_pub
    assert ids == {
        fp[k].id
        for k in ("one_range", "two_ranges", "narration", "children_cats", "draft")
    }
    assert fp["deleted"].id not in ids and fp["unmerged"].id not in ids
    s = body["session"]
    assert {"owner_name", "fail_code", "review_ready_at"} <= set(s)
    clips = body["clips"]
    assert body["progress"] == {
        "clips_total": len(clips),
        "clips_ready": sum(c["status"] == "ready" for c in clips),
        "clips_failed": sum(c["status"] == "failed" for c in clips),
    }
    one = next(f for f in body["facts"] if f["id"] == fp["one_range"].id)
    assert {
        "situation",
        "behavior",
        "source",
        "origin",
        "status",
        "flags",
        "observed_on",
        "evidence",
        "clip_length",
        "confirmed",
        "created_by",
        "can_confirm",
        "blocked_reason",
    } <= set(one)
    ev = one["evidence"][0]
    assert (
        ev["media_url"] == f"/media/{ev['clip_id']}.mp4" and ev["played_by_me"] is False
    )
    assert one["clip_length"]["label"] == "1 clip, 3 s"
    assert one["confirmed"]["by_member_id"] == world.vol1.id

    # unchanged: 304 with the same ETag, no body
    same = client.get(f"/api/sessions/{sid}", headers={"If-None-Match": etag})
    assert same.status_code == 304 and same.content == b""

    # a clip status change gives a new ETag
    from app.models import Clip

    clip_id = world.clips_pub["c1"].id
    db.query(Clip).filter(Clip.id == clip_id).update(
        {"status": "failed", "fail_code": "transcode_failed", "step": "transcode"}
    )
    db.commit()
    changed = client.get(f"/api/sessions/{sid}", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["ETag"] != etag
    assert changed.json()["progress"]["clips_failed"] == 1

    light = client.get(f"/api/sessions/{sid}?include=none")
    assert light.status_code == 200 and "facts" not in light.json()
    del token


def test_api_ses_08_any_org_member_can_read(client, world, login_as):
    login_as(world.vol2)
    r = client.get(f"/api/sessions/{world.session_review.id}")
    assert r.status_code == 200
    login_as(world.staff_b)
    r = client.get(f"/api/sessions/{world.session_review.id}")
    assert r.status_code == 404 and _code(r) == "not_found"


def test_api_ses_get_unknown_and_deleted_dog_is_404(client, seed, world, login_as):
    login_as(world.vol1)
    assert client.get("/api/sessions/" + "0" * 32).status_code == 404
    sess = seed.session(world.dog_deleted, world.vol1)
    assert client.get(f"/api/sessions/{sess.id}").status_code == 404


def test_api_ses_13_session_fields(client, seed, world, login_as):
    sess = seed.session(
        world.dog_empty, world.vol1, status="failed", fail_code="merge_failed"
    )
    login_as(world.vol2)
    s = client.get(f"/api/sessions/{sess.id}").json()["session"]
    assert s["owner_name"] == "Vol One"
    assert s["fail_code"] == "merge_failed"
    assert s["review_ready_at"] is None
    review = client.get(f"/api/sessions/{world.session_review.id}").json()["session"]
    assert review["fail_code"] is None
    assert review["review_ready_at"].endswith("Z")


# ------------------------------------------------------------------ submit


def test_api_ses_09_submit(client, db, seed, world, open_session, login_as):
    seed.clip(open_session, 1, status="uploaded", step="transcode")
    token = login_as(world.vol1)
    r = client.post(
        f"/api/sessions/{open_session.id}/submit", json={}, headers=csrf(token)
    )
    assert r.status_code == 200, r.text
    s = r.json()["session"]
    assert s["status"] == "processing" and s["submitted_at"] is not None
    assert jobs(db, type="merge") == []  # the last clip's draft job enqueues it


def test_api_ses_10_submit_guards(client, db, seed, world, login_as):
    empty = seed.session(world.dog_empty, world.vol1)
    token = login_as(world.vol1)
    r = client.post(f"/api/sessions/{empty.id}/submit", json={}, headers=csrf(token))
    assert (r.status_code, _code(r)) == (409, "invalid_state")
    r = client.post(
        f"/api/sessions/{world.session_review.id}/submit", json={}, headers=csrf(token)
    )
    assert (r.status_code, _code(r)) == (409, "invalid_state")

    owned = seed.session(world.dog_empty, world.vol1)
    seed.clip(owned, 1, status="uploaded", step="transcode")
    token = login_as(world.vol2)
    r = client.post(f"/api/sessions/{owned.id}/submit", json={}, headers=csrf(token))
    assert (r.status_code, _code(r)) == (403, "not_own_session")
    token = login_as(world.staff1)
    r = client.post(f"/api/sessions/{owned.id}/submit", json={}, headers=csrf(token))
    assert r.status_code == 200


def test_api_ses_11_submit_with_all_clips_terminal(
    client, db, seed, world, open_session, login_as
):
    seed.clip(open_session, 1, status="ready")
    seed.clip(
        open_session, 2, status="failed", fail_code="transcode_failed", step="transcode"
    )
    token = login_as(world.vol1)
    r = client.post(
        f"/api/sessions/{open_session.id}/submit", json={}, headers=csrf(token)
    )
    assert r.status_code == 200 and r.json()["session"]["status"] == "processing"
    merges = jobs(db, type="merge")
    assert len(merges) == 1
    job = merges[0]
    assert job.dedupe_key == f"merge:{open_session.id}"
    assert job.session_id == open_session.id and job.dog_id == world.dog_empty.id
    assert job.status == "queued" and job.attempts == 0
    assert job.payload["session_id"] == open_session.id
    assert r.json()["session"]["review_ready_at"] is None


@pytest.mark.xfail(
    reason="lane P: merge and check handlers and the pipeline helper", strict=False
)
def test_api_ses_12_review_ready_at_lifecycle(
    client, db, container, seed, world, open_session, login_as
):
    seed.clip(open_session, 1, status="ready")
    token = login_as(world.vol1)
    r = client.post(
        f"/api/sessions/{open_session.id}/submit", json={}, headers=csrf(token)
    )
    assert r.json()["session"]["status"] == "processing"
    assert r.json()["session"]["review_ready_at"] is None
    # run the merge and check steps with the real handlers (lane P)
    container.services.merge_service.merge_session(open_session.id)
    container.services.session_service.mark_review_ready(open_session.id)
    s = client.get(f"/api/sessions/{open_session.id}").json()["session"]
    assert s["status"] == "review" and s["review_ready_at"] is not None


def test_api_ses_12_review_ready_at_is_null_while_processing(
    client, db, container, seed, world, open_session, login_as
):
    """The parts of SES-12 that need no handler: null after submit and after a
    clip retry; `mark_review_ready` is the only writer (I-22)."""
    c = seed.clip(open_session, 1, status="ready")
    token = login_as(world.vol1)
    client.post(f"/api/sessions/{open_session.id}/submit", json={}, headers=csrf(token))
    s = client.get(f"/api/sessions/{open_session.id}").json()["session"]
    assert (s["status"], s["review_ready_at"]) == ("processing", None)
    container.services.session_service.mark_review_ready(open_session.id)
    s = client.get(f"/api/sessions/{open_session.id}").json()["session"]
    assert s["status"] == "review" and s["review_ready_at"] is not None
    # a failed clip retried from review puts the session back to processing, null
    from app.models import Clip

    db.query(Clip).filter(Clip.id == c.id).update(
        {"status": "failed", "fail_code": "ai_failed", "step": "draft"}
    )
    db.commit()
    r = client.post(f"/api/clips/{c.id}/retry", json={}, headers=csrf(token))
    assert r.status_code == 200
    s = client.get(f"/api/sessions/{open_session.id}").json()["session"]
    assert (s["status"], s["review_ready_at"]) == ("processing", None)


@pytest.mark.xfail(
    reason="lane P: merge step marks a session with no ready clip failed", strict=False
)
def test_api_ses_14_all_clips_failed_merge_step(
    client, container, seed, world, open_session, login_as
):
    seed.clip(open_session, 1, status="failed", fail_code="ai_failed", step="draft")
    token = login_as(world.vol1)
    client.post(f"/api/sessions/{open_session.id}/submit", json={}, headers=csrf(token))
    container.services.merge_service.merge_session(open_session.id)
    s = client.get(f"/api/sessions/{open_session.id}").json()["session"]
    assert (s["status"], s["fail_code"]) == ("failed", "no_usable_clip")


def test_api_ses_14_submit_with_no_ready_clip_fails_the_session(
    client, db, seed, world, open_session, login_as
):
    """06 submit post: every live clip terminal and none `ready` gives
    `failed` with `no_usable_clip`; no merge job."""
    seed.clip(open_session, 1, status="failed", fail_code="ai_failed", step="draft")
    token = login_as(world.vol1)
    r = client.post(
        f"/api/sessions/{open_session.id}/submit", json={}, headers=csrf(token)
    )
    assert r.status_code == 200
    s = client.get(f"/api/sessions/{open_session.id}").json()["session"]
    assert (s["status"], s["fail_code"]) == ("failed", "no_usable_clip")
    assert jobs(db, type="merge") == []
    r = client.post(
        f"/api/sessions/{open_session.id}/retry-merge", json={}, headers=csrf(token)
    )
    assert (r.status_code, _code(r)) == (409, "invalid_state")


def test_session_service_hooks_for_the_pipeline(
    container, db, seed, world, open_session
):
    """`on_clip_terminal`, `enqueue_merge`, `mark_failed` (lane P calls these)."""
    svc = container.services.session_service
    seed.clip(open_session, 1, status="ready")
    seed.clip(open_session, 2, status="processing", step="draft")
    from app.models import Clip

    db.query(FilmingSession).filter(FilmingSession.id == open_session.id).update(
        {"status": "processing"}
    )
    db.commit()
    svc.on_clip_terminal(open_session.id)
    assert jobs(db, type="merge") == []  # one clip still running
    db.query(Clip).filter(Clip.session_id == open_session.id, Clip.ordinal == 2).update(
        {"status": "failed", "fail_code": "ai_failed", "step": "draft"}
    )
    db.commit()
    svc.on_clip_terminal(open_session.id)
    svc.on_clip_terminal(open_session.id)  # idempotent
    assert len(jobs(db, type="merge", dedupe_key=f"merge:{open_session.id}")) == 1
    svc.mark_failed(open_session.id, "merge_failed")
    row = session_row(db, open_session.id)
    assert (row.status, row.fail_code) == ("failed", "merge_failed")


# ------------------------------------------------------------- retry-merge


def _merge_failed(seed, world, owner=None):
    return seed.session(
        world.dog_empty, owner or world.vol1, status="failed", fail_code="merge_failed"
    )


def test_api_rmg_01_retry_merge_ok(client, db, seed, world, login_as):
    sess = _merge_failed(seed, world)
    token = login_as(world.vol1)
    r = client.post(
        f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
    )
    assert r.status_code == 200, r.text
    s = r.json()["session"]
    assert (s["status"], s["fail_code"], s["review_ready_at"]) == (
        "processing",
        None,
        None,
    )
    merges = jobs(db, type="merge", session_id=sess.id)
    assert len(merges) == 1
    assert merges[0].dedupe_key == f"merge:{sess.id}" and merges[0].attempts == 0
    assert merges[0].status == "queued"


def test_api_rmg_02_retry_merge_idempotent(client, db, seed, world, login_as):
    sess = _merge_failed(seed, world)
    token = login_as(world.vol1)
    first = client.post(
        f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
    )
    again = client.post(
        f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
    )
    assert again.status_code == 200
    assert again.json()["session"] == first.json()["session"]
    assert len(jobs(db, type="merge", session_id=sess.id)) == 1


def test_api_rmg_03_retry_merge_auth(client, db, seed, world, login_as):
    def fresh():
        return _merge_failed(seed, world)

    cases = [
        (world.vol1, 200, None),
        (world.staff1, 200, None),
        (world.vol2, 403, "not_own_session"),
        (world.staff_b, 404, "not_found"),
        (world.vol_new, 403, "consent_required"),
    ]
    for member, status, code in cases:
        sess = fresh()
        token = login_as(member)
        r = client.post(
            f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
        )
        assert r.status_code == status, (member.display_name, r.text)
        if code:
            assert _code(r) == code, member.display_name
    sess = fresh()
    client.cookies.clear()
    r = client.post(f"/api/sessions/{sess.id}/retry-merge", json={})
    assert (r.status_code, _code(r)) == (401, "unauthenticated")
    login_as(world.vol1)
    r = client.post(f"/api/sessions/{sess.id}/retry-merge", json={})
    assert (r.status_code, _code(r)) == (403, "csrf_failed")


def test_api_rmg_04_retry_merge_unknown_id(client, world, login_as):
    token = login_as(world.vol1)
    r = client.post(
        "/api/sessions/" + "f" * 32 + "/retry-merge", json={}, headers=csrf(token)
    )
    assert (r.status_code, _code(r)) == (404, "not_found")


def test_api_rmg_05_retry_merge_invalid_states(client, seed, world, login_as):
    token = login_as(world.vol1)
    sessions = [
        seed.session(world.dog_empty, world.vol1, status="open"),
        seed.session(world.dog_empty, world.vol1, status="processing"),
        seed.session(world.dog_empty, world.vol1, status="review"),
        seed.session(
            world.dog_empty, world.vol1, status="failed", fail_code="no_usable_clip"
        ),
    ]
    for sess in sessions:
        r = client.post(
            f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
        )
        assert (r.status_code, _code(r)) == (409, "invalid_state"), sess.status


def test_api_rmg_06_retry_merge_on_hidden_dog(client, db, seed, world, login_as):
    sess = seed.session(
        world.dog_deleted, world.vol1, status="failed", fail_code="merge_failed"
    )
    token = login_as(world.vol1)
    r = client.post(
        f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
    )
    assert (r.status_code, _code(r)) == (404, "not_found")
    assert jobs(db, type="merge") == []
