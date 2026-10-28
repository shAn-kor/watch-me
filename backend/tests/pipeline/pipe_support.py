"""Shared harness of the lane P pipeline tests (07 section 3.15).

`PipeEnv` builds the real worker (`app.worker.build_runner`) over the test
container: real ffmpeg, `MockAdapter` AI (scripted fakes where a test needs
them), temp storage, `FakeClock`. Nothing here is imported by the app.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.adapters.mock import MockAdapter
from app.clock import FakeClock
from app.config import Settings
from app.container import AiSlots, Container, build_container
from app.db.base import new_id
from app.domain.situations import SITUATION_ORDER
from app.models import (
    Clip,
    CostLedger,
    Dog,
    Fact,
    FactEvidence,
    FilmingSession,
    Job,
    Segment,
    TranscriptSegment,
)
from app.pipeline.ffmpeg import FFmpeg
from app.services.views import JobSpec
from app.storage.base import StorageError, StorageFull
from app.storage.local import LocalStorage
from tools.make_fixtures import get as fixture

ALL_SITUATIONS = list(SITUATION_ORDER)
FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "ffprobe"


def csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


# ------------------------------------------------------------------ doubles


class Spy:
    """Wraps one AI adapter and records every request per method."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.calls: dict[str, list[Any]] = {
            "transcribe": [], "draft": [], "check": [], "select": [],
        }  # fmt: skip

    def transcribe(self, req: Any):
        self.calls["transcribe"].append(req)
        return self.inner.transcribe(req)

    def draft(self, req: Any):
        self.calls["draft"].append(req)
        return self.inner.draft(req)

    def check(self, req: Any):
        self.calls["check"].append(req)
        return self.inner.check(req)

    def select(self, req: Any):
        self.calls["select"].append(req)
        return self.inner.select(req)


