"""`playback_event` reads and writes (02 section 2.10; lane S4)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import FactEvidence, PlaybackEvent


class PlaybackRepository:
    def __init__(self, session: Session):
        self._s = session

    def events_of_member(self, fact_ids: Sequence[str], member_id: str) -> list[PlaybackEvent]:
        if not fact_ids:
            return []
        return list(
            self._s.scalars(
                select(PlaybackEvent).where(
                    PlaybackEvent.fact_id.in_(fact_ids), PlaybackEvent.member_id == member_id
                )
            )
        )

    def upsert(
        self,
        *,
        fact_id: str,
        evidence: FactEvidence,
        member_id: str,
        watched_s: float,
        at: datetime,
    ) -> None:
        """One event per (evidence, member): insert, or update with the current snapshot."""
        event = self._s.scalar(
            select(PlaybackEvent).where(
                PlaybackEvent.evidence_id == evidence.id, PlaybackEvent.member_id == member_id
            )
        )
        if event is None:
            self._s.add(
                PlaybackEvent(
                    fact_id=fact_id,
                    evidence_id=evidence.id,
                    member_id=member_id,
                    start_s=evidence.start_s,
                    end_s=evidence.end_s,
                    watched_s=watched_s,
                    completed_at=at,
                )
            )
        else:
            event.start_s = evidence.start_s
            event.end_s = evidence.end_s
            event.watched_s = watched_s
            event.completed_at = at
        self._s.flush()

    def delete_for_evidence(self, evidence_ids: Sequence[str]) -> None:
        if evidence_ids:
            self._s.execute(delete(PlaybackEvent).where(PlaybackEvent.evidence_id.in_(evidence_ids)))

    def delete_for_fact(self, fact_id: str) -> None:
        self._s.execute(delete(PlaybackEvent).where(PlaybackEvent.fact_id == fact_id))
