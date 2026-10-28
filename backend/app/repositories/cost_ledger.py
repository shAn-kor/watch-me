"""SQL for `cost_ledger` (02 section 2.13). No business rules."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CostLedger


class CostLedgerRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add_usage(
        self,
        usage: Any,  # a `Usage` (provider, model, tokens_in, tokens_out, audio_s, usd_micros)
        *,
        purpose: str,
        dog_id: str | None,
        now: datetime,
        session_id: str | None = None,
    ) -> int:
        row = CostLedger(
            purpose=purpose,
            provider=usage.provider,
            model=usage.model,
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            audio_s=usage.audio_s or None,
            usd_micros=usage.usd_micros,
            dog_id=dog_id,
            session_id=session_id,
            created_at=now,
        )
        self._s.add(row)
        self._s.flush()
        return row.id

    def spend_since(self, purpose: str, since: datetime) -> int:
        total = self._s.scalar(
            select(func.coalesce(func.sum(CostLedger.usd_micros), 0)).where(
                CostLedger.purpose == purpose, CostLedger.created_at >= since
            )
        )
        return int(total or 0)
