"""Fact review reads and writes (lane S4). All SQL of `FactReviewService` lives here.

The dog and clip lookups at the bottom are deliberately small and named for this
lane (`get_dog_in_org`, `get_clip_context`); the lead consolidates them with the
dog and clip repositories later.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Clip,
    Dog,
    Fact,
    FactEvidence,
    FilmingSession,
    Member,
    TranscriptSegment,
)
from app.repositories.playback import PlaybackRepository


@dataclass(frozen=True)
class FactRow:
    """A fact with its dog and the member who owns its session (None without session)."""

    fact: Fact
    dog: Dog
    session_owner_id: str | None


@dataclass(frozen=True)
class ClipContext:
    """A clip with the owner and date of its session and the org of its dog."""

    clip: Clip
    session_owner_id: str
    session_observed_on: date
    org_id: str


class FactRepository:
    def __init__(self, session: Session):
        self._s = session

    # ------------------------------------------------------------------ facts

    def get_fact_row(self, fact_id: str, org_id: str) -> FactRow | None:
        """The fact in the member's org, whatever its status. Callers decide what
        `deleted` and `merged=0` mean."""
        row = self._s.execute(
            select(Fact, Dog, FilmingSession.member_id)
            .join(Dog, Dog.id == Fact.dog_id)
            .outerjoin(FilmingSession, FilmingSession.id == Fact.session_id)
            .where(Fact.id == fact_id, Dog.org_id == org_id)
        ).first()
        if row is None:
            return None
        return FactRow(fact=row[0], dog=row[1], session_owner_id=row[2])

    def add_fact(self, fact: Fact) -> None:
        self._s.add(fact)
        self._s.flush()

    def flush(self) -> None:
        self._s.flush()

    # --------------------------------------------------------------- evidence

    def replace_evidence(
        self, fact: Fact, remove: Iterable[FactEvidence], add: Iterable[FactEvidence]
    ) -> None:
        """Remove rows (and their playback events) and add new rows."""
        remove = list(remove)
        if remove:
            PlaybackRepository(self._s).delete_for_evidence([e.id for e in remove])
            for row in remove:
                fact.evidence.remove(row)
            self._s.flush()
        for row in add:
            fact.evidence.append(row)
        self._s.flush()

    def delete_all_evidence_and_events(self, fact: Fact) -> None:
        PlaybackRepository(self._s).delete_for_fact(fact.id)
        for row in list(fact.evidence):
            fact.evidence.remove(row)
        self._s.flush()

    # -------------------------------------------------- view support lookups

    def clips_by_id(self, clip_ids: Iterable[str]) -> dict[str, Clip]:
        ids = list(set(clip_ids))
        if not ids:
            return {}
        return {c.id: c for c in self._s.scalars(select(Clip).where(Clip.id.in_(ids)))}

    def clip_ids_with_transcript(self, clip_ids: Iterable[str]) -> set[str]:
        ids = list(set(clip_ids))
        if not ids:
            return set()
        return set(
            self._s.scalars(
                select(TranscriptSegment.clip_id)
                .where(TranscriptSegment.clip_id.in_(ids))
                .distinct()
            )
        )

    def member_names(self, member_ids: Iterable[str]) -> dict[str, str]:
        ids = list({m for m in member_ids if m})
        if not ids:
            return {}
        return {
            m.id: m.display_name
            for m in self._s.scalars(select(Member).where(Member.id.in_(ids)))
        }

    # ------------------------------------------- dog and clip lookups (lane S4)

    def get_dog_in_org(self, dog_id: str, org_id: str) -> Dog | None:
        return self._s.scalar(select(Dog).where(Dog.id == dog_id, Dog.org_id == org_id))

    def get_clip_context(self, clip_id: str) -> ClipContext | None:
        row = self._s.execute(
            select(Clip, FilmingSession.member_id, FilmingSession.observed_on, Dog.org_id)
            .join(FilmingSession, FilmingSession.id == Clip.session_id)
            .join(Dog, Dog.id == Clip.dog_id)
            .where(Clip.id == clip_id)
        ).first()
        if row is None:
            return None
        return ClipContext(clip=row[0], session_owner_id=row[1], session_observed_on=row[2], org_id=row[3])
