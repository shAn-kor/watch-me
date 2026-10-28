"""CostService: the only writer of `cost_ledger` for the pipeline (04 section 9.2, I-20).

`record_usages` joins the caller's transaction. `record_usages_independent`
commits on its own, so the rows of a failed AI call survive the rollback of the
step that made the call.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.clock import Clock
from app.db.uow import UnitOfWork, UowFactory
from app.repositories.cost_ledger import CostLedgerRepository


class CostService:
    def __init__(self, *, uow_factory: UowFactory, clock: Clock):
        self._uow_factory = uow_factory
        self._clock = clock

    def record_usages(
        self,
        usages: Iterable[Any],
        dog_id: str | None,
        session_id: str | None,
        *,
        uow: UnitOfWork | None = None,
    ) -> int:
        """One ledger row per usage (the purpose comes from the usage)."""
        rows = list(usages)
        if not rows:
            return 0
        if uow is not None:
            return self._add(uow, rows, dog_id, session_id)
        with self._uow_factory() as unit:
            n = self._add(unit, rows, dog_id, session_id)
            unit.commit()
            return n

    def record_usages_independent(
        self, usages: Iterable[Any], dog_id: str | None, session_id: str | None
    ) -> int:
        """Own transaction, committed at once (usages of a failed call)."""
        rows = list(usages)
        if not rows:
            return 0
        with self._uow_factory() as unit:
            n = self._add(unit, rows, dog_id, session_id)
            unit.commit()
            return n

    def qa_spend_today_micros(self) -> int:
        now = self._clock.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        with self._uow_factory() as unit:
            return CostLedgerRepository(unit.session).spend_since("qa_select", start)

    def _add(
        self, unit: UnitOfWork, rows: list[Any], dog_id: str | None, session_id: str | None
    ) -> int:
        repo = CostLedgerRepository(unit.session)
        now = self._clock.now()
        for usage in rows:
            repo.add_usage(
                usage, purpose=usage.purpose, dog_id=dog_id, now=now, session_id=session_id
            )
        return len(rows)


__all__ = ["CostService"]
