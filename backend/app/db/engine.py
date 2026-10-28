"""Engine factory. SQLite pragmas are applied on every connection (02 section 0):
WAL, foreign keys ON, busy_timeout 5000."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

BUSY_TIMEOUT_MS = 5000


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _is_memory(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or ":memory:" in url


def make_engine(url: str, *, echo: bool = False) -> Engine:
    connect_args: dict[str, object] = {}
    if _is_sqlite(url):
        # The api serves requests from a thread pool; connections are not shared
        # across threads at the same time (one session per request).
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = BUSY_TIMEOUT_MS / 1000
    engine = create_engine(url, echo=echo, connect_args=connect_args, future=True)
    if _is_sqlite(url):
        _install_sqlite_pragmas(engine, memory=_is_memory(url))
    return engine


def _install_sqlite_pragmas(engine: Engine, *, memory: bool) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):
        # Take over transaction control so BEGIN is emitted by SQLAlchemy (below)
        # and SAVEPOINT / DDL behave predictably with pysqlite.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            if not memory:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(connection):
        connection.exec_driver_sql("BEGIN")


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)
