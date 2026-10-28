"""ClipUploadService: the checks and the commit of a clip upload (01 section 5.3).

The api receives the body (`app.api.upload.UploadReceiver`) and hands the finished
tmp file here. `precheck` runs before any body byte is read; `accept` runs the rest
of the check order: extension, probe, duration, then storage, rows, and the
`transcode` job. A rejected upload leaves no row and no file.

Job enqueued: type `transcode`, payload `{clip_id, session_id, dog_id}`, columns
`clip_id`, `session_id`, `dog_id`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Protocol

from app.clock import Clock
from app.config import Settings
from app.db.base import new_id
from app.db.uow import UnitOfWork
from app.errors import (
    ClipLimitReached,
    ClipTooLong,
    ConsentRequired,
    InvalidState,
    NotFound,
    NotOwnSession,
    StorageUnavailable,
    UnsupportedFileType,
    ValidationFailed,
)
from app.repositories.clips import ClipRepository
from app.repositories.sessions import SessionRepository
from app.services.job_queue import JobQueue
from app.services.session_service import ClipView, build_clip_view
from app.services.views import JobSpec, MediaUrls, Principal
from app.storage.base import StorageError

MAX_FILENAME_CHARS = 200
MAX_REQUEST_ID_CHARS = 40
DURATION_TOLERANCE_S = 0.5
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ReceivedFile(Protocol):
    path: Any  # pathlib.Path of the tmp file
    filename: str
    size: int
    client_request_id: str | None


@dataclass(frozen=True, slots=True)
class UploadResult:
    clip: ClipView
    warnings: tuple[str, ...]
    created: bool


def clean_filename(raw: str) -> str:
    """Control characters out, directory parts out, at most 200 characters."""
    name = _CONTROL.sub("", raw).replace("\\", "/")
    name = name.rsplit("/", 1)[-1].strip()
    if name in ("", ".", ".."):
        name = "upload"
    return name[:MAX_FILENAME_CHARS]


class ClipUploadService:
    def __init__(
        self,
        *,
        clock: Clock,
        settings: Settings,
        job_queue: JobQueue,
        storage: Any,
        ffmpeg: Any,
        media_urls: MediaUrls,
    ):
        self._clock = clock
        self._settings = settings
        self._jobs = job_queue
        self._storage = storage
        self._ffmpeg = ffmpeg
        self._media = media_urls

    # ------------------------------------------------------------ prechecks

    def precheck(self, who: Principal, session_id: str, *, uow: UnitOfWork) -> None:
        """consent, not_found, not_own_session, invalid_state, clip_limit_reached.
        Reads no body."""
        self._guard(who, session_id, uow, check_limit=True)

    def _guard(
        self, who: Principal, session_id: str, uow: UnitOfWork, *, check_limit: bool
    ):
        if not who.consented:
            raise ConsentRequired()
        repo = SessionRepository(uow.session)
        found = repo.session_with_dog(session_id, who.org_id)
        if found is None or found[1].status == "deleted":
            raise NotFound()
        sess, dog = found
        if not who.is_staff and sess.member_id != who.member_id:
            raise NotOwnSession()
        if sess.status != "open" or dog.status != "draft":
            raise InvalidState()
        if check_limit:
            self._check_limit(repo, sess.id)
        return sess, dog, repo

    def _check_limit(self, repo: SessionRepository, session_id: str) -> None:
        if len(repo.live_clips(session_id)) >= self._settings.max_clips_per_session:
            raise ClipLimitReached(
                details={"max": self._settings.max_clips_per_session}
            )

    # --------------------------------------------------------------- accept

    def accept(
        self,
        who: Principal,
        session_id: str,
        received: ReceivedFile,
        *,
        uow: UnitOfWork,
    ) -> UploadResult:
        """Blocking (ffprobe, file copy): call it from a worker thread."""
        tmp = received.path
        key: str | None = None
        try:
            sess, dog, repo = self._guard(who, session_id, uow, check_limit=False)
            clip_repo = ClipRepository(uow.session)
            request_id = self._request_id(received.client_request_id)
            if request_id is not None:
                existing = clip_repo.by_request_id(sess.id, request_id)
                if existing is not None and existing.deleted_at is None:
                    return UploadResult(
                        clip=self._view(repo, existing),
                        warnings=() if existing.has_audio else ("no_audio_track",),
                        created=False,
                    )
            self._check_limit(repo, sess.id)

            ext = PurePosixPath(clean_filename(received.filename)).suffix.lower()
            allowed = [e.lower() for e in self._settings.allowed_extensions]
            if ext not in allowed:
                raise UnsupportedFileType(details={"allowed": allowed})
            probe = self._probe(tmp, allowed)
            if probe.duration_s > self._settings.max_clip_s + DURATION_TOLERANCE_S:
                raise ClipTooLong(
                    details={
                        "max_s": int(self._settings.max_clip_s),
                        "duration_s": round(probe.duration_s, 1),
                    }
                )

            clip_id = new_id()
            new_key = f"dogs/{dog.id}/clips/{clip_id}/original{ext}"
            try:
                self._storage.put_file(new_key, tmp)
            except StorageError as exc:
                raise StorageUnavailable() from exc
            key = new_key

            ordinal = next(
                n for n in range(1, 4) if n not in clip_repo.live_ordinals(sess.id)
            )
            clip = clip_repo.add_clip(
                id=clip_id,
                session_id=sess.id,
                dog_id=dog.id,
                ordinal=ordinal,
                client_request_id=request_id,
                original_filename=clean_filename(received.filename),
                original_path=key,
                original_size_bytes=received.size,
                source_container=(probe.container or "")[:40] or None,
                source_codec=probe.video_codec,
                has_audio=bool(probe.has_audio),
                duration_s=min(probe.duration_s, 120.5),
                status="uploaded",
                step="transcode",
                created_at=self._clock.now(),
            )
            dog.people_check_at = None
            dog.people_check_by = None
            self._jobs.enqueue(
                JobSpec(
                    type="transcode",
                    payload={
                        "clip_id": clip.id,
                        "session_id": sess.id,
                        "dog_id": dog.id,
                    },
                    dog_id=dog.id,
                    session_id=sess.id,
                    clip_id=clip.id,
                ),
                uow=uow,
            )
            uow.commit()
            view = self._view(repo, clip)
            key = None  # committed: the file now belongs to the clip
            return UploadResult(
                clip=view,
                warnings=() if probe.has_audio else ("no_audio_track",),
                created=True,
            )
        except BaseException:
            try:
                uow.rollback()
            except Exception:  # noqa: BLE001
                pass
            if key is not None:
                try:
                    self._storage.delete(key)
                except Exception:  # noqa: BLE001
                    pass
            raise
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    # -------------------------------------------------------------- helpers

    def _view(self, repo: SessionRepository, clip: Any) -> ClipView:
        return build_clip_view(
            clip,
            self._media,
            has_transcript=bool(repo.clip_ids_with_transcript([clip.id])),
        )

    @staticmethod
    def _request_id(raw: str | None) -> str | None:
        if raw is None:
            return None
        raw = raw.strip()
        if not raw:
            return None
        if len(raw) > MAX_REQUEST_ID_CHARS:
            raise ValidationFailed(
                details={
                    "fields": [{"field": "client_request_id", "reason": "too_long"}]
                }
            )
        return raw

    def _probe(self, path: Any, allowed: list[str]):
        try:
            probe = self._ffmpeg.probe(path)
        except (
            Exception
        ) as exc:  # FFmpegError is duck-typed: services do not import pipeline
            kind = getattr(exc, "kind", None)
            if kind == "timeout":
                raise UnsupportedFileType(
                    details={"allowed": allowed, "reason": "probe_timeout"}
                ) from exc
            if kind in ("exit", "bad_output", "killed"):
                raise UnsupportedFileType(
                    details={"allowed": allowed, "reason": "unreadable"}
                ) from exc
            raise
        if not probe.has_video or probe.duration_s <= 0:
            raise UnsupportedFileType(
                details={"allowed": allowed, "reason": "no_video"}
            )
        return probe
