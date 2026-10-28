"""UT-JOB-01..16: JobQueue and JobRunner with fake handlers (07 section 3.5)."""

from __future__ import annotations

import threading
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.clock import FakeClock
from app.container import Container
from app.errors import JobError
from app.models import Job
from app.pipeline.handlers.base import HandlerContext, HandlerResult
from app.pipeline.runner import JobRunner
from app.services.job_queue import JobQueue
from app.services.views import JobSpec, JobView

# ------------------------------------------------------------------ helpers


class FakeHandler:
    """A scripted handler. `script` items are consumed one per call: an exception
    instance is raised, a `HandlerResult` is returned, a callable is invoked."""

    def __init__(self, job_type: str, *script: Any, timeout_s: float = 30):
        self.job_type = job_type
        self.timeout_s = timeout_s
        self.script = list(script)
        self.calls: list[JobView] = []
        self.finals: list[tuple[JobView, JobError]] = []

    def handle(self, job: JobView, ctx: HandlerContext) -> HandlerResult:
        self.calls.append(job)
        item = self.script.pop(0) if self.script else HandlerResult()
        if callable(item) and not isinstance(item, HandlerResult):
            item = item(job)
        if isinstance(item, BaseException):
            raise item
        return item

    def on_final_failure(
        self, job: JobView, error: JobError, ctx: HandlerContext
    ) -> None:
        self.finals.append((job, error))


class Env:
    def __init__(self, container: Container, clock: FakeClock, engine):
        self.container = container
        self.clock = clock
        self.engine = engine
        self.queue = JobQueue(container.uow_factory, clock, stale_s=600)

    def runner(self, *handlers: FakeHandler, worker_id: str = "w1") -> JobRunner:
        ctx = HandlerContext(
            settings=self.container.settings,
            storage=None,  # type: ignore[arg-type]
            ffmpeg=None,
            ai=None,
            services=self.container.services,
            clock=self.clock,
        )
        return JobRunner(
            self.queue, handlers, ctx, self.clock, worker_id=worker_id, poll_s=0.01
        )

    def row(self, job_id: int) -> Job:
        with Session(self.engine) as s:
            job = s.get(Job, job_id)
            assert job is not None
            s.expunge(job)
            return job

    def jobs(self, **where: Any) -> list[Job]:
        with Session(self.engine) as s:
            rows = s.query(Job).filter_by(**where).order_by(Job.id).all()
            s.expunge_all()
            return rows


@pytest.fixture
def env(container: Container, clock: FakeClock, engine) -> Env:
    return Env(container, clock, engine)


def _seed_job(seed, clock: FakeClock, type: str = "draft", **kw: Any) -> Job:
    kw.setdefault("run_after", clock.now())
    return seed.job(type, **kw)


# ---------------------------------------------------------------- UT-JOB-01


def test_ut_job_01_success_enqueues_next_jobs(env: Env):
    nxt = JobSpec(type="transcribe", clip_id="c1", dedupe_key="transcribe:c1")
    h = FakeHandler("transcode", HandlerResult(next_jobs=(nxt,)))
    runner = env.runner(h, FakeHandler("transcribe"))
    jid = env.queue.enqueue(JobSpec(type="transcode", clip_id="c1"))
    assert runner.run_once() is True
    row = env.row(jid)
    assert row.status == "succeeded"
    assert row.attempts == 1
    queued = env.jobs(status="queued")
    assert [j.type for j in queued] == ["transcribe"]
    assert queued[0].clip_id == "c1"
    assert queued[0].dedupe_key == "transcribe:c1"
    assert queued[0].max_attempts == 2


# ---------------------------------------------------------------- UT-JOB-02


def test_ut_job_02_retryable_then_success(env: Env):
    h = FakeHandler("draft", JobError("ai_failed", True), HandlerResult())
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="draft", clip_id="c1"))
    t0 = env.clock.now()
    assert runner.run_once() is True
    row = env.row(jid)
    assert row.status == "queued"
    assert row.attempts == 1
    assert row.run_after == t0 + timedelta(seconds=30)
    assert h.finals == []
    assert runner.run_once() is False  # not due yet
    env.clock.advance(30)
    assert runner.run_once() is True
    row = env.row(jid)
    assert row.status == "succeeded"
    assert row.attempts == 2


def test_ut_job_02_retry_after_wins_over_backoff(env: Env):
    h = FakeHandler("draft", JobError("ai_failed", True, retry_after_s=90))
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="draft"))
    t0 = env.clock.now()
    runner.run_once()
    assert env.row(jid).run_after == t0 + timedelta(seconds=90)


