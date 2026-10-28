"""Shared test harness (08 section 2, 07 sections 1.2 and 2.2).

Fixtures
- `settings`      test `Settings` (temp SQLite file, temp storage, insecure cookie)
- `engine`        engine on a per-test copy of a once-migrated database
- `db`            a SQLAlchemy `Session` on that database (rolled back at the end)
- `clock`         `FakeClock` starting 2026-10-28T12:00:00Z
- `container`     `Container` with scripted AI fakes and the FakeClock
- `app`, `client` the ASGI app and a TestClient (httpx under the hood)
- `seed`          `SeedBuilder` (tests/factories.py)
- `login_as`      stub until lane S1 (see its docstring)

Markers are applied by directory: tests/unit -> unit, tests/db -> db,
tests/api -> api, tests/pipeline -> pipeline + slow.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.clock import FakeClock
from app.config import Settings
from app.container import Container, build_container
from app.db.engine import make_engine, make_session_factory
from tests.factories import SeedBuilder
from tests.fakes import scripted_ai_slots

BACKEND = Path(__file__).resolve().parents[1]
TEST_SECRET_KEY = "test-secret-key-0123456789abcdef0123456789"
TEST_IP_HASH_KEY = "test-ip-hash-key-0123456789"

_DIR_MARKERS = {
    "unit": ("unit",),
    "db": ("db",),
    "api": ("api",),
    "pipeline": ("pipeline", "slow"),
}


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    for item in items:
        parts = Path(str(item.fspath)).relative_to(BACKEND / "tests").parts
        for marker in _DIR_MARKERS.get(parts[0], ()):
            item.add_marker(getattr(pytest.mark, marker))


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings must come from fixtures, never from the developer's shell."""
    names = {f.upper() for f in Settings.model_fields}
    for name in list(os.environ):
        if name.upper() in names:
            monkeypatch.delenv(name, raising=False)


# ------------------------------------------------------------------ database


@pytest.fixture(scope="session")
def migrated_template_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One database migrated with Alembic (head) and shared as a template, so each
    test only pays for a file copy."""
    path = tmp_path_factory.mktemp("template") / "template.db"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.upgrade(cfg, "head")
    # Fold the WAL into the main file so copying one file is enough.
    engine = make_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    engine.dispose()
    return path


@pytest.fixture
def settings(tmp_path: Path, migrated_template_db: Path) -> Settings:
    db_path = tmp_path / "test.db"
    shutil.copyfile(migrated_template_db, db_path)
    return Settings(
        _env_file=None,
        app_env="test",
        secret_key=TEST_SECRET_KEY,
        ip_hash_key=TEST_IP_HASH_KEY,
        database_url=f"sqlite:///{db_path}",
        storage_root=tmp_path / "storage",
        cookie_secure=False,
        ai_mock_fixtures_dir=BACKEND / "tests" / "fixtures" / "ai",
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    eng = make_engine(settings.database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A session for direct reads and writes. Commit what other code must see."""
    session = make_session_factory(engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def seed(engine: Engine, clock: FakeClock) -> SeedBuilder:
    return SeedBuilder(make_session_factory(engine), clock)


# ---------------------------------------------------------- clock, container


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def container(settings: Settings, engine: Engine, clock: FakeClock) -> Container:
    return build_container(settings, clock=clock, engine=engine, ai=scripted_ai_slots())


@pytest.fixture
def app(container: Container) -> FastAPI:
    from app.main import create_app

    return create_app(container)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://testserver") as c:
        yield c


# ---------------------------------------------------------------- login_as


@pytest.fixture
def login_as(client: TestClient, container: Container) -> Callable[..., str]:
    """`login_as(member, *, password=None) -> csrf_token`: sign `client` in as a
    seeded member and return the CSRF token to send as `X-CSRF-Token`.

    STUB until lane S1 (auth). Phase 0 has neither `SessionCookieCodec` (lane B)
    nor `/api/auth/login` (lane S1), so this raises. Lane S1 replaces the body
    with a call to the real login endpoint or to the cookie codec; every API test
    uses this one helper so the change stays in one place.
    """

    def _login_as(member: object, *, password: str | None = None) -> str:
        raise NotImplementedError(
            "login_as is a stub until lane S1 (auth) implements /api/auth/login "
            "and the session cookie codec"
        )

    return _login_as
