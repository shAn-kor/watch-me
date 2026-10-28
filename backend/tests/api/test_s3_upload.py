"""API-UP (07 section 3.9): clip upload."""

from __future__ import annotations

import stat

import pytest
from sqlalchemy import func, select

from app.models import Clip, Dog, Job
from app.storage.base import StorageFull
from tests.api._s3_support import (  # noqa: F401
    MAX_BYTES,
    FakeUploadStream,
    clips_of,
    csrf,
    jobs,
    media,
    open_session,
    stored_keys,
    tmp_files,
    upload_bytes,
    upload_file,
    world,
)


def _code(r) -> str:
    return r.json()["error"]["code"]


def _no_trace(container, db, session_id):
    assert clips_of(db, session_id) == []
    assert stored_keys(container) == []
    assert tmp_files(container) == []
    assert jobs(db, type="transcode") == []


def test_api_up_01_upload_mp4_ok(
    client, db, container, seed, world, open_session, login_as
):
    from app.db.base import new_id  # noqa: F401

    # a dog whose people check was done earlier: the upload must clear it
    db.query(Dog).filter(Dog.id == world.dog_empty.id).update(
        {"people_check_at": seed.clock.now(), "people_check_by": world.staff1.id}
    )
    db.commit()
    token = login_as(world.vol1)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["warnings"] == []
    clip = body["clip"]
    assert clip["status"] == "uploaded" and clip["step"] == "transcode"
    assert clip["ordinal"] == 1 and clip["has_audio"] is True
    assert clip["duration_s"] == pytest.approx(5.0, abs=0.2)
    assert clip["media_url"] is None and clip["error"] is None
    assert clip["original_filename"] == "h264_5s.mp4"
    key = f"dogs/{world.dog_empty.id}/clips/{clip['id']}/original.mp4"
    assert container.storage.exists(key)
    queued = jobs(db, type="transcode")
    assert len(queued) == 1
    job = queued[0]
    assert (job.clip_id, job.session_id, job.dog_id) == (
        clip["id"],
        open_session.id,
        world.dog_empty.id,
    )
    assert job.status == "queued" and job.attempts == 0
    assert job.payload["clip_id"] == clip["id"]
    db.expire_all()
    assert db.get(Dog, world.dog_empty.id).people_check_at is None
    row = clips_of(db, open_session.id)[0]
    assert row.original_path == key and row.source_codec == "h264"
    assert tmp_files(container) == []


def test_api_up_02_upload_hevc_mov_octet_stream(
    client, db, container, world, open_session, login_as
):
    token = login_as(world.vol1)
    r = upload_file(
        client,
        token,
        open_session.id,
        "hevc_8s.mov",
        content_type="application/octet-stream",
    )
    assert r.status_code == 201, r.text
    row = clips_of(db, open_session.id)[0]
    assert row.source_codec == "hevc"
    assert row.original_path.endswith("original.mov")


def test_api_up_03_extension_check(
    client, db, container, world, open_session, login_as
):
    token = login_as(world.vol1)
    r = upload_file(
        client, token, open_session.id, "legacy.avi", content_type="video/x-msvideo"
    )
    assert r.status_code == 415 and _code(r) == "unsupported_file_type"
    assert "allowed" in r.json()["error"]["details"]
    r = upload_file(
        client, token, open_session.id, "h264_5s.mp4", filename="noextension"
    )
    assert r.status_code == 415 and _code(r) == "unsupported_file_type"
    assert clips_of(db, open_session.id) == []
    r = upload_file(client, token, open_session.id, "hevc_8s.mov", filename="A.MOV")
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("key", ["not_video.mp4", "audio_only.mp4"])
def test_api_up_04_content_check_by_probe(
    client, db, container, world, open_session, login_as, key
):
    token = login_as(world.vol1)
    r = upload_file(client, token, open_session.id, key)
    assert r.status_code == 415 and _code(r) == "unsupported_file_type"
    _no_trace(container, db, open_session.id)


