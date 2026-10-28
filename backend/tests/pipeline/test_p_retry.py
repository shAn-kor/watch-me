"""PIPE-RETRY-01..14: retries, error mapping and manual retry (07 section 3.15)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import update

from app.ai.adapters.mock import MockAdapter
from app.ai.adapters.openai_compat import OpenAICompatDrafter
from app.ai.cost import PriceTable
from app.ai.types import DraftOutput
from app.errors import JobError
from app.models import Fact
from app.pipeline.ffmpeg import FFmpeg, FFmpegError
from tests.pipeline.pipe_support import (
    FFMPEG_BIN,
    FFPROBE_BIN,
    CountingFFmpeg,
    FnDrafter,
    ai_slots,
    csrf,
)
from tests.unit.ai_helpers import VALID_DRAFT, FakeHttp, completion_body, ok


def _setup(env, media="len_25s.mp4", filename=None, ordinal=1):
    _, _, vol, dog = env.world()
    sess = env.session(dog, vol)
    clip = env.add_clip(sess, media, ordinal=ordinal, filename=filename)
    return dog, vol, sess, clip


def _stub_env(settings, make_env, http: FakeHttp, **kw):
    drafter = OpenAICompatDrafter(http.chat(), PriceTable({}), strict=True)
    return make_env(ai=ai_slots(settings, drafter=drafter), **kw)


def _retry(env, member, clip_id) -> int:
    with env.api(member) as (client, token):
        return client.post(
            f"/api/clips/{clip_id}/retry", json={}, headers=csrf(token)
        ).status_code


INVALID = "this is not json"


# ---------------------------------------------------------------- PIPE-RETRY-01


def test_pipe_retry_01_invalid_once_then_valid(settings, make_env):
    http = FakeHttp(ok(INVALID), ok(json.dumps(VALID_DRAFT)))
    env = _stub_env(settings, make_env, http)
    dog, vol, sess, clip = _setup(env)
    env.run()
    assert env.clip(clip.id).status == "ready"
    assert env.jobs("draft")[0].attempts == 1
    assert http.calls == 2
    assert len(env.ledger("draft")) == 2
    second = json.dumps(http.requests[1])
    assert len(second) > len(
        json.dumps(http.requests[0])
    )  # carries the validation error


# ---------------------------------------------------------------- PIPE-RETRY-02


def test_pipe_retry_02_invalid_twice_stub(settings, make_env):
    http = FakeHttp(ok(INVALID), ok(INVALID))
    env = _stub_env(settings, make_env, http)
    dog, vol, sess, clip = _setup(env)
    env.run()
    row = env.clip(clip.id)
    assert (row.status, row.fail_code) == ("failed", "ai_invalid_output")
    job = env.jobs("draft")[0]
    assert (job.status, job.attempts) == ("failed", 1)
    assert http.calls == 2 and len(env.ledger("draft")) == 2
    assert _retry(env, vol, clip.id) == 200  # retryable by hand


def test_pipe_retry_02_invalid_twice_mock(make_env):
    env = make_env()
    dog, vol, sess, clip = _setup(env, "silent_5s.mp4", filename="fault_invalid.mp4")
    env.mock._calls.clear()
    env.run()
    # fixture fails once: with the mock the whole step fails at attempts 1
    row = env.clip(clip.id)
    assert (row.status, row.fail_code) == ("failed", "ai_invalid_output")
    job = env.jobs("draft")[0]
    assert (job.status, job.attempts) == ("failed", 1)
    assert len(env.spy("drafter").calls["draft"]) == 1


# ---------------------------------------------------------------- PIPE-RETRY-03/04


def test_pipe_retry_03_transient_then_success(make_env):
    env = make_env()
    dog, vol, sess, clip = _setup(
        env, "silent_5s.mp4", filename="fault_transient_1.mp4"
    )
    t0 = env.clock.now()
    while env.run_step():
        pass
    job = env.jobs("draft")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    assert job.run_after == t0 + timedelta(seconds=30)
    assert len(env.spy("drafter").calls["draft"]) == 1
    env.advance(30)
    env.run()
    assert env.clip(clip.id).status == "ready"
    assert len(env.spy("drafter").calls["draft"]) == 2


def test_pipe_retry_04_transient_twice(make_env):
    env = make_env()
    dog, vol, sess, clip = _setup(
        env, "silent_5s.mp4", filename="fault_transient_2.mp4"
    )
    env.run()
    env.advance(30)
    env.run()
    row = env.clip(clip.id)
    assert (row.status, row.fail_code) == ("failed", "ai_failed")
    job = env.jobs("draft")[0]
    assert (job.status, job.attempts, job.max_attempts) == ("failed", 2, 2)
    assert len(env.spy("drafter").calls["draft"]) == 2
    with env.api(vol) as (client, _):
        body = client.get(f"/api/sessions/{sess.id}?include=none").json()
    assert body["clips"][0]["error"]["retryable"] is True


# ---------------------------------------------------------------- PIPE-RETRY-05


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_pipe_retry_05_retried_statuses(settings, make_env, status):
    def resp():
        return httpx.Response(
            status,
            json={"error": {"message": "x"}},
            headers={"Retry-After": "45"} if status == 429 else {},
        )

    http = FakeHttp(resp(), resp())
    env = _stub_env(settings, make_env, http)
    dog, vol, sess, clip = _setup(env)
    t0 = env.clock.now()
    while env.run_step():
        pass
    job = env.jobs("draft")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    assert job.run_after >= t0 + timedelta(seconds=30)
    env.advance(60)
    env.run()
    job = env.jobs("draft")[0]
    assert (job.status, job.attempts) == ("failed", 2)
    assert env.clip(clip.id).fail_code == "ai_failed"
    assert http.calls == 2


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404])
def test_pipe_retry_05_permanent_statuses(settings, make_env, status):
    http = FakeHttp(httpx.Response(status, json={"error": {"message": "x"}}))
    env = _stub_env(settings, make_env, http)
    dog, vol, sess, clip = _setup(env)
    env.run()
    job = env.jobs("draft")[0]
    assert (job.status, job.attempts) == ("failed", 1)
    assert env.clip(clip.id).fail_code == "ai_failed"
    assert http.calls == 1


@pytest.mark.xfail(
    reason="metrics `alerts` (ai_auth_error) belong to lane I", strict=False
)
@pytest.mark.parametrize("status", [401, 402, 403])
def test_pipe_retry_05_auth_errors_raise_alert(settings, make_env, status):
    http = FakeHttp(httpx.Response(status, json={"error": {"message": "x"}}))
    env = _stub_env(settings, make_env, http)
    dog, vol, sess, clip = _setup(env)
    env.run()
    staff = env.staff
    with env.api(staff) as (client, _):
        body = client.get("/api/admin/metrics").json()
    assert "ai_auth_error" in json.dumps(body.get("alerts"))


# ---------------------------------------------------------------- PIPE-RETRY-06


def test_pipe_retry_06_bounded_provider_calls(settings, make_env):
    unavailable = lambda: httpx.Response(503, json={"error": {"message": "x"}})  # noqa: E731
    http = FakeHttp(ok(INVALID), unavailable(), ok(INVALID), unavailable())
    env = _stub_env(settings, make_env, http)
    dog, vol, sess, clip = _setup(env)
    while env.run_step():
        pass
    env.advance(60)
    env.run()
    job = env.jobs("draft")[0]
    assert job.attempts <= 2 and job.status == "failed"
    assert 2 <= http.calls <= 4


# ---------------------------------------------------------------- PIPE-RETRY-07


class _Transcriber:
    def __init__(self, *errors: Exception | None, inner: Any):
        self.errors = list(errors)
        self.inner = inner

    def transcribe(self, req):
        if self.errors:
            err = self.errors.pop(0)
            if err is not None:
                raise err
        return self.inner.transcribe(req)


def test_pipe_retry_07_malformed_transcript_fails_at_once(settings, make_env):
    mock = MockAdapter(settings.ai_mock_fixtures_dir)
    tr = _Transcriber(JobError("ai_failed", False), inner=mock)
    env = make_env(ai=ai_slots(settings, transcriber=tr, mock=mock))
    dog, vol, sess, clip = _setup(env, "h264_5s.mp4")
    env.run()
    job = env.jobs("transcribe")[0]
    assert (job.status, job.attempts) == ("failed", 1)
    row = env.clip(clip.id)
    assert (row.status, row.fail_code, row.step) == (
        "failed",
        "ai_failed",
        "transcribe",
    )


def test_pipe_retry_07_mock_permanent(make_env):
    env = make_env()
    dog, vol, sess, clip = _setup(env, "h264_5s.mp4", filename="fault_tr_permanent.mp4")
    env.run()
    job = env.jobs("transcribe")[0]
    assert (job.status, job.attempts) == ("failed", 1)
    assert env.clip(clip.id).fail_code == "ai_failed"


def test_pipe_retry_07_mock_transient_then_ok(make_env):
    env = make_env()
    dog, vol, sess, clip = _setup(
        env, "h264_5s.mp4", filename="fault_tr_transient_1.mp4"
    )
    while env.run_step():
        pass
    job = env.jobs("transcribe")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    env.advance(30)
    env.run()
    assert env.clip(clip.id).status == "ready"
    assert env.transcript(clip.id)


# ---------------------------------------------------------------- manual retry


class Switch:
    """A drafter that fails (per clip ordinal) until `ok` is switched on."""

    def __init__(self, mock: MockAdapter, fail: dict[int, Exception]):
        self.mock, self.fail, self.ok = mock, fail, False

    def draft(self, req):
        if not self.ok and req.clip_ord in self.fail:
            raise self.fail[req.clip_ord]
        return self.mock.draft(req)


def _switch_env(settings, make_env, fail, **kw):
    mock = MockAdapter(settings.ai_mock_fixtures_dir)
    sw = Switch(mock, fail)
    env = make_env(ai=ai_slots(settings, drafter=sw, mock=mock), **kw)
    return env, sw


def test_pipe_retry_08_manual_retry_resumes_at_step(settings, make_env):
    env, sw = _switch_env(settings, make_env, {1: JobError("ai_failed", False)})
    dog, vol, sess, clip = _setup(env, "h264_5s.mp4")
    env.run()
    assert env.clip(clip.id).status == "failed"
    assert env.session_row(sess.id).status == "review"
    transcript_before = [(t.id, t.text) for t in env.transcript(clip.id)]
    calls_before = env.ffmpeg.exec_calls
    sw.ok = True
    assert _retry(env, vol, clip.id) == 200
    assert env.session_row(sess.id).status == "processing"
    queued = [j.type for j in env.jobs(status="queued")]
    assert queued == ["draft"]
    env.run()
    assert env.ffmpeg.exec_calls == calls_before
    assert [(t.id, t.text) for t in env.transcript(clip.id)] == transcript_before
    assert env.clip(clip.id).status == "ready"
    assert env.session_row(sess.id).status == "review"


class FrameBreaker(CountingFFmpeg):
    broken = True

    def extract_frames(self, src, times, out_dir):  # noqa: ANN001
        if self.broken:
            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "t99.jpg").write_bytes(b"stale")
            raise FFmpegError("exit", "boom")
        return super().extract_frames(src, times, out_dir)


def test_pipe_retry_09_retry_cleans_partial_frames(make_env):
    ff = FrameBreaker(FFMPEG_BIN, FFPROBE_BIN)
    env = make_env(ffmpeg=ff)
    dog, vol, sess, clip = _setup(env, "len_25s.mp4")
    env.run()
    row = env.clip(clip.id)
    assert (row.status, row.fail_code, row.step) == (
        "failed",
        "transcode_failed",
        "sample",
    )
    ff.broken = False
    assert _retry(env, vol, clip.id) == 200
    env.run()
    assert env.clip(clip.id).status == "ready"
    frames = [k for k in env.clip_keys(clip) if "/frames/" in k]
    assert not any(k.endswith("t99.jpg") for k in frames)
    segs = env.segments(clip.id)
    assert [s.idx for s in segs] == list(range(1, len(segs) + 1))


def test_pipe_retry_10_retry_merges_only_new_drafts(settings, make_env):
    env, sw = _switch_env(
        settings, make_env, {2: JobError("ai_failed", False)}, keep_originals=True
    )
    dog, vol, sess, _ = _setup(env, "h264_5s.mp4")
    c2 = env.add_clip(sess, "h264_5s.mp4", ordinal=2)
    env.run()
    old = env.facts(session_id=sess.id)
    assert old and all(f.merged for f in old)
    with env.db() as s:
        s.execute(update(Fact).where(Fact.id == old[0].id).values(status="confirmed"))
        s.commit()
    snapshot = {
        f.id: (f.behavior, f.flags, f.status) for f in env.facts(session_id=sess.id)
    }
    sw.ok = True
    assert _retry(env, vol, c2.id) == 200
    env.run()
    after = {f.id: f for f in env.facts(session_id=sess.id)}
    for fid, (behavior, flags, status) in snapshot.items():
        assert (after[fid].behavior, after[fid].flags) == (behavior, flags)
    assert after[old[0].id].status == "confirmed"
    new = [f for fid, f in after.items() if fid not in snapshot]
    assert new and all(f.merged for f in new)
    assert env.session_row(sess.id).status == "review"


# ---------------------------------------------------------------- PIPE-RETRY-11/12


def _break_merge(env, errors):
    svc = env.services.merge_service
    real = svc.merge_session
    pending = list(errors)

    def merge_session(session_id, *a, **kw):
        if pending:
            raise pending.pop(0)
        return real(session_id, *a, **kw)

    svc.merge_session = merge_session


def test_pipe_retry_11_retry_merge_end_to_end(env):
    dog, vol, sess, clip = _setup(env, "h264_5s.mp4")
    _break_merge(env, [JobError("merge_failed", False)])
    env.run()
    row = env.session_row(sess.id)
    assert (row.status, row.fail_code) == ("failed", "merge_failed")
    assert env.jobs("merge")[0].attempts == 1
    with env.api(vol) as (client, token):
        r = client.post(
            f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
        )
    assert r.status_code == 200
    row = env.session_row(sess.id)
    assert (row.status, row.fail_code, row.review_ready_at) == (
        "processing",
        None,
        None,
    )
    assert len([j for j in env.jobs("merge") if j.status == "queued"]) == 1
    env.run()
    row = env.session_row(sess.id)
    assert row.status == "review" and row.review_ready_at is not None
    assert env.jobs("check")


def test_pipe_retry_11_transient_variant(env):
    dog, vol, sess, clip = _setup(env, "h264_5s.mp4")
    _break_merge(env, [JobError("merge_failed", True)])
    while env.run_step():
        pass
    job = env.jobs("merge")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    assert env.session_row(sess.id).status == "processing"
    env.advance(30)
    env.run()
    assert env.session_row(sess.id).status == "review"


def test_pipe_retry_12_retry_merge_twice_runs_once(env):
    dog, vol, sess, clip = _setup(env, "h264_5s.mp4")
    calls = []
    _break_merge(env, [JobError("merge_failed", False)])
    real = env.services.merge_service.merge_session

    def counting(session_id, *a, **kw):
        calls.append(session_id)
        return real(session_id, *a, **kw)

    env.run()
    env.services.merge_service.merge_session = counting
    with env.api(vol) as (client, token):
        a = client.post(
            f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
        )
        b = client.post(
            f"/api/sessions/{sess.id}/retry-merge", json={}, headers=csrf(token)
        )
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["status"] == b.json()["status"] == "processing"
    assert len([j for j in env.jobs("merge") if j.status == "queued"]) == 1
    env.run()
    assert len(calls) == 1


# ---------------------------------------------------------------- PIPE-RETRY-13


def test_pipe_retry_13_manual_retry_after_automatic_give_up(settings, make_env):
    env, sw = _switch_env(
        settings,
        make_env,
        {1: JobError("ai_failed", False), 2: JobError("ai_failed", True)},
    )
    dog, vol, sess, c1 = _setup(env, "h264_5s.mp4")
    c2 = env.add_clip(sess, "silent_5s.mp4", ordinal=2)
    while env.run_step():
        pass
    env.advance(30)
    env.run()
    assert [env.clip(c.id).status for c in (c1, c2)] == ["failed", "failed"]
    assert {j.clip_id: j.attempts for j in env.jobs("draft")} == {c1.id: 1, c2.id: 2}
    sw.ok = True
    counts = {t: len(env.jobs(t)) for t in ("transcode", "transcribe", "sample")}
    calls_before = env.ffmpeg.exec_calls
    assert _retry(env, vol, c1.id) == 200
    assert _retry(env, vol, c2.id) == 200
    fresh = [j for j in env.jobs("draft") if j.status == "queued"]
    assert len(fresh) == 2 and all(j.attempts == 0 for j in fresh)
    env.run()
    assert [env.clip(c.id).status for c in (c1, c2)] == ["ready", "ready"]
    assert counts == {t: len(env.jobs(t)) for t in counts}
    assert env.ffmpeg.exec_calls == calls_before


# ---------------------------------------------------------------- PIPE-RETRY-14


def test_pipe_retry_14_check_failure_never_fails_session(env):
    dog, vol, sess, clip = _setup(env, "h264_5s.mp4")
    svc = env.services.wording_service
    errors = [JobError("ai_failed", True), JobError("ai_failed", False)]

    def boom(*a, **kw):
        raise errors.pop(0)

    svc.apply_model_flags = boom
    while env.run_step():
        pass
    job = env.jobs("check")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    env.advance(30)
    env.run()
    job = env.jobs("check")[0]
    assert job.status == "failed"
    facts = env.facts(session_id=sess.id)
    assert facts
    for f in facts:
        assert any(x["code"] == "check_unavailable" for x in f.flags)
    row = env.session_row(sess.id)
    assert (
        row.status == "review"
        and row.fail_code is None
        and row.review_ready_at is not None
    )