# ---------------------------------------------------------------- UT-JOB-03


def test_ut_job_03_retryable_until_max(env: Env):
    h = FakeHandler(
        "draft", JobError("ai_failed", True), JobError("ai_failed", True)
    )
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="draft", clip_id="c1"))
    t0 = env.clock.now()
    runner.run_once()
    row = env.row(jid)
    assert (row.status, row.attempts) == ("queued", 1)
    assert row.run_after == t0 + timedelta(seconds=30)
    assert h.finals == []
    env.clock.advance(30)
    runner.run_once()
    row = env.row(jid)
    assert (row.status, row.attempts) == ("failed", 2)
    assert len(h.finals) == 1
    assert h.finals[0][1].code == "ai_failed"
    assert h.finals[0][0].id == jid


def test_ut_job_03_backoff_table_third_attempt_waits_120s(env: Env):
    h = FakeHandler(
        "draft",
        JobError("ai_failed", True),
        JobError("ai_failed", True),
        JobError("ai_failed", True),
    )
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="draft", max_attempts=3))
    runner.run_once()
    env.clock.advance(30)
    t1 = env.clock.now()
    runner.run_once()
    assert env.row(jid).run_after == t1 + timedelta(seconds=120)


# ---------------------------------------------------------------- UT-JOB-04


@pytest.mark.parametrize(
    ("job_type", "code"),
    [
        ("draft", "ai_invalid_output"),
        ("draft", "ai_failed"),
        ("transcode", "transcode_failed"),
    ],
)
def test_ut_job_04_non_retryable_error_is_immediate(env: Env, job_type: str, code: str):
    h = FakeHandler(job_type, JobError(code, False))
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type=job_type, clip_id="c1"))
    before = env.row(jid).run_after
    runner.run_once()
    row = env.row(jid)
    assert (row.status, row.attempts) == ("failed", 1)
    assert row.run_after == before
    assert [e.code for _, e in h.finals] == [code]


# ---------------------------------------------------------------- UT-JOB-05


@pytest.mark.parametrize(
    ("job_type", "default_code"),
    [
        ("transcode", "transcode_failed"),
        ("sample", "transcode_failed"),
        ("draft", "ai_failed"),
        ("merge", "merge_failed"),
    ],
)
def test_ut_job_05_unknown_exception_is_non_retryable(
    env: Env, caplog, job_type: str, default_code: str
):
    h = FakeHandler(job_type, ValueError("secret detail"))
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type=job_type, clip_id="c1"))
    with caplog.at_level("ERROR"):
        runner.run_once()
    row = env.row(jid)
    assert (row.status, row.attempts) == ("failed", 1)
    assert [e.code for _, e in h.finals] == [default_code]
    assert h.finals[0][1].retryable is False
    # the stack trace goes to the log only, never into the job row
    assert "Traceback" in caplog.text or any(r.exc_info for r in caplog.records)
    assert "secret detail" not in (row.error or "")


# ---------------------------------------------------------------- UT-JOB-06


def test_ut_job_06_timeout_is_retryable(env: Env):
    release = threading.Event()

    def hang(job: JobView):
        release.wait(5)
        return HandlerResult()

    h = FakeHandler("sample", hang, timeout_s=0.2)
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="sample", clip_id="c1"))
    t0 = env.clock.now()
    try:
        runner.run_once()
    finally:
        release.set()
    row = env.row(jid)
    assert (row.status, row.attempts) == ("queued", 1)
    assert row.run_after == t0 + timedelta(seconds=30)
    assert h.finals == []


def test_ut_job_06_timeout_at_max_attempts_fails_with_step_code(env: Env):
    release = threading.Event()
    h = FakeHandler("sample", lambda j: release.wait(5), timeout_s=0.1)
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="sample", max_attempts=1))
    try:
        runner.run_once()
    finally:
        release.set()
    assert env.row(jid).status == "failed"
    assert [e.code for _, e in h.finals] == ["transcode_failed"]


# ---------------------------------------------------------------- UT-JOB-07


def test_ut_job_07_claim_ordering(env: Env, seed):
    now = env.clock.now()
    j_late = _seed_job(seed, env.clock, run_after=now - timedelta(seconds=10))
    j_old_b = _seed_job(seed, env.clock, run_after=now - timedelta(seconds=60))
    j_old_a = _seed_job(seed, env.clock, run_after=now - timedelta(seconds=60))
    j_future = _seed_job(seed, env.clock, run_after=now + timedelta(seconds=60))
    got = []
    while (view := env.queue.claim("w1")) is not None:
        got.append(view.id)
    assert got == [j_old_b.id, j_old_a.id, j_late.id]
    assert j_future.id not in got
    assert env.row(j_future.id).status == "queued"
    env.clock.advance(61)
    assert env.queue.claim("w1").id == j_future.id


