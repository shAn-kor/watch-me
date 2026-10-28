"""API-DOG-01 to API-DOG-10 (07 section 3.8)."""

from __future__ import annotations

import io

import pytest

from app.domain.situations import SITUATION_ORDER
from app.models import Dog
from tests.api._s2_support import (
    LANE_S3_S4,
    LANE_S5,
    cross_lane,
    csrf,
    dog_body,
    fresh,
    make_gif,
    make_jpeg_with_gps,
    make_png,
)


@pytest.fixture
def world(seed):
    return seed.standard_world()


# ---------------------------------------------------------------- API-DOG-01


def test_api_dog_01_create_dog(client, login_as, world, db):
    token = login_as(world.vol1)
    r = client.post("/api/dogs", json=dog_body(), headers=csrf(token))
    assert r.status_code == 201, r.text
    dog = r.json()["dog"]
    assert dog["status"] == "draft"
    assert dog["public_slug"] is None and dog["public_path"] is None
    assert dog["created_by"] == world.vol1.id
    assert dog["photo_url"] is None
    assert dog["name"] == "Biscuit" and dog["location"] == "Portland, OR"
    assert dog["published_at"] is None and dog["adopted_at"] is None
    assert dog["created_at"].endswith("Z")
    row = fresh(db, Dog, dog["id"])
    assert row.org_id == world.org_a.id


def test_api_dog_01_create_without_csrf_and_without_login(client, login_as, world):
    assert client.post("/api/dogs", json=dog_body()).status_code == 401
    login_as(world.vol1)
    r = client.post("/api/dogs", json=dog_body())
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"


def test_api_dog_01_location_optional_and_blank_becomes_null(client, login_as, world):
    token = login_as(world.vol1)
    body = dog_body()
    del body["location"]
    r = client.post("/api/dogs", json=body, headers=csrf(token))
    assert r.status_code == 201 and r.json()["dog"]["location"] is None
    r = client.post("/api/dogs", json=dog_body(location="   "), headers=csrf(token))
    assert r.status_code == 201 and r.json()["dog"]["location"] is None


# ---------------------------------------------------------------- API-DOG-02


@pytest.mark.parametrize(
    ("over", "path"),
    [
        ({"name": ""}, "body.name"),
        ({"name": "   "}, "body.name"),
        ({"name": "n" * 61}, "body.name"),
        ({"sex": "x"}, "body.sex"),
        ({"size": "huge"}, "body.size"),
        ({"age_estimate": "a" * 41}, "body.age_estimate"),
        ({"location": "l" * 121}, "body.location"),
    ],
)
def test_api_dog_02_validation(client, login_as, world, over, path):
    token = login_as(world.vol1)
    r = client.post("/api/dogs", json=dog_body(**over), headers=csrf(token))
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert path in [f["path"] for f in err["details"]["fields"]]


def test_api_dog_02_boundaries_pass(client, login_as, world):
    token = login_as(world.vol1)
    body = dog_body(name="n" * 60, age_estimate="a" * 40, location="l" * 120)
    assert client.post("/api/dogs", json=body, headers=csrf(token)).status_code == 201


# ---------------------------------------------------------------- API-DOG-03


def test_api_dog_03_list_shows_coverage_and_counts(client, login_as, world):
    login_as(world.vol1)
    r = client.get("/api/dogs")
    assert r.status_code == 200, r.text
    items = r.json()["dogs"]
    by_id = {i["dog"]["id"]: i for i in items}
    for item in items:
        assert set(item) == {"dog", "coverage", "counts"}
        assert set(item["coverage"]) == {"situations_total", "situations_covered"}
        assert item["coverage"]["situations_total"] == 8
        assert set(item["counts"]) == {
            "draft_facts",
            "confirmed_facts",
            "sessions_in_review",
            "clips",
        }
    assert world.dog_deleted.id not in by_id
    assert world.dog_b.id not in by_id
    assert world.dog_pub.id in by_id and world.dog_adopted.id in by_id

    pub = by_id[world.dog_pub.id]
    assert pub["coverage"]["situations_covered"] == 3
    assert pub["counts"] == {
        "draft_facts": 1,
        "confirmed_facts": 5,
        "sessions_in_review": 2,
        "clips": 4,
    }
    empty = by_id[world.dog_empty.id]
    assert empty["coverage"]["situations_covered"] == 0
    assert empty["counts"] == {
        "draft_facts": 0,
        "confirmed_facts": 0,
        "sessions_in_review": 0,
        "clips": 0,
    }
    review = by_id[world.dog_review.id]
    assert review["counts"]["draft_facts"] == 6 and review["counts"]["clips"] == 3
    assert review["coverage"]["situations_covered"] == 0

    created = [i["dog"]["created_at"] for i in items]
    assert created == sorted(created, reverse=True)


