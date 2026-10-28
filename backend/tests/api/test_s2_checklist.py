"""API-CHK-01 to API-CHK-04 (07 section 3.8)."""

from __future__ import annotations

import pytest

from app.models import Dog
from tests.api._s2_support import csrf, fresh


@pytest.fixture
def world(seed):
    return seed.standard_world()


def _put(client, dog_id, token, **body):
    body.setdefault("people_check", False)
    return client.put(
        f"/api/dogs/{dog_id}/publish-checklist", json=body, headers=csrf(token)
    )


def test_api_chk_01_checklist_set(client, login_as, world, db):
    token = login_as(world.staff1)
    r = _put(
        client,
        world.dog_review.id,
        token,
        people_check=True,
        known_concerns="Pulls hard toward other dogs on leash.",
    )
    assert r.status_code == 200, r.text
    c = r.json()["checklist"]
    assert c["people_check"] is True
    assert c["people_check_at"].endswith("Z")
    assert c["known_concerns"] == "Pulls hard toward other dogs on leash."
    assert c["known_concerns_none"] is False
    assert c["confirmed_fact_count"] == 0
    assert c["ready_to_publish"] is False
    assert c["missing"] == ["confirmed_fact"]
    row = fresh(db, Dog, world.dog_review.id)
    assert row.people_check_by == world.staff1.id
    assert row.people_check_at is not None


def test_api_chk_01_ready_when_complete(client, login_as, world):
    token = login_as(world.staff1)
    r = _put(client, world.dog_ready.id, token, people_check=True, known_concerns_none=True)
    c = r.json()["checklist"]
    assert c["ready_to_publish"] is True and c["missing"] == []
    assert c["confirmed_fact_count"] == 2


def test_api_chk_01_volunteer_forbidden_and_hidden_dogs(client, login_as, world):
    token = login_as(world.vol1)
    r = _put(client, world.dog_review.id, token, people_check=True)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"
    token = login_as(world.staff1)
    for dog_id in (world.dog_deleted.id, world.dog_b.id, "0" * 32):
        r = _put(client, dog_id, token, people_check=True)
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_api_chk_01_checklist_shown_in_detail(client, login_as, world):
    token = login_as(world.staff1)
    _put(client, world.dog_review.id, token, people_check=True, known_concerns_none=True)
    c = client.get(f"/api/dogs/{world.dog_review.id}").json()["checklist"]
    assert c["people_check"] is True and c["known_concerns_none"] is True
    assert c["missing"] == ["confirmed_fact"]


def test_api_chk_02_concerns_rules(client, login_as, world, db):
    token = login_as(world.staff1)
    dog = world.dog_review.id

    r = _put(client, dog, token, known_concerns_none=True, known_concerns="Bites.")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"

    r = _put(client, dog, token, people_check=True)  # both empty, none false
    assert r.status_code == 200
    assert r.json()["checklist"]["missing"] == ["known_concerns", "confirmed_fact"]

    r = _put(client, dog, token, known_concerns="x" * 1001)
    assert r.status_code == 422
    paths = [f["path"] for f in r.json()["error"]["details"]["fields"]]
    assert "body.known_concerns" in paths

    r = _put(client, dog, token, people_check=True, known_concerns="x" * 1000)
    assert r.status_code == 200

    r = _put(client, dog, token, people_check=True, known_concerns="   \n  ")
    assert r.status_code == 200
    c = r.json()["checklist"]
    assert "known_concerns" in c["missing"]
    assert c["known_concerns"] is None
    assert fresh(db, Dog, dog).known_concerns is None

    # whitespace-only text next to none=true is still "empty", so it is valid
    r = _put(client, dog, token, known_concerns_none=True, known_concerns="   ")
    assert r.status_code == 200
    assert r.json()["checklist"]["known_concerns_none"] is True


def test_api_chk_02_text_is_trimmed(client, login_as, world):
    token = login_as(world.staff1)
    r = _put(client, world.dog_review.id, token, known_concerns="  Shy at the door.  ")
    assert r.json()["checklist"]["known_concerns"] == "Shy at the door."


def test_api_chk_03_uncheck(client, login_as, world, db):
    token = login_as(world.staff1)
    r = _put(client, world.dog_ready.id, token, people_check=True, known_concerns_none=True)
    assert r.json()["checklist"]["ready_to_publish"] is True
    r = _put(client, world.dog_ready.id, token, people_check=False, known_concerns_none=True)
    assert r.status_code == 200
    c = r.json()["checklist"]
    assert c["people_check"] is False and c["people_check_at"] is None
    assert c["ready_to_publish"] is False and "people_check" in c["missing"]
    row = fresh(db, Dog, world.dog_ready.id)
    assert row.people_check_at is None and row.people_check_by is None


def test_api_chk_04_checklist_on_published_dog(client, login_as, world):
    token = login_as(world.staff1)
    r = _put(client, world.dog_pub.id, token, people_check=False, known_concerns_none=True)
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"
    r = _put(client, world.dog_pub.id, token, people_check=True)  # clears the concerns decision
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"
    # an edit that keeps the checklist complete is fine
    r = _put(client, world.dog_pub.id, token, people_check=True, known_concerns="Needs a quiet home.")
    assert r.status_code == 200
    assert r.json()["checklist"]["ready_to_publish"] is True
