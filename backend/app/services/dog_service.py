"""DogService: dog CRUD, photo, list with coverage short form, dog detail
(06 section 3.2; 01 sections 4.1 to 4.5).

A method takes the request's `UnitOfWork` first (the api commits it after the route
returns, 08 section 8). Services return frozen views, never ORM rows.
"""

from __future__ import annotations

import io
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from app.clock import Clock
from app.config import Settings
from app.db.uow import UnitOfWork
from app.domain.confirm_policy import (
    ActorInfo,
    ConfirmContext,
    ConfirmPolicy,
    DogInfo,
    EvidenceInfo,
    FactInfo,
    missing_playback_evidence_ids,
)
from app.domain.coverage import Coverage
from app.domain.labels import clip_length
from app.domain.ranges import Range
from app.domain.situations import SITUATION_ORDER
from app.errors import (
    FileTooLarge,
    NotFound,
    StorageUnavailable,
    UnsupportedFileType,
    ValidationFailed,
)
from app.models import Clip, Dog, Fact, FilmingSession
from app.repositories.dogs import DogCounts, DogRepository, SessionCounts
from app.services.coverage_service import CoverageService, ShortCoverage
from app.services.views import (
    ClipErrorView,
    ClipLengthView,
    ClipView,
    ConfirmedView,
    EvidenceView,
    FactView,
    FlagView,
    MediaUrls,
    Principal,
)
from app.storage.base import Storage, StorageError

if TYPE_CHECKING:
    from app.services.publish_service import ChecklistView, PublishService

PHOTO_ALLOWED = [".jpg", ".jpeg", ".png"]
_MAGIC = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}
_CLIP_ERRORS = {
    "unsupported_file": ("This file could not be read as a video.", False),
    "too_long": ("This clip is longer than 2 minutes.", False),
    "transcode_failed": ("We could not convert this clip.", True),
    "ai_failed": ("We could not draft facts from this clip.", True),
    "ai_invalid_output": ("We could not draft facts from this clip.", True),
}


def clean_text(value: str | None) -> str:
    """NFC and trimmed (02 section 0)."""
    return unicodedata.normalize("NFC", value or "").strip()


# ------------------------------------------------------------------- views


@dataclass(frozen=True, slots=True)
class DogView:
    id: str
    name: str
    sex: str
    age_estimate: str
    size: str
    location: str | None
    photo_url: str | None
    status: str
    public_slug: str | None
    public_path: str | None
    created_by: str
    created_at: datetime
    published_at: datetime | None
    adopted_at: datetime | None


@dataclass(frozen=True, slots=True)
class DogListItem:
    dog: DogView
    coverage: ShortCoverage
    counts: DogCounts


@dataclass(frozen=True, slots=True)
class SessionSummaryView:
    id: str
    dog_id: str
    member_id: str
    owner_name: str
    situations: tuple[str, ...]
    observed_on: date
    status: str
    fail_code: str | None
    created_at: datetime
    submitted_at: datetime | None
    review_ready_at: datetime | None
    clip_count: int
    ready_clip_count: int
    draft_fact_count: int


@dataclass(frozen=True, slots=True)
class DogDetailView:
    dog: DogView
    coverage: Coverage
    checklist: ChecklistView
    sessions: tuple[SessionSummaryView, ...]
    clips: tuple[ClipView, ...]
    facts: tuple[FactView, ...]


def dog_view(row: Dog, media_urls: MediaUrls) -> DogView:
    return DogView(
        id=row.id,
        name=row.name,
        sex=row.sex,
        age_estimate=row.age_estimate,
        size=row.size,
        location=row.location,
        photo_url=media_urls.dog_photo(row.id, has_photo=bool(row.photo_path)),
        status=row.status,
        public_slug=row.public_slug,
        public_path=f"/d/{row.public_slug}" if row.public_slug else None,
        created_by=row.created_by,
        created_at=row.created_at,
        published_at=row.published_at,
        adopted_at=row.adopted_at,
    )


def load_dog(uow: UnitOfWork, principal: Principal, dog_id: str) -> Dog:
    """The dog in the member's org, else `not_found` (also for a `deleted` dog)."""
    dog = DogRepository(uow.session).get_in_org(principal.org_id, dog_id)
    if dog is None:
        raise NotFound()
    return dog


# ----------------------------------------------------------------- service


