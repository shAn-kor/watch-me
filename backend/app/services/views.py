"""Shared view objects (06 sections 1 and 3.5; fields per 01 section 2).

The api layer never sees ORM rows: services return these frozen dataclasses.
Phase 0 freezes the shapes shared across lanes (`Principal`, `MediaUrls`,
`FactView`, the job views). Assemblers that need ConfirmPolicy and the
repositories (`FactView.can_confirm`, `blocked_reason`) are written by the
lanes that own them (S4 for the creator side, S5 for the public side).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.domain.enums import Role

# ----------------------------------------------------------------- principal


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated member of a request (06 section 3.5)."""

    member_id: str
    org_id: str
    role: str  # "staff" | "volunteer"
    consented: bool
    sid: str  # random session id from the cookie; CSRF token input

    @property
    def is_staff(self) -> bool:
        return self.role == Role.STAFF


# ---------------------------------------------------------------- media urls


class MediaUrls:
    """Builds `media_url` and `captions_url` for creator and public facts alike (D7),
    so no client ever builds a URL from a clip id.

    Layout (01 section 7): `/media/{clip_id}.mp4` (playback) and `/media/{clip_id}.vtt`
    (captions), `/media/dogs/{dog_id}/photo.jpg` for photos.
    """

    def __init__(self, prefix: str = "/media"):
        self._prefix = prefix.rstrip("/")

    def clip_media(self, clip_id: str) -> str:
        return f"{self._prefix}/{clip_id}.mp4"

    def clip_captions(self, clip_id: str, *, has_transcript: bool) -> str | None:
        """`None` when the clip has no transcript rows."""
        return f"{self._prefix}/{clip_id}.vtt" if has_transcript else None

    def dog_photo(self, dog_id: str, *, has_photo: bool = True) -> str | None:
        return f"{self._prefix}/dogs/{dog_id}/photo.jpg" if has_photo else None


# ---------------------------------------------------------------- fact views


@dataclass(frozen=True, slots=True)
class FlagView:
    code: str  # banned_word | trait_claim | check_unavailable
    severity: str  # warn | info
    source: str  # rules | model | system
    detail: str


@dataclass(frozen=True, slots=True)
class EvidenceView:
    id: str
    clip_id: str
    start_s: float
    end_s: float
    played_by_me: bool
    media_url: str | None
    captions_url: str | None


@dataclass(frozen=True, slots=True)
class ClipLengthView:
    """Fact clip length (02 section 4.3, single implementation in coverage_service)."""

    clip_count: int
    seconds: int
    label: str  # e.g. "1 clip, 9 s"


@dataclass(frozen=True, slots=True)
class ConfirmedView:
    by_member_id: str
    by_name: str
    role: str
    at: datetime


@dataclass(frozen=True, slots=True)
class FactView:
    """Creator view of a fact (01 section 2 `Fact`). `merged=0` and `deleted` facts
    are never turned into a view."""

    id: str
    dog_id: str
    session_id: str | None
    situation: str
    behavior: str
    source: str
    origin: str
    status: str
    flags: tuple[FlagView, ...]
    observed_on: date
    evidence: tuple[EvidenceView, ...]
    clip_length: ClipLengthView
    confirmed: ConfirmedView | None
    created_by: str | None
    can_confirm: bool
    blocked_reason: str | None  # first failing confirm guard code, None when allowed


# ----------------------------------------------------------------- clip views


@dataclass(frozen=True, slots=True)
class ClipErrorView:
    cause: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class ClipView:
    """A creator `Clip` (01 section 2); also what the dog detail lists."""


    id: str
    session_id: str
    ordinal: int
    original_filename: str
    original_size_bytes: int
    duration_s: float
    has_audio: bool
    status: str
    step: str | None
    fail_code: str | None
    error: ClipErrorView | None
    media_url: str | None
    captions_url: str | None
    created_at: datetime
    ready_at: datetime | None


# ----------------------------------------------------------------- job views


@dataclass(frozen=True, slots=True)
class JobSpec:
    """A job to enqueue (`JobQueue.enqueue`). Handlers return these as `next_jobs`.

    `max_attempts=None` lets the queue pick the per-type default (02 section 2.11:
    2 pipeline, 8 purge, 1 retention_sweep)."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    dog_id: str | None = None
    session_id: str | None = None
    clip_id: str | None = None
    dedupe_key: str | None = None
    max_attempts: int | None = None
    run_after: datetime | None = None


@dataclass(frozen=True, slots=True)
class JobView:
    """A claimed job as seen by the runner and the handlers (no ORM row)."""

    id: int
    type: str
    payload: dict[str, Any]
    dog_id: str | None
    session_id: str | None
    clip_id: str | None
    dedupe_key: str | None
    attempts: int
    max_attempts: int