def test_api_up_05_size_by_content_length(
    client, db, container, world, open_session, login_as
):
    token = login_as(world.vol1)
    stream = FakeUploadStream(1024, declare=MAX_BYTES + 1)
    r = stream.post(client, token, open_session.id)
    assert r.status_code == 413 and _code(r) == "file_too_large"
    assert r.json()["error"]["details"]["max_bytes"] == MAX_BYTES
    assert stream.sent == 0  # the body was not read
    _no_trace(container, db, open_session.id)


def test_api_up_06_size_with_dishonest_length(
    client, db, container, world, open_session, login_as
):
    token = login_as(world.vol1)
    stream = FakeUploadStream(MAX_BYTES + 1, declare=None)
    r = stream.post(client, token, open_session.id)
    assert r.status_code == 413 and _code(r) == "file_too_large"
    assert stream.sent <= MAX_BYTES + stream.chunk  # aborted at the limit, not drained
    _no_trace(container, db, open_session.id)


def test_api_up_07_size_boundary(client, db, container, world, open_session, login_as):
    token = login_as(world.vol1)
    prefix = media("h264_5s.mp4").read_bytes()
    stream = FakeUploadStream(MAX_BYTES, prefix=prefix, declare=None)
    r = stream.post(client, token, open_session.id)
    assert r.status_code != 413, r.text  # the probe decides
    assert stream.sent == MAX_BYTES


def test_api_up_08_duration_boundary(client, db, container, seed, world, login_as):
    token = login_as(world.vol1)
    ok = seed.session(world.dog_empty, world.vol1)
    r = upload_file(client, token, ok.id, "len_120_4s.mp4")
    assert r.status_code == 201, r.text  # 0.5 s tolerance
    too_long = seed.session(world.dog_empty, world.vol1)
    r = upload_file(client, token, too_long.id, "len_120_6s.mp4")
    assert r.status_code == 422 and _code(r) == "clip_too_long"
    d = r.json()["error"]["details"]
    assert d["max_s"] == 120 and d["duration_s"] == pytest.approx(120.6, abs=0.1)
    assert clips_of(db, too_long.id) == []
    assert not any(too_long.id in k for k in stored_keys(container))
    assert tmp_files(container) == []


def test_api_up_09_three_clip_limit(
    client, db, container, seed, world, open_session, login_as
):
    token = login_as(world.vol1)
    ids = []
    for _ in range(3):
        r = upload_file(client, token, open_session.id, "h264_5s.mp4")
        assert r.status_code == 201, r.text
        ids.append(r.json()["clip"]["id"])
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 409 and _code(r) == "clip_limit_reached"
    staff_token = login_as(world.staff1)
    d = client.delete(f"/api/clips/{ids[1]}", headers=csrf(staff_token))
    assert d.status_code == 202
    token = login_as(world.vol1)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 201 and r.json()["clip"]["ordinal"] == 2


def test_api_up_10_session_and_dog_state(client, seed, world, login_as):
    token = login_as(world.vol1)
    processing = seed.session(world.dog_empty, world.vol1, status="processing")
    published = seed.session(world.dog_pub, world.vol1, status="open")
    adopted = seed.session(world.dog_adopted, world.vol1, status="open")
    for sess in (processing, published, adopted):
        r = upload_file(client, token, sess.id, "h264_5s.mp4")
        assert r.status_code == 409 and _code(r) == "invalid_state", sess.id


def test_upload_to_deleted_dog_is_404(client, seed, world, login_as):
    token = login_as(world.vol1)
    sess = seed.session(world.dog_deleted, world.vol1, status="open")
    r = upload_file(client, token, sess.id, "h264_5s.mp4")
    assert r.status_code == 404 and _code(r) == "not_found"


