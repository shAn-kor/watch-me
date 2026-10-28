"""API-PUB-01 to API-PUB-11 (07 section 3.8)."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import func, select

from app.models import Clip, Dog, Fact
from tests.api._s2_support import (
    SLUG_RE,
    csrf,
    fresh,
)
from tests.api._s5_support import put_clip_file


@pytest.fixture
def world(seed):
    return seed.standard_world()


def _post(client, token, dog_id, action):
    return client.post(f"/api/dogs/{dog_id}/{action}", json={}, headers=csrf(token))


def _fact_rows(db, dog_id):
    db.expire_all()
    rows = db.scalars(select(Fact).where(Fact.dog_id == dog_id).order_by(Fact.id)).all()
    return [(f.id, f.status, f.merged, f.behavior, f.confirmed_at) for f in rows]


def test_api_pub_01_publish_ok(client, login_as, world, container, db):
    token = login_as(world.staff1)
    r = _post(client, token, world.dog_ready.id, "publish")
    assert r.status_code == 200, r.text
    body = r.json()
    dog = body["dog"]
    assert dog["status"] == "published"
    assert re.match(SLUG_RE, dog["public_slug"])
    assert dog["public_path"] == f"/d/{dog['public_slug']}"
    assert dog["published_at"].endswith("Z")
    base = container.settings.public_base_url.rstrip("/")
    assert body["public_url"] == f"{base}/d/{dog['public_slug']}"
    row = fresh(db, Dog, world.dog_ready.id)
    assert row.status == "published" and row.public_slug == dog["public_slug"]


def test_api_pub_01_volunteer_and_hidden_dogs(client, login_as, world):
    token = login_as(world.vol1)
    r = _post(client, token, world.dog_ready.id, "publish")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"
    token = login_as(world.staff1)
    for dog_id in (world.dog_deleted.id, world.dog_b.id):
        assert _post(client, token, dog_id, "publish").status_code == 404


def test_api_pub_02_publish_guard_each_missing_item(client, login_as, world, seed):
    token = login_as(world.staff1)

    def dog_with(*, people=False, concerns=False, confirmed=False, name="V"):
        kw = {}
        if people:
            kw["people_check_at"] = seed.clock.now()
            kw["people_check_by"] = world.staff1.id
        if concerns:
            kw["known_concerns"] = "Shy with strangers."
        dog = seed.dog(world.org_a, world.staff1, name=name, **kw)
        if confirmed:
            sess = seed.session(dog, world.vol1, status="review")
            clip = seed.clip(sess, 1)
            seed.fact(dog, status="confirmed", session=sess, clip=clip, confirmed_by=world.vol1)
        return dog

    cases = [
        (dog_with(concerns=True, confirmed=True, name="A"), ["people_check"]),
        (dog_with(people=True, confirmed=True, name="B"), ["known_concerns"]),
        (dog_with(people=True, concerns=True, name="C"), ["confirmed_fact"]),
        (world.dog_review, ["people_check", "known_concerns", "confirmed_fact"]),
    ]
    for dog, missing in cases:
        r = _post(client, token, dog.id, "publish")
        assert r.status_code == 409, r.text
        err = r.json()["error"]
        assert err["code"] == "publish_checklist_incomplete"
        assert err["details"]["missing"] == missing


def test_api_pub_02_unmerged_or_deleted_facts_do_not_count(client, login_as, world, seed):
    token = login_as(world.staff1)
    dog = seed.dog(
        world.org_a,
        world.staff1,
        name="D",
        known_concerns_none=True,
        people_check_at=seed.clock.now(),
        people_check_by=world.staff1.id,
    )
    sess = seed.session(dog, world.vol1, status="review")
    clip = seed.clip(sess, 1)
    seed.fact(dog, status="deleted", session=sess, clip=clip)
    seed.fact(dog, status="draft", session=sess, clip=clip)
    r = _post(client, token, dog.id, "publish")
    assert r.json()["error"]["details"]["missing"] == ["confirmed_fact"]


def test_api_pub_03_publish_state_guard(client, login_as, world):
    token = login_as(world.staff1)
    for dog in (world.dog_pub, world.dog_adopted):
        r = _post(client, token, dog.id, "publish")
        assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"


def test_api_pub_04_publish_does_not_copy_or_flip_facts(client, login_as, world, db):
    before = _fact_rows(db, world.dog_ready.id)
    assert len(before) == 2
    token = login_as(world.staff1)
    assert _post(client, token, world.dog_ready.id, "publish").status_code == 200
    assert _fact_rows(db, world.dog_ready.id) == before


def test_api_pub_05_link_works_without_sign_in(client, login_as, world):
    token = login_as(world.staff1)
    slug = _post(client, token, world.dog_ready.id, "publish").json()["dog"]["public_slug"]
    client.cookies.clear()
    r = client.get(f"/api/public/dogs/{slug}")
    assert r.status_code == 200


def test_api_pub_06_unpublish(client, login_as, world, db):
    slug = world.dog_pub.public_slug
    token = login_as(world.staff1)
    r = _post(client, token, world.dog_pub.id, "unpublish")
    assert r.status_code == 200, r.text
    dog = r.json()["dog"]
    assert dog["status"] == "draft" and dog["public_slug"] == slug
    row = fresh(db, Dog, world.dog_pub.id)
    assert row.status == "draft" and row.public_slug == slug
    assert row.people_check_at is not None  # checklist is kept


def test_api_pub_06_volunteer_forbidden(client, login_as, world):
    token = login_as(world.vol1)
    r = _post(client, token, world.dog_pub.id, "unpublish")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"


def test_api_pub_06_hidden_reads_after_unpublish(client, container, login_as, world):
    token = login_as(world.staff1)
    clip = world.clips_pub["c1"]
    put_clip_file(container, clip)  # the pipeline would have written it
    slug = world.dog_pub.public_slug
    client.cookies.clear()
    assert client.get(f"/api/public/dogs/{slug}").status_code == 200
    token = login_as(world.staff1)
    _post(client, token, world.dog_pub.id, "unpublish")
    client.cookies.clear()
    assert client.get(f"/api/public/dogs/{slug}").status_code == 404
    assert client.get(f"/media/{clip.id}.mp4").status_code == 404
    login_as(world.vol1)
    assert client.get(f"/media/{clip.id}.mp4").status_code == 200


def test_api_pub_07_republish_same_link(client, login_as, world):
    slug = world.dog_pub.public_slug
    token = login_as(world.staff1)
    assert _post(client, token, world.dog_pub.id, "unpublish").status_code == 200
    r = _post(client, token, world.dog_pub.id, "publish")
    assert r.status_code == 200, r.text
    assert r.json()["dog"]["public_slug"] == slug
    assert r.json()["dog"]["status"] == "published"


def test_api_pub_07_profile_back_after_republish(client, login_as, world):
    token = login_as(world.staff1)
    _post(client, token, world.dog_pub.id, "unpublish")
    client.cookies.clear()
    assert client.get(f"/api/public/dogs/{world.dog_pub.public_slug}").status_code == 404
    token = login_as(world.staff1)
    _post(client, token, world.dog_pub.id, "publish")
    client.cookies.clear()
    assert client.get(f"/api/public/dogs/{world.dog_pub.public_slug}").status_code == 200


def test_api_pub_08_adopted(client, login_as, world, db):
    def counts():
        db.expire_all()
        return (
            db.scalar(select(func.count()).select_from(Clip).where(Clip.dog_id == world.dog_pub.id)),
            db.scalar(select(func.count()).select_from(Fact).where(Fact.dog_id == world.dog_pub.id)),
        )

    before = counts()
    token = login_as(world.staff1)
    r = _post(client, token, world.dog_pub.id, "adopted")
    assert r.status_code == 200, r.text
    dog = r.json()["dog"]
    assert dog["status"] == "adopted" and dog["adopted_at"].endswith("Z")
    assert counts() == before
    listed = {i["dog"]["id"]: i["dog"] for i in client.get("/api/dogs").json()["dogs"]}
    assert listed[world.dog_pub.id]["status"] == "adopted"
    assert client.get(f"/api/dogs/{world.dog_pub.id}").status_code == 200


def test_api_pub_08_draft_to_adopted_and_volunteer(client, login_as, world):
    token = login_as(world.vol1)
    r = _post(client, token, world.dog_review.id, "adopted")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"
    token = login_as(world.staff1)
    r = _post(client, token, world.dog_review.id, "adopted")
    assert r.status_code == 200 and r.json()["dog"]["status"] == "adopted"


def test_api_pub_08_adopted_hidden_reads(client, container, login_as, world):
    token = login_as(world.staff1)
    clip = world.clips_pub["c1"]
    put_clip_file(container, clip)  # the pipeline would have written it
    slug = world.dog_pub.public_slug
    client.cookies.clear()
    assert client.get(f"/api/public/dogs/{slug}").status_code == 200
    token = login_as(world.staff1)
    _post(client, token, world.dog_pub.id, "adopted")
    client.cookies.clear()
    assert client.get(f"/api/public/dogs/{slug}").status_code == 404
    assert client.get(f"/media/{clip.id}.mp4").status_code == 404
    login_as(world.vol1)
    assert client.get(f"/media/{clip.id}.mp4").status_code == 200


def test_api_pub_09_adopted_reopen(client, login_as, world, db):
    token = login_as(world.staff1)
    r = _post(client, token, world.dog_adopted.id, "unpublish")
    assert r.status_code == 200, r.text
    assert r.json()["dog"]["status"] == "draft" and r.json()["dog"]["adopted_at"] is None
    row = fresh(db, Dog, world.dog_adopted.id)
    assert row.status == "draft" and row.adopted_at is None


def test_api_pub_10_bad_states(client, login_as, world):
    token = login_as(world.staff1)
    r = _post(client, token, world.dog_adopted.id, "adopted")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"
    r = _post(client, token, world.dog_review.id, "unpublish")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"
    for action in ("unpublish", "adopted"):
        r = _post(client, token, world.dog_deleted.id, action)
        assert r.status_code == 404


def test_api_pub_11_hidden_profile_identical_404(client, login_as, world):
    login_as(world.staff1)
    # positive control: a published profile exists, so a 404 below is not a missing route
    client.cookies.clear()
    assert client.get(f"/api/public/dogs/{world.dog_pub.public_slug}").status_code == 200
    slugs = [
        "zzzzzzzzzzzz",
        world.dog_adopted.public_slug,
        world.dog_deleted.public_slug or "deletedslug2",
    ]
    token = login_as(world.staff1)
    r = _post(client, token, world.dog_review.id, "adopted")  # becomes a hidden draft with no slug
    assert r.status_code == 200
    client.cookies.clear()
    seen = []
    for slug in slugs:
        g = client.get(f"/api/public/dogs/{slug}")
        a = client.post(f"/api/public/dogs/{slug}/ask", json={"question": "Is he calm?"})
        seen.append((g.status_code, g.content, "set-cookie" in g.headers, a.status_code, a.content))
    assert len(set(seen)) == 1
    assert seen[0][0] == 404
