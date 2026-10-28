"""DB-MIG-01: Alembic head equals the models; downgrade to base works."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext

from alembic import command

BACKEND = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "org",
    "member",
    "dog",
    "session",
    "clip",
    "transcript_segment",
    "segment",
    "fact",
    "fact_evidence",
    "playback_event",
    "job",
    "qa_log",
    "cost_ledger",
}


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _norm(sql: str) -> str | tuple[str, ...]:
    """Normalize whitespace/quotes; for CREATE TABLE compare the column and
    constraint definitions as a sorted tuple (constraint order is not significant)."""
    flat = re.sub(r"[\s\"`]+", " ", sql).strip().lower()
    if not flat.startswith("create table"):
        return flat
    head, _, rest = flat.partition("(")
    body = rest.rsplit(")", 1)[0]
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    parts.append(cur.strip())
    return (head.strip(), *sorted(parts))


def _schema(path: Path) -> dict[str, object]:
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
        ).fetchall()
    finally:
        con.close()
    return {f"{typ}:{name}": _norm(sql) for typ, name, sql in rows}


def test_db_mig_01_upgrade_matches_models_and_downgrades(tmp_path):
    import app.models  # noqa: F401  (registers tables on Base.metadata)
    from app.db.base import Base
    from app.db.engine import make_engine

    url = f"sqlite:///{tmp_path / 'mig.db'}"
    cfg = alembic_config(url)
    command.upgrade(cfg, "head")

    engine = make_engine(url)
    try:
        insp = sa.inspect(engine)
        tables = set(insp.get_table_names()) - {"alembic_version"}
        assert tables == EXPECTED_TABLES

        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn, opts={"compare_type": True, "compare_server_default": False}
            )
            diff = compare_metadata(ctx, Base.metadata)
        assert diff == [], f"models and migration differ: {diff}"
    finally:
        engine.dispose()

    # Alembic does not compare CHECK constraints or partial-index predicates,
    # so compare the stored DDL with what metadata.create_all() produces.
    fresh = tmp_path / "fresh.db"
    fresh_engine = make_engine(f"sqlite:///{fresh}")
    Base.metadata.create_all(fresh_engine)
    fresh_engine.dispose()
    assert _schema(tmp_path / "mig.db") == _schema(fresh)

    command.downgrade(cfg, "base")
    assert _schema(tmp_path / "mig.db") == {}


def test_db_mig_01_upgrade_twice_is_a_noop(tmp_path):
    cfg = alembic_config(f"sqlite:///{tmp_path / 'again.db'}")
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
