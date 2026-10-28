"""API-CLP (07 section 3.9): clip status, retry, delete."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Clip, Fact, FactEvidence, Job, PlaybackEvent
from tests.api._s3_support import csrf, jobs, session_row, world  # noqa: F401

CAUSES = {
    "unsupported_file": ("This video format could not be read.", False),
    "too_long": ("The clip is longer than 2 minutes.", False),
    "transcode_failed": ("We could not convert this clip.", True),
    "ai_failed": ("The AI step did not finish.", True),
    "ai_invalid_output": ("The AI answer was not usable.", True),
}


def _code(r) -> str:
    return r.json()["error"]["code"]


def _failed(seed, session, ordinal, fail_code, step="draft", **kw):
    return seed.clip(
        session,
        ordinal,
        status="failed",
        fail_code=fail_code,
        step=step,
        fail_detail="provider said: secret model text",
        **kw,
    )


@pytest.fixture
def sess(seed, world):
    return seed.session(world.dog_empty, world.vol1, status="open")


def test_api_clp_01_clip_status_endpoint(client, seed, world, sess, login_as):
    clip = seed.clip(
        sess, 1, status="processing", step="transcribe", original_filename="IMG_1.MOV"
    )
    login_as(world.vol2)  # any org member may read
    r = client.get(f"/api/clips/{clip.id}")
    assert r.status_code == 200, r.text
    c = r.json()["clip"]
    assert c["id"] == clip.id and c["session_id"] == sess.id and c["ordinal"] == 1
    assert (c["status"], c["step"]) == ("processing", "transcribe")
    assert c["media_url"] is None and c["captions_url"] is None and c["error"] is None
    assert c["original_filename"] == "IMG_1.MOV" and c["fail_code"] is None
    assert c["created_at"].endswith("Z") and c["ready_at"] is None


def test_clip_ready_has_media_urls(client, seed, world, sess, login_as):
    ready = seed.clip(sess, 1, status="ready")
    silent = seed.clip(sess, 2, status="ready")
    seed.transcript(ready, "hello there")
    login_as(world.vol1)
    c = client.get(f"/api/clips/{ready.id}").json()["clip"]
    assert c["media_url"] == f"/media/{ready.id}.mp4"
    assert c["captions_url"] == f"/media/{ready.id}.vtt"
    c2 = client.get(f"/api/clips/{silent.id}").json()["clip"]
    assert c2["media_url"] == f"/media/{silent.id}.mp4" and c2["captions_url"] is None


def test_clip_org_scope_and_deleted(client, db, seed, world, sess, login_as):
    clip = seed.clip(sess, 1)
    login_as(world.staff_b)
    assert client.get(f"/api/clips/{clip.id}").status_code == 404
    login_as(world.vol1)
    assert client.get("/api/clips/" + "9" * 32).status_code == 404
    db.query(Clip).filter(Clip.id == clip.id).update({"deleted_at": seed.clock.now()})
    db.commit()
    assert client.get(f"/api/clips/{clip.id}").status_code == 404


def test_api_clp_02_failed_clip_shape(client, seed, world, sess, login_as):
    login_as(world.vol1)
    for i, (code, (cause, retryable)) in enumerate(CAUSES.items()):
        session = seed.session(world.dog_empty, world.vol1) if i else sess
        clip = _failed(seed, session, 1, code, step="transcode")
        r = client.get(f"/api/clips/{clip.id}")
        c = r.json()["clip"]
        assert c["status"] == "failed" and c["fail_code"] == code
        assert c["error"] == {"cause": cause, "retryable": retryable}
        assert "secret model text" not in r.text


def _retry(client, token, clip_id):
    return client.post(f"/api/clips/{clip_id}/retry", json={}, headers=csrf(token))


@pytest.mark.parametrize("code", ["ai_failed", "ai_invalid_output"])
def test_api_clp_03_retry_allowed(client, db, seed, world, sess, login_as, code):
    clip = _failed(seed, sess, 1, code, step="draft")
    seed.job(
        "draft",
        clip_id=clip.id,
        session_id=sess.id,
        dog_id=sess.dog_id,
        status="failed",
        attempts=2,
    )
    token = login_as(world.vol1)
    r = _retry(client, token, clip.id)
    assert r.status_code == 200, r.text
    c = r.json()["clip"]
    assert (c["status"], c["fail_code"], c["error"], c["step"]) == (
        "processing",
        None,
        None,
        "draft",
    )
    queued = jobs(db, clip_id=clip.id, status="queued")
    assert [j.type for j in queued] == ["draft"]
    assert queued[0].attempts == 0 and queued[0].payload["clip_id"] == clip.id
    assert (queued[0].session_id, queued[0].dog_id) == (sess.id, sess.dog_id)


def test_clp_retry_from_transcribe_removes_later_outputs(
    client, db, seed, world, sess, login_as
):
    from app.models import Segment, TranscriptSegment

    clip = _failed(seed, sess, 1, "ai_failed", step="transcribe")
    seed.transcript(clip, "old text")
    db.add(Segment(clip_id=clip.id, idx=0, start_s=0, end_s=5))
    db.commit()
    token = login_as(world.vol1)
    assert _retry(client, token, clip.id).status_code == 200
    db.expire_all()
    assert (
        db.scalars(
            select(TranscriptSegment).where(TranscriptSegment.clip_id == clip.id)
        ).all()
        == []
    )
    assert db.scalars(select(Segment).where(Segment.clip_id == clip.id)).all() == []
    assert [j.type for j in jobs(db, clip_id=clip.id, status="queued")] == [
        "transcribe"
    ]


def test_api_clp_04_retry_not_allowed(client, seed, world, sess, login_as):
    ready = seed.clip(sess, 1, status="ready")
    unsupported = _failed(seed, sess, 2, "unsupported_file", step="transcode")
    too_long = _failed(seed, sess, 3, "too_long", step="transcode")
    token = login_as(world.vol1)
    for clip in (ready, unsupported, too_long):
        r = _retry(client, token, clip.id)
        assert r.status_code == 409 and _code(r) == "invalid_state", clip.id
    retryable = seed.session(world.dog_empty, world.vol1)
    other = _failed(seed, retryable, 1, "ai_failed")
    token = login_as(world.vol2)
    r = _retry(client, token, other.id)
    assert r.status_code == 403 and _code(r) == "not_own_session"


def test_api_clp_05_retry_in_open_session(client, db, seed, world, sess, login_as):
    clip = _failed(seed, sess, 1, "transcode_failed", step="transcode")
    token = login_as(world.vol1)
    assert _retry(client, token, clip.id).status_code == 200
    assert session_row(db, sess.id).status == "open"
    assert [j.type for j in jobs(db, clip_id=clip.id, status="queued")] == ["transcode"]


def test_api_clp_06_retry_reopens_session(client, db, seed, world, login_as):
    review = seed.session(world.dog_empty, world.vol1, status="review")
    assert review.review_ready_at is not None
    clip = _failed(seed, review, 1, "ai_failed")
    token = login_as(world.vol1)
    assert _retry(client, token, clip.id).status_code == 200
    row = session_row(db, review.id)
    assert (row.status, row.review_ready_at, row.fail_code) == (
        "processing",
        None,
        None,
    )
    failed = seed.session(
        world.dog_empty, world.vol1, status="failed", fail_code="no_usable_clip"
    )
    clip2 = _failed(seed, failed, 1, "ai_failed")
    assert _retry(client, token, clip2.id).status_code == 200
    row = session_row(db, failed.id)
    assert (row.status, row.fail_code) == ("processing", None)


def test_api_clp_12_manual_retry_after_automatic_path_gave_up(
    client, db, seed, world, sess, login_as
):
    a = _failed(seed, sess, 1, "ai_failed")
    b = _failed(seed, sess, 2, "ai_failed")
    seed.job("draft", clip_id=a.id, status="failed", attempts=2, max_attempts=2)
    seed.job("draft", clip_id=b.id, status="failed", attempts=1, max_attempts=2)
    token = login_as(world.vol1)
    for clip in (a, b):
        r = _retry(client, token, clip.id)
        assert r.status_code == 200 and r.json()["clip"]["status"] == "processing"
    for clip in (a, b):
        fresh = jobs(db, clip_id=clip.id, status="queued")
        assert len(fresh) == 1 and fresh[0].attempts == 0


def test_clp_retry_staff_ok_and_deleted_dog_hidden(client, seed, world, sess, login_as):
    clip = _failed(seed, sess, 1, "ai_failed")
    token = login_as(world.staff1)
    assert _retry(client, token, clip.id).status_code == 200
    gone = seed.session(world.dog_deleted, world.vol1)
    clip2 = _failed(seed, gone, 1, "ai_failed")
    r = _retry(client, token, clip2.id)
    assert r.status_code == 404


# ------------------------------------------------------------------ delete


def _delete(client, token, clip_id):
    return client.delete(f"/api/clips/{clip_id}", headers=csrf(token))


def test_api_clp_07_delete_clip_as_owner(client, db, seed, world, sess, login_as):
    x = seed.clip(sess, 1)
    y = seed.clip(sess, 2)
    only_x = seed.fact(
        world.dog_empty, session=sess, clip=x, behavior="Only on clip x."
    )
    both = seed.fact(world.dog_empty, session=sess, clip=x, behavior="Seen on x and y.")
    db.add(
        FactEvidence(id="e" * 32, fact_id=both.id, clip_id=y.id, start_s=2.0, end_s=5.0)
    )
    db.commit()
    token = login_as(world.vol1)
    r = _delete(client, token, x.id)
    assert r.status_code == 202, r.text
    assert r.json() == {
        "clip_id": x.id,
        "purge": "queued",
        "facts_deleted": 1,
        "facts_demoted": 0,
    }
    db.expire_all()
    assert db.get(Fact, only_x.id).status == "deleted"
    assert db.get(Fact, both.id).status == "draft"
    ev = db.scalars(select(FactEvidence).where(FactEvidence.fact_id == both.id)).all()
    assert [e.clip_id for e in ev] == [y.id]
    purge = jobs(db, type="purge_clip")
    assert (
        len(purge) == 1 and purge[0].clip_id == x.id and purge[0].dog_id == sess.dog_id
    )
    assert purge[0].dedupe_key == f"purge_clip:{x.id}" and purge[0].max_attempts == 8
    assert client.get(f"/api/clips/{x.id}").status_code == 404
    assert client.get(f"/media/{x.id}.mp4").status_code == 404
    again = _delete(client, token, x.id)
    assert again.status_code == 404


def test_api_clp_08_delete_clip_guard(client, db, seed, world, sess, login_as):
    clip = seed.clip(sess, 1)
    seed.fact(
        world.dog_empty,
        session=sess,
        clip=clip,
        status="confirmed",
        confirmed_by=world.vol1,
    )
    token = login_as(world.vol1)
    r = _delete(client, token, clip.id)
    assert r.status_code == 403 and _code(r) == "forbidden_role"
    token = login_as(world.staff1)
    assert _delete(client, token, clip.id).status_code == 202


def test_api_clp_09_clip_delete_effects_on_facts(
    client, db, seed, world, sess, login_as
):
    x = seed.clip(sess, 1)
    y = seed.clip(sess, 2)
    a = seed.fact(
        world.dog_empty,
        session=sess,
        clip=x,
        status="confirmed",
        confirmed_by=world.vol1,
        behavior="Fact A on x only.",
    )
    b = seed.fact(
        world.dog_empty,
        session=sess,
        clip=x,
        status="confirmed",
        confirmed_by=world.vol1,
        behavior="Fact B on x and y.",
    )
    c = seed.fact(world.dog_empty, session=sess, clip=x, behavior="Fact C draft on x.")
    db.add(
        FactEvidence(id="d" * 32, fact_id=b.id, clip_id=y.id, start_s=2.0, end_s=6.0)
    )
    ev_a = db.scalars(select(FactEvidence).where(FactEvidence.fact_id == a.id)).one()
    db.add(
        PlaybackEvent(
            fact_id=a.id,
            evidence_id=ev_a.id,
            member_id=world.vol1.id,
            start_s=ev_a.start_s,
            end_s=ev_a.end_s,
            watched_s=3.0,
        )
    )
    db.commit()
    token = login_as(world.staff1)
    r = _delete(client, token, x.id)
    assert r.status_code == 202
    assert r.json()["facts_deleted"] == 2 and r.json()["facts_demoted"] == 1
    db.expire_all()
    fa, fb, fc = (db.get(Fact, f.id) for f in (a, b, c))
    assert (
        fa.status == "deleted" and fa.deleted_by is None and fa.deleted_at is not None
    )
    assert fc.status == "deleted" and fc.deleted_by is None
    assert (
        fb.status == "draft" and fb.confirmed_at is None and fb.confirmed_role is None
    )
    assert [e.clip_id for e in fb.evidence] == [y.id]
    assert db.scalars(select(PlaybackEvent)).all() == []


def test_api_clp_10_clip_delete_cancels_jobs(client, db, seed, world, sess, login_as):
    clip = seed.clip(sess, 1, status="processing", step="transcribe")
    job = seed.job(
        "transcribe", clip_id=clip.id, session_id=sess.id, dog_id=sess.dog_id
    )
    token = login_as(world.vol1)
    assert _delete(client, token, clip.id).status_code == 202
    db.expire_all()
    assert db.get(Job, job.id).status == "cancelled"


def test_api_clp_11_other_members_clip(client, seed, world, sess, login_as):
    clip = seed.clip(sess, 1)
    token = login_as(world.vol2)
    r = _delete(client, token, clip.id)
    assert r.status_code == 403 and _code(r) == "not_own_session"


def test_clp_delete_last_unfinished_clip_reevaluates_merge(
    client, db, seed, world, login_as
):
    processing = seed.session(world.dog_empty, world.vol1, status="processing")
    seed.clip(processing, 1, status="ready")
    running = seed.clip(processing, 2, status="processing", step="draft")
    token = login_as(world.vol1)
    assert _delete(client, token, running.id).status_code == 202
    merges = jobs(db, type="merge")
    assert len(merges) == 1 and merges[0].session_id == processing.id