def test_api_up_11_ownership(client, db, world, open_session, login_as):
    token = login_as(world.vol2)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 403 and _code(r) == "not_own_session"
    token = login_as(world.staff1)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 201
    token = login_as(world.staff_b)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 404


def test_api_up_12_consent_first(client, db, container, seed, world, login_as):
    sess = seed.session(world.dog_empty, world.vol_new, status="open")
    token = login_as(world.vol_new)
    r = upload_file(client, token, sess.id, "h264_5s.mp4")
    assert r.status_code == 403 and _code(r) == "consent_required"
    _no_trace(container, db, sess.id)


def test_api_up_13_truncated_upload(
    client, db, container, world, open_session, login_as
):
    token = login_as(world.vol1)
    stream = FakeUploadStream(4 * 1024 * 1024, abort_at=0.5)
    r = stream.post(client, token, open_session.id)
    assert r.status_code == 400 and _code(r) == "upload_incomplete"
    _no_trace(container, db, open_session.id)


def test_api_up_14_idempotent_retry(
    client, db, container, world, open_session, login_as
):
    token = login_as(world.vol1)
    first = upload_file(
        client,
        token,
        open_session.id,
        "h264_5s.mp4",
        fields={"client_request_id": "r1"},
    )
    assert first.status_code == 201
    second = upload_file(
        client,
        token,
        open_session.id,
        "h264_5s.mp4",
        fields={"client_request_id": "r1"},
    )
    assert second.status_code == 200
    assert second.json()["clip"]["id"] == first.json()["clip"]["id"]
    assert len(clips_of(db, open_session.id)) == 1
    assert len(stored_keys(container)) == 1
    assert len(jobs(db, type="transcode")) == 1
    assert tmp_files(container) == []


def test_api_up_15_no_audio_warning(client, db, world, open_session, login_as):
    token = login_as(world.vol1)
    r = upload_file(client, token, open_session.id, "silent_5s.mp4")
    assert r.status_code == 201
    assert r.json()["warnings"] == ["no_audio_track"]
    assert r.json()["clip"]["has_audio"] is False


def test_api_up_16_storage_full(
    client, db, container, monkeypatch, world, open_session, login_as
):
    def boom(*_a, **_k):
        raise StorageFull("no space left on device")

    monkeypatch.setattr(container.storage, "put_file", boom)
    token = login_as(world.vol1)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 503 and _code(r) == "storage_unavailable"
    _no_trace(container, db, open_session.id)


def test_api_up_17_upload_rate_limit(client, seed, clock, world, login_as):
    token = login_as(world.vol1)
    tiny = media("h264_5s.mp4").read_bytes()
    sessions = [seed.session(world.dog_empty, world.vol1) for _ in range(22)]
    for sess in sessions[:20]:
        r = upload_bytes(client, token, sess.id, tiny, "t.mp4")
        assert r.status_code == 201, r.text
    r = upload_bytes(client, token, sessions[20].id, tiny, "t.mp4")
    assert r.status_code == 429 and _code(r) == "rate_limited"
    assert r.json()["error"]["details"]["scope"] == "member"
    assert int(r.headers["Retry-After"]) > 0
    clock.advance(3601)
    r = upload_bytes(client, token, sessions[20].id, tiny, "t.mp4")
    assert r.status_code == 201


