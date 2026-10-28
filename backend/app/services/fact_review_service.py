"""FactReviewService (06 section 3.2): playback, confirm, edit, delete, add by hand.

Every method takes the request's `UnitOfWork` first and never commits: the caller
(the `uow` dependency, or a test) owns the transaction. Messages and guard order
follow 01 sections 5.8 to 5.12 and 02 section 3.4.

Methods other lanes may call:
- `get_view(uow, principal, fact_id)`: one `FactView` (hidden facts raise `NotFound`).
- `views_for_facts(uow, principal, fact_ids)`: `FactView`s in the given order,
  skipping facts that are deleted, unmerged, or of another org (S3 session detail).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from app.clock import Clock
from app.db.base import new_id
from app.db.uow import UnitOfWork
from app.domain.confirm_policy import (
    ActorInfo,
    ConfirmContext,
    ConfirmPolicy,
    DogInfo,
    EvidenceInfo,
    FactInfo,
    PlaybackSnapshot,
    missing_playback_evidence_ids,
)
from app.domain.ranges import Range, round_half_up, union_seconds
from app.domain.wording import BannedWordMatcher, behavior_problem, normalize_behavior
from app.errors import (
    ERROR_CLASSES,
    ForbiddenRole,
    InvalidState,
    NotFound,
    NotOwnSession,
    PlaybackRequired,
    PublishChecklistIncomplete,
    ValidationFailed,
)
from app.models import Fact, FactEvidence
from app.repositories.dogs import DogRepository
from app.repositories.facts import FactRepository, FactRow
from app.repositories.playback import PlaybackRepository
from app.services.evidence_validator import (
    EvidenceInput,
    EvidenceValidator,
    ValidEvidence,
)
from app.services.views import (
    ClipLengthView,
    ConfirmedView,
    EvidenceView,
    FactView,
    FlagView,
    MediaUrls,
    Principal,
)

PLAYBACK_END_TOL_S = 0.5
PLAYBACK_MIN_SHARE = 0.8
_EPS = 1e-6


@dataclass(frozen=True)
class FactPatch:
    """Fields the client sent. `None` means not sent."""

    situation: str | None = None
    behavior: str | None = None
    evidence: Sequence[EvidenceInput] | None = None


@dataclass(frozen=True)
class NewFact:
    situation: str
    behavior: str
    evidence: Sequence[EvidenceInput] = field(default_factory=tuple)
    observed_on: date | None = None


@dataclass(frozen=True)
class PlaybackResult:
    fact_id: str
    evidence_id: str
    completed_at: datetime
    all_ranges_played: bool


def _field_error(path: str, problem: str, limit: int | None = None) -> ValidationFailed:
    item: dict[str, object] = {"path": path, "problem": problem}
    if limit is not None:
        item["limit"] = limit
    return ValidationFailed(details={"fields": [item]})


def _checked_behavior(text: str) -> str:
    """NFC and trim, then the length and newline rules (01 section 2)."""
    problem = behavior_problem(text)
    if problem == "too_short":
        raise _field_error("body.behavior", "too_short", 3)
    if problem == "too_long":
        raise _field_error("body.behavior", "too_long", 280)
    if problem is not None:
        raise _field_error("body.behavior", "invalid_value")
    return normalize_behavior(text)


def clip_length(source: str, ranges: Sequence[Range]) -> ClipLengthView:
    """Fact clip length (02 section 4.3)."""
    clips = len({r.clip_id for r in ranges})
    seconds = max(1, round_half_up(union_seconds(ranges))) if ranges else 0
    if source == "staff_note" or not ranges:
        return ClipLengthView(clip_count=0, seconds=0, label="No clip")
    if source == "narration":
        return ClipLengthView(clip_count=clips, seconds=seconds, label=f"Narration only, {seconds} s")
    return ClipLengthView(
        clip_count=clips, seconds=seconds, label=f"{clips} clip{'s' if clips != 1 else ''}, {seconds} s"
    )


class FactReviewService:
    def __init__(
        self,
        *,
        clock: Clock,
        media_urls: MediaUrls,
        banned: BannedWordMatcher,
        validator: EvidenceValidator | None = None,
        policy: ConfirmPolicy | None = None,
    ) -> None:
        self._clock = clock
        self._media = media_urls
        self._banned = banned
        self._validator = validator or EvidenceValidator()
        self._policy = policy or ConfirmPolicy()

    # ------------------------------------------------------------------ reads

    def get_view(self, uow: UnitOfWork, principal: Principal, fact_id: str) -> FactView:
        repo = FactRepository(uow.session)
        return self._view(uow, principal, self._load(repo, principal, fact_id))

    def views_for_facts(
        self, uow: UnitOfWork, principal: Principal, fact_ids: Sequence[str]
    ) -> list[FactView]:
        repo = FactRepository(uow.session)
        views = []
        for fact_id in fact_ids:
            try:
                row = self._load(repo, principal, fact_id)
            except NotFound:
                continue
            views.append(self._view(uow, principal, row))
        return views

    def ensure_visible(self, uow: UnitOfWork, principal: Principal, fact_id: str) -> None:
        """Raise `not_found` unless the fact is visible to the member. The router runs
        this before body validation, so an id from another org is `not_found`
        whatever the body holds (I-21)."""
        self._load(FactRepository(uow.session), principal, fact_id)

    def ensure_dog_visible(self, uow: UnitOfWork, principal: Principal, dog_id: str) -> None:
        dog = DogRepository(uow.session).get_in_org(principal.org_id, dog_id)
        if dog is None:
            raise NotFound()

    # --------------------------------------------------------------- playback

    def record_playback(
        self,
        uow: UnitOfWork,
        principal: Principal,
        fact_id: str,
        evidence_id: str,
        position_s: float,
        watched_s: float,
    ) -> PlaybackResult:
        repo = FactRepository(uow.session)
        row = self._load(repo, principal, fact_id)
        self._require_owner_or_staff(principal, row)
        fact = row.fact
        if fact.status != "draft":
            raise InvalidState()
        evidence = next((e for e in fact.evidence if e.id == evidence_id), None)
        if evidence is None:
            raise NotFound()
        length = evidence.end_s - evidence.start_s
        if position_s < evidence.end_s - PLAYBACK_END_TOL_S - _EPS:
            raise _field_error("body.position_s", "range_not_completed")
        if watched_s < PLAYBACK_MIN_SHARE * length - _EPS:
            raise _field_error("body.watched_s", "range_not_completed")
        now = self._clock.now()
        playback = PlaybackRepository(uow.session)
        playback.upsert(
            fact_id=fact.id, evidence=evidence, member_id=principal.member_id,
            watched_s=watched_s, at=now,
        )
        played = self._played_ids(playback, fact, principal.member_id)
        return PlaybackResult(
            fact_id=fact.id,
            evidence_id=evidence.id,
            completed_at=now,
            all_ranges_played=all(e.id in played for e in fact.evidence),
        )

    # ---------------------------------------------------------------- confirm

    def confirm(
        self, uow: UnitOfWork, principal: Principal, fact_id: str, acknowledge_flags: bool = False
    ) -> FactView:
        repo = FactRepository(uow.session)
        row = self._load(repo, principal, fact_id)
        ctx = self._confirm_context(uow, principal, row, acknowledge_flags)
        failure = self._policy.evaluate(ctx)
        if failure is not None:
            self._raise_confirm_failure(failure, ctx)
        fact = row.fact
        fact.status = "confirmed"
        fact.confirmed_by = principal.member_id
        fact.confirmed_role = principal.role
        fact.confirmed_at = self._clock.now()
        repo.flush()
        return self._view(uow, principal, row)

    # ------------------------------------------------------------------- edit

    def edit(
        self, uow: UnitOfWork, principal: Principal, fact_id: str, patch: FactPatch
    ) -> FactView:
        repo = FactRepository(uow.session)
        row = self._load(repo, principal, fact_id)
        self._require_owner_or_staff(principal, row)
        fact = row.fact

        behavior = _checked_behavior(patch.behavior) if patch.behavior is not None else None
        situation = patch.situation
        behavior_changed = behavior is not None and behavior != fact.behavior
        situation_changed = situation is not None and situation != fact.situation

        keep: list[FactEvidence] = []
        new_rows: list[FactEvidence] = []
        evidence_changed = False
        if patch.evidence is not None:
            if not patch.evidence and fact.source in ("clip", "narration"):
                raise _field_error("body.evidence", "evidence_required")
            if patch.evidence and fact.source == "staff_note":
                raise _field_error("body.evidence", "invalid_value")
            current = {e.id: e for e in fact.evidence}
            fresh: list[EvidenceInput] = []
            for item in patch.evidence:
                existing = current.get(item.id) if item.id else None
                if (
                    existing is not None
                    and existing not in keep
                    and existing.clip_id == item.clip_id
                    and math.isclose(existing.start_s, round(item.start_s, 1), abs_tol=_EPS)
                    and math.isclose(existing.end_s, round(item.end_s, 1), abs_tol=_EPS)
                ):
                    keep.append(existing)
                else:
                    fresh.append(item)
            validated = self._validator.validate(repo, principal, fact.dog_id, fresh)
            new_rows = [self._evidence_row(v) for v in validated]
            removed = [e for e in fact.evidence if e not in keep]
            evidence_changed = bool(new_rows or removed)
            if evidence_changed:
                repo.replace_evidence(fact, removed, new_rows)

        if behavior_changed:
            fact.behavior = behavior  # type: ignore[assignment]
            fact.flags = [f.as_dict() for f in self._banned.check(fact.behavior)]
        if situation_changed:
            fact.situation = situation  # type: ignore[assignment]
        if behavior_changed or situation_changed or evidence_changed:
            if fact.origin == "ai_unchanged":
                fact.origin = "human_edited"
            if fact.status == "confirmed":
                fact.status = "draft"
                fact.confirmed_by = None
                fact.confirmed_role = None
                fact.confirmed_at = None
        repo.flush()
        return self._view(uow, principal, row)

    # ----------------------------------------------------------------- delete

    def delete(self, uow: UnitOfWork, principal: Principal, fact_id: str) -> None:
        repo = FactRepository(uow.session)
        row = self._load(repo, principal, fact_id)
        self._require_owner_or_staff(principal, row)
        fact = row.fact
        fact.status = "deleted"
        fact.deleted_at = self._clock.now()
        fact.deleted_by = principal.member_id
        fact.confirmed_by = None
        fact.confirmed_role = None
        fact.confirmed_at = None
        repo.delete_all_evidence_and_events(fact)
        repo.flush()

    # -------------------------------------------------------------------- add

    def add_manual(
        self, uow: UnitOfWork, principal: Principal, dog_id: str, data: NewFact
    ) -> FactView:
        if not principal.consented:
            from app.errors import ConsentRequired

            raise ConsentRequired()
        repo = FactRepository(uow.session)
        dog = DogRepository(uow.session).get_in_org(principal.org_id, dog_id)
        if dog is None:
            raise NotFound()
        behavior = _checked_behavior(data.behavior)
        validated = self._validator.validate(repo, principal, dog.id, list(data.evidence))
        today = self._clock.now().date()
        if validated:
            first = validated[0]
            session_id: str | None = first.session_id
            observed_on = first.session_observed_on
            source = "clip"
        else:
            session_id = None
            observed_on = data.observed_on or today
            source = "staff_note"
        fact = Fact(
            id=new_id(),
            dog_id=dog.id,
            session_id=session_id,
            created_by=principal.member_id,
            situation=data.situation,
            behavior=behavior,
            source=source,
            origin="human_added",
            status="draft",
            merged=True,
            flags=[f.as_dict() for f in self._banned.check(behavior)],
            observed_on=observed_on,
        )
        for v in validated:
            fact.evidence.append(self._evidence_row(v))
        repo.add_fact(fact)
        return self._view(uow, principal, repo.get_fact_row(fact.id, principal.org_id))  # type: ignore[arg-type]

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _evidence_row(v: ValidEvidence) -> FactEvidence:
        return FactEvidence(id=new_id(), clip_id=v.clip_id, start_s=v.start_s, end_s=v.end_s)

    @staticmethod
    def _load(repo: FactRepository, principal: Principal, fact_id: str) -> FactRow:
        """The fact in the member's org. Deleted facts, `merged=0` facts, and facts of
        a deleted dog are `not_found` everywhere (01 section 2, 06 M8)."""
        row = repo.get_fact_row(fact_id, principal.org_id)
        if (
            row is None
            or row.fact.status == "deleted"
            or not row.fact.merged
            or row.dog.status == "deleted"
        ):
            raise NotFound()
        return row

    @staticmethod
    def _require_owner_or_staff(principal: Principal, row: FactRow) -> None:
        """Staff may act on any fact. A volunteer needs the fact's session; for a
        session-less staff note the author counts as the owner."""
        if principal.is_staff:
            return
        owner = row.session_owner_id if row.fact.session_id else row.fact.created_by
        if owner != principal.member_id:
            raise NotOwnSession()

    @staticmethod
    def _played_ids(playback: PlaybackRepository, fact: Fact, member_id: str) -> set[str]:
        by_evidence = {
            e.evidence_id: e for e in playback.events_of_member([fact.id], member_id)
        }
        played = set()
        for ev in fact.evidence:
            event = by_evidence.get(ev.id)
            if (
                event is not None
                and math.isclose(event.start_s, ev.start_s, abs_tol=_EPS)
                and math.isclose(event.end_s, ev.end_s, abs_tol=_EPS)
            ):
                played.add(ev.id)
        return played

    def _confirm_context(
        self, uow: UnitOfWork, principal: Principal, row: FactRow, acknowledge_flags: bool
    ) -> ConfirmContext:
        fact, dog = row.fact, row.dog
        evidence = sorted(fact.evidence, key=lambda e: (e.start_s, e.end_s, e.id))
        events = PlaybackRepository(uow.session).events_of_member([fact.id], principal.member_id)
        return ConfirmContext(
            fact=FactInfo(
                id=fact.id,
                org_id=dog.org_id,
                status=fact.status,
                merged=fact.merged,
                situation=fact.situation,
                source=fact.source,
                session_id=fact.session_id,
                session_owner_id=row.session_owner_id,
                flags=tuple(fact.flags or ()),
            ),
            dog=DogInfo(status=dog.status, people_check_at=dog.people_check_at),
            actor=ActorInfo(
                id=principal.member_id,
                org_id=principal.org_id,
                role=principal.role,
                consent_accepted=principal.consented,
            ),
            evidence=tuple(EvidenceInfo(e.id, e.start_s, e.end_s) for e in evidence),
            events=tuple(
                PlaybackSnapshot(e.evidence_id, e.member_id, e.start_s, e.end_s) for e in events
            ),
            acknowledge_flags=acknowledge_flags,
        )

    @staticmethod
    def _raise_confirm_failure(failure: str, ctx: ConfirmContext) -> None:
        if failure == "playback_required":
            raise PlaybackRequired(
                details={"missing_evidence_ids": list(missing_playback_evidence_ids(ctx))}
            )
        if failure == "publish_checklist_incomplete":
            raise PublishChecklistIncomplete(details={"missing": ["people_check"]})
        if failure == "forbidden_role":
            raise ForbiddenRole()
        raise ERROR_CLASSES[failure]()

    def _view(self, uow: UnitOfWork, principal: Principal, row: FactRow) -> FactView:
        repo = FactRepository(uow.session)
        fact, dog = row.fact, row.dog
        evidence = sorted(fact.evidence, key=lambda e: (e.start_s, e.end_s, e.id))
        clips = repo.clips_by_id(e.clip_id for e in evidence)
        with_transcript = repo.clip_ids_with_transcript(clips)
        playback = PlaybackRepository(uow.session)
        played = self._played_ids(playback, fact, principal.member_id)
        evidence_views = []
        for e in evidence:
            clip = clips.get(e.clip_id)
            ready = clip is not None and clip.is_ready
            evidence_views.append(
                EvidenceView(
                    id=e.id,
                    clip_id=e.clip_id,
                    start_s=e.start_s,
                    end_s=e.end_s,
                    played_by_me=e.id in played,
                    media_url=self._media.clip_media(e.clip_id) if ready else None,
                    captions_url=(
                        self._media.clip_captions(e.clip_id, has_transcript=e.clip_id in with_transcript)
                        if ready
                        else None
                    ),
                )
            )
        # `can_confirm` assumes the flag acknowledgement is given: the UI shows the
        # tick box itself from `flags` (01 section 5.9).
        ctx = self._confirm_context(uow, principal, row, acknowledge_flags=True)
        blocked = self._policy.evaluate(ctx)
        names = repo.member_names([fact.confirmed_by])
        confirmed = None
        if fact.status == "confirmed" and fact.confirmed_at is not None and fact.confirmed_by:
            confirmed = ConfirmedView(
                by_member_id=fact.confirmed_by,
                by_name=names.get(fact.confirmed_by, ""),
                role=fact.confirmed_role or "",
                at=fact.confirmed_at,
            )
        return FactView(
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
                for f in (fact.flags or ())
            ),
            observed_on=fact.observed_on,
            evidence=tuple(evidence_views),
            clip_length=clip_length(
                fact.source, [Range(e.start_s, e.end_s, e.clip_id) for e in evidence]
            ),
            confirmed=confirmed,
            created_by=fact.created_by,
            can_confirm=blocked is None,
            blocked_reason=blocked,
        )