class DogService:
    def __init__(
        self,
        *,
        clock: Clock,
        settings: Settings,
        storage: Storage,
        media_urls: MediaUrls,
        coverage: CoverageService,
        publish: PublishService,
    ):
        self._clock = clock
        self._settings = settings
        self._storage = storage
        self._media = media_urls
        self._coverage = coverage
        self._publish = publish
        self._policy = ConfirmPolicy()

    # ---------------------------------------------------------------- create

    def create(
        self,
        uow: UnitOfWork,
        principal: Principal,
        *,
        name: str,
        sex: str,
        age_estimate: str,
        size: str,
        location: str | None = None,
    ) -> DogView:
        dog = DogRepository(uow.session).add(
            Dog(
                org_id=principal.org_id,
                created_by=principal.member_id,
                name=clean_text(name),
                sex=sex,
                age_estimate=clean_text(age_estimate),
                size=size,
                location=clean_text(location) or None,
                status="draft",
            )
        )
        return dog_view(dog, self._media)

    # ---------------------------------------------------------------- update

    def update(
        self, uow: UnitOfWork, principal: Principal, dog_id: str, patch: dict[str, Any]
    ) -> DogView:
        """Any subset of name, sex, age_estimate, size, location (`None` clears the
        location). Allowed in every status except `deleted`."""
        dog = load_dog(uow, principal, dog_id)
        for field in ("name", "age_estimate"):
            if field in patch:
                setattr(dog, field, clean_text(patch[field]))
        for field in ("sex", "size"):
            if field in patch:
                setattr(dog, field, patch[field])
        if "location" in patch:
            dog.location = clean_text(patch["location"]) or None
        uow.flush()
        return dog_view(dog, self._media)

    # ------------------------------------------------------------------ list

    def list_for_org(self, uow: UnitOfWork, principal: Principal) -> list[DogListItem]:
        repo = DogRepository(uow.session)
        dogs = repo.list_for_org(principal.org_id)
        ids = [d.id for d in dogs]
        short = self._coverage.short_for_dogs(uow, ids)
        counts = repo.counts_for_dogs(ids)
        return [
            DogListItem(dog_view(d, self._media), short[d.id], counts[d.id]) for d in dogs
        ]

    # ---------------------------------------------------------------- detail

    def get_detail(self, uow: UnitOfWork, principal: Principal, dog_id: str) -> DogDetailView:
        dog = load_dog(uow, principal, dog_id)
        repo = DogRepository(uow.session)
        coverage = self._coverage.for_dog(uow, dog.id)
        checklist = self._publish.checklist_for(uow, dog)

        sessions = tuple(
            SessionSummaryView(
                id=s.id,
                dog_id=s.dog_id,
                member_id=s.member_id,
                owner_name=owner,
                situations=tuple(s.situations),
                observed_on=s.observed_on,
                status=s.status,
                fail_code=s.fail_code,
                created_at=s.created_at,
                submitted_at=s.submitted_at,
                review_ready_at=s.review_ready_at,
                clip_count=counts.clip_count,
                ready_clip_count=counts.ready_clip_count,
                draft_fact_count=counts.draft_fact_count,
            )
            for s, owner, counts in repo.sessions_of_dog(dog.id)
        )
        clips = repo.live_clips_of_dog(dog.id)
        with_transcript = repo.clip_ids_with_transcript([c.id for c in clips])
        clip_views = tuple(self._clip_view(c, c.id in with_transcript) for c in clips)
        facts = self._fact_views(uow, principal, dog, clips, with_transcript)
        return DogDetailView(
            dog=dog_view(dog, self._media),
            coverage=coverage,
            checklist=checklist,
            sessions=sessions,
            clips=clip_views,
            facts=facts,
        )

    def _clip_view(self, clip: Clip, has_transcript: bool) -> ClipView:
        ready = clip.is_ready
        error = None
        if clip.status == "failed" and clip.fail_code:
            cause, retryable = _CLIP_ERRORS.get(
                clip.fail_code, ("We could not process this clip.", False)
            )
            error = ClipErrorView(cause, retryable)
        return ClipView(
            id=clip.id,
            session_id=clip.session_id,
            ordinal=clip.ordinal,
            original_filename=clip.original_filename,
            original_size_bytes=clip.original_size_bytes,
            duration_s=clip.duration_s,
            has_audio=clip.has_audio,
            status=clip.status,
            step=clip.step,
            fail_code=clip.fail_code,
            error=error,
            media_url=self._media.clip_media(clip.id) if ready else None,
            captions_url=(
                self._media.clip_captions(clip.id, has_transcript=has_transcript)
                if ready
                else None
            ),
            created_at=clip.created_at,
            ready_at=clip.ready_at,
        )

    def _fact_views(
        self,
        uow: UnitOfWork,
        principal: Principal,
        dog: Dog,
        clips: Sequence[Clip],
        with_transcript: set[str],
    ) -> tuple[FactView, ...]:
        repo = DogRepository(uow.session)
        facts = repo.review_facts_of_dog(dog.id)
        facts.sort(
            key=lambda f: (SITUATION_ORDER.index(f.situation), -f.observed_on.toordinal(), f.created_at)
        )
        clip_by_id = {c.id: c for c in clips}
        clip_pos = {c.id: i for i, c in enumerate(clips)}
        owners = repo.session_owners(f.session_id for f in facts if f.session_id)
        names = repo.member_names(f.confirmed_by for f in facts if f.confirmed_by)
        snapshots = repo.playback_snapshots(principal.member_id, [f.id for f in facts])
        actor = ActorInfo(
            principal.member_id, principal.org_id, principal.role, principal.consented
        )
        dog_info = DogInfo(dog.status, dog.people_check_at)
        views = []
        for fact in facts:
            rows = sorted(
                fact.evidence, key=lambda e: (clip_pos.get(e.clip_id, 10**6), e.start_s, e.id)
            )
            ctx = ConfirmContext(
                fact=FactInfo(
                    id=fact.id,
                    org_id=dog.org_id,
                    status=fact.status,
                    merged=fact.merged,
                    situation=fact.situation,
                    source=fact.source,
                    session_id=fact.session_id,
                    session_owner_id=owners.get(fact.session_id or ""),
                    flags=fact.flags or [],
                ),
                dog=dog_info,
                actor=actor,
                evidence=[EvidenceInfo(e.id, e.start_s, e.end_s) for e in rows],
                events=snapshots,
            )
            unplayed = set(missing_playback_evidence_ids(ctx))
            evidence = []
            for e in rows:
                clip = clip_by_id.get(e.clip_id)
                ready = clip is not None and clip.is_ready
                evidence.append(
                    EvidenceView(
                        id=e.id,
                        clip_id=e.clip_id,
                        start_s=e.start_s,
                        end_s=e.end_s,
                        played_by_me=e.id not in unplayed,
                        media_url=self._media.clip_media(e.clip_id) if ready else None,
                        captions_url=(
                            self._media.clip_captions(
                                e.clip_id, has_transcript=e.clip_id in with_transcript
                            )
                            if ready
                            else None
                        ),
                    )
                )
            length = clip_length(
                fact.source, [Range(e.start_s, e.end_s, e.clip_id) for e in rows]
            )
            blocked = self._policy.evaluate(ctx)
            confirmed = None
            if fact.status == "confirmed" and fact.confirmed_at and fact.confirmed_role:
                confirmed = ConfirmedView(
                    by_member_id=fact.confirmed_by or "",
                    by_name=names.get(fact.confirmed_by or "", ""),
                    role=fact.confirmed_role,
                    at=fact.confirmed_at,
                )
            views.append(
                FactView(
                    id=fact.id,
                    dog_id=fact.dog_id,
                    session_id=fact.session_id,
                    situation=fact.situation,
                    behavior=fact.behavior,
                    source=fact.source,
                    origin=fact.origin,
                    status=fact.status,
                    flags=tuple(
                        FlagView(
                            code=f.get("code", ""),
                            severity=f.get("severity", "warn"),
                            source=f.get("source", ""),
                            detail=f.get("detail", ""),
                        )
                        for f in (fact.flags or [])
                    ),
                    observed_on=fact.observed_on,
                    evidence=tuple(evidence),
                    clip_length=ClipLengthView(length.clip_count, length.seconds, length.label),
                    confirmed=confirmed,
                    created_by=fact.created_by,
                    can_confirm=blocked is None,
                    blocked_reason=blocked,
                )
            )
        return tuple(views)

    # ----------------------------------------------------------------- photo

    def set_photo(
        self,
        uow: UnitOfWork,
        principal: Principal,
        dog_id: str,
        image_bytes: bytes | None,
        filename: str,
    ) -> DogView:
        """Re-encode to JPEG (longest side `photo_max_side_px`), drop EXIF and GPS,
        store `dogs/{id}/photo.jpg` (01 section 4.5, CAP-1, NFR-5)."""
        dog = load_dog(uow, principal, dog_id)
        if image_bytes is None:
            raise ValidationFailed(
                details={"fields": [{"path": "body.photo", "problem": "required"}]}
            )
        if len(image_bytes) > self._settings.max_photo_bytes:
            raise FileTooLarge(
                "The photo is larger than 8 MiB.",
                details={"max_bytes": self._settings.max_photo_bytes},
            )
        jpeg = self._reencode(image_bytes, filename)
        key = f"dogs/{dog.id}/photo.jpg"
        tmp = self._storage.new_tmp_path()
        try:
            tmp.write_bytes(jpeg)
            self._storage.put_file(key, tmp)
        except (StorageError, OSError) as exc:
            raise StorageUnavailable() from exc
        finally:
            tmp.unlink(missing_ok=True)
        dog.photo_path = key
        uow.flush()
        return dog_view(dog, self._media)

    def _reencode(self, data: bytes, filename: str) -> bytes:
        from PIL import Image, ImageOps

        details = {"allowed": PHOTO_ALLOWED}
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        magics = _MAGIC.get(ext)
        if magics is None or not any(data.startswith(m) for m in magics):
            raise UnsupportedFileType(details=details)
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                img = ImageOps.exif_transpose(img)
                rgb = img.convert("RGB")
        except Exception as exc:  # bad bytes, truncated file, decompression bomb
            raise UnsupportedFileType(details=details) from exc
        side = self._settings.photo_max_side_px
        rgb.thumbnail((side, side), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        rgb.save(out, "JPEG", quality=85, optimize=True)  # no exif argument: tags are dropped
        return out.getvalue()
