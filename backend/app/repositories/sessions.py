"""SQL for filming sessions and the dog lookups lane S3 needs (02 sections 2.3, 2.4).

No business rules: `SessionService` and `ClipUploadService` decide. The dog lookups
live here until the lead consolidates them with lane S2's `dogs` repository.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Clip,
    Dog,
    Fact,
    FactEvidence,
    FilmingSession,
    Member,
    PlaybackEvent,
    TranscriptSegment,
)


class SessionRepository:
    def __init__(self, session: Session):
        self._s = session

    # ----------------------------------------------------------- dogs

    def dog_in_org(self, dog_id: str, org_id: str) -> Dog | None:
        """The dog when it belongs to the org (any status, including `deleted`)."""
        return self._s.scalar(select(Dog).where(Dog.id == dog_id, Dog.org_id == org_id))

    def set_dog_people_check_cleared(self, dog: Dog) -> None:
        dog.people_check_at = None

    # ------------------------------------------------------- sessions

    def add_session(
        self,
        *,
        id: str,
        dog_id: str,
        member_id: str,
        situations: list[str],
        observed_on: date,
        rules_ack_at: datetime,
        created_at: datetime,
    ) -> FilmingSession:
        row = FilmingSession(
            id=id,
            dog_id=dog_id,
            member_id=member_id,
            situations=list(situations),
            observed_on=observed_on,
            status="open",
            rules_ack_at=rules_ack_at,
            created_at=created_at,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def session_with_dog(
        self, session_id: str, org_id: str
    ) -> tuple[FilmingSession, Dog] | None:
        """A session and its dog, only when the dog is in the org (any dog status)."""
        row = self._s.execute(
            select(FilmingSession, Dog)
            .join(Dog, Dog.id == FilmingSession.dog_id)
            .where(FilmingSession.id == session_id, Dog.org_id == org_id)
        ).first()
        return (row[0], row[1]) if row else None

    def get_session(self, session_id: str) -> FilmingSession | None:
        return self._s.get(FilmingSession, session_id)

    def member_names(self, member_ids: Iterable[str]) -> dict[str, str]:
        ids = {m for m in member_ids if m}
        if not ids:
            return {}
        rows = self._s.execute(
            select(Member.id, Member.display_name).where(Member.id.in_(ids))
        )
        return {mid: name for mid, name in rows}

    # ----------------------------------------------------------- clips

    def live_clips(self, session_id: str) -> list[Clip]:
        return list(
            self._s.scalars(
                select(Clip)
                .where(Clip.session_id == session_id, Clip.deleted_at.is_(None))
                .order_by(Clip.ordinal)
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

    # ----------------------------------------------------------- facts

    def visible_facts(self, session_id: str) -> list[Fact]:
        """Non-deleted, merged facts of the session with their evidence."""
        return list(
            self._s.scalars(
                select(Fact)
                .options(selectinload(Fact.evidence))
                .where(
                    Fact.session_id == session_id,
                    Fact.status != "deleted",
                    Fact.merged.is_(True),
                )
                .order_by(Fact.created_at, Fact.id)
            )
        )

    def playback_for(
        self, member_id: str, evidence_ids: Sequence[str]
    ) -> list[PlaybackEvent]:
        if not evidence_ids:
            return []
        return list(
            self._s.scalars(
                select(PlaybackEvent).where(
                    PlaybackEvent.member_id == member_id,
                    PlaybackEvent.evidence_id.in_(evidence_ids),
                )
            )
        )

    def evidence_count(self, fact_id: str) -> int:
        return len(
            self._s.scalars(select(FactEvidence.id).where(FactEvidence.fact_id == fact_id)).all()
        )
