"""Lane S5: API-MED-01..20 (07 section 3.13), `/media/...`."""

from __future__ import annotations

import pytest

from tests.api._s5_support import (
    comparable,
    put_clip_file,
    put_file,
    set_clip,
    set_dog,
    set_fact,
)

BODY = bytes(range(256)) * 4  # 1024 bytes


@pytest.fixture
def world(seed, container):
    w = seed.standard_world()
    for clip in list(w.clips_pub.values()) + w.clips_review:
        put_clip_file(container, clip, BODY)
    return w


def mp4(clip):
    return f"/media/{clip.id}.mp4"


def vtt(clip):
    return f"/media/{clip.id}.vtt"


def anon(client, url, **kw):
    client.cookies.clear()
    return client.get(url, **kw)


def member(client, login_as, who, url, **kw):
    login_as(who)
    return client.get(url, **kw)


def own_dog_clip(seed, world, container, *, status, confirmed=True, **dog_kw):
    """A dog in org A with one ready clip (file written), cited by one confirmed fact."""
    dog = seed.dog(
        world.org_a, world.staff1, name=f"D-{status}", status=status, **dog_kw
    )
    sess = seed.session(dog, world.vol1, status="review")
    clip = seed.clip(sess, 1)
    put_clip_file(container, clip, BODY)
    fact = None
    if confirmed:
        fact = seed.fact(
            dog, status="confirmed", session=sess, clip=clip, confirmed_by=world.staff1
        )
    return dog, clip, fact


def test_api_med_01_public_cited_clip(client, world):
    r = anon(client, mp4(world.clips_pub["c1"]))
    assert r.status_code == 200
    assert r.headers["content-type"] == "video/mp4"
    assert r.content == BODY


def test_api_med_02_uncited_clip(client, login_as, world):
    for key in ("uncited", "draft_only"):
        r = anon(client, mp4(world.clips_pub[key]))
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert (
        member(
            client, login_as, world.vol1, mp4(world.clips_pub["uncited"])
        ).status_code
        == 200
    )


def test_api_med_03_fact_demoted(client, world, db, seed, container):
    dog, clip, fact = own_dog_clip(seed, world, container, status="published")
    assert anon(client, mp4(clip)).status_code == 200
    set_fact(
        db,
        fact.id,
        status="draft",
        confirmed_at=None,
        confirmed_role=None,
        confirmed_by=None,
    )
    assert anon(client, mp4(clip)).status_code == 404


def test_api_med_04_draft_dog(client, login_as, world, seed, container):
    _dog, clip, _f = own_dog_clip(seed, world, container, status="draft")
    assert anon(client, mp4(clip)).status_code == 404
    assert member(client, login_as, world.vol1, mp4(clip)).status_code == 200


def test_api_med_05_adopted_dog(client, login_as, world, seed, container):
    _dog, clip, _f = own_dog_clip(seed, world, container, status="adopted")
    assert anon(client, mp4(clip)).status_code == 404
    assert member(client, login_as, world.vol1, mp4(clip)).status_code == 200


def test_api_med_06_deleted_dog(client, login_as, world, seed, container):
    _dog, clip, _f = own_dog_clip(
        seed, world, container, status="deleted", confirmed=False
    )
    assert anon(client, mp4(clip)).status_code == 404
    assert member(client, login_as, world.vol1, mp4(clip)).status_code == 404


