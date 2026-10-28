"""API-MET-01..07: `GET /api/admin/metrics` (07 section 3.14, 01 section 8.1)."""

from __future__ import annotations

from datetime import timedelta

import pytest

URL = "/api/admin/metrics"


@pytest.fixture
def world(seed):
    org = seed.org()
    staff = seed.member(org, "staff", name="Staff")
    vol = seed.member(org, "volunteer", name="Vol")
    return org, staff, vol


def _get(client, login_as, member):
    login_as(member)
    r = client.get(URL)
    assert r.status_code == 200, r.text
    return r.json()


def _facts(seed, dog, n, **kw):
    return [seed.fact(dog, **kw) for _ in range(n)]


# ---------------------------------------------------------------- API-MET-01


def test_api_met_01_draft_acceptance(client, login_as, seed, world):
    org, staff, vol = world
    dog = seed.dog(org, staff)
    _facts(seed, dog, 12, status="confirmed", origin="ai_unchanged", confirmed_by=staff)
    _facts(seed, dog, 3, status="confirmed", origin="human_edited", confirmed_by=staff)
    _facts(seed, dog, 2, status="deleted", origin="ai_unchanged")
    _facts(seed, dog, 3, status="draft", origin="ai_unchanged")
    # not AI drafts: a human-added fact, an unmerged duplicate candidate
    seed.fact(dog, source="staff_note", status="confirmed", confirmed_by=staff)
    seed.fact(dog, status="draft", origin="ai_unchanged", merged=False)
    body = _get(client, login_as, staff)
    assert body["draft_acceptance"] == {
        "confirmed_ai_unchanged": 12,
        "all_drafts": 20,
        "rate": 0.6,
    }
    assert body["as_of"].endswith("Z")
    assert set(body) == {
        "as_of", "draft_acceptance", "facts", "time", "cost", "alerts", "purge_pending",
    }


def test_api_met_01_empty_database(client, login_as, world):
    _, staff, _ = world
    body = _get(client, login_as, staff)
    assert body["draft_acceptance"] == {"confirmed_ai_unchanged": 0, "all_drafts": 0, "rate": 0.0}
    assert body["facts"]["clip_evidence_share"] == 0.0
    assert body["time"] == {
        "median_session_to_review_s": None,
        "median_dog_first_session_to_publish_s": None,
    }
    assert body["cost"]["total_usd"] == 0 and body["cost"]["per_dog_usd"] == []
    assert body["alerts"] == [] and body["purge_pending"] == []


# ---------------------------------------------------------------- API-MET-02


def test_api_met_02_clip_evidence_share(client, login_as, seed, world):
    org, staff, _ = world
    dog = seed.dog(org, staff, status="published")
    sess = seed.session(dog, staff, status="review")
    clip = seed.clip(sess)
    for _ in range(12):
        seed.fact(dog, status="confirmed", confirmed_by=staff, session=sess, clip=clip)
    for _ in range(2):
        seed.fact(dog, source="staff_note", status="confirmed", confirmed_by=staff)
    seed.fact(dog, status="draft", session=sess, clip=clip)  # draft: not counted
    body = _get(client, login_as, staff)
    assert body["facts"]["published_dogs"] == 1
    assert body["facts"]["confirmed"] == 14
    assert body["facts"]["with_clip_evidence"] == 12
    assert body["facts"]["clip_evidence_share"] == pytest.approx(0.857, abs=0.001)


def test_api_met_02_published_dogs_excludes_draft_and_adopted(client, login_as, seed, world):
    org, staff, _ = world
    seed.dog(org, staff, status="published")
    seed.dog(org, staff, status="adopted")
    seed.dog(org, staff, status="draft")
    body = _get(client, login_as, staff)
    assert body["facts"]["published_dogs"] == 1


# ---------------------------------------------------------------- API-MET-03


def test_api_met_03_time_metrics(client, login_as, seed, world, clock):
    org, staff, vol = world
    t0 = clock.now()
    dog = seed.dog(org, staff)
    s = lambda **kw: seed.session(dog, vol, **kw)
    s(status="review", submitted_at=t0, review_ready_at=t0 + timedelta(seconds=100))
    s(status="review", submitted_at=t0, review_ready_at=t0 + timedelta(seconds=300))
    # retried: review_ready_at cleared, then set 5 minutes later; submitted_at is the original
    s(status="review", submitted_at=t0, review_ready_at=t0 + timedelta(seconds=300 + 300))
    s(status="processing", submitted_at=t0, review_ready_at=None)
    s(status="open")
    body = _get(client, login_as, staff)
    assert body["time"]["median_session_to_review_s"] == 300

    # publish time: from the first session's created_at to published_at
    d1 = seed.dog(org, staff, status="published", published_at=t0 + timedelta(seconds=1000))
    seed.session(d1, vol, status="review", created_at=t0)
    seed.session(d1, vol, status="review", created_at=t0 + timedelta(seconds=500))
    d2 = seed.dog(org, staff, status="adopted", published_at=t0 + timedelta(seconds=2000))
    seed.session(d2, vol, status="review", created_at=t0)
    seed.dog(org, staff, status="draft")  # never published: excluded
    body = _get(client, login_as, staff)
    assert body["time"]["median_dog_first_session_to_publish_s"] == 1500


