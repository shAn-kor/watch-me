"""Lane S5: API-PRF-01..14 (07 section 3.11), `GET /api/public/dogs/{slug}`."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app.domain.situations import SITUATION_LABELS, SITUATION_ORDER
from app.repositories.public_facts import public_facts
from tests.api._s5_support import (
    PROFILE,
    UNKNOWN_SLUG,
    all_keys,
    set_dog,
    set_fact,
)


@pytest.fixture
def world(seed):
    return seed.standard_world()


def get(client, slug):
    client.cookies.clear()
    return client.get(PROFILE.format(slug=slug))


def facts_flat(body):
    return [f for g in body["facts_by_situation"] for f in g["facts"]]


def test_api_prf_01_content(client, world, db):
    set_dog(
        db,
        world.dog_pub.id,
        photo_path=f"dogs/{world.dog_pub.id}/photo.jpg",
        sex="male",
    )
    r = get(client, world.dog_pub.public_slug)
    assert r.status_code == 200
    body = r.json()
    assert body["banner_id"] == "pub0_v1"
    dog = body["dog"]
    assert dog["slug"] == world.dog_pub.public_slug
    assert dog["name"] == "Published"
    assert dog["sex"] == "male"
    assert dog["age_estimate"] == "2 years"
    assert dog["size"] == "medium"
    assert dog["location"] == world.org_a.location  # org fallback
    assert dog["photo_url"] == f"/media/dogs/{world.dog_pub.id}/photo.jpg"
    assert dog["published_at"].endswith("Z")
    assert body["org"] == {"name": "Maple Street Rescue", "country": "US"}
    assert body["contact"] == {
        "url": None,
        "email": "contact@example.test",
        "phone": None,
    }
    assert body["ask"] == {
        "enabled": True,
        "max_question_chars": 300,
        "limit_per_hour": 10,
    }
    assert {"facts_by_situation", "not_observed", "coverage", "known_concerns"} <= set(
        body
    )
    cov = body["coverage"]
    assert cov["situations_total"] == 8 and len(cov["by_situation"]) == 8


def test_api_prf_01_own_location_wins_and_no_photo(client, world, db):
    set_dog(db, world.dog_pub.id, location="Portland, OR")
    body = get(client, world.dog_pub.public_slug).json()
    assert body["dog"]["location"] == "Portland, OR"
    assert body["dog"]["photo_url"] is None


def test_api_prf_02_headers(client, world):
    r = get(client, world.dog_pub.public_slug)
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["X-Robots-Tag"] == "noindex"


def test_api_prf_03_only_confirmed_merged_facts(client, world, db):
    r = get(client, world.dog_pub.public_slug)
    shown = {f["id"] for f in facts_flat(r.json())}
    fp = world.facts_pub
    assert shown == {
        fp[k].id
        for k in ("one_range", "two_ranges", "narration", "staff_note", "children_cats")
    }
    for hidden in ("draft", "deleted", "unmerged"):
        assert fp[hidden].id not in shown
    db.expire_all()
    assert shown == {f.id for f in public_facts(db, world.dog_pub.id)}


def test_api_prf_03_demoted_fact_disappears(client, world, db):
    set_fact(
        db,
        world.facts_pub["one_range"].id,
        status="draft",
        confirmed_at=None,
        confirmed_role=None,
        confirmed_by=None,
    )
    shown = {f["id"] for f in facts_flat(get(client, world.dog_pub.public_slug).json())}
    assert world.facts_pub["one_range"].id not in shown


def test_api_prf_04_grouping_and_order(client, seed, world):
    org, staff = world.org_a, world.staff1
    dog = seed.dog(org, staff, name="Order", status="published")
    sess = seed.session(dog, staff, status="review")
    clip = seed.clip(sess, 1)
    base = seed.clock.now()
    day = date(2026, 10, 20)

    def add(situation, label, observed, confirmed_delta):
        return seed.fact(
            dog,
            situation=situation,
            behavior=label,
            status="confirmed",
            session=sess,
            clip=clip,
            confirmed_by=staff,
            observed_on=observed,
            confirmed_at=base + timedelta(minutes=confirmed_delta),
        )

    add("children_cats", "cc", day, 0)
    add("leash_walk", "lw-old", day, 5)
    add("leash_walk", "lw-new", day + timedelta(days=3), 1)
    add("leash_walk", "lw-new-later", day + timedelta(days=3), 9)
    add("new_person", "np", day, 0)
    body = get(client, dog.public_slug).json()
    order = [g["situation"] for g in body["facts_by_situation"]]
    assert order == [
        "new_person",
        "leash_walk",
        "children_cats",
    ]  # PRD order, empty omitted
    assert [g["label"] for g in body["facts_by_situation"]] == [
        SITUATION_LABELS[s] for s in order
    ]
    leash = next(
        g for g in body["facts_by_situation"] if g["situation"] == "leash_walk"
    )
    assert [f["behavior"] for f in leash["facts"]] == [
        "lw-new-later",
        "lw-new",
        "lw-old",
    ]



def test_api_prf_05_clip_fact_fields(client, seed, world):
    seed.transcript(world.clips_pub["c1"], "Hello there", "Good dog")
    body = get(client, world.dog_pub.public_slug).json()
    fact = next(
        f for f in facts_flat(body) if f["id"] == world.facts_pub["one_range"].id
    )
    assert fact["behavior"] == "Walks on a loose leash past another dog."
    assert fact["source"] == "clip"
    assert fact["source_label"] == "Seen in clip"
    assert fact["observed_on"] == seed.clock.now().date().isoformat()
    assert fact["confirmed_by_label"] == "Confirmed by volunteer"
    assert fact["clip_length"] == {
        "clip_count": 1,
        "seconds": 3,
        "label": "1 clip, 3 s",
    }
    c1 = world.clips_pub["c1"].id
    assert fact["evidence"] == [
        {
            "clip_id": c1,
            "start_s": 1.0,
            "end_s": 4.0,
            "media_url": f"/media/{c1}.mp4",
            "captions_url": f"/media/{c1}.vtt",
        }
    ]
    staff = next(
        f for f in facts_flat(body) if f["id"] == world.facts_pub["children_cats"].id
    )
    assert staff["confirmed_by_label"] == "Confirmed by staff"
    c2 = world.clips_pub["c2"].id
    assert staff["evidence"][0]["captions_url"] is None  # no transcript rows
    assert staff["evidence"][0]["media_url"] == f"/media/{c2}.mp4"
    two = next(
        f for f in facts_flat(body) if f["id"] == world.facts_pub["two_ranges"].id
    )
    assert len(two["evidence"]) == 2
    assert two["clip_length"] == {"clip_count": 1, "seconds": 5, "label": "1 clip, 5 s"}


def test_api_prf_06_narration_and_staff_note(client, world):
    body = get(client, world.dog_pub.public_slug).json()
    flat = {f["id"]: f for f in facts_flat(body)}
    narr = flat[world.facts_pub["narration"].id]
    assert narr["source_label"] == "Said by volunteer, not in clip"
    assert narr["clip_length"]["label"] == "Narration only, 3 s"
    assert narr["evidence"][0]["start_s"] == 1.0 and narr["evidence"][0]["end_s"] == 4.0
    note = flat[world.facts_pub["staff_note"].id]
    assert note["source_label"] == "Shelter staff note"
    assert note["clip_length"] == {"clip_count": 0, "seconds": 0, "label": "No clip"}
    assert note["evidence"] == []


def test_api_prf_07_coverage_numbers_and_summary(client, seed, world):
    staff = world.staff1
    dog = seed.dog(world.org_a, staff, name="Cov", status="published")
    sess = seed.session(dog, staff, status="review")
    a = seed.clip(sess, 1, duration_s=74.0)
    b = seed.clip(sess, 2, duration_s=31.0)
    seed.fact(
        dog,
        situation="leash_walk",
        status="confirmed",
        session=sess,
        clip=a,
        ranges=[(0.0, 16.0)],
        confirmed_by=staff,
    )
    seed.fact(
        dog,
        situation="food_toys",
        status="confirmed",
        session=sess,
        clip=b,
        ranges=[(0.0, 7.0)],
        confirmed_by=staff,
    )
    cov = get(client, dog.public_slug).json()["coverage"]
    assert cov["situations_covered"] == 2
    assert cov["summary"] == "clips in 2 of 8 situations"
    by = {e["situation"]: e for e in cov["by_situation"]}
    assert [e["situation"] for e in cov["by_situation"]] == list(SITUATION_ORDER)
    assert by["leash_walk"] == {
        "situation": "leash_walk",
        "label": "Leash walk",
        "covered": True,
        "clip_count": 1,
        "filmed_s": 74,
        "confirmed_s": 16,
    }
    assert by["food_toys"]["filmed_s"] == 31 and by["food_toys"]["confirmed_s"] == 7
    assert by["new_person"] == {
        "situation": "new_person",
        "label": "Meeting a new person",
        "covered": False,
        "clip_count": 0,
        "filmed_s": 0,
        "confirmed_s": 0,
    }


def test_api_prf_08_not_observed(client, seed, world):
    staff = world.staff1
    dog = seed.dog(world.org_a, staff, name="Two", status="published")
    sess = seed.session(dog, staff, status="review")
    clip = seed.clip(sess, 1)
    for sit in ("leash_walk", "food_toys"):
        seed.fact(
            dog,
            situation=sit,
            status="confirmed",
            session=sess,
            clip=clip,
            confirmed_by=staff,
        )
    body = get(client, dog.public_slug).json()
    expected = [s for s in SITUATION_ORDER if s not in ("leash_walk", "food_toys")]
    assert [n["situation"] for n in body["not_observed"]] == expected
    assert [n["label"] for n in body["not_observed"]] == [
        SITUATION_LABELS[s] for s in expected
    ]
    assert len(body["not_observed"]) + body["coverage"]["situations_covered"] == 8


def test_api_prf_09_children_cats_notice(client, world):
    body = get(client, world.dog_pub.public_slug).json()
    for f in facts_flat(body):
        if f["id"] == world.facts_pub["children_cats"].id:
            assert f["notice"] == {
                "code": "ask_shelter_in_person_meeting",
                "text": "Ask the shelter about an in-person meeting.",
            }
        else:
            assert f["notice"] is None


def test_api_prf_10_known_concerns(client, world, db):
    none = get(client, world.dog_pub.public_slug).json()["known_concerns"]
    assert none == {"none_known": True, "text": None}
    set_dog(
        db,
        world.dog_pub.id,
        known_concerns_none=False,
        known_concerns="Pulls hard toward other dogs on leash.",
    )
    text = get(client, world.dog_pub.public_slug).json()["known_concerns"]
    assert text == {
        "none_known": False,
        "text": "Pulls hard toward other dogs on leash.",
    }


def test_api_prf_11_no_private_data(client, seed, world):
    members = [world.staff1, world.vol1, world.vol2]
    seed.transcript(world.clips_pub["c1"], "private words")
    r = get(client, world.dog_pub.public_slug)
    raw = r.text
    for m in members:
        assert m.email not in raw and m.display_name not in raw
    keys = all_keys(r.json())
    for banned in (
        "ip",
        "original_path",
        "created_by",
        "played_by_me",
        "confirmed_by",
        "member_id",
        "email_hash",
        "playback_path",
    ):
        assert banned not in keys, banned
    for name in ("draft", "deleted", "unmerged"):
        assert world.facts_pub[name].id not in raw
    assert "private words" not in raw  # transcript text is never inline
    json.loads(raw)


def test_api_prf_12_profile_read_limit(client, world):
    client.cookies.clear()
    url = PROFILE.format(slug=world.dog_pub.public_slug)
    for _ in range(120):
        assert client.get(url).status_code == 200
    r = client.get(url)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert r.json()["error"]["details"]["scope"] == "ip"


def test_api_prf_13_changes_live(client, world, db):
    slug = world.dog_pub.public_slug
    before = {f["id"] for f in facts_flat(get(client, slug).json())}
    assert world.facts_pub["two_ranges"].id in before
    set_fact(
        db,
        world.facts_pub["two_ranges"].id,
        status="draft",
        confirmed_at=None,
        confirmed_role=None,
        confirmed_by=None,
    )
    after = {f["id"] for f in facts_flat(get(client, slug).json())}
    assert after == before - {world.facts_pub["two_ranges"].id}


def test_api_prf_14_slug_case_and_format(client, world):
    unknown = get(client, UNKNOWN_SLUG)
    assert unknown.status_code == 404
    upper = get(client, world.dog_pub.public_slug.upper())
    short = get(client, "k7m2q9x4tbw")
    for r in (upper, short):
        assert r.status_code == 404
        assert r.content == unknown.content


def test_api_prf_hidden_dogs_share_one_404(client, world):
    ok = get(client, world.dog_pub.public_slug)
    assert ok.status_code == 200
    seen = {
        (r.status_code, r.content)
        for r in (
            get(client, UNKNOWN_SLUG),
            get(client, world.dog_adopted.public_slug),
            get(client, "deleteddogxx"),
        )
    }
    assert len(seen) == 1 and next(iter(seen))[0] == 404


def test_api_prf_draft_dog_slug_is_hidden(client, world, db):
    set_dog(db, world.dog_ready.id, public_slug="readyslug234")
    assert get(client, "readyslug234").status_code == 404
