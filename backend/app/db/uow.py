"""UnitOfWork: session scope, commit, rollback, `independent_session()`.

Only `services` and `repositories` open transactions; a service method is a
transaction boundary and the api commits through the unit of work after the
service returns (06 section 2, rule 1).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker


class UnitOfWork:
    """One database session scope. Use as a context manager::

        with uow_factory() as uow:
            ...uow.session...
            uow.commit()

    Leaving the block without `commit()` rolls back, as does any exception.
    """

    def __init__(self, session_factory: sessionmaker[Session]):
        self._factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> UnitOfWork:
        self._session = self._factory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._session
        self._session = None
        if session is None:
            return
        try:
            if exc_type is not None:
                session.rollback()
        finally:
            session.close()

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active; use it as a context manager")
        return self._session

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    @contextmanager
    def independent_session(self) -> Iterator[Session]:
        """A separate short transaction that commits on success (for example the
        ledger rows of a failed AI call, invariant I-20). It does not touch the
        outer session, so a rollback there does not undo it."""
        session = self._factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()


UowFactory = Callable[[], UnitOfWork]


def make_uow_factory(session_factory: sessionmaker[Session]) -> UowFactory:
    def factory() -> UnitOfWork:
        return UnitOfWork(session_factory)

    return factory
