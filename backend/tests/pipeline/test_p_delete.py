"""PIPE-DEL-01..10: dog and clip purge (07 section 3.15, 02 section 6, 03 section 3.3)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app.ai.types import DraftFactOut, DraftOutput, EvidenceFrames
from app.models import (
    Clip,
    CostLedger,
    Dog,
    Fact,
    FactEvidence,
    FilmingSession,
    Job,
    PlaybackEvent,
    QaLog,
    Segment,
    TranscriptSegment,
)
from app.storage.local import LocalStorage
from tests.pipeline.pipe_support import FaultyStorage, FnDrafter, ai_slots, csrf

DOG_TABLES = (
    (PlaybackEvent, None),
    (FactEvidence, None),
    (Fact, "dog_id"),
    (Clip, "dog_id"),
    (FilmingSession, "dog_id"),
    (QaLog, "dog_id"),
    (Job, "dog_id"),
)


def _populated(env, *, clips=2, run=True):
    """A published dog with clips, facts, transcript, segments, QA rows."""
    org, staff, vol, _ = env.world()
    dog = env.seed.dog(org, staff, name="Pub", status="published")
    sess = env.session(dog, vol)
    made = [
        env.add_clip(sess, "len_25s.mp4" if i == 1 else "h264_5s.mp4", ordinal=i)
        for i in range(1, clips + 1)
    ]
    if run:
        env.run()
    env.seed.qa_log(dog, question="Is she good with kids?")
    return dog, staff, vol, sess, made


def _count(env, model, dog_id) -> int:
    with env.db() as s:
        if model is PlaybackEvent:
            q = (
                select(func.count())
                .select_from(PlaybackEvent)
                .join(Fact, Fact.id == PlaybackEvent.fact_id)
                .where(Fact.dog_id == dog_id)
            )
        elif model is FactEvidence:
            q = (
                select(func.count())
                .select_from(FactEvidence)
                .join(Fact, Fact.id == FactEvidence.fact_id)
                .where(Fact.dog_id == dog_id)
            )
        else:
            q = (
                select(func.count())
                .select_from(model)
                .where(getattr(model, "dog_id") == dog_id)
            )
        return s.scalar(q)


def _row_totals(env, dog_id) -> dict[str, int]:
    out = {m.__tablename__: _count(env, m, dog_id) for m, _ in DOG_TABLES}
    with env.db() as s:
        out["transcript_segment"] = s.scalar(
            select(func.count())
            .select_from(TranscriptSegment)
            .join(Clip, Clip.id == TranscriptSegment.clip_id)
            .where(Clip.dog_id == dog_id)
        )
        out["segment"] = s.scalar(
            select(func.count())
            .select_from(Segment)
            .join(Clip, Clip.id == Segment.clip_id)
            .where(Clip.dog_id == dog_id)
        )
        out["dog"] = s.scalar(
            select(func.count()).select_from(Dog).where(Dog.id == dog_id)
        )
    return out


def _delete_dog(env, staff, dog_id) -> int:
    with env.api(staff) as (client, token):
        return client.delete(f"/api/dogs/{dog_id}", headers=csrf(token)).status_code


def _dog_visible(env, member, dog_id) -> int:
    with env.api(member) as (client, _):
        return client.get(f"/api/dogs/{dog_id}").status_code


def _add_playback(env, dog, vol):
    fact = env.facts(dog_id=dog.id)[0]
    ev = env.evidence(fact.id)[0]
    env.seed.playback(fact, ev, vol)


# ---------------------------------------------------------------- PIPE-DEL-01


def test_pipe_del_01_purge_dog_end_to_end(env):
    dog, staff, vol, sess, clips = _populated(env)
    _add_playback(env, dog, vol)
    env.seed.ledger("qa_select", usd_micros=11, dog_id=dog.id)
    before = _row_totals(env, dog.id)
    assert (
        all(v > 0 for k, v in before.items() if k not in ("playback_event",))
        or before["fact"] > 0
    )
    assert env.keys(f"dogs/{dog.id}/")
    ledger_before = [(r.id, r.usd_micros) for r in env.ledger()]
    assert _delete_dog(env, staff, dog.id) == 202
    env.run()
    assert env.keys(f"dogs/{dog.id}/") == []
    after = _row_totals(env, dog.id)
    assert all(v == 0 for v in after.values()), after
    rows = env.ledger()
    assert [(r.id, r.usd_micros) for r in rows] == ledger_before
    assert all(r.dog_id is None and r.session_id is None for r in rows)


# ---------------------------------------------------------------- PIPE-DEL-02


def test_pipe_del_02_order_hide_files_verify_rows(settings, make_env):
    storage = FaultyStorage(LocalStorage(settings.storage_root))
    env = make_env(storage=storage)
    dog, staff, vol, sess, clips = _populated(env)
    seen: dict[str, object] = {}

    def at_delete(prefix: str) -> None:
        seen["rows_at_delete"] = _row_totals(env, dog.id)
        seen["files_at_delete"] = bool(env.storage._inner.list_prefix(prefix))

    storage.on_delete_prefix = at_delete
    storage.events.clear()  # the pipeline run that filled the dog also used storage
    assert _delete_dog(env, staff, dog.id) == 202
    assert _dog_visible(env, staff, dog.id) == 404  # hidden at once
    assert (
        env.keys(f"dogs/{dog.id}/") and _count(env, Clip, dog.id) > 0
    )  # nothing removed yet
    assert storage.events == []
    env.run()
    assert seen["files_at_delete"] is True
    assert seen["rows_at_delete"]["clip"] > 0 and seen["rows_at_delete"]["dog"] == 1
    prefix = f"dogs/{dog.id}/"
    assert storage.events[:2] == [
        f"delete_prefix:{prefix}",
        f"list_prefix:{prefix}",
    ]  # delete, then verify
    assert _row_totals(env, dog.id)["dog"] == 0


# ---------------------------------------------------------------- PIPE-DEL-03


def test_pipe_del_03_file_delete_fails_twice(settings, make_env):
    storage = FaultyStorage(LocalStorage(settings.storage_root))
    env = make_env(storage=storage)
    dog, staff, vol, sess, clips = _populated(env, clips=1)
    storage.delete_prefix_failures = 2
    assert _delete_dog(env, staff, dog.id) == 202
    t0 = env.clock.now()
    while env.run_step():
        pass
    job = env.jobs("purge_dog")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    assert job.run_after == t0 + timedelta(minutes=1)
    assert _count(env, Clip, dog.id) > 0 and env.keys(f"dogs/{dog.id}/")
    env.advance(60)
    t1 = env.clock.now()
    while env.run_step():
        pass
    job = env.jobs("purge_dog")[0]
    assert (job.status, job.attempts) == ("queued", 2)
    assert job.run_after == t1 + timedelta(minutes=5)
    assert _count(env, Clip, dog.id) > 0  # never reports success early
    env.advance(300)
    env.run()
    assert env.keys(f"dogs/{dog.id}/") == []
    assert _row_totals(env, dog.id)["dog"] == 0


# ---------------------------------------------------------------- PIPE-DEL-04


def test_pipe_del_04_verification_catches_leftovers(settings, make_env):
    storage = FaultyStorage(LocalStorage(settings.storage_root))
    env = make_env(storage=storage)
    dog, staff, vol, sess, clips = _populated(env, clips=1)
    leftover = f"dogs/{dog.id}/photo.jpg"
    env.storage.open_path(leftover).write_bytes(b"x")
    storage.delete_prefix_leaves = {leftover}
    before = _row_totals(env, dog.id)
    assert _delete_dog(env, staff, dog.id) == 202
    while env.run_step():
        pass
    job = env.jobs("purge_dog")[0]
    assert (job.status, job.attempts) == ("queued", 1)
    assert _row_totals(env, dog.id) == before | {"job": _count(env, Job, dog.id)}
    assert _count(env, Clip, dog.id) == before["clip"]
    storage.delete_prefix_leaves = set()
    env.advance(60)
    env.run()
    assert _row_totals(env, dog.id)["dog"] == 0


# ---------------------------------------------------------------- PIPE-DEL-05


def test_pipe_del_05_purge_exhausted(settings, make_env):
    storage = FaultyStorage(LocalStorage(settings.storage_root))
    storage.delete_prefix_always_fails = True
    env = make_env(storage=storage)
    dog, staff, vol, sess, clips = _populated(env, clips=1)
    assert _delete_dog(env, staff, dog.id) == 202
    for _ in range(8):
        while env.run_step():
            pass
        env.advance(13 * 3600)
    job = env.jobs("purge_dog")[0]
    assert (job.status, job.attempts, job.max_attempts) == ("failed", 8, 8)
    with env.db() as s:
        assert s.get(Dog, dog.id).status == "deleted"
    assert _dog_visible(env, staff, dog.id) == 404


@pytest.mark.xfail(
    reason="GET /api/admin/metrics (`purge_pending`) belongs to lane I", strict=False
)
def test_pipe_del_05_purge_pending_listed(settings, make_env):
    storage = FaultyStorage(LocalStorage(settings.storage_root))
    storage.delete_prefix_always_fails = True
    env = make_env(storage=storage)
    dog, staff, vol, sess, clips = _populated(env, clips=1)
    _delete_dog(env, staff, dog.id)
    for _ in range(8):
        while env.run_step():
            pass
        env.advance(13 * 3600)
    with env.api(staff) as (client, _):
        body = client.get("/api/admin/metrics").json()
    assert dog.id in str(body["purge_pending"])


# ---------------------------------------------------------------- PIPE-DEL-06


def test_pipe_del_06_running_draft_result_is_discarded(settings, make_env):
    out = DraftOutput(
        facts=[
            DraftFactOut(
                situation="leash_walk",
                behavior="Walked on a loose leash.",
                source="clip",
                evidence=[EvidenceFrames(start_t=0, end_t=3)],
            )
        ]
    )
    holder: dict[str, object] = {}

    def drafter(req):
        # the dog is deleted while this draft job is running
        holder["status"] = _delete_dog(holder["env"], holder["staff"], holder["dog_id"])
        return out

    env = make_env(ai=ai_slots(settings, drafter=FnDrafter(drafter)))
    org, staff, vol, _ = env.world()
    dog = env.seed.dog(org, staff, name="Pub", status="published")
    sess = env.session(dog, vol)
    clip = env.add_clip(sess, "h264_5s.mp4")
    holder.update(env=env, staff=staff, dog_id=dog.id)
    while env.run_step():
        job = env.jobs("draft")
        if job and job[0].status == "cancelled":
            break
    assert holder["status"] == 202
    assert env.jobs("draft")[0].status == "cancelled"
    assert _count(env, Fact, dog.id) == 0
    assert env.jobs("merge") == [] and env.jobs("check") == []


def test_pipe_del_06_purge_waits_without_counting_attempt(env):
    dog, staff, vol, sess, clips = _populated(env, clips=1)
    other = env.seed.job(
        "draft", dog_id=dog.id, status="running", attempts=1, max_attempts=2,
        locked_at=env.clock.now(), locked_by="other-worker",
    )  # fmt: skip
    assert _delete_dog(env, staff, dog.id) == 202
    t0 = env.clock.now()
    env.run_step()
    purge = env.jobs("purge_dog")[0]
    assert purge.status == "queued" and purge.attempts == 0
    assert purge.run_after == t0 + timedelta(seconds=30)
    assert _count(env, Clip, dog.id) > 0 and env.keys(f"dogs/{dog.id}/")
    with env.db() as s:
        s.execute(
            update(Job)
            .where(Job.id == other.id)
            .values(status="cancelled", locked_at=None, locked_by=None)
        )
        s.commit()
    env.advance(30)
    env.run()
    assert _row_totals(env, dog.id)["dog"] == 0 and env.keys(f"dogs/{dog.id}/") == []


# ---------------------------------------------------------------- PIPE-DEL-07


def test_pipe_del_07_queued_jobs_cancelled(env):
    org, staff, vol, _ = env.world()
    dog = env.seed.dog(org, staff, name="Pub", status="published")
    sess = env.session(dog, vol)
    clips = [env.add_clip(sess, "h264_5s.mp4", ordinal=i) for i in (1, 2)]
    env.enqueue_step(clips[0], "draft")
    assert _delete_dog(env, staff, dog.id) == 202
    jobs = env.jobs()
    assert {j.type: j.status for j in jobs if j.type != "purge_dog"} == {
        "transcode": "cancelled",
        "draft": "cancelled",
    }
    calls = env.ffmpeg.exec_calls
    env.run()
    assert env.ffmpeg.exec_calls == calls
    assert env.spy("drafter").calls["draft"] == []
    assert _row_totals(env, dog.id)["dog"] == 0


# ---------------------------------------------------------------- PIPE-DEL-08


def test_pipe_del_08_purge_clip(make_env):
    env = make_env(keep_originals=True)
    dog, staff, vol, sess, (c1, c2) = _populated(env)
    assert env.transcript(c1.id) and env.segments(c1.id)
    other_keys = env.clip_keys(c2)
    other_rows = (len(env.transcript(c2.id)), len(env.segments(c2.id)))
    with env.api(staff) as (client, token):
        r = client.delete(f"/api/clips/{c1.id}", headers=csrf(token))
    assert r.status_code == 202
    env.run()
    assert env.clip_keys(c1) == []
    assert env.transcript(c1.id) == [] and env.segments(c1.id) == []
    with env.db() as s:
        assert s.get(Clip, c1.id) is None
        assert s.get(Clip, c2.id) is not None
    assert env.clip_keys(c2) == other_keys
    assert (len(env.transcript(c2.id)), len(env.segments(c2.id))) == other_rows
    assert env.jobs("purge_clip")[0].status == "succeeded"


# ---------------------------------------------------------------- PIPE-DEL-09


def test_pipe_del_09_adopted_keeps_files(env):
    dog, staff, vol, sess, clips = _populated(env)
    keys = env.keys(f"dogs/{dog.id}/")
    before = _row_totals(env, dog.id)
    with env.api(staff) as (client, token):
        r = client.post(f"/api/dogs/{dog.id}/adopted", json={}, headers=csrf(token))
    assert r.status_code == 200
    env.run()
    assert env.keys(f"dogs/{dog.id}/") == keys
    after = _row_totals(env, dog.id)
    assert {k: v for k, v in after.items() if k != "job"} == {
        k: v for k, v in before.items() if k != "job"
    }
    assert all(j.type != "purge_dog" for j in env.jobs())


# ---------------------------------------------------------------- PIPE-DEL-10


def test_pipe_del_10_cost_ledger_survives(env):
    dog, staff, vol, sess, clips = _populated(env)
    env.seed.ledger("qa_select", usd_micros=250, dog_id=dog.id)
    with env.db() as s:
        total = s.scalar(select(func.coalesce(func.sum(CostLedger.usd_micros), 0)))
        count = s.scalar(select(func.count()).select_from(CostLedger))
    assert count > 1
    assert _delete_dog(env, staff, dog.id) == 202
    env.run()
    with env.db() as s:
        assert (
            s.scalar(select(func.coalesce(func.sum(CostLedger.usd_micros), 0))) == total
        )
        assert s.scalar(select(func.count()).select_from(CostLedger)) == count
        assert (
            s.scalar(
                select(func.count())
                .select_from(CostLedger)
                .where(CostLedger.dog_id.is_not(None))
            )
            == 0
        )
        assert (
            s.scalar(
                select(func.count())
                .select_from(CostLedger)
                .where(CostLedger.session_id.is_not(None))
            )
            == 0
        )
