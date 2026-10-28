"""SQL for `qa_log` (02 section 2.12). The sliding-hour limit is counted here.

Rows with outcome `error` never count toward a limit (03 section 7).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import QaLog


class QaLogRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        *,
        dog_id: str,
        ip_hash: str,
        cookie_id: str,
        question: str,
        outcome: str,
        fact_ids: list[str],
        dropped_ids: int,
        ledger_id: int | None,
        latency_ms: int,
        now: datetime,
    ) -> QaLog:
        row = QaLog(
            dog_id=dog_id,
            ip_hash=ip_hash,
            cookie_id=cookie_id,
            question=question,
            outcome=outcome,
            fact_ids=list(fact_ids),
            dropped_ids=dropped_ids,
            ledger_id=ledger_id,
            latency_ms=latency_ms,
            created_at=now,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def _active(self, column, value: str, since: datetime):  # noqa: ANN001, ANN202
        return (column == value, QaLog.created_at > since, QaLog.outcome != "error")

    def count_since(self, *, since: datetime, ip_hash: str | None = None, cookie_id: str | None = None) -> int:
        column, value = (QaLog.ip_hash, ip_hash) if ip_hash is not None else (QaLog.cookie_id, cookie_id)
        return int(
            self._s.scalar(
                select(func.count()).select_from(QaLog).where(*self._active(column, value, since))  # type: ignore[arg-type]
            )
            or 0
        )

    def times_since(
        self, *, since: datetime, ip_hash: str | None = None, cookie_id: str | None = None
    ) -> list[datetime]:
        """Creation times of the counted rows, oldest first."""
        column, value = (QaLog.ip_hash, ip_hash) if ip_hash is not None else (QaLog.cookie_id, cookie_id)
        return list(
            self._s.scalars(
                select(QaLog.created_at)
                .where(*self._active(column, value, since))  # type: ignore[arg-type]
                .order_by(QaLog.created_at, QaLog.id)
            )
        )

    # ------------------------------------------------------------ retention

    def null_questions_before(self, cutoff: datetime) -> int:
        """Drop the question text of rows older than `cutoff` (30 days, I-18)."""
        res = self._s.execute(
            update(QaLog)
            .where(QaLog.created_at < cutoff, QaLog.question.is_not(None))
            .values(question=None)
        )
        return res.rowcount or 0

    def delete_before(self, cutoff: datetime) -> int:
        """Delete rows older than `cutoff` (90 days)."""
        res = self._s.execute(delete(QaLog).where(QaLog.created_at < cutoff))
        return res.rowcount or 0