class CountingFFmpeg(FFmpeg):
    """Real ffmpeg that counts every process it starts."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.exec_calls = 0

    def _exec(self, argv: list[str], timeout: float) -> Any:
        self.exec_calls += 1
        return super()._exec(argv, timeout)


class FaultyStorage:
    """`LocalStorage` with switches: fail or skip deletes, fill the disk."""

    def __init__(self, inner: LocalStorage):
        self._inner = inner
        self.delete_prefix_failures = 0  # fail this many calls, then work
        self.delete_prefix_always_fails = False
        self.delete_prefix_leaves: set[str] = set()  # keys that survive a delete
        self.full_on_put_suffix: str | None = None
        self.events: list[str] = []
        self.on_delete_prefix: Callable[[str], None] | None = None
        self.delete_prefix_calls = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def put_file(self, key: str, src_path: Path) -> None:
        if self.full_on_put_suffix and key.endswith(self.full_on_put_suffix):
            raise StorageFull("no space left on device")
        self._inner.put_file(key, src_path)

    def delete_prefix(self, prefix: str) -> int:
        self.delete_prefix_calls += 1
        self.events.append(f"delete_prefix:{prefix}")
        if self.on_delete_prefix:
            self.on_delete_prefix(prefix)
        if self.delete_prefix_always_fails:
            raise StorageError("disk error")
        if self.delete_prefix_failures > 0:
            self.delete_prefix_failures -= 1
            raise StorageError("disk error")
        if self.delete_prefix_leaves:
            keep = {
                k: self._inner.open_path(k).read_bytes()
                for k in self.delete_prefix_leaves
            }
            count = self._inner.delete_prefix(prefix)
            for k, data in keep.items():
                p = self._inner.open_path(k)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            return count
        return self._inner.delete_prefix(prefix)

    def list_prefix(self, prefix: str) -> list[str]:
        self.events.append(f"list_prefix:{prefix}")
        return self._inner.list_prefix(prefix)


def write_script(path: Path, body: str) -> str:
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def make_short_clip(dest: Path, seconds: float = 0.8) -> Path:
    """A video-only clip shorter than 1 s (no fixture exists for it)."""
    subprocess.run(
        [FFMPEG_BIN, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25", "-t", str(seconds),
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an", str(dest)],
        check=True,
    )  # fmt: skip
    return dest


def ai_slots(
    settings: Settings,
    *,
    drafter: Any = None,
    checker: Any = None,
    transcriber: Any = None,
    mock: MockAdapter | None = None,
) -> AiSlots:
    """Mock AI with the given roles replaced; every role is wrapped in a `Spy`."""
    from app.ai.adapters.rules import RulesChecker

    mock = mock or MockAdapter(settings.ai_mock_fixtures_dir)
    return AiSlots(
        transcriber=Spy(transcriber or mock),
        drafter=Spy(drafter or mock),
        checker=Spy(checker or RulesChecker()),
        selector=Spy(mock),
    )


class FnDrafter:
    """A drafter driven by a function `fn(req) -> DraftOutput` (may raise)."""

    def __init__(self, fn: Callable[[Any], Any]):
        self.fn = fn

    def draft(self, req: Any):
        from app.ai.types import Usage

        return self.fn(req), [Usage(provider="mock", model="mock", purpose="draft")]


# --------------------------------------------------------------------- env


class PipeEnv:
    def __init__(
        self,
        settings: Settings,
        clock: FakeClock,
        engine: Any,
        seed: Any,
        *,
        ai: AiSlots | None = None,
        ffmpeg: FFmpeg | None = None,
        storage: Any = None,
        checker: str = "rules",
        **settings_update: Any,
    ):
        from app.worker import build_runner

        self.settings = (
            settings.model_copy(update=settings_update) if settings_update else settings
        )
        self.clock = clock
        self.engine = engine
        self.seed = seed
        self.mock = MockAdapter(self.settings.ai_mock_fixtures_dir)
        if ai is None:
            from app.ai.adapters.rules import RulesChecker

            check_impl: Any = (
                self.mock
                if checker == "mock"
                else RulesChecker()
            )
            ai = AiSlots(
                transcriber=Spy(self.mock),
                drafter=Spy(self.mock),
                checker=Spy(check_impl),
                selector=Spy(self.mock),
            )
        self.ai = ai
        self.container: Container = build_container(
            self.settings, clock=clock, engine=engine, ai=ai, storage=storage
        )
        self.storage = self.container.storage
        self.ffmpeg = ffmpeg or CountingFFmpeg(
            FFMPEG_BIN, FFPROBE_BIN,
            transcode_timeout_s=self.settings.transcode_timeout_s,
            frames_timeout_s=self.settings.sample_timeout_s,
        )  # fmt: skip
        self.container.pipeline["ffmpeg"] = self.ffmpeg
        self.runner = build_runner(self.container, worker_id="w1", poll_s=0.01)
        self.services = self.container.services

    # ------------------------------------------------------------- seeding

    def world(self) -> tuple[Any, Any, Any, Any]:
        """(org, staff, volunteer, dog)."""
        org = self.seed.org()
        staff = self.seed.member(org, "staff", name="Staff")
        vol = self.seed.member(org, "volunteer", name="Vol")
        dog = self.seed.dog(org, staff, name="Biscuit")
        self.org, self.staff, self.vol, self.dog = org, staff, vol, dog
        self.seed_member = vol
        return org, staff, vol, dog

    def session(
        self,
        dog: Dog,
        member: Any,
        *,
        situations: list[str] | None = None,
        status: str = "processing",
    ) -> FilmingSession:
        return self.seed.session(
            dog, member, status=status, situations=situations or ALL_SITUATIONS
        )

    def add_clip(
        self,
        session: FilmingSession,
        media: str | Path = "h264_5s.mp4",
        *,
        ordinal: int = 1,
        filename: str | None = None,
        enqueue: bool = True,
    ) -> Clip:
        """Store the media as the clip original, insert an `uploaded` clip row and
        (by default) enqueue its `transcode` job, as the upload service does."""
        src = Path(media) if isinstance(media, Path) else fixture(media)
        cid = new_id()
        key = f"dogs/{session.dog_id}/clips/{cid}/original{src.suffix}"
        self.storage.put_file(key, src)
        probe = FFmpeg(FFMPEG_BIN, FFPROBE_BIN).probe(src)
        clip = Clip(
            id=cid,
            session_id=session.id,
            dog_id=session.dog_id,
            ordinal=ordinal,
            original_filename=filename or src.name,
            original_path=key,
            original_size_bytes=src.stat().st_size,
            has_audio=probe.has_audio,
            duration_s=probe.duration_s,
            status="uploaded",
        )
        with Session(self.engine, expire_on_commit=False) as s:
            s.add(clip)
            s.commit()
        if enqueue:
            self.enqueue_step(clip, "transcode")
        return clip

    def enqueue_step(self, clip: Clip, step: str) -> int:
        return self.services.job_queue.enqueue(
            JobSpec(
                type=step,
                payload={
                    "clip_id": clip.id,
                    "session_id": clip.session_id,
                    "dog_id": clip.dog_id,
                },
                dog_id=clip.dog_id,
                session_id=clip.session_id,
                clip_id=clip.id,
            )
        )

    # ----------------------------------------------------------------- run

    def run(self, limit: int = 400) -> int:
        """Run due jobs until none is due. Returns the number of jobs run."""
        n = 0
        while self.runner.run_once():
            n += 1
            if n > limit:
                raise AssertionError("worker did not become idle")
        return n

    def run_step(self) -> bool:
        return self.runner.run_once()

    # ------------------------------------------------------------- queries

    @contextmanager
    def db(self) -> Iterator[Session]:
        with Session(self.engine) as s:
            yield s

    def clip(self, clip_id: str) -> Clip:
        with self.db() as s:
            row = s.get(Clip, clip_id)
            s.expunge(row)
            return row

    def session_row(self, session_id: str) -> FilmingSession:
        with self.db() as s:
            row = s.get(FilmingSession, session_id)
            s.expunge(row)
            return row

    def facts(
        self,
        *,
        session_id: str | None = None,
        dog_id: str | None = None,
        merged: bool | None = None,
    ) -> list[Fact]:
        with self.db() as s:
            q = select(Fact).order_by(Fact.created_at, Fact.id)
            if session_id:
                q = q.where(Fact.session_id == session_id)
            if dog_id:
                q = q.where(Fact.dog_id == dog_id)
            if merged is not None:
                q = q.where(Fact.merged.is_(merged))
            rows = list(s.scalars(q))
            for r in rows:
                _ = list(r.evidence)
            s.expunge_all()
            return rows

    def evidence(self, fact_id: str) -> list[FactEvidence]:
        with self.db() as s:
            rows = list(
                s.scalars(select(FactEvidence).where(FactEvidence.fact_id == fact_id))
            )
            s.expunge_all()
            return rows

    def transcript(self, clip_id: str) -> list[TranscriptSegment]:
        with self.db() as s:
            rows = list(
                s.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.clip_id == clip_id)
                    .order_by(TranscriptSegment.idx)
                )
            )
            s.expunge_all()
            return rows

    def segments(self, clip_id: str) -> list[Segment]:
        with self.db() as s:
            rows = list(
                s.scalars(
                    select(Segment)
                    .where(Segment.clip_id == clip_id)
                    .order_by(Segment.idx)
                )
            )
            s.expunge_all()
            return rows

    def jobs(self, type: str | None = None, **where: Any) -> list[Job]:
        with self.db() as s:
            q = select(Job).order_by(Job.id)
            if type:
                q = q.where(Job.type == type)
            for k, v in where.items():
                q = q.where(getattr(Job, k) == v)
            rows = list(s.scalars(q))
            s.expunge_all()
            return rows

    def ledger(self, purpose: str | None = None) -> list[CostLedger]:
        with self.db() as s:
            q = select(CostLedger).order_by(CostLedger.id)
            if purpose:
                q = q.where(CostLedger.purpose == purpose)
            rows = list(s.scalars(q))
            s.expunge_all()
            return rows

    def keys(self, prefix: str) -> list[str]:
        return self.storage.list_prefix(prefix)

    def clip_keys(self, clip: Clip) -> list[str]:
        return self.keys(f"dogs/{clip.dog_id}/clips/{clip.id}/")

    def clip_prefix(self, clip: Clip) -> str:
        return f"dogs/{clip.dog_id}/clips/{clip.id}/"

    # ----------------------------------------------------------------- api

    @contextmanager
    def api(self, member: Any) -> Iterator[tuple[TestClient, str]]:
        from app.main import create_app

        app = create_app(self.container)
        with TestClient(app, base_url="http://testserver") as client:
            issued = self.container.security["cookie_codec"].issue(
                member.id, getattr(member, "session_epoch", 0) or 0
            )
            client.cookies.set("wm_session", issued.value)
            yield client, self.container.security["csrf"].token_for(issued.payload.sid)

    def spy(self, role: str) -> Spy:
        return getattr(self.ai, role)

    def advance(self, seconds: float) -> None:
        self.clock.advance(seconds)

    def run_in_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return t


def count_running(name: str) -> int:
    """Processes whose command line contains `name` (orphan check)."""
    out = subprocess.run(["pgrep", "-f", name], check=False, capture_output=True)
    return 0 if out.returncode == 1 else len(out.stdout.split())


def python_script(path: Path, code: str) -> str:
    """A tiny wrapper script that runs `code` with this interpreter."""
    return write_script(path, f'exec "{sys.executable}" -c \'{code}\' "$@"')


def utime_ago(path: Path, now_ts: float, hours: float) -> None:
    ts = now_ts - hours * 3600
    os.utime(path, (ts, ts))


def minutes(n: float) -> timedelta:
    return timedelta(minutes=n)
