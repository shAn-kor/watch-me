"""Take the SQLite write lock before the first read of a lane P transaction.

The engine opens deferred transactions. A transaction that reads and then writes
fails at once with `database is locked` when another connection committed in
between (the read snapshot is stale), and `busy_timeout` does not help. A no-op
write as the first statement queues for the lock instead.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text


def lock_for_write(uow: Any) -> None:
    uow.session.execute(text("UPDATE job SET id = id WHERE 0"))
