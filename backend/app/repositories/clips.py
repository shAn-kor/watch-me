"""SQL for clips (02 section 2.5), the clip delete effects on facts (02 6.2), and the
partial outputs a manual retry removes (02 C6). No business rules."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Clip,
    Dog,
    Fact,
    FactEvidence,
    FilmingSession,
    Segment,
    TranscriptSegment,
)


class ClipRepository:
    def __init__(self, session: Session):
        self._s = session

    # ---------------------------------------------------------- lookups

    def scoped(
        self, clip_id: str, org_id: str
    ) -> tuple[Clip, FilmingSession, Dog] | None:
        """A live clip with its session and dog, only when the dog is in the org
        (any dog status; the service hides `deleted` dogs)."""
        row = self._s.execute(
            select(Clip, FilmingSession, Dog)
            .join(FilmingSession, FilmingSession.id == Clip.session_id)
            .join(Dog, Dog.id == Clip.dog_id)
            .where(Clip.id == clip_id, Clip.deleted_at.is_(None), Dog.org_id == org_id)
        ).first()
        return (row[0], row[1], row[2]) if row else None

    def live_ordinals(self, session_id: str) -> list[int]:
        return sorted(
            self._s.scalars(
                select(Clip.ordinal).where(
                    Clip.session_id == session_id, Clip.deleted_at.is_(None)
                )
            )
        )

    def by_request_id(self, session_id: str, client_request_id: str) -> Clip | None:
        return self._s.scalar(
            select(Clip).where(
                Clip.session_id == session_id,
                Clip.client_request_id == client_request_id,
            )
        )

    def has_transcript(self, clip_id: str) -> bool:
        return (
            self._s.scalar(
                select(TranscriptSegment.id).where(TranscriptSegment.clip_id == clip_id).limit(1)
            )
            is not None
        )

    # ----------------------------------------------------------- writes

    def add_clip(self, **fields: object) -> Clip:
        clip = Clip(**fields)
        self._s.add(clip)
        self._s.flush()
        return clip

    # ----------------------------------------------------- delete effects

    def confirmed_fact_cites(self, clip_id: str) -> bool:
        return (
            self._s.scalar(
                select(Fact.id)
                .join(FactEvidence, FactEvidence.fact_id == Fact.id)
                .where(FactEvidence.clip_id == clip_id, Fact.status == "confirmed")
                .limit(1)
            )
            is not None
        )

    def evidence_of_clip(self, clip_id: str) -> list[FactEvidence]:
        """Evidence rows of the clip whose fact is not deleted, with the fact and
        all of its evidence loaded."""
        return list(
            self._s.scalars(
                select(FactEvidence)
                .join(Fact, Fact.id == FactEvidence.fact_id)
                .options(selectinload(FactEvidence.fact).selectinload(Fact.evidence))
                .where(FactEvidence.clip_id == clip_id, Fact.status != "deleted")
                .order_by(FactEvidence.id)
            )
        )

    # ------------------------------------------------------ retry cleanup

    def delete_transcript(self, clip_id: str) -> None:
        self._s.execute(delete(TranscriptSegment).where(TranscriptSegment.clip_id == clip_id))

    def delete_segments(self, clip_id: str) -> None:
        self._s.execute(delete(Segment).where(Segment.clip_id == clip_id))

    def unmerged_draft_facts(self, clip_id: str) -> list[Fact]:
        """AI drafts of this clip still waiting for the session merge (`merged=0`)."""
        return list(
            self._s.scalars(
                select(Fact)
                .join(FactEvidence, FactEvidence.fact_id == Fact.id)
                .where(FactEvidence.clip_id == clip_id, Fact.merged.is_(False))
                .distinct()
            )
        )
