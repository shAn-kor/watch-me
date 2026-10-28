"""SessionService: create, read, submit, retry-merge, and the hooks the pipeline
calls (06 section 4, 01 sections 5.1 to 5.4a).

Routes pass the request `uow`; every method then works inside that transaction and
the api commits it. The pipeline hooks (`enqueue_merge`, `on_clip_terminal`,
`mark_review_ready`, `mark_failed`) take an optional `uow` and open their own
transaction when it is `None`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.clock import Clock
from app.config import Settings
from app.db.base import new_id
from app.db.uow import UnitOfWork, UowFactory
from app.domain.confirm_policy import (
    ActorInfo,
    ConfirmContext,
    ConfirmPolicy,
    DogInfo,
    EvidenceInfo,
    FactInfo,
    PlaybackSnapshot,
)
from app.domain.enums import Situation
from app.domain.ranges import Range, round_half_up, union_seconds
from app.errors import (
    ConsentRequired,
    InvalidState,
    NotFound,
    NotOwnSession,
    ValidationFailed,
)
from app.models import Clip, Dog, Fact, FilmingSession
from app.repositories import jobs as jobs_repo
from app.repositories.sessions import SessionRepository
from app.services.job_queue import JobQueue
from app.services.views import (
    ClipLengthView,
    ConfirmedView,
    EvidenceView,
    FactView,
    FlagView,
    JobSpec,
    MediaUrls,
    Principal,
)

MAX_SITUATIONS = 8
OBSERVED_ON_SLACK_DAYS = 1
TERMINAL_CLIP_STATUSES = frozenset({"ready", "failed"})

CLIP_ERROR_CAUSES: dict[str, tuple[str, bool]] = {
    "unsupported_file": ("This video format could not be read.", False),
    "too_long": ("The clip is longer than 2 minutes.", False),
    "transcode_failed": ("We could not convert this clip.", True),
    "ai_failed": ("The AI step did not finish.", True),
    "ai_invalid_output": ("The AI answer was not usable.", True),
}


# ------------------------------------------------------------------- views


@dataclass(frozen=True, slots=True)
class SessionView:
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


@dataclass(frozen=True, slots=True)
class ClipErrorView:
    cause: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class ClipView:
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


@dataclass(frozen=True, slots=True)
class ProgressView:
    clips_total: int
    clips_ready: int
    clips_failed: int


@dataclass(frozen=True, slots=True)
class SessionBundle:
    session: SessionView
    clips: tuple[ClipView, ...]
    facts: tuple[FactView, ...] | None
    progress: ProgressView


def build_clip_view(clip: Clip, media_urls: MediaUrls, *, has_transcript: bool) -> ClipView:
    """The creator view of a clip. `fail_detail` is never exposed."""
    ready = clip.status == "ready"
    error = None
    if clip.status == "failed" and clip.fail_code:
        cause, retryable = CLIP_ERROR_CAUSES.get(
            clip.fail_code, ("We could not process this clip.", False)
        )
        error = ClipErrorView(cause=cause, retryable=retryable)
    return ClipView(
        id=clip.id,
        session_id=clip.session_id,
        ordinal=clip.ordinal,
        original_filename=clip.original_filename,
        original_size_bytes=clip.original_size_bytes,
        duration_s=clip.duration_s,
        has_audio=bool(clip.has_audio),
        status=clip.status,
        step=clip.step,
        fail_code=clip.fail_code,
        error=error,
        media_url=media_urls.clip_media(clip.id) if ready else None,
        captions_url=(
            media_urls.clip_captions(clip.id, has_transcript=has_transcript) if ready else None
        ),
        created_at=clip.created_at,
        ready_at=clip.ready_at,
    )


# ----------------------------------------------------------------- service


class SessionService:
    def __init__(
        self,
        *,
        uow_factory: UowFactory,
        clock: Clock,
        settings: Settings,
        job_queue: JobQueue,
        media_urls: MediaUrls,
    ):
        self._uow_factory = uow_factory
        self._clock = clock
        self._settings = settings
        self._jobs = job_queue
        self._media = media_urls
        self._policy = ConfirmPolicy()

    # ------------------------------------------------------------ plumbing

    @contextmanager
    def _scope(self, uow: UnitOfWork | None) -> Iterator[UnitOfWork]:
        if uow is not None:
            yield uow
            return
        with self._uow_factory() as own:
            yield own
            own.commit()

    def _load_for_member(
        self, repo: SessionRepository, who: Principal, session_id: str
    ) -> tuple[FilmingSession, Dog]:
        """The session when it belongs to the member's org and its dog is not
        deleted; otherwise `not_found` (a deleted dog is hidden)."""
        found = repo.session_with_dog(session_id, who.org_id)
        if found is None or found[1].status == "deleted":
            raise NotFound()
        return found

    @staticmethod
    def _check_owner(who: Principal, sess: FilmingSession) -> None:
        if not who.is_staff and sess.member_id != who.member_id:
            raise NotOwnSession()

    def _view(self, sess: FilmingSession, names: dict[str, str]) -> SessionView:
        return SessionView(
            id=sess.id,
            dog_id=sess.dog_id,
            member_id=sess.member_id,
            owner_name=names.get(sess.member_id, ""),
            situations=tuple(sess.situations),
            observed_on=sess.observed_on,
            status=sess.status,
            fail_code=sess.fail_code,
            created_at=sess.created_at,
            submitted_at=sess.submitted_at,
            review_ready_at=sess.review_ready_at,
        )

    def session_view(self, repo: SessionRepository, sess: FilmingSession) -> SessionView:
        return self._view(sess, repo.member_names([sess.member_id]))

    # -------------------------------------------------------------- create

    def create(
        self,
        who: Principal,
        dog_id: str,
        *,
        situations: list[str],
        observed_on: date | None,
        capture_rules_ack: bool,
        uow: UnitOfWork,
    ) -> SessionView:
        if not who.consented:
            raise ConsentRequired()
        repo = SessionRepository(uow.session)
        dog = repo.dog_in_org(dog_id, who.org_id)
        if dog is None or dog.status == "deleted":
            raise NotFound()
        if dog.status != "draft":
            raise InvalidState(details={"dog_status": dog.status})
        fields: list[dict[str, str]] = []
        if capture_rules_ack is not True:
            fields.append({"field": "capture_rules_ack", "reason": "must_be_true"})
        valid = {s.value for s in Situation}
        if not 1 <= len(situations) <= MAX_SITUATIONS:
            fields.append({"field": "situations", "reason": "count"})
        elif len(set(situations)) != len(situations):
            fields.append({"field": "situations", "reason": "duplicate"})
        elif any(s not in valid for s in situations):
            fields.append({"field": "situations", "reason": "unknown_code"})
        now = self._clock.now()
        today = now.date()
        if observed_on is None:
            observed_on = today
        elif observed_on > today + timedelta(days=OBSERVED_ON_SLACK_DAYS):
            fields.append({"field": "observed_on", "reason": "in_the_future"})
        if fields:
            raise ValidationFailed(details={"fields": fields})
        row = repo.add_session(
            id=new_id(),
            dog_id=dog.id,
            member_id=who.member_id,
            situations=situations,
            observed_on=observed_on,
            rules_ack_at=now,
            created_at=now,
        )
        return self.session_view(repo, row)

    # ----------------------------------------------------------------- get

    def get(
        self,
        who: Principal,
        session_id: str,
        *,
        include_facts: bool = True,
        uow: UnitOfWork,
    ) -> SessionBundle:
        repo = SessionRepository(uow.session)
        sess, dog = self._load_for_member(repo, who, session_id)
        clips = repo.live_clips(sess.id)
        with_transcript = repo.clip_ids_with_transcript([c.id for c in clips])
        clip_views = tuple(
            build_clip_view(c, self._media, has_transcript=c.id in with_transcript)
            for c in clips
        )
        facts = self._fact_views(repo, who, sess, dog, clips) if include_facts else None
        progress = ProgressView(
            clips_total=len(clips),
            clips_ready=sum(c.status == "ready" for c in clips),
            clips_failed=sum(c.status == "failed" for c in clips),
        )
        return SessionBundle(
            session=self.session_view(repo, sess),
            clips=clip_views,
            facts=facts,
            progress=progress,
        )

    def _fact_views(
        self,
        repo: SessionRepository,
        who: Principal,
        sess: FilmingSession,
        dog: Dog,
        clips: list[Clip],
    ) -> tuple[FactView, ...]:
        facts = repo.visible_facts(sess.id)
        ordinals = {c.id: c.ordinal for c in clips}
        evidence_ids = [e.id for f in facts for e in f.evidence]
        events = repo.playback_for(who.member_id, evidence_ids)
        played = {(e.evidence_id) for e in events}
        clip_ids = {e.clip_id for f in facts for e in f.evidence}
        with_transcript = repo.clip_ids_with_transcript(sorted(clip_ids))
        names = repo.member_names(f.confirmed_by for f in facts if f.confirmed_by)
        snapshots = [
            PlaybackSnapshot(
                evidence_id=e.evidence_id,
                member_id=e.member_id,
                start_s=e.start_s,
                end_s=e.end_s,
            )
            for e in events
        ]
        actor = ActorInfo(
            id=who.member_id,
            org_id=who.org_id,
            role=who.role,
            consent_accepted=who.consented,
        )
        dog_info = DogInfo(status=dog.status, people_check_at=dog.people_check_at)

        def sort_key(f: Fact) -> tuple[int, float, datetime]:
            if not f.evidence:
                return (99, 0.0, f.created_at)
            first = min(
                f.evidence,
                key=lambda e: (ordinals.get(e.clip_id, 98), e.start_s),
            )
            return (ordinals.get(first.clip_id, 98), first.start_s, f.created_at)

        views = []
        for f in sorted(facts, key=sort_key):
            ctx = ConfirmContext(
                fact=FactInfo(
                    id=f.id,
                    org_id=dog.org_id,
                    status=f.status,
                    merged=bool(f.merged),
                    situation=f.situation,
                    source=f.source,
                    session_id=f.session_id,
                    session_owner_id=sess.member_id,
                    flags=tuple(f.flags or ()),
                ),
                dog=dog_info,
                actor=actor,
                evidence=tuple(
                    EvidenceInfo(id=e.id, start_s=e.start_s, end_s=e.end_s)
                    for e in f.evidence
                ),
                events=snapshots,
            )
            blocked = self._policy.evaluate(ctx)
            views.append(
                FactView(
                    id=f.id,
                    dog_id=f.dog_id,
                    session_id=f.session_id,
                    situation=f.situation,
                    behavior=f.behavior,
                    source=f.source,
                    origin=f.origin,
                    status=f.status,
                    flags=tuple(
                        FlagView(
                            code=str(x.get("code", "")),
                            severity=str(x.get("severity", "warn")),
                            source=str(x.get("source", "rules")),
                            detail=str(x.get("detail", "")),
                        )
                        for x in (f.flags or ())
                    ),
                    observed_on=f.observed_on,
                    evidence=tuple(
                        EvidenceView(
                            id=e.id,
                            clip_id=e.clip_id,
                            start_s=e.start_s,
                            end_s=e.end_s,
                            played_by_me=e.id in played,
                            media_url=self._media.clip_media(e.clip_id),
                            captions_url=self._media.clip_captions(
                                e.clip_id, has_transcript=e.clip_id in with_transcript
                            ),
                        )
                        for e in f.evidence
                    ),
                    clip_length=self._clip_length(f),
                    confirmed=(
                        ConfirmedView(
                            by_member_id=f.confirmed_by,
                            by_name=names.get(f.confirmed_by, ""),
                            role=f.confirmed_role,
                            at=f.confirmed_at,
                        )
                        if f.status == "confirmed" and f.confirmed_by
                        else None
                    ),
                    created_by=f.created_by,
                    can_confirm=blocked is None,
                    blocked_reason=blocked,
                )
            )
        return tuple(views)

    @staticmethod
    def _clip_length(fact: Fact) -> ClipLengthView:
        """02 section 4.3: union per clip, at least 1 s, .5 rounds up."""
        ranges = [Range(e.start_s, e.end_s, e.clip_id) for e in fact.evidence]
        count = len({e.clip_id for e in fact.evidence})
        seconds = max(1, round_half_up(union_seconds(ranges))) if ranges else 0
        label = f"{count} clip{'s' if count != 1 else ''}, {seconds} s"
        return ClipLengthView(clip_count=count, seconds=seconds, label=label)

    # -------------------------------------------------------------- submit

    def submit(self, who: Principal, session_id: str, *, uow: UnitOfWork) -> SessionView:
        if not who.consented:
            raise ConsentRequired()
        repo = SessionRepository(uow.session)
        sess, _dog = self._load_for_member(repo, who, session_id)
        self._check_owner(who, sess)
        if sess.status != "open" or not repo.live_clips(sess.id):
            raise InvalidState()
        sess.status = "processing"
        sess.submitted_at = self._clock.now()
        sess.review_ready_at = None
        self._evaluate(repo, sess, uow)
        return self.session_view(repo, sess)

    # --------------------------------------------------------- retry-merge

    def retry_merge(self, who: Principal, session_id: str, *, uow: UnitOfWork) -> SessionView:
        if not who.consented:
            raise ConsentRequired()
        repo = SessionRepository(uow.session)
        sess, _dog = self._load_for_member(repo, who, session_id)
        self._check_owner(who, sess)
        if sess.status == "processing":
            live = jobs_repo.find_live_by_dedupe(uow.session, self._merge_key(sess.id))
            if live is None:
                raise InvalidState()
            return self.session_view(repo, sess)  # idempotent repeat
        if sess.status != "failed" or sess.fail_code != "merge_failed":
            raise InvalidState()
        sess.status = "processing"
        sess.fail_code = None
        self.enqueue_merge(sess.id, uow=uow)
        return self.session_view(repo, sess)

    # ------------------------------------------------- hooks for pipeline

    @staticmethod
    def _merge_key(session_id: str) -> str:
        return f"merge:{session_id}"

    def enqueue_merge(self, session_id: str, *, uow: UnitOfWork | None = None) -> int | None:
        """Enqueue the session `merge` job (dedupe `merge:{id}`) and clear
        `review_ready_at`. Payload: `{"session_id"}`."""
        with self._scope(uow) as unit:
            sess = unit.session.get(FilmingSession, session_id)
            if sess is None:
                return None
            sess.review_ready_at = None
            return self._jobs.enqueue(
                JobSpec(
                    type="merge",
                    payload={"session_id": sess.id},
                    dog_id=sess.dog_id,
                    session_id=sess.id,
                    dedupe_key=self._merge_key(sess.id),
                ),
                uow=unit,
            )

    def on_clip_terminal(self, session_id: str, *, uow: UnitOfWork | None = None) -> None:
        """Called when a clip reaches `ready` or `failed` (or is deleted): when the
        session is `processing` and every live clip is terminal, enqueue the merge,
        or fail the session with `no_usable_clip` when no clip is ready."""
        with self._scope(uow) as unit:
            repo = SessionRepository(unit.session)
            sess = repo.get_session(session_id)
            if sess is None:
                return
            self._evaluate(repo, sess, unit)

    def _evaluate(self, repo: SessionRepository, sess: FilmingSession, uow: UnitOfWork) -> None:
        if sess.status != "processing":
            return
        clips = repo.live_clips(sess.id)
        if any(c.status not in TERMINAL_CLIP_STATUSES for c in clips):
            return
        if any(c.status == "ready" for c in clips):
            self.enqueue_merge(sess.id, uow=uow)
        else:
            sess.status = "failed"
            sess.fail_code = "no_usable_clip"
            sess.review_ready_at = None

    def mark_review_ready(self, session_id: str, *, uow: UnitOfWork | None = None) -> None:
        """The only writer of `review_ready_at` (I-22)."""
        with self._scope(uow) as unit:
            sess = unit.session.get(FilmingSession, session_id)
            if sess is None or sess.status != "processing":
                return
            sess.status = "review"
            sess.fail_code = None
            sess.review_ready_at = self._clock.now()

    def mark_failed(
        self, session_id: str, fail_code: str, *, uow: UnitOfWork | None = None
    ) -> None:
        with self._scope(uow) as unit:
            sess = unit.session.get(FilmingSession, session_id)
            if sess is None:
                return
            sess.status = "failed"
            sess.fail_code = fail_code
            sess.review_ready_at = None

    # ------------------------------------------------------------- helpers

    def reopen_for_retry(self, sess: FilmingSession) -> None:
        """A clip retry puts a `review` or `failed` session back to `processing`."""
        if sess.status in ("review", "failed"):
            sess.status = "processing"
            sess.fail_code = None
            sess.review_ready_at = None


__all__: list[Any] = [
    "ClipErrorView",
    "ClipView",
    "ProgressView",
    "SessionBundle",
    "SessionService",
    "SessionView",
    "build_clip_view",
]
