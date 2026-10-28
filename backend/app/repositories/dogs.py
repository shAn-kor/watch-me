"""SQL for dogs and the dog-scope reads of the S2 services (02 sections 2.3, 4.1, 6.1).

No business rules: services decide. Queries on other tables (sessions, clips, facts,
playback, jobs) live here with the name of the question they answer; the lead
consolidates them into the per-table repositories later.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.domain.confirm_policy import PlaybackSnapshot
from app.domain.coverage import CoverageClip, CoverageFact
from app.domain.ranges import Range
from app.models import (
    Clip,
    Dog,
    Fact,
    FilmingSession,
    Job,
    Member,
    PlaybackEvent,
    TranscriptSegment,
)

DOG_LIST_LIMIT = 200


@dataclass(frozen=True, slots=True)
class DogCounts:
    draft_facts: int = 0
    confirmed_facts: int = 0
    sessions_in_review: int = 0
    clips: int = 0


@dataclass(frozen=True, slots=True)
class SessionCounts:
    clip_count: int = 0
    ready_clip_count: int = 0
    draft_fact_count: int = 0


class DogRepository:
    def __init__(self, session: Session):
        self._s = session

    # ------------------------------------------------------------------ dogs

    def get_in_org(self, org_id: str, dog_id: str) -> Dog | None:
        """The dog, or None when unknown, in another org, or `deleted` (hidden)."""
        dog = self._s.get(Dog, dog_id)
        if dog is None or dog.org_id != org_id or dog.status == "deleted":
            return None
        return dog

    def list_for_org(self, org_id: str) -> list[Dog]:
        return list(
            self._s.scalars(
                select(Dog)
                .where(Dog.org_id == org_id, Dog.status != "deleted")
                .order_by(Dog.created_at.desc(), Dog.id.desc())
                .limit(DOG_LIST_LIMIT)
            )
        )

    def add(self, dog: Dog) -> Dog:
        self._s.add(dog)
        self._s.flush()
        return dog

    def slug_exists(self, slug: str) -> bool:
        return (
            self._s.scalar(select(func.count()).select_from(Dog).where(Dog.public_slug == slug))
            or 0
        ) > 0

    def member_names(self, member_ids: Iterable[str]) -> dict[str, str]:
        ids = {m for m in member_ids if m}
        if not ids:
            return {}
        rows = self._s.execute(
            select(Member.id, Member.display_name).where(Member.id.in_(ids))
        )
        return {mid: name for mid, name in rows}

    # ---------------------------------------------------------------- counts

    def confirmed_fact_count(self, dog_id: str) -> int:
        """Facts that can be published: `confirmed` and `merged` (02 D2)."""
        return (
            self._s.scalar(
                select(func.count())
                .select_from(Fact)
                .where(Fact.dog_id == dog_id, Fact.status == "confirmed", Fact.merged.is_(True))
            )
            or 0
        )

    def counts_for_dogs(self, dog_ids: Sequence[str]) -> dict[str, DogCounts]:
        if not dog_ids:
            return {}
        fact_rows = self._s.execute(
            select(Fact.dog_id, Fact.status, func.count())
            .where(
                Fact.dog_id.in_(dog_ids),
                Fact.status.in_(("draft", "confirmed")),
                Fact.merged.is_(True),
            )
            .group_by(Fact.dog_id, Fact.status)
        )
        facts: dict[tuple[str, str], int] = {(d, s): n for d, s, n in fact_rows}
        review = dict(
            self._s.execute(
                select(FilmingSession.dog_id, func.count())
                .where(FilmingSession.dog_id.in_(dog_ids), FilmingSession.status == "review")
                .group_by(FilmingSession.dog_id)
            ).all()
        )
        clips = dict(
            self._s.execute(
                select(Clip.dog_id, func.count())
                .where(Clip.dog_id.in_(dog_ids), Clip.deleted_at.is_(None))
                .group_by(Clip.dog_id)
            ).all()
        )
        return {
            d: DogCounts(
                draft_facts=facts.get((d, "draft"), 0),
                confirmed_facts=facts.get((d, "confirmed"), 0),
                sessions_in_review=review.get(d, 0),
                clips=clips.get(d, 0),
            )
            for d in dog_ids
        }

    # -------------------------------------------------------------- coverage

    def coverage_inputs(
        self, dog_ids: Sequence[str]
    ) -> dict[str, tuple[list[CoverageFact], list[CoverageClip]]]:
        """Plain inputs of `domain.coverage.compute_coverage` per dog (02 section 4.1):
        confirmed `clip` facts with their evidence, and the dog's live clips."""
        out: dict[str, tuple[list[CoverageFact], list[CoverageClip]]] = {
            d: ([], []) for d in dog_ids
        }
        if not dog_ids:
            return out
        facts = self._s.scalars(
            select(Fact)
            .options(selectinload(Fact.evidence))
            .where(
                Fact.dog_id.in_(dog_ids),
                Fact.status == "confirmed",
                Fact.source == "clip",
                Fact.merged.is_(True),
            )
        )
        for fact in facts:
            out[fact.dog_id][0].append(
                CoverageFact(
                    situation=fact.situation,
                    source=fact.source,
                    status=fact.status,
                    evidence=tuple(Range(e.start_s, e.end_s, e.clip_id) for e in fact.evidence),
                    confirmed_role=fact.confirmed_role,
                )
            )
        clips = self._s.execute(
            select(Clip.dog_id, Clip.id, Clip.duration_s, Clip.status).where(
                Clip.dog_id.in_(dog_ids), Clip.deleted_at.is_(None)
            )
        )
        for dog_id, clip_id, duration_s, status in clips:
            out[dog_id][1].append(CoverageClip(clip_id, duration_s, status))
        return out

    # ----------------------------------------------------------- dog detail

    def sessions_of_dog(self, dog_id: str) -> list[tuple[FilmingSession, str, SessionCounts]]:
        """Sessions oldest first, each with the owner's display name and counts."""
        sessions = list(
            self._s.scalars(
                select(FilmingSession)
                .where(FilmingSession.dog_id == dog_id)
                .order_by(FilmingSession.created_at, FilmingSession.id)
            )
        )
        if not sessions:
            return []
        ids = [s.id for s in sessions]
        clip_rows = self._s.execute(
            select(Clip.session_id, Clip.status, func.count())
            .where(Clip.session_id.in_(ids), Clip.deleted_at.is_(None))
            .group_by(Clip.session_id, Clip.status)
        )
        clip_count: dict[str, int] = defaultdict(int)
        ready_count: dict[str, int] = defaultdict(int)
        for sid, status, n in clip_rows:
            clip_count[sid] += n
            if status == "ready":
                ready_count[sid] += n
        draft = dict(
            self._s.execute(
                select(Fact.session_id, func.count())
                .where(Fact.session_id.in_(ids), Fact.status == "draft", Fact.merged.is_(True))
                .group_by(Fact.session_id)
            ).all()
        )
        names = self.member_names(s.member_id for s in sessions)
        return [
            (
                s,
                names.get(s.member_id, ""),
                SessionCounts(clip_count[s.id], ready_count[s.id], draft.get(s.id, 0)),
            )
            for s in sessions
        ]

    def live_clips_of_dog(self, dog_id: str) -> list[Clip]:
        return list(
            self._s.scalars(
                select(Clip)
                .where(Clip.dog_id == dog_id, Clip.deleted_at.is_(None))
                .order_by(Clip.created_at, Clip.id)
            )
        )

    def clip_ids_with_transcript(self, clip_ids: Sequence[str]) -> set[str]:
        if not clip_ids:
            return set()
        return set(
            self._s.scalars(
                select(TranscriptSegment.clip_id)
                .where(TranscriptSegment.clip_id.in_(clip_ids))
                .distinct()
            )
        )

    def review_facts_of_dog(self, dog_id: str) -> list[Fact]:
        """Draft and confirmed, merged facts with their evidence (no `deleted`, no `merged=0`)."""
        return list(
            self._s.scalars(
                select(Fact)
                .options(selectinload(Fact.evidence))
                .where(
                    Fact.dog_id == dog_id,
                    Fact.status.in_(("draft", "confirmed")),
                    Fact.merged.is_(True),
                )
            )
        )

    def session_owners(self, session_ids: Iterable[str]) -> dict[str, str]:
        ids = {i for i in session_ids if i}
        if not ids:
            return {}
        return dict(
            self._s.execute(
                select(FilmingSession.id, FilmingSession.member_id).where(
                    FilmingSession.id.in_(ids)
                )
            ).all()
        )

    def playback_snapshots(
        self, member_id: str, fact_ids: Sequence[str]
    ) -> list[PlaybackSnapshot]:
        if not fact_ids:
            return []
        rows = self._s.execute(
            select(
                PlaybackEvent.evidence_id,
                PlaybackEvent.member_id,
                PlaybackEvent.start_s,
                PlaybackEvent.end_s,
            ).where(PlaybackEvent.member_id == member_id, PlaybackEvent.fact_id.in_(fact_ids))
        )
        return [PlaybackSnapshot(e, m, s, t) for e, m, s, t in rows]

    # -------------------------------------------------------------- deletion

    def cancel_queued_jobs(self, dog_id: str, *, now: object) -> int:
        """Queued jobs of the dog become `cancelled` (02 section 6.1 step 1)."""
        result = self._s.execute(
            update(Job)
            .where(Job.dog_id == dog_id, Job.status == "queued")
            .values(status="cancelled", updated_at=now)
        )
        return result.rowcount or 0
