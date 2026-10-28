"""API-DEL-01 to API-DEL-04 (07 section 3.8)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Dog, Job
from tests.api._s2_support import (
    csrf,
    fresh,
)
from tests.api._s5_support import put_clip_file


@pytest.fixture
def world(seed):
    return seed.standard_world()


def _delete(client, token, dog_id):
    return client.delete(f"/api/dogs/{dog_id}", headers=csrf(token))


def test_api_del_01_delete_dog_request(client, login_as, world, seed, db):
    queued = seed.job("draft", dog_id=world.dog_pub.id, status="queued")
    running = seed.job("transcode", dog_id=world.dog_pub.id, status="running")
    other = seed.job("draft", dog_id=world.dog_review.id, status="queued")
    token = login_as(world.staff1)
    r = _delete(client, token, world.dog_pub.id)
    assert r.status_code == 202, r.text
    assert r.json() == {"dog_id": world.dog_pub.id, "status": "deleted", "purge": "queued"}

    row = fresh(db, Dog, world.dog_pub.id)
    assert row.status == "deleted" and row.public_slug is None and row.deleted_at is not None
    db.expire_all()
    assert db.get(Job, queued.id).status == "cancelled"
    assert db.get(Job, running.id).status == "running"
    assert db.get(Job, other.id).status == "queued"
    purge = db.scalars(
        select(Job).where(Job.type == "purge_dog", Job.dog_id == world.dog_pub.id)
    ).all()
    assert len(purge) == 1
    assert purge[0].max_attempts == 8
    assert purge[0].status == "queued"
    assert purge[0].dedupe_key == f"purge_dog:{world.dog_pub.id}"


def test_api_del_01_hidden_reads_after_delete(client, login_as, world):
    slug = world.dog_pub.public_slug
    clip = world.clips_pub["c1"]
    client.cookies.clear()
    assert client.get(f"/api/public/dogs/{slug}").status_code == 200
    token = login_as(world.staff1)
    assert _delete(client, token, world.dog_pub.id).status_code == 202
    client.cookies.clear()
    assert client.get(f"/api/public/dogs/{slug}").status_code == 404
    assert client.get(f"/media/{clip.id}.mp4").status_code == 404


def test_api_del_02_delete_twice_and_volunteer(client, login_as, world):
    token = login_as(world.staff1)
    assert _delete(client, token, world.dog_review.id).status_code == 202
    r = _delete(client, token, world.dog_review.id)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = _delete(client, token, world.dog_deleted.id)
    assert r.status_code == 404
    token = login_as(world.vol1)
    r = _delete(client, token, world.dog_empty.id)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"
    r = _delete(client, token, world.dog_deleted.id)
    assert r.status_code == 403  # role check comes before the lookup


def test_api_del_02_other_org_dog_404(client, login_as, world):
    token = login_as(world.staff1)
    assert _delete(client, token, world.dog_b.id).status_code == 404


def test_api_del_03_deleted_dog_hidden_for_members(client, login_as, world):
    token = login_as(world.vol1)
    dog_id = world.dog_deleted.id
    assert client.get(f"/api/dogs/{dog_id}").status_code == 404
    assert dog_id not in [i["dog"]["id"] for i in client.get("/api/dogs").json()["dogs"]]
    assert client.patch(f"/api/dogs/{dog_id}", json={"name": "x"}, headers=csrf(token)).status_code == 404
    staff = login_as(world.staff1)
    for action in ("publish", "unpublish", "adopted"):
        r = client.post(f"/api/dogs/{dog_id}/{action}", json={}, headers=csrf(staff))
        assert r.status_code == 404
    r = client.put(
        f"/api/dogs/{dog_id}/publish-checklist",
        json={"people_check": True},
        headers=csrf(staff),
    )
    assert r.status_code == 404


def test_api_del_03_dog_deleted_through_api_disappears(client, login_as, world):
    token = login_as(world.staff1)
    assert _delete(client, token, world.dog_pub.id).status_code == 202
    assert client.get(f"/api/dogs/{world.dog_pub.id}").status_code == 404
    assert world.dog_pub.id not in [i["dog"]["id"] for i in client.get("/api/dogs").json()["dogs"]]


def test_api_del_03_session_and_media_of_deleted_dog(client, container, login_as, world):
    sess = world.session_review
    clip = world.clips_review[0]
    put_clip_file(container, clip)  # the pipeline would have written it
    login_as(world.vol1)
    assert client.get(f"/api/sessions/{sess.id}").status_code == 200  # positive control
    assert client.get(f"/media/{clip.id}.mp4").status_code == 200
    token = login_as(world.staff1)
    assert _delete(client, token, world.dog_review.id).status_code == 202
    assert client.get(f"/api/sessions/{sess.id}").status_code == 404
    assert client.get(f"/media/{clip.id}.mp4").status_code == 404


def test_api_del_04_mutations_on_hidden_dogs(client, login_as, world, seed):
    token = login_as(world.vol1)
    session_body = {
        "situations": ["leash_walk"],
        "capture_rules_ack": True,
    }
    # positive control: a draft dog accepts a session
    ok = client.post(f"/api/dogs/{world.dog_empty.id}/sessions", json=session_body, headers=csrf(token))
    assert ok.status_code == 201

    for dog in (world.dog_pub, world.dog_adopted):
        r = client.post(f"/api/dogs/{dog.id}/sessions", json=session_body, headers=csrf(token))
        assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"
    r = client.post(f"/api/dogs/{world.dog_deleted.id}/sessions", json=session_body, headers=csrf(token))
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"

    sess_pub = seed.session(world.dog_pub, world.vol1, status="open")
    r = client.post(
        f"/api/sessions/{sess_pub.id}/clips",
        files={"file": ("a.mp4", b"\0\0\0", "video/mp4")},
        headers=csrf(token),
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"

    sess_del = seed.session(world.dog_deleted, world.vol1, status="open")
    r = client.post(
        f"/api/sessions/{sess_del.id}/clips",
        files={"file": ("a.mp4", b"\0\0\0", "video/mp4")},
        headers=csrf(token),
    )
    assert r.status_code == 404
    r = client.post(
        f"/api/dogs/{world.dog_deleted.id}/facts",
        json={"situation": "handling", "behavior": "Stood still for the vet."},
        headers=csrf(token),
    )
    assert r.status_code == 404
    r = client.post(f"/api/sessions/{sess_del.id}/submit", json={}, headers=csrf(token))
    assert r.status_code == 404
