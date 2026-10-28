"""MediaAccessService (06 section 3.8; 01 section 7, ADR-0043, I-14).

Order of checks (every failure is the same `not_found`, never 403):
1. the clip exists, is not soft-deleted, is `ready`, and its dog is not deleted;
2. a member of the dog's org may read any dog status except `deleted`;
3. otherwise public: the dog is `published` and a confirmed, merged fact of that dog
   cites the clip (decided by `repositories.public_facts`, UT-ARCH-02).

The whole file of a cited clip is public by design (D9); the range is not checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.db.uow import UnitOfWork
from app.errors import NotFound
from app.repositories.public_facts import (
    clip_is_publicly_cited,
    get_media_clip,
    get_media_dog,
    transcript_cues,
)
from app.services.views import Principal
from app.storage.base import Storage, StorageError


@dataclass(frozen=True, slots=True)
class MediaFile:
    """Either a file on disk (`path`) or generated text (`body`)."""

    content_type: str
    path: Path | None = None
    body: bytes | None = None
    modified: datetime | None = None


def vtt_timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    h, rest = divmod(total_ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def build_vtt(cues: list[tuple[float, float, str]]) -> str:
    lines = ["WEBVTT", ""]
    for start, end, text in cues:
        clean = " ".join(text.replace("-->", "->").split())
        lines += [f"{vtt_timestamp(start)} --> {vtt_timestamp(end)}", clean, ""]
    return "\n".join(lines)


class MediaAccessService:
    def __init__(self, *, storage: Storage):
        self._storage = storage

    # ------------------------------------------------------------------ clips

    def resolve_clip_video(
        self, uow: UnitOfWork, clip_id: str, principal: Principal | None
    ) -> MediaFile:
        clip = self._readable_clip(uow, clip_id, principal)
        if not clip.playback_path:
            raise NotFound()
        return MediaFile("video/mp4", path=self._existing(clip.playback_path), modified=clip.ready_at)

    def resolve_clip_captions(
        self, uow: UnitOfWork, clip_id: str, principal: Principal | None
    ) -> MediaFile:
        clip = self._readable_clip(uow, clip_id, principal)
        cues = transcript_cues(uow.session, clip.id)
        if not cues:
            raise NotFound()
        return MediaFile(
            "text/vtt; charset=utf-8",
            body=build_vtt(cues).encode("utf-8"),
            modified=clip.ready_at,
        )

    def _readable_clip(self, uow: UnitOfWork, clip_id: str, principal: Principal | None):
        clip = get_media_clip(uow.session, clip_id)
        if clip is None:
            raise NotFound()
        if principal is not None and principal.org_id == clip.org_id:
            return clip
        if clip.dog_status == "published" and clip_is_publicly_cited(
            uow.session, clip.id, clip.dog_id
        ):
            return clip
        raise NotFound()

    # ------------------------------------------------------------------ photo

    def resolve_dog_photo(
        self, uow: UnitOfWork, dog_id: str, principal: Principal | None
    ) -> MediaFile:
        dog = get_media_dog(uow.session, dog_id)
        if dog is None or not dog.photo_path:
            raise NotFound()
        in_org = principal is not None and principal.org_id == dog.org_id
        if not in_org and dog.status != "published":
            raise NotFound()
        return MediaFile("image/jpeg", path=self._existing(dog.photo_path))

    # ---------------------------------------------------------------- helpers

    def _existing(self, key: str) -> Path:
        try:
            if not self._storage.exists(key):
                raise NotFound()
            return self._storage.open_path(key)
        except StorageError as exc:
            raise NotFound() from exc