def test_ut_job_07_claim_sets_running_fields(env: Env):
    jid = env.queue.enqueue(JobSpec(type="draft"))
    view = env.queue.claim("worker-9")
    assert view is not None and view.id == jid
    assert view.attempts == 1
    row = env.row(jid)
    assert (row.status, row.locked_by) == ("running", "worker-9")
    assert row.locked_at == env.clock.now()
    assert env.queue.claim("worker-9") is None


# ---------------------------------------------------------------- UT-JOB-08


def test_ut_job_08_claim_atomicity(env: Env):
    total = 40
    for i in range(total):
        env.queue.enqueue(JobSpec(type="draft", clip_id=f"c{i}"))
    claimed: list[list[int]] = [[], []]
    errors: list[BaseException] = []

    def work(idx: int) -> None:
        try:
            while (view := env.queue.claim(f"w{idx}")) is not None:
                claimed[idx].append(view.id)
        except BaseException as exc:  # noqa: BLE001  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not errors
    both = claimed[0] + claimed[1]
    assert len(both) == total
    assert len(set(both)) == total
    assert all(r.attempts == 1 for r in env.jobs())


# ---------------------------------------------------------------- UT-JOB-09


def test_ut_job_09_dedupe(env: Env):
    spec = JobSpec(type="merge", session_id="s1", dedupe_key="merge:s1")
    first = env.queue.enqueue(spec)
    second = env.queue.enqueue(spec)
    assert first == second
    assert len(env.jobs(type="merge")) == 1
    # still deduped while running
    env.queue.claim("w1")
    assert env.queue.enqueue(spec) == first
    env.queue.complete(first)
    third = env.queue.enqueue(spec)
    assert third != first
    assert len(env.jobs(type="merge")) == 2


# ---------------------------------------------------------------- UT-JOB-10


def test_ut_job_10_stale_lock_reset(env: Env, seed):
    locked = env.clock.now() - timedelta(minutes=11)
    retry = _seed_job(
        seed, env.clock, "draft", status="running", attempts=1, max_attempts=2,
        locked_at=locked, locked_by="dead",
    )
    final = _seed_job(
        seed, env.clock, "draft", status="running", attempts=2, max_attempts=2,
        locked_at=locked, locked_by="dead", clip_id="c9",
    )
    fresh = _seed_job(
        seed, env.clock, "draft", status="running", attempts=1, max_attempts=2,
        locked_at=env.clock.now() - timedelta(minutes=2), locked_by="alive",
    )
    h = FakeHandler("draft")
    runner = env.runner(h)
    runner.reset_stale()
    assert env.row(retry.id).status == "queued"
    assert env.row(retry.id).attempts == 1
    assert env.row(final.id).status == "failed"
    assert env.row(fresh.id).status == "running"
    assert [j.id for j, _ in h.finals] == [final.id]


# ---------------------------------------------------------------- UT-JOB-11


def test_ut_job_11_discard_on_deleted_dog(env: Env, seed):
    org = seed.org()
    staff = seed.member(org, "staff")
    dog = seed.dog(org, staff)
    nxt = JobSpec(type="transcribe", dog_id=dog.id)

    def delete_dog(job: JobView):
        from app.models import Dog

        with Session(env.engine) as s:
            d = s.get(Dog, dog.id)
            d.status = "deleted"
            d.deleted_at = env.clock.now()
            d.public_slug = None
            s.commit()
        return HandlerResult(next_jobs=(nxt,))

    h = FakeHandler("transcode", delete_dog)
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="transcode", dog_id=dog.id, clip_id="c1"))
    runner.run_once()
    assert env.row(jid).status == "cancelled"
    assert env.jobs(status="queued") == []


def test_ut_job_11_purge_dog_is_not_discarded(env: Env, seed):
    org = seed.org()
    staff = seed.member(org, "staff")
    dog = seed.dog(org, staff, status="deleted")
    h = FakeHandler("purge_dog")
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="purge_dog", dog_id=dog.id))
    runner.run_once()
    assert env.row(jid).status == "succeeded"


# ---------------------------------------------------------------- UT-JOB-12