def test_api_med_07_unpublish_takes_effect(client, login_as, world):
    clip = world.clips_pub["c1"]
    assert anon(client, mp4(clip)).status_code == 200
    token = login_as(world.staff1)
    r = client.post(
        f"/api/dogs/{world.dog_pub.id}/unpublish",
        json={},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200
    assert anon(client, mp4(clip)).status_code == 404


@pytest.mark.parametrize("state", ["soft_deleted", "uploaded", "processing", "failed"])
def test_api_med_08_clip_states(client, login_as, world, seed, container, db, state):
    sess = seed.session(world.dog_pub, world.vol1, status="review")
    kw = {"status": state}
    if state == "soft_deleted":
        kw = {"status": "ready", "deleted_at": seed.clock.now()}
    if state == "failed":
        kw["fail_code"] = "transcode_failed"
    clip = seed.clip(sess, 1, **kw)
    set_clip(
        db, clip.id, playback_path=f"dogs/{clip.dog_id}/clips/{clip.id}/playback.mp4"
    )
    put_file(container, f"dogs/{clip.dog_id}/clips/{clip.id}/playback.mp4", BODY)
    assert member(client, login_as, world.vol1, mp4(clip)).status_code == 404
    assert anon(client, mp4(clip)).status_code == 404


def test_api_med_09_other_org(client, login_as, world):
    r = member(client, login_as, world.staff_b, mp4(world.clips_pub["uncited"]))
    assert r.status_code == 404


def test_api_med_10_revoked_cookie(client, login_as, world):
    url = mp4(world.clips_pub["uncited"])
    token = login_as(world.vol1)
    assert client.get(url).status_code == 200
    old = client.cookies.get("wm_session")
    assert (
        client.post("/api/auth/logout", headers={"X-CSRF-Token": token}).status_code
        == 204
    )
    client.cookies.clear()
    client.cookies.set("wm_session", old)
    assert client.get(url).status_code == 404


def test_api_med_11_identical_denials(client, login_as, world, seed, container):
    _d, draft_clip, _f = own_dog_clip(seed, world, container, status="draft")
    unknown = comparable(anon(client, "/media/" + "0" * 32 + ".mp4"))
    hidden = comparable(anon(client, mp4(draft_clip)))
    uncited = comparable(anon(client, mp4(world.clips_pub["uncited"])))
    login_as(world.staff_b)
    other_org = comparable(client.get(mp4(world.clips_pub["uncited"])))
    assert unknown[0] == 404
    assert unknown == hidden == uncited == other_org


def test_api_med_12_captions(client, login_as, world, seed):
    c1, uncited = world.clips_pub["c1"], world.clips_pub["uncited"]
    seed.transcript(c1, "Hello there", "Good dog")
    seed.transcript(uncited, "secret")
    r = anon(client, vtt(c1))
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/vtt; charset=utf-8"
    assert r.text.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.000" in r.text and "Hello there" in r.text
    assert "00:00:01.000 --> 00:00:02.000" in r.text and "Good dog" in r.text
    assert anon(client, vtt(uncited)).status_code == 404
    assert member(client, login_as, world.vol1, vtt(uncited)).status_code == 200


def test_api_med_13_captions_absent(client, world):
    assert anon(client, vtt(world.clips_pub["c2"])).status_code == 404


def test_api_med_14_photo_access(client, login_as, world, container, db):
    def photo(dog):
        key = f"dogs/{dog.id}/photo.jpg"
        put_file(container, key, b"\xff\xd8\xff\xe0jpeg")
        set_dog(db, dog.id, photo_path=key)
        return f"/media/dogs/{dog.id}/photo.jpg"

    pub = photo(world.dog_pub)
    r = anon(client, pub)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    draft = photo(world.dog_ready)
    assert anon(client, draft).status_code == 404
    assert member(client, login_as, world.vol1, draft).status_code == 200
    nophoto = f"/media/dogs/{world.dog_review.id}/photo.jpg"
    assert anon(client, nophoto).status_code == 404
    assert member(client, login_as, world.vol1, nophoto).status_code == 404


def test_api_med_15_range_requests(client, world):
    url, n = mp4(world.clips_pub["c1"]), len(BODY)
    r = anon(client, url, headers={"Range": "bytes=100-199"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 100-199/{n}"
    assert r.headers["content-length"] == "100" and r.content == BODY[100:200]
    r = anon(client, url, headers={"Range": "bytes=0-"})
    assert r.status_code == 206 and r.headers["content-range"] == f"bytes 0-{n - 1}/{n}"
    r = anon(client, url, headers={"Range": f"bytes={n}-"})
    assert r.status_code == 416 and r.headers["content-range"] == f"bytes */{n}"
    r = anon(client, url, headers={"Range": "bytes=100-"})
    assert (
        r.status_code == 206 and r.headers["content-range"] == f"bytes 100-{n - 1}/{n}"
    )
    assert r.content == BODY[100:]


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_api_med_16_headers(client, world, method):
    client.cookies.clear()
    r = client.request(method, mp4(world.clips_pub["c1"]))
    assert r.status_code == 200
    h = r.headers
    assert h["accept-ranges"] == "bytes"
    assert h["cache-control"] == "private, no-cache"
    assert h["content-disposition"] == "inline"
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-robots-tag"] == "noindex"
    assert h["vary"] == "Cookie"
    assert h["etag"] and h["last-modified"]
    if method == "HEAD":
        assert r.content == b""
        assert int(h["content-length"]) == len(BODY)


def test_api_med_17_revalidation(client, login_as, world):
    clip = world.clips_pub["c1"]
    etag = anon(client, mp4(clip)).headers["etag"]
    r = anon(client, mp4(clip), headers={"If-None-Match": etag})
    assert r.status_code == 304
    token = login_as(world.staff1)
    client.post(
        f"/api/dogs/{world.dog_pub.id}/unpublish",
        json={},
        headers={"X-CSRF-Token": token},
    )
    r = anon(client, mp4(clip), headers={"If-None-Match": etag})
    assert r.status_code == 404


def test_api_med_18_media_rate_limit(client, world):
    client.cookies.clear()
    url = mp4(world.clips_pub["c1"])
    for _ in range(600):
        assert client.get(url).status_code == 200
    r = client.get(url)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"


def test_api_med_19_route_abuse(client, world):
    cid = world.clips_pub["c1"].id
    for url in (
        "/media/..%2f..%2fetc%2fpasswd",
        f"/media/{cid}.exe",
        f"/media/{cid}",
        f"/media/dogs/{cid}/original.mov",
        f"/media/dogs/{world.dog_pub.id}/original.mov",
    ):
        assert anon(client, url).status_code == 404, url


def test_api_med_20_whole_file_of_cited_clip_is_public(client, seed, world, container):
    """D9, ADR-0043: the known limit. A range outside the cited 1-4 s is served."""
    r = anon(client, mp4(world.clips_pub["c1"]), headers={"Range": "bytes=0-10"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-10/{len(BODY)}"
