"""Upload vs. a concurrent worker write: `database is locked` must not reach the client."""

from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.uow import UnitOfWork
from app.services.views import Principal
from tests.api._s3_support import (  # noqa: F401
    clips_of,
    media,
    open_session,
    upload_file,
    world,
)


@dataclass
class _Received:
    path: Path
    filename: str = "h264_5s.mp4"
    size: int = 1000
    client_request_id: str | None = None


def _principal(member) -> Principal:
    return Principal(
        member_id=member.id,
        org_id=member.org_id,
        role=member.role,
        consented=True,
        sid="s" * 16,
    )


def test_upload_survives_a_worker_commit_between_precheck_and_accept(
    container, engine, seed, world, open_session, tmp_path
):
    """The api reads in `precheck`, streams the body for a while, and writes in
    `accept`. A worker commit in between made the deferred read-then-write
    transaction fail at once with `database is locked` (busy_timeout does not help)."""
    service = container.services.clip_upload_service
    who = _principal(world.vol1)
    other = seed.clip(seed.session(world.dog_empty, world.vol2), 1, status="processing")
    tmp = tmp_path / "up.mp4"
    shutil.copy(media("h264_5s.mp4"), tmp)

    with UnitOfWork(container.session_factory) as uow:
        service.precheck(who, open_session.id, uow=uow)  # read snapshot is now open
        # the worker commits (begin_step / complete_transcode style)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE clip SET step = 'sample' WHERE id = :i"), {"i": other.id}
            )
        result = service.accept(who, open_session.id, _Received(tmp), uow=uow)
    assert result.created


def test_upload_waits_for_a_worker_write_transaction(
    client, db, engine, world, open_session, login_as
):
    token = login_as(world.vol1)
    holding = threading.Event()

    def worker() -> None:
        raw = sqlite3.connect(engine.url.database, timeout=5, isolation_level=None)
        try:
            raw.execute("BEGIN IMMEDIATE")  # a worker-like write transaction
            holding.set()
            time.sleep(1.0)
            raw.execute("COMMIT")
        finally:
            raw.close()

    t = threading.Thread(target=worker)
    t.start()
    holding.wait(5)
    started = time.monotonic()
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    waited = time.monotonic() - started
    t.join()
    assert r.status_code == 201, r.text
    assert waited >= 0.5  # it queued for the lock instead of failing
    assert len(clips_of(db, open_session.id)) == 1


def test_residual_database_locked_is_a_retryable_503(
    client, db, container, world, open_session, login_as, monkeypatch
):
    import app.services.clip_upload_service as mod

    def locked(_uow):
        raise OperationalError("UPDATE job", {}, Exception("database is locked"))

    monkeypatch.setattr(mod, "lock_for_write", locked)
    token = login_as(world.vol1)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "service_busy"
    assert int(r.headers["Retry-After"]) >= 1
    assert clips_of(db, open_session.id) == []


def test_other_operational_errors_stay_500(
    client, world, open_session, login_as, monkeypatch
):
    import app.services.clip_upload_service as mod

    def broken(_uow):
        raise OperationalError("UPDATE job", {}, Exception("disk I/O error"))

    monkeypatch.setattr(mod, "lock_for_write", broken)
    token = login_as(world.vol1)
    r = upload_file(client, token, open_session.id, "h264_5s.mp4")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