def test_ut_job_12_cancel_queued_by_dog_and_clip(env: Env, seed):
    now = env.clock.now()
    q_dog = _seed_job(seed, env.clock, dog_id="d1", clip_id="c1")
    q_clip = _seed_job(seed, env.clock, dog_id="d2", clip_id="c2")
    q_other = _seed_job(seed, env.clock, dog_id="d3", clip_id="c3")
    running = _seed_job(
        seed, env.clock, dog_id="d1", status="running", attempts=1,
        locked_at=now, locked_by="w",
    )
    assert env.queue.cancel_for_dog("d1") == 1
    assert env.queue.cancel_for_clip("c2") == 1
    assert env.row(q_dog.id).status == "cancelled"
    assert env.row(q_clip.id).status == "cancelled"
    assert env.row(q_other.id).status == "queued"
    assert env.row(running.id).status == "running"


# ---------------------------------------------------------------- UT-JOB-13


def test_ut_job_13_purge_backoff(env: Env):
    h = FakeHandler(
        "purge_dog",
        *[JobError("purge_failed", True) for _ in range(8)],
    )
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="purge_dog", dog_id="d1"))
    assert env.row(jid).max_attempts == 8
    expected = [60, 300, 900, 3600, 10800, 21600, 43200]
    for i, seconds in enumerate(expected, start=1):
        t = env.clock.now()
        assert runner.run_once() is True
        row = env.row(jid)
        assert (row.status, row.attempts) == ("queued", i)
        assert row.run_after == t + timedelta(seconds=seconds)
        env.clock.set(row.run_after)
    runner.run_once()
    row = env.row(jid)
    assert (row.status, row.attempts) == ("failed", 8)
    assert [e.code for _, e in h.finals] == ["purge_failed"]


def test_ut_job_13_default_max_attempts_by_type(env: Env):
    ids = {
        t: env.queue.enqueue(JobSpec(type=t))
        for t in (
            "transcode", "transcribe", "sample", "draft", "merge", "check",
            "purge_clip", "purge_dog", "retention_sweep",
        )
    }
    expected = {"purge_clip": 8, "purge_dog": 8, "retention_sweep": 1}
    for t, jid in ids.items():
        assert env.row(jid).max_attempts == expected.get(t, 2), t


def test_ut_job_13_retention_sweep_has_no_retry(env: Env):
    h = FakeHandler("retention_sweep", JobError("purge_failed", True))
    runner = env.runner(h)
    jid = env.queue.enqueue(JobSpec(type="retention_sweep", dedupe_key="sweep:2026-10-28"))
    runner.run_once()
    assert env.row(jid).status == "failed"


# ---------------------------------------------------------------- UT-JOB-14


def test_ut_job_14_ffmpeg_error_translation():
    """The ffmpeg half of 04 8.7 / 06 4.x: timeout, kill, disk full are retryable
    `transcode_failed`; any other exit is `transcode_failed`, not retryable."""
    from app.pipeline.ffmpeg import FFmpegError, ffmpeg_error_to_job_error

    for kind in ("timeout", "killed", "disk_full"):
        err = ffmpeg_error_to_job_error(FFmpegError(kind, "x"))
        assert (err.code, err.retryable) == ("transcode_failed", True), kind
    err = ffmpeg_error_to_job_error(FFmpegError("exit", "bad", returncode=1))
    assert (err.code, err.retryable) == ("transcode_failed", False)