def test_api_met_03_median_is_whole_seconds(client, login_as, seed, world, clock):
    org, staff, vol = world
    t0 = clock.now()
    dog = seed.dog(org, staff)
    for secs in (10, 21):
        seed.session(
            dog, vol, status="review", submitted_at=t0, review_ready_at=t0 + timedelta(seconds=secs)
        )
    body = _get(client, login_as, staff)
    assert body["time"]["median_session_to_review_s"] in (15, 16)
    assert isinstance(body["time"]["median_session_to_review_s"], int)


# ---------------------------------------------------------------- API-MET-04


def test_api_met_04_cost_metrics(client, login_as, seed, world, clock):
    org, staff, _ = world
    d1 = seed.dog(org, staff, name="One")
    d2 = seed.dog(org, staff, name="Two")
    now = clock.now()
    yesterday = now - timedelta(days=1)
    seed.ledger("draft", usd_micros=2_500_000, dog_id=d1.id, created_at=now)
    seed.ledger("transcribe", usd_micros=500_000, dog_id=d1.id, created_at=now)
    seed.ledger("draft", usd_micros=400_000, dog_id=d2.id, created_at=now)
    seed.ledger("qa_select", usd_micros=20_000, created_at=now)
    seed.ledger("qa_select", usd_micros=1_000_000, created_at=yesterday)
    body = _get(client, login_as, staff)
    cost = body["cost"]
    assert cost["total_usd"] == pytest.approx(4.42)
    assert cost["qa_today_usd"] == pytest.approx(0.02)
    assert cost["qa_daily_cap_usd"] == 3.0
    per = {row["dog_id"]: row["usd"] for row in cost["per_dog_usd"]}
    assert per == {d1.id: pytest.approx(3.0), d2.id: pytest.approx(0.4)}
    assert [row["dog_id"] for row in cost["per_dog_usd"]] == [d1.id, d2.id]  # biggest first


# ---------------------------------------------------------------- API-MET-05


def test_api_met_05_purge_pending(client, login_as, seed, world):
    org, staff, _ = world
    gone = seed.dog(org, staff, status="deleted")
    seed.job("purge_dog", dog_id=gone.id, status="failed", attempts=8, max_attempts=8)
    queued = seed.dog(org, staff, status="deleted")
    seed.job("purge_dog", dog_id=queued.id, status="queued")
    seed.dog(org, staff, status="published")
    body = _get(client, login_as, staff)
    assert sorted(body["purge_pending"]) == sorted([gone.id, queued.id])


# ---------------------------------------------------------------- API-MET-06


def test_api_met_06_access(client, login_as, world):
    _, staff, vol = world
    client.cookies.clear()
    r = client.get(URL)
    assert (r.status_code, r.json()["error"]["code"]) == (401, "unauthenticated")
    login_as(vol)
    r = client.get(URL)
    assert (r.status_code, r.json()["error"]["code"]) == (403, "forbidden_role")
    assert client.get(URL, headers={"Cache-Control": "x"}).status_code == 403
    login_as(staff)
    assert client.get(URL).status_code == 200


# ---------------------------------------------------------------- API-MET-07


def test_api_met_07_metrics_survive_dog_delete(client, login_as, seed, world, container):
    org, staff, vol = world
    keep = seed.dog(org, staff, name="Keep")
    gone = seed.dog(org, staff, name="Gone")
    for dog in (keep, gone):
        sess = seed.session(dog, vol, status="review")
        clip = seed.clip(sess)
        for _ in range(3):
            seed.fact(dog, status="confirmed", confirmed_by=staff, session=sess, clip=clip)
        seed.fact(dog, status="deleted", origin="ai_unchanged")
        seed.ledger("draft", usd_micros=1_000_000, dog_id=dog.id, session_id=sess.id)
    before = _get(client, login_as, staff)
    assert before["facts"]["confirmed"] == 6 and before["draft_acceptance"]["all_drafts"] == 8
    token = login_as(staff)
    r = client.delete(f"/api/dogs/{gone.id}", headers={"X-CSRF-Token": token})
    assert r.status_code == 202, r.text
    # tombstone: the dog's counts are already gone, its cost stays in the total
    mid = _get(client, login_as, staff)
    assert mid["facts"]["confirmed"] == 3 and mid["draft_acceptance"]["all_drafts"] == 4
    assert mid["cost"]["total_usd"] == before["cost"]["total_usd"]
    assert mid["purge_pending"] == [gone.id]
    # after the purge the ledger rows are orphaned, not deleted
    with container.uow() as uow:
        from sqlalchemy import select

        from app.models import Job

        job_id = uow.session.scalar(select(Job.id).where(Job.dog_id == gone.id))
    assert container.services.deletion_service.run_purge_dog(gone.id, job_id) == "purged"
    after = _get(client, login_as, staff)
    assert after["facts"]["confirmed"] == 3 and after["draft_acceptance"]["all_drafts"] == 4
    assert after["cost"]["total_usd"] == before["cost"]["total_usd"]
    assert [row["dog_id"] for row in after["cost"]["per_dog_usd"]] == [keep.id]
    assert after["purge_pending"] == []
