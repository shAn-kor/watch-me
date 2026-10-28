"""WordingService: the model pass of the wording check (04 section 6.3).

The rules layer ran at merge time. This pass asks the checker once for the whole
batch, turns each result into a `trait_claim` flag, and on any checker error marks
the batch `check_unavailable`. A check never fails a session (D2).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import select

from app.ai.errors import AiError, to_job_error
from app.ai.types import CheckItem, CheckRequest
from app.clock import Clock
from app.db.uow import UowFactory
from app.errors import JobError
from app.models import Clip, Fact, FactEvidence, FilmingSession
from app.services._write_lock import lock_for_write

log = logging.getLogger(__name__)

UNAVAILABLE_DETAIL = "The wording check did not run. Read the sentence yourself."
KIND_TEMPLATES = {
    "trait_label": 'Possible trait label: "{phrase}"',
    "judgment": 'Possible judgment: "{phrase}"',
    "mental_state": 'Possible feeling or thought: "{phrase}"',
    "safety_claim": 'Possible safety claim: "{phrase}"',
    "paraphrased_trait": 'Possible trait claim in other words: "{phrase}"',
}
MODEL_SOURCES = ("model", "system")


class WordingService:
    def __init__(self, *, uow_factory: UowFactory, clock: Clock, cost_service: Any):
        self._uow_factory = uow_factory
        self._clock = clock
        self._cost = cost_service

    def apply_model_flags(
        self, session_id: str, fact_ids: Sequence[str], checker: Any
    ) -> int:
        """Run the batch check and store the flags. Returns the number of facts
        flagged. Never raises for a checker error."""
        with self._uow_factory() as uow:
            lock_for_write(uow)
            facts = self._facts(uow, session_id, fact_ids)
            if not facts:
                return 0
            sess = uow.session.get(FilmingSession, session_id)
            dog_id = sess.dog_id if sess else None
            items = [
                CheckItem(
                    ref=f"C{i}",
                    situation=f.situation,
                    behavior=f.behavior,
                    source=f.source,
                )
                for i, f in enumerate(facts, 1)
            ]
            req = CheckRequest(
                items=items, fixture_key=self._fixture_key(uow, facts[0])
            )
            by_ref = {item.ref: fact for item, fact in zip(items, facts, strict=True)}
            try:
                results, usages = checker.check(req)
            except Exception as exc:  # noqa: BLE001 - any failure means "unavailable"
                error = exc if isinstance(exc, JobError) else self._as_job_error(exc)
                self._cost.record_usages(error.usages, dog_id, session_id, uow=uow)
                for fact in facts:
                    self._set_unavailable(fact)
                log.warning(
                    "wording check unavailable for session %s: %s",
                    session_id,
                    error.code,
                )
                uow.commit()
                return len(facts)

            self._cost.record_usages(usages, dog_id, session_id, uow=uow)
            flagged = 0
            seen: set[str] = set()
            for fact in facts:
                fact.flags = [
                    f
                    for f in (fact.flags or [])
                    if f.get("source") not in MODEL_SOURCES
                ]
            for res in results:
                fact = by_ref.get(res.ref)
                if fact is None or res.ref in seen:
                    continue
                seen.add(res.ref)
                flag = self._flag(res, fact.behavior)
                if flag is not None:
                    fact.flags = [*fact.flags, flag]
                    flagged += 1
            uow.commit()
            return flagged

    def mark_check_unavailable(self, session_id: str, fact_ids: Sequence[str]) -> None:
        with self._uow_factory() as uow:
            lock_for_write(uow)
            for fact in self._facts(uow, session_id, fact_ids):
                self._set_unavailable(fact)
            uow.commit()

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _as_job_error(exc: Exception) -> JobError:
        if isinstance(exc, AiError):
            return to_job_error(exc, "check")
        return JobError("ai_failed", False)

    @staticmethod
    def _facts(uow: Any, session_id: str, fact_ids: Sequence[str]) -> list[Fact]:
        if not fact_ids:
            return []
        return list(
            uow.session.scalars(
                select(Fact)
                .where(
                    Fact.id.in_(list(fact_ids)),
                    Fact.session_id == session_id,
                    Fact.status != "deleted",
                )
                .order_by(Fact.created_at, Fact.id)
            )
        )

    @staticmethod
    def _fixture_key(uow: Any, fact: Fact) -> str | None:
        name = uow.session.scalar(
            select(Clip.original_filename)
            .join(FactEvidence, FactEvidence.clip_id == Clip.id)
            .where(FactEvidence.fact_id == fact.id)
            .order_by(FactEvidence.id)
            .limit(1)
        )
        return PurePosixPath(name.replace("\\", "/")).stem if name else None

    @staticmethod
    def _set_unavailable(fact: Fact) -> None:
        kept = [f for f in (fact.flags or []) if f.get("code") != "check_unavailable"]
        fact.flags = [
            *kept,
            {
                "code": "check_unavailable",
                "severity": "info",
                "source": "system",
                "detail": UNAVAILABLE_DETAIL,
            },
        ]

    @staticmethod
    def _flag(result: Any, behavior: str) -> dict[str, str] | None:
        template = KIND_TEMPLATES.get(result.kind)
        phrase = (result.phrase or "").strip()
        if template is None or not phrase:
            return None
        if phrase.casefold() not in behavior.casefold():
            return None  # a model that cannot quote the problem is guessing
        return {
            "code": "trait_claim",
            "severity": "warn",
            "source": "model",
            "detail": template.format(phrase=phrase),
        }


__all__ = ["WordingService"]