# ---------------------------------------------------------------- API-DOG-04


def test_api_dog_04_list_and_detail_coverage_agree(client, login_as, world):
    login_as(world.vol1)
    listed = {i["dog"]["id"]: i for i in client.get("/api/dogs").json()["dogs"]}
    detail = client.get(f"/api/dogs/{world.dog_pub.id}").json()
    cov = detail["coverage"]
    assert cov["situations_covered"] == listed[world.dog_pub.id]["coverage"][
        "situations_covered"
    ] == 3
    assert cov["situations_total"] == 8
    assert [e["situation"] for e in cov["by_situation"]] == list(SITUATION_ORDER)
    by = {e["situation"]: e for e in cov["by_situation"]}
    assert by["leash_walk"] == {
        "situation": "leash_walk",
        "label": "Leash walk",
        "covered": True,
        "clip_count": 1,
        "filmed_s": 20,
        "confirmed_s": 3,
    }
    assert by["new_person"]["covered"] and by["new_person"]["confirmed_s"] == 5
    assert by["children_cats"]["covered"] and by["children_cats"]["clip_count"] == 1
    assert not by["handling"]["covered"] and by["handling"]["filmed_s"] == 0
    assert [n["situation"] for n in cov["not_observed"]] == [
        s for s in SITUATION_ORDER if not by[s]["covered"]
    ]
    assert cov["not_observed"][0] == {"situation": "handling", "label": "Handling"}


@cross_lane(LANE_S5)
def test_api_dog_04_public_profile_agrees(client, login_as, world):
    login_as(world.vol1)
    detail = client.get(f"/api/dogs/{world.dog_pub.id}").json()
    client.cookies.clear()
    r = client.get(f"/api/public/dogs/{world.dog_pub.public_slug}")
    assert r.status_code == 200
    pub = r.json()
    assert pub["coverage"]["situations_covered"] == detail["coverage"]["situations_covered"]
    assert pub["coverage"]["by_situation"] == detail["coverage"]["by_situation"]


# ---------------------------------------------------------------- API-DOG-05