def test_ut_job_14_handler_error_translation():
    """The adapter half of 04 8.7: ai errors leave the lane P handlers as
    `JobError` with the step code; ffmpeg errors in the transcode handler follow
    the same retry rule."""
    from types import SimpleNamespace

    from app.ai.errors import AiPermanentError, AiTransientError
    from app.pipeline.ffmpeg import FFmpegError
    from app.pipeline.handlers.draft import DraftHandler
    from app.pipeline.handlers.transcode import TranscodeHandler
    from app.pipeline.handlers.transcribe import TranscribeHandler

    info = SimpleNamespace(
        id="c1", session_id="s1", dog_id="d1", ordinal=1, original_filename="a.mp4",
        original_path="dogs/d1/clips/c1/original.mp4", has_audio=True, duration_s=5.0,
        playback_path="p", situations=("new_person",), observed_on=date(2026, 10, 1), dog_name="Rex",
        fixture_key="a", prefix="dogs/d1/clips/c1/",
    )
    pctx = SimpleNamespace(info=info, transcript=(), language=None, segments=())
    pipeline = SimpleNamespace(
        begin_step=lambda cid, step: info, draft_context=lambda cid: pctx
    )

    class Storage:
        def exists(self, key):
            return True

        def open_path(self, key):
            from pathlib import Path

            return Path("/nonexistent") / key

        def new_tmp_path(self):
            import tempfile
            from pathlib import Path

            return Path(tempfile.mkdtemp())

    def raiser(exc):
        def call(*a, **k):
            raise exc

        return call

    class Ffmpeg:
        def __init__(self, exc):
            self.probe = raiser(exc)

    def ctx(**kw):
        base = {
            "settings": SimpleNamespace(draft_mode="frames", max_clip_s=120,
                                     clip_duration_tolerance_s=0.5),
            "storage": Storage(),
            "services": SimpleNamespace(clip_pipeline_service=pipeline),
        }
        base.update(kw)
        return SimpleNamespace(**base)

    job = JobView(
        id=1, type="x", payload={"clip_id": "c1"}, dog_id="d1", session_id="s1",
        clip_id="c1", dedupe_key=None, attempts=1, max_attempts=2,
    )
    for exc_type, retryable in ((AiTransientError, True), (AiPermanentError, False)):
        ai = SimpleNamespace(transcriber=SimpleNamespace(transcribe=raiser(exc_type("x"))))
        with pytest.raises(JobError) as caught:
            TranscribeHandler().handle(job, ctx(ai=ai))
        assert (caught.value.code, caught.value.retryable) == ("ai_failed", retryable)

    class Frames(Storage):
        pass

    ai = SimpleNamespace(drafter=SimpleNamespace(draft=raiser(AiTransientError("x"))))
    services = SimpleNamespace(
        clip_pipeline_service=SimpleNamespace(
            begin_step=lambda cid, step: info,
            draft_context=lambda cid: SimpleNamespace(
                info=info, transcript=(), language=None, segments=()
            ),
        ),
        draft_ingest_service=None,
    )
    with pytest.raises(JobError) as caught:
        DraftHandler().handle(job, ctx(ai=ai, services=services))
    assert (caught.value.code, caught.value.retryable) == ("ai_failed", True)

    for kind, code, retryable in (
        ("timeout", "transcode_failed", True),
        ("disk_full", "transcode_failed", True),
        ("not_found", "transcode_failed", False),
        ("exit", "unsupported_file", False),
    ):
        with pytest.raises(JobError) as caught:
            TranscodeHandler().handle(job, ctx(ffmpeg=Ffmpeg(FFmpegError(kind, "x"))))
        assert (caught.value.code, caught.value.retryable) == (code, retryable), kind


# ---------------------------------------------------------------- UT-JOB-15


def test_ut_job_15_check_never_fails_a_session(env: Env, seed):
    org = seed.org()
    staff = seed.member(org, "staff")
    dog = seed.dog(org, staff)
    sess = seed.session(dog, staff, status="processing")

    def final(job: JobView, error: JobError, ctx: HandlerContext) -> None:
        # the real CheckHandler adds check_unavailable flags and nothing else
        calls.append(error.code)

    calls: list[str] = []
    h = FakeHandler("check", JobError("ai_failed", False))
    h.on_final_failure = final  # type: ignore[method-assign]
    runner = env.runner(h)
    env.queue.enqueue(JobSpec(type="check", session_id=sess.id, dog_id=dog.id))
    runner.run_once()

    h2 = FakeHandler("check", JobError("ai_failed", True), JobError("ai_failed", True))
    h2.on_final_failure = final  # type: ignore[method-assign]
    runner2 = env.runner(h2)
    jid2 = env.queue.enqueue(JobSpec(type="check", session_id=sess.id, dog_id=dog.id))
    runner2.run_once()
    env.clock.advance(30)
    runner2.run_once()

    assert env.row(jid2).status == "failed"
    assert calls == ["ai_failed", "ai_failed"]
    from app.models import FilmingSession

    with Session(env.engine) as s:
        row = s.get(FilmingSession, sess.id)
        assert row.fail_code is None
        assert row.status == sess.status


# ---------------------------------------------------------------- UT-JOB-16


@pytest.mark.parametrize("max_attempts", [2, 3, 8])
def test_ut_job_16_stale_reset_follows_j4_j5(env: Env, seed, max_attempts: int):
    locked = env.clock.now() - timedelta(minutes=11)
    below = _seed_job(
        seed, env.clock, "draft", status="running", attempts=1,
        max_attempts=max_attempts, locked_at=locked, locked_by="dead",
    )
    at_max = _seed_job(
        seed, env.clock, "draft", status="running", attempts=max_attempts,
        max_attempts=max_attempts, locked_at=locked, locked_by="dead",
    )
    h = FakeHandler("draft")
    runner = env.runner(h)
    runner.reset_stale()
    if max_attempts > 1:
        assert env.row(below.id).status == "queued"
    assert env.row(at_max.id).status == "failed"
    assert [j.id for j, _ in h.finals] == [at_max.id]
    assert env.row(below.id).locked_by is None
