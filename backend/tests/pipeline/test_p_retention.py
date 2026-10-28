"""PIPE-RET-01..02 and PIPE-RUN-01 (07 section 3.15)."""

from __future__ import annotations

import os
from datetime import timedelta

from sqlalchemy import select, update

from app.models import Job, QaLog
from app.services.views import JobSpec
from tests.pipeline.pipe_support import utime_ago


def _days_ago(env, d: float):
    return env.clock.now() - timedelta(days=d)


# ---------------------------------------------------------------- PIPE-RET-01


def test_pipe_ret_01_retention_sweep(env):
    org, staff, vol, dog = env.world()
    q29 = env.seed.qa_log(dog, question="q29", created_at=_days_ago(env, 29))
    q31 = env.seed.qa_log(dog, question="q31", created_at=_days_ago(env, 31))
    q91 = env.seed.qa_log(dog, question="q91", created_at=_days_ago(env, 91))
    j13 = env.seed.job(
        "transcode", status="succeeded", updated_at=_days_ago(env, 13), dog_id=dog.id
    )
    j15 = env.seed.job(
        "transcode", status="failed", updated_at=_days_ago(env, 15), dog_id=dog.id
    )
    j15q = env.seed.job(
        "transcode", status="queued", updated_at=_days_ago(env, 15), dog_id=dog.id
    )
    ledger = env.seed.ledger("qa_select", usd_micros=5, created_at=_days_ago(env, 100))
    now_ts = env.clock.now().timestamp()
    young = env.storage.open_path("tmp/young")
    old = env.storage.open_path("tmp/old")
    for p in (young, old):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    utime_ago(young, now_ts, 5)
    utime_ago(old, now_ts, 7)

    env.services.job_queue.enqueue(
        JobSpec(type="retention_sweep", dedupe_key="sweep:test")
    )
    assert env.run_step()

    with env.db() as s:
        rows = {r.id: r for r in s.scalars(select(QaLog))}
        assert rows[q29.id].question == "q29"
        assert q31.id in rows and rows[q31.id].question is None
        assert q91.id not in rows
        left = {j.id for j in s.scalars(select(Job))}
    assert j13.id in left and j15.id not in left and j15q.id in left
    assert young.exists() and not old.exists()
    assert [(r.id, r.usd_micros) for r in env.ledger() if r.id == ledger.id] == [
        (ledger.id, 5)
    ]
    assert env.jobs("retention_sweep")[0].status == "succeeded"
    assert os.path.exists(young)


# ---------------------------------------------------------------- PIPE-RET-02


def test_pipe_ret_02_one_sweep_per_utc_date(env):
    runner = env.runner
    runner._enqueue_daily_sweep()
    runner._enqueue_daily_sweep()
    assert [j.dedupe_key for j in env.jobs("retention_sweep")] == ["sweep:2026-10-28"]
    env.advance(24 * 3600)
    runner._enqueue_daily_sweep()
    runner._enqueue_daily_sweep()
    assert [j.dedupe_key for j in env.jobs("retention_sweep")] == [
        "sweep:2026-10-28",
        "sweep:2026-10-29",
    ]


# ---------------------------------------------------------------- PIPE-RUN-01


def test_pipe_run_01_worker_restart_resets_stale_lock(env):
    org, staff, vol, dog = env.world()
    sess = env.session(dog, vol)
    clip = env.add_clip(sess, "h264_5s.mp4")
    last = env.add_clip(sess, "silent_5s.mp4", ordinal=2)
    stale = env.clock.now() - timedelta(hours=3)
    jobs = env.jobs("transcode")
    with env.db() as s:
        s.execute(
            update(Job)
            .where(Job.id == jobs[0].id)
            .values(
                status="running", attempts=1, locked_at=stale, locked_by="dead-worker"
            )
        )
        s.execute(
            update(Job)
            .where(Job.id == jobs[1].id)
            .values(
                status="running", attempts=2, locked_at=stale, locked_by="dead-worker"
            )
        )
        s.commit()
    env.runner.reset_stale()
    first, second = env.jobs("transcode")
    assert first.status == "queued" and first.locked_by is None
    assert second.status == "failed"
    assert env.clip(last.id).status == "failed"  # the final failure hook ran
    env.advance(60)  # the requeued job waits out its 30 s backoff
    env.run()
    assert env.clip(clip.id).status == "ready"
