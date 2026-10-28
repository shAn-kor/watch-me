"""ClipPipelineService: the clip state the step handlers read and write
(02 section 3.3, 04 sections 2 to 5, 03 section 2.2).

Handlers hold no SQL. Each method here is one short transaction. A step starts
with `begin_step` (which also tells the handler to skip when the clip or its dog is
gone), writes its output through one of the `save_*` or `complete_*` methods, and a
final failure goes through `mark_failed`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import delete, select

from app.clock import Clock
from app.config import Settings
from app.db.uow import UowFactory
from app.domain.enums import CLIP_FAIL_CODES
from app.models import Clip, Dog, FilmingSession, Segment, TranscriptSegment
from app.services._write_lock import lock_for_write
from app.storage.base import Storage, StorageError

log = logging.getLogger(__name__)

STARTABLE = ("uploaded", "processing")
_VALID_CODES = frozenset(c.value for c in CLIP_FAIL_CODES)
DETAIL_MAX = 300


@dataclass(frozen=True, slots=True)
class ClipInfo:
    id: str
    session_id: str
    dog_id: str
    ordinal: int
    original_filename: str
    original_path: str | None
    has_audio: bool
    duration_s: float
    playback_path: str | None
    situations: tuple[str, ...]
    observed_on: date
    dog_name: str | None

    @property
    def fixture_key(self) -> str:
        """Mock-adapter fixture key: the stem of the uploaded file name."""
        return PurePosixPath(self.original_filename.replace("\\", "/")).stem

    @property
    def prefix(self) -> str:
        return f"dogs/{self.dog_id}/clips/{self.id}/"


@dataclass(frozen=True, slots=True)
class DraftContext:
    info: ClipInfo
    transcript: tuple[tuple[int, float, float, str], ...]  # seq, start, end, text
    language: str | None
    segments: tuple[tuple[int, float, float], ...]  # idx (1-based), start, end


class ClipPipelineService:
    def __init__(
        self,
        *,
        uow_factory: UowFactory,
        clock: Clock,
        settings: Settings,
        storage: Storage,
        session_service: Any,
        cost_service: Any,
    ):
        self._uow_factory = uow_factory
        self._clock = clock
        self._settings = settings
        self._storage = storage
        self._sessions = session_service
        self._cost = cost_service

    # ---------------------------------------------------------------- reads

    def _info(self, clip: Clip, sess: FilmingSession, dog: Dog) -> ClipInfo:
        return ClipInfo(
            id=clip.id,
            session_id=clip.session_id,
            dog_id=clip.dog_id,
            ordinal=clip.ordinal,
            original_filename=clip.original_filename,
            original_path=clip.original_path,
            has_audio=bool(clip.has_audio),
            duration_s=float(clip.duration_s),
            playback_path=clip.playback_path,
            situations=tuple(sess.situations or ()),
            observed_on=sess.observed_on,
            dog_name=dog.name,
        )

    def _load(self, uow: Any, clip_id: str) -> tuple[Clip, FilmingSession, Dog] | None:
        row = uow.session.execute(
            select(Clip, FilmingSession, Dog)
            .join(FilmingSession, FilmingSession.id == Clip.session_id)
            .join(Dog, Dog.id == Clip.dog_id)
            .where(Clip.id == clip_id)
        ).first()
        if row is None:
            return None
        clip, sess, dog = row
        if clip.deleted_at is not None or dog.status == "deleted":
            return None
        return clip, sess, dog

    def info(self, clip_id: str) -> ClipInfo | None:
        with self._uow_factory() as uow:
            found = self._load(uow, clip_id)
            return self._info(*found) if found else None

    # ---------------------------------------------------------------- steps

    def begin_step(self, clip_id: str, step: str) -> ClipInfo | None:
        """Mark the clip `processing` at `step`. None means: nothing to do (the clip
        or its dog is gone, or the clip is already terminal)."""
        with self._uow_factory() as uow:
            lock_for_write(uow)
            found = self._load(uow, clip_id)
            if found is None:
                return None
            clip, sess, dog = found
            if clip.status not in STARTABLE:
                return None
            clip.status = "processing"
            clip.step = step
            uow.commit()
            return self._info(clip, sess, dog)

    def complete_transcode(
        self,
        clip_id: str,
        *,
        playback_path: str,
        duration_s: float,
        container: str | None = None,
        codec: str | None = None,
    ) -> None:
        with self._uow_factory() as uow:
            lock_for_write(uow)
            clip = uow.session.get(Clip, clip_id)
            if clip is None or clip.deleted_at is not None:
                return
            clip.playback_path = playback_path
            if duration_s > 0:
                clip.duration_s = min(float(duration_s), 120.5)
            if container:
                clip.source_container = container[:40]
            if codec:
                clip.source_codec = codec[:20]
            uow.commit()

    def save_transcript(
        self,
        clip_id: str,
        result: Any,
        usages: Iterable[Any],
        dog_id: str,
        session_id: str,
    ) -> int:
        """Replace the transcript rows and write the `transcribe` ledger rows."""
        with self._uow_factory() as uow:
            lock_for_write(uow)
            found = self._load(uow, clip_id)
            if found is None:
                return 0
            uow.session.execute(
                delete(TranscriptSegment).where(TranscriptSegment.clip_id == clip_id)
            )
            n = 0
            for seg in result.segments:
                if seg.end_s <= seg.start_s or seg.start_s < 0 or not seg.text.strip():
                    continue
                uow.session.add(
                    TranscriptSegment(
                        clip_id=clip_id,
                        idx=n,
                        start_s=seg.start_s,
                        end_s=seg.end_s,
                        text=seg.text,
                        lang=result.language,
                    )
                )
                n += 1
            self._cost.record_usages(usages, dog_id, session_id, uow=uow)
            uow.commit()
            return n

    def save_segments(self, clip_id: str, windows: Sequence[Any]) -> None:
        """Replace the fixed 10 s segment rows (1-based `idx`)."""
        with self._uow_factory() as uow:
            lock_for_write(uow)
            if self._load(uow, clip_id) is None:
                return
            uow.session.execute(delete(Segment).where(Segment.clip_id == clip_id))
            for w in windows:
                uow.session.add(
                    Segment(
                        clip_id=clip_id, idx=w.index, start_s=w.start_s, end_s=w.end_s
                    )
                )
            uow.commit()

    def draft_context(self, clip_id: str) -> DraftContext | None:
        with self._uow_factory() as uow:
            found = self._load(uow, clip_id)
            if found is None:
                return None
            clip, sess, dog = found
            tr = list(
                uow.session.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.clip_id == clip_id)
                    .order_by(TranscriptSegment.idx)
                )
            )
            segs = list(
                uow.session.scalars(
                    select(Segment)
                    .where(Segment.clip_id == clip_id)
                    .order_by(Segment.idx)
                )
            )
            return DraftContext(
                info=self._info(clip, sess, dog),
                transcript=tuple((t.idx, t.start_s, t.end_s, t.text) for t in tr),
                language=tr[0].lang if tr else None,
                segments=tuple((s.idx, s.start_s, s.end_s) for s in segs),
            )

    # -------------------------------------------------------------- failure

    def mark_failed(self, clip_id: str, code: str, detail: str | None = None) -> None:
        """Final failure of a step: the clip is `failed` and the session is told."""
        if code not in _VALID_CODES:
            code = "transcode_failed"
        with self._uow_factory() as uow:
            lock_for_write(uow)
            clip = uow.session.get(Clip, clip_id)
            if clip is None or clip.deleted_at is not None or clip.status == "ready":
                return
            clip.status = "failed"
            clip.fail_code = code
            clip.fail_detail = (detail or "")[:DETAIL_MAX] or None
            clip.ready_at = None
            self._sessions.on_clip_terminal(clip.session_id, uow=uow)
            uow.commit()

    # -------------------------------------------------------------- cleanup

    def cleanup_derivatives(self, clip_id: str) -> None:
        """After `ready` and `KEEP_ORIGINALS=false`: drop the original, the WAV and
        the frames. The playback file stays (03 section 2.2)."""
        if self._settings.keep_originals:
            return
        with self._uow_factory() as uow:
            lock_for_write(uow)
            clip = uow.session.get(Clip, clip_id)
            if clip is None or clip.status != "ready":
                return
            prefix = f"dogs/{clip.dog_id}/clips/{clip.id}/"
            try:
                if clip.original_path:
                    self._storage.delete(clip.original_path)
                self._storage.delete(prefix + "audio.wav")
                self._storage.delete_prefix(prefix + "frames/")
            except StorageError:
                log.warning(
                    "derivative cleanup failed for clip %s", clip_id, exc_info=True
                )
                return
            clip.original_path = None
            uow.commit()


__all__ = ["ClipInfo", "ClipPipelineService", "DraftContext"]