def test_api_up_18_check_order_matrix(client, db, container, seed, world, login_as):
    # no consent beats oversize
    sess_new = seed.session(world.dog_empty, world.vol_new)
    token = login_as(world.vol_new)
    r = FakeUploadStream(1024, declare=MAX_BYTES + 1).post(client, token, sess_new.id)
    assert _code(r) == "consent_required"
    # wrong owner beats the 4th clip
    full = seed.session(world.dog_empty, world.vol1)
    for i in (1, 2, 3):
        seed.clip(full, i)
    token = login_as(world.vol2)
    r = upload_file(client, token, full.id, "h264_5s.mp4")
    assert _code(r) == "not_own_session"
    # not found beats everything
    r = upload_file(client, token, "e" * 32, "h264_5s.mp4")
    assert _code(r) == "not_found"
    # state beats the clip limit
    done = seed.session(world.dog_empty, world.vol2, status="processing")
    for i in (1, 2, 3):
        seed.clip(done, i)
    r = upload_file(client, token, done.id, "h264_5s.mp4")
    assert _code(r) == "invalid_state"
    # the clip limit beats the size gate
    token = login_as(world.vol1)
    r = FakeUploadStream(1024, declare=MAX_BYTES + 1).post(client, token, full.id)
    assert _code(r) == "clip_limit_reached"
    # size beats the extension check
    fresh = seed.session(world.dog_empty, world.vol1)
    r = FakeUploadStream(1024, declare=MAX_BYTES + 1, filename="movie.avi").post(
        client, token, fresh.id
    )
    assert _code(r) == "file_too_large"
    # extension beats the duration (a legacy file is never probed for length)
    r = upload_file(client, token, fresh.id, "legacy.avi")
    assert _code(r) == "unsupported_file_type"


def test_api_up_19_probe_timeout(
    client, db, container, tmp_path, world, open_session, login_as
):
    script = tmp_path / "slow_ffprobe.sh"
    script.write_text("#!/bin/sh\nsleep 12\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    ff = container.pipeline["ffmpeg"]
    ff.ffprobe_bin = str(script)
    ff.probe_timeout_s = 1  # the 10 s bound of 01, shortened for the test
    token = login_as(world.vol1)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 415 and _code(r) == "unsupported_file_type"
    assert r.json()["error"]["details"]["reason"] == "probe_timeout"
    _no_trace(container, db, open_session.id)


def test_api_up_20_filename_handling(
    client, db, container, world, open_session, login_as
):
    from tests.api._s3_support import BOUNDARY, TAIL, csrf as _csrf, part_head

    token = login_as(world.vol1)
    data = media("h264_5s.mp4").read_bytes()
    evil = b"../../evil\x01\x1f.mp4"
    body = part_head(evil) + data + TAIL
    r = client.post(
        f"/api/sessions/{open_session.id}/clips",
        content=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={BOUNDARY}",
            **_csrf(token),
        },
    )
    assert r.status_code == 201, r.text
    name = r.json()["clip"]["original_filename"]
    assert (
        not any(ord(c) < 32 for c in name)
        and "/" not in name
        and ".." not in name.replace("evil", "")
    )
    long_name = ("a" * 296) + ".mp4"
    r = upload_file(client, token, open_session.id, "h264_5s.mp4", filename=long_name)
    assert r.status_code == 201
    assert len(r.json()["clip"]["original_filename"]) <= 200
    for key in stored_keys(container):
        assert key.startswith(f"dogs/{world.dog_empty.id}/clips/")
        assert key.rsplit("/", 1)[1] == "original.mp4"
    assert tmp_files(container) == []


def test_api_up_21_tmp_never_public(
    client, db, container, world, open_session, login_as
):
    token = login_as(world.vol1)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    clip_id = r.json()["clip"]["id"]
    for path in (
        f"/media/{clip_id}.mp4",
        f"/media/{clip_id}.mov",
        "/media/tmp/x",
        f"/media/dogs/{world.dog_empty.id}/clips/{clip_id}/original.mp4",
    ):
        assert client.get(path).status_code == 404, path


def test_upload_total_rows_only_on_success(
    client, db, container, world, open_session, login_as
):
    before = (
        db.scalar(select(func.count()).select_from(Clip)),
        db.scalar(select(func.count()).select_from(Job)),
    )
    token = login_as(world.vol1)
    upload_file(client, token, open_session.id, "not_video.mp4")
    db.expire_all()
    assert (
        db.scalar(select(func.count()).select_from(Clip)),
        db.scalar(select(func.count()).select_from(Job)),
    ) == before