def test_api_dog_05_dog_detail(client, login_as, world, seed):
    # extra rows the detail must hide
    gone = seed.clip(
        seed.session(world.dog_review, world.vol1), 1, deleted_at=seed.clock.now()
    )
    seed.fact(world.dog_review, status="deleted", behavior="Removed behavior text.")
    seed.fact(
        world.dog_review,
        merged=False,
        behavior="Unmerged draft waiting for the merge.",
    )
    seed.fact(
        world.dog_review,
        situation="handling",
        session=world.session_review,
        behavior="Newer handling observation text.",
        observed_on=world.session_review.observed_on,
    )

    login_as(world.vol1)
    r = client.get(f"/api/dogs/{world.dog_review.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"dog", "coverage", "checklist", "sessions", "clips", "facts"}
    assert body["dog"]["id"] == world.dog_review.id
    assert len(body["coverage"]["by_situation"]) == 8

    sessions = {s["id"]: s for s in body["sessions"]}
    s = sessions[world.session_review.id]
    assert s["clip_count"] == 3 and s["ready_clip_count"] == 3
    assert s["draft_fact_count"] == 6 + 1  # six seeded plus the handling fact
    assert s["owner_name"] == world.vol1.display_name
    assert s["situations"] == ["leash_walk", "new_person", "children_cats"]

    clip_ids = [c["id"] for c in body["clips"]]
    assert clip_ids[:3] == [c.id for c in world.clips_review]
    assert gone.id not in clip_ids
    created = [c["created_at"] for c in body["clips"]]
    assert created == sorted(created)

    facts = body["facts"]
    texts = [f["behavior"] for f in facts]
    assert "Removed behavior text." not in texts
    assert "Unmerged draft waiting for the merge." not in texts
    assert len(facts) == 7
    order = [SITUATION_ORDER.index(f["situation"]) for f in facts]
    assert order == sorted(order)
    for f in facts:
        assert f["status"] in ("draft", "confirmed")
        assert {"can_confirm", "blocked_reason", "clip_length", "evidence"} <= set(f)


def test_api_dog_05_facts_sorted_by_observed_on_desc(client, login_as, world, seed):
    from datetime import date

    older = seed.fact(
        world.dog_review,
        situation="alone_time",
        behavior="Older alone-time observation here.",
        observed_on=date(2026, 10, 1),
    )
    newer = seed.fact(
        world.dog_review,
        situation="alone_time",
        behavior="Newer alone-time observation here.",
        observed_on=date(2026, 10, 20),
    )
    login_as(world.vol1)
    facts = client.get(f"/api/dogs/{world.dog_review.id}").json()["facts"]
    ids = [f["id"] for f in facts if f["situation"] == "alone_time"]
    assert ids == [newer.id, older.id]


def test_api_dog_05_unknown_and_other_org_dog_404(client, login_as, world):
    login_as(world.vol1)
    for dog_id in ("0" * 32, world.dog_b.id):
        r = client.get(f"/api/dogs/{dog_id}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


# ---------------------------------------------------------------- API-DOG-10


def test_api_dog_10_creator_evidence_carries_media_urls(client, login_as, world, seed):
    sess = world.session_review
    with_tr = world.clips_review[0]
    seed.transcript(with_tr, "hello there", "good dog")
    no_tr = world.clips_review[1]
    processing = seed.clip(seed.session(world.dog_review, world.vol1), 1, status="processing")
    seed.fact(
        world.dog_review,
        behavior="Evidence on a clip with transcript rows.",
        session=sess,
        clip=with_tr,
    )
    seed.fact(
        world.dog_review,
        behavior="Evidence on a clip without transcript rows.",
        session=sess,
        clip=no_tr,
    )
    seed.fact(
        world.dog_review,
        behavior="Evidence on a clip that is not ready.",
        session=sess,
        clip=processing,
    )
    login_as(world.vol1)
    facts = client.get(f"/api/dogs/{world.dog_review.id}").json()["facts"]
    seen = {}
    for fact in facts:
        for ev in fact["evidence"]:
            assert set(ev) >= {
                "id",
                "clip_id",
                "start_s",
                "end_s",
                "played_by_me",
                "media_url",
                "captions_url",
            }
            seen[ev["clip_id"]] = ev
    ok = seen[with_tr.id]
    assert ok["media_url"] == f"/media/{with_tr.id}.mp4"
    assert ok["captions_url"] == f"/media/{with_tr.id}.vtt"
    assert ok["played_by_me"] is False
    plain = seen[no_tr.id]
    assert plain["media_url"] == f"/media/{no_tr.id}.mp4"
    assert plain["captions_url"] is None
    waiting = seen[processing.id]
    assert waiting["media_url"] is None and waiting["captions_url"] is None


@cross_lane(LANE_S3_S4)
def test_api_dog_10_session_and_patch_fact_carry_media_urls(client, login_as, world, seed):
    clip = world.clips_review[0]
    fact = seed.fact(
        world.dog_review, session=world.session_review, clip=clip, behavior="Cited behavior text."
    )
    token = login_as(world.vol1)
    sess = client.get(f"/api/sessions/{world.session_review.id}").json()
    ev = next(f for f in sess["facts"] if f["id"] == fact.id)["evidence"][0]
    assert ev["media_url"] == f"/media/{clip.id}.mp4"
    r = client.patch(
        f"/api/facts/{fact.id}",
        json={"behavior": "Edited behavior text here."},
        headers=csrf(token),
    )
    assert r.json()["fact"]["evidence"][0]["media_url"] == f"/media/{clip.id}.mp4"


# ---------------------------------------------------------------- API-DOG-06


def test_api_dog_06_patch_dog(client, login_as, world, db):
    token = login_as(world.vol1)
    url = f"/api/dogs/{world.dog_review.id}"
    r = client.patch(url, json={"age_estimate": "about 4 years"}, headers=csrf(token))
    assert r.status_code == 200, r.text
    assert r.json()["dog"]["age_estimate"] == "about 4 years"
    assert r.json()["dog"]["name"] == "Review"

    client.patch(url, json={"location": "Salem"}, headers=csrf(token))
    r = client.patch(url, json={"location": None}, headers=csrf(token))
    assert r.status_code == 200 and r.json()["dog"]["location"] is None
    assert fresh(db, Dog, world.dog_review.id).location is None

    r = client.patch(url, json={}, headers=csrf(token))
    assert r.status_code == 200

    r = client.patch(
        f"/api/dogs/{world.dog_deleted.id}", json={"age_estimate": "x"}, headers=csrf(token)
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.patch(
        f"/api/dogs/{world.dog_b.id}", json={"age_estimate": "x"}, headers=csrf(token)
    )
    assert r.status_code == 404


@pytest.mark.parametrize(
    "body",
    [{"name": ""}, {"name": None}, {"sex": "x"}, {"size": None}, {"location": "l" * 121}],
)
def test_api_dog_06_patch_validation(client, login_as, world, body):
    token = login_as(world.vol1)
    r = client.patch(f"/api/dogs/{world.dog_review.id}", json=body, headers=csrf(token))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_api_dog_06_published_header_edit_allowed(client, login_as, world):
    token = login_as(world.vol1)
    r = client.patch(
        f"/api/dogs/{world.dog_pub.id}", json={"name": "Renamed"}, headers=csrf(token)
    )
    assert r.status_code == 200 and r.json()["dog"]["name"] == "Renamed"
    assert r.json()["dog"]["status"] == "published"


@cross_lane(LANE_S5)
def test_api_dog_06_published_header_edit_visible_on_profile(client, login_as, world):
    token = login_as(world.vol1)
    client.patch(f"/api/dogs/{world.dog_pub.id}", json={"age_estimate": "7 years"}, headers=csrf(token))
    client.cookies.clear()
    pub = client.get(f"/api/public/dogs/{world.dog_pub.public_slug}").json()
    assert pub["dog"]["age_estimate"] == "7 years"


# ---------------------------------------------------------------- API-DOG-07


def _put_photo(client, dog_id, token, data, name="photo_gps.jpg", mime="image/jpeg"):
    return client.put(
        f"/api/dogs/{dog_id}/photo",
        files={"photo": (name, io.BytesIO(data), mime)},
        headers=csrf(token),
    )


def test_api_dog_07_photo_upload_strips_exif_and_resizes(
    client, login_as, world, container, db
):
    from PIL import Image

    data = make_jpeg_with_gps()
    pre = Image.open(io.BytesIO(data))
    assert pre.getexif().get_ifd(0x8825), "fixture must carry GPS tags"
    token = login_as(world.vol1)
    r = _put_photo(client, world.dog_review.id, token, data)
    assert r.status_code == 200, r.text
    dog = r.json()["dog"]
    assert dog["photo_url"] == f"/media/dogs/{world.dog_review.id}/photo.jpg"
    key = f"dogs/{world.dog_review.id}/photo.jpg"
    assert fresh(db, Dog, world.dog_review.id).photo_path == key
    stored = container.storage.open_path(key).read_bytes()
    img = Image.open(io.BytesIO(stored))
    assert img.format == "JPEG"
    assert max(img.size) == 1600
    assert img.size == (1600, 1000)
    assert not img.getexif().get_ifd(0x8825)
    assert len(img.getexif()) == 0
    assert b"Exif" not in stored[:64] and b"TestCam" not in stored


def test_api_dog_07_small_png_is_reencoded_without_upscaling(
    client, login_as, world, container
):
    from PIL import Image

    token = login_as(world.vol1)
    r = _put_photo(client, world.dog_review.id, token, make_png(), "p.png", "image/png")
    assert r.status_code == 200, r.text
    stored = container.storage.open_path(f"dogs/{world.dog_review.id}/photo.jpg").read_bytes()
    img = Image.open(io.BytesIO(stored))
    assert img.format == "JPEG" and img.size == (64, 48)


def test_api_dog_07_photo_of_hidden_dog_404(client, login_as, world):
    token = login_as(world.vol1)
    for dog_id in (world.dog_deleted.id, world.dog_b.id):
        r = _put_photo(client, dog_id, token, make_png(), "p.png", "image/png")
        assert r.status_code == 404


# ---------------------------------------------------------------- API-DOG-08


def test_api_dog_08_photo_limits(client, login_as, world):
    token = login_as(world.vol1)
    big = b"\xff\xd8\xff" + b"\0" * (9 * 1024 * 1024)
    r = _put_photo(client, world.dog_review.id, token, big)
    assert r.status_code == 413
    err = r.json()["error"]
    assert err["code"] == "file_too_large" and err["details"]["max_bytes"] == 8388608

    r = _put_photo(client, world.dog_review.id, token, make_gif(), "a.gif", "image/gif")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_file_type"

    r = _put_photo(client, world.dog_review.id, token, b"just some text\n", "fake.jpg")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_file_type"


def test_api_dog_08_missing_photo_field_is_422(client, login_as, world):
    token = login_as(world.vol1)
    r = client.put(
        f"/api/dogs/{world.dog_review.id}/photo",
        files={"other": ("a.jpg", io.BytesIO(b"x"), "image/jpeg")},
        headers=csrf(token),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------- API-DOG-09


def test_api_dog_09_photo_url_shown(client, login_as, world):
    token = login_as(world.vol1)
    assert client.get(f"/api/dogs/{world.dog_review.id}").json()["dog"]["photo_url"] is None
    _put_photo(client, world.dog_review.id, token, make_png(), "p.png", "image/png")
    dog = client.get(f"/api/dogs/{world.dog_review.id}").json()["dog"]
    assert dog["photo_url"] == f"/media/dogs/{world.dog_review.id}/photo.jpg"
    listed = {i["dog"]["id"]: i["dog"] for i in client.get("/api/dogs").json()["dogs"]}
    assert listed[world.dog_review.id]["photo_url"] == dog["photo_url"]


@cross_lane(LANE_S5)
def test_api_dog_09_photo_media_access(client, login_as, world):
    token = login_as(world.vol1)
    _put_photo(client, world.dog_review.id, token, make_png(), "p.png", "image/png")
    url = f"/media/dogs/{world.dog_review.id}/photo.jpg"
    assert client.get(url).status_code == 200  # member
    client.cookies.clear()
    assert client.get(url).status_code == 404  # anon, dog is a draft
