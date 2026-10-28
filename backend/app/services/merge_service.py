"""MergeService: session-level merge of the unmerged drafts (04 section 5.6, D3/D5).

Only `merged=0` facts of the session take part. Cross-clip duplicates collapse
into one fact with combined evidence, the banned-word rules flag the survivors,
and the survivors become `merged=1` (visible to review). Safe to run twice.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.clock import Clock
from app.db.base import new_id
from app.db.uow import UowFactory
from app.domain.dedupe import FactDraft, dedupe_within_clip, merge_across_clips
from app.domain.ranges import Range
from app.domain.wording import BannedWordMatcher
from app.models import Clip, Fact, FactEvidence, FilmingSession
from app.services._write_lock import lock_for_write


@dataclass(frozen=True, slots=True)
class MergeReport:
    fact_ids: tuple[str, ...]
    merged: int = 0
    removed: int = 0
    failed: bool = False  # the session cannot go on (no usable clip)


class MergeService:
    def __init__(
        self,
        *,
        uow_factory: UowFactory,
        clock: Clock,
        banned: BannedWordMatcher,
        session_service: object,
    ):
        self._uow_factory = uow_factory
        self._clock = clock
        self._banned = banned
        self._sessions = session_service

    def merge_session(self, session_id: str) -> MergeReport:
        with self._uow_factory() as uow:
            lock_for_write(uow)
            sess = uow.session.get(FilmingSession, session_id)
            if sess is None:
                return MergeReport(())
            ready = uow.session.scalar(
                select(Clip.id)
                .where(
                    Clip.session_id == session_id,
                    Clip.deleted_at.is_(None),
                    Clip.status == "ready",
                )
                .limit(1)
            )
            if ready is None:
                if sess.status == "processing":
                    self._sessions.mark_failed(session_id, "no_usable_clip", uow=uow)  # type: ignore[attr-defined]
                    uow.commit()
                    return MergeReport((), failed=True)
                return MergeReport(())

            facts = list(
                uow.session.scalars(
                    select(Fact)
                    .where(Fact.session_id == session_id, Fact.merged.is_(False))
                    .order_by(Fact.created_at, Fact.id)
                )
            )
            if not facts:
                return MergeReport(())
            by_id = {f.id: f for f in facts}
            drafts = [self._draft(f) for f in facts]
            across = merge_across_clips(drafts)
            within = dedupe_within_clip(across.facts)
            removed = [*across.removed, *within.removed]

            for ref in removed:
                uow.session.delete(by_id[ref])
            uow.session.flush()

            survivors: list[str] = []
            for draft in within.facts:
                fact = by_id[draft.ref]
                self._replace_evidence(fact, draft.evidence)
                fact.flags = [
                    flag.as_dict() for flag in self._banned.check(fact.behavior)
                ]
                fact.merged = True
                survivors.append(fact.id)
            uow.commit()
            return MergeReport(
                tuple(survivors), merged=len(survivors), removed=len(removed)
            )

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _draft(fact: Fact) -> FactDraft:
        rows = tuple(Range(e.start_s, e.end_s, e.clip_id) for e in fact.evidence)
        return FactDraft(
            ref=fact.id,
            situation=fact.situation,
            source=fact.source,
            text=fact.behavior,
            evidence=rows,
            clip_id=rows[0].clip_id if rows else None,
        )

    @staticmethod
    def _replace_evidence(fact: Fact, rows: tuple[Range, ...]) -> None:
        current = {(e.clip_id, e.start_s, e.end_s) for e in fact.evidence}
        wanted = {(r.clip_id, r.start_s, r.end_s) for r in rows}
        if current == wanted:
            return
        fact.evidence[:] = [
            FactEvidence(
                id=new_id(), clip_id=r.clip_id, start_s=r.start_s, end_s=r.end_s
            )
            for r in rows
        ]


__all__ = ["MergeReport", "MergeService"]
