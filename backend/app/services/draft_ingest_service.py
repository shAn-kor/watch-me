"""DraftIngestService: turns one clip's `DraftOutput` into unmerged draft facts
(04 section 5, 03 section 2.2 steps D1 to D6).

One transaction writes the facts, their evidence, the ledger rows and the clip
`ready` state, then tells the session the clip is terminal. A deleted dog or clip
discards the result (PIPE-DEL-06).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.clock import Clock
from app.db.base import new_id
from app.db.uow import UowFactory
from app.domain.dedupe import FactDraft, dedupe_within_clip
from app.domain.ranges import (
    Range,
    filter_narration_rows,
    repair_citations,
    segment_ranges,
)
from app.domain.wording import normalize_ai_behavior
from app.models import Clip, Dog, Fact, FactEvidence, FilmingSession, TranscriptSegment

log = logging.getLogger(__name__)

MAX_FACTS_PER_CLIP = 8


@dataclass(frozen=True, slots=True)
class IngestReport:
    stored: int
    dropped: int
    discarded: bool = False


class DraftIngestService:
    def __init__(
        self,
        *,
        uow_factory: UowFactory,
        clock: Clock,
        session_service: Any,
        cost_service: Any,
    ):
        self._uow_factory = uow_factory
        self._clock = clock
        self._sessions = session_service
        self._cost = cost_service

    def store_drafts(
        self,
        *,
        clip_id: str,
        output: Any,
        usages: Iterable[Any],
        mode: str,
        k: int,
        ai_model: str,
    ) -> IngestReport:
        usages = list(usages)
        with self._uow_factory() as uow:
            row = uow.session.execute(
                select(Clip, FilmingSession, Dog)
                .join(FilmingSession, FilmingSession.id == Clip.session_id)
                .join(Dog, Dog.id == Clip.dog_id)
                .where(Clip.id == clip_id)
            ).first()
            if row is None:
                return IngestReport(0, 0, discarded=True)
            clip, sess, dog = row
            if clip.deleted_at is not None or dog.status == "deleted":
                # the AI call was made and paid for: keep its ledger rows
                self._cost.record_usages(usages, clip.dog_id, clip.session_id, uow=uow)
                uow.commit()
                return IngestReport(0, 0, discarded=True)
            if clip.status == "ready":  # a repeated job: nothing left to do
                return IngestReport(0, 0, discarded=True)

            transcript = [
                (t.start_s, t.end_s)
                for t in uow.session.scalars(
                    select(TranscriptSegment).where(
                        TranscriptSegment.clip_id == clip.id
                    )
                )
            ]
            drafts, dropped = self._prepare(
                output.facts, sess.situations, mode, k, clip, transcript
            )

            # idempotence: earlier unmerged drafts of this clip go first
            for old in uow.session.scalars(
                select(Fact)
                .join(FactEvidence, FactEvidence.fact_id == Fact.id)
                .where(FactEvidence.clip_id == clip.id, Fact.merged.is_(False))
                .distinct()
            ):
                uow.session.delete(old)
            uow.session.flush()

            for draft in drafts:
                fact = Fact(
                    id=new_id(),
                    dog_id=clip.dog_id,
                    session_id=clip.session_id,
                    created_by=None,
                    situation=draft.situation,
                    behavior=draft.text,
                    source=draft.source,
                    origin="ai_unchanged",
                    status="draft",
                    merged=False,
                    flags=[],
                    observed_on=sess.observed_on,
                    ai_model=ai_model,
                )
                for rng in draft.evidence:
                    fact.evidence.append(
                        FactEvidence(
                            id=new_id(),
                            clip_id=clip.id,
                            start_s=rng.start_s,
                            end_s=rng.end_s,
                        )
                    )
                uow.session.add(fact)

            self._cost.record_usages(usages, clip.dog_id, clip.session_id, uow=uow)
            clip.status = "ready"
            clip.step = "draft"
            clip.fail_code = None
            clip.fail_detail = None
            clip.ready_at = self._clock.now()
            uow.session.flush()
            if not drafts:
                log.warning("zero_fact_clip clip_id=%s", clip.id)
            self._sessions.on_clip_terminal(clip.session_id, uow=uow)
            uow.commit()
            return IngestReport(len(drafts), dropped)

    # ------------------------------------------------------------- pipeline

    @staticmethod
    def _prepare(
        facts: Sequence[Any],
        situations: Sequence[str],
        mode: str,
        k: int,
        clip: Clip,
        transcript: Sequence[tuple[float, float]],
    ) -> tuple[list[FactDraft], int]:
        """Steps 1 to 6 of 04 section 5: text, situation filter, evidence repair,
        narration filter, within-clip dedupe, cap."""
        duration = float(clip.duration_s)
        kept: list[tuple[Any, str]] = []
        dropped = 0
        for fact in facts:
            text = normalize_ai_behavior(fact.behavior)
            if text is None or fact.situation not in situations:
                dropped += 1
                continue
            kept.append((fact, text))

        rows_per_fact: list[tuple[Range, ...]] = []
        if mode == "segments":
            for fact, _ in kept:
                refs = [r for r in fact.evidence if isinstance(r, str)]
                rows, _gone = segment_ranges(refs, clip.ordinal, duration, clip.id)
                rows_per_fact.append(rows)
        else:
            citations = [
                [(c.start_t, c.end_t) for c in fact.evidence if not isinstance(c, str)]
                for fact, _ in kept
            ]
            report = repair_citations(citations, max(1, k), duration, clip.id)
            rows_per_fact = list(report.rows)

        drafts: list[FactDraft] = []
        for i, ((fact, text), rows) in enumerate(zip(kept, rows_per_fact, strict=True)):
            if fact.source == "narration":
                rows = filter_narration_rows(rows, transcript)
            if not rows:
                dropped += 1
                continue
            drafts.append(
                FactDraft(
                    ref=str(i),
                    situation=fact.situation,
                    source=fact.source,
                    text=text,
                    evidence=tuple(rows),
                    clip_id=clip.id,
                )
            )
        result = dedupe_within_clip(drafts)
        dropped += len(result.removed)
        survivors = list(result.facts)
        if len(survivors) > MAX_FACTS_PER_CLIP:
            dropped += len(survivors) - MAX_FACTS_PER_CLIP
            survivors = survivors[:MAX_FACTS_PER_CLIP]
        return survivors, dropped


__all__ = ["DraftIngestService", "IngestReport"]
