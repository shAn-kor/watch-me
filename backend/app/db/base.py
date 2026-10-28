"""Declarative base with a constraint naming convention and shared column helpers."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def new_id() -> str:
    """Entity id: `uuid4().hex`, generated in Python (02 section 0)."""
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """Python-side default for timestamp columns. Services pass `clock.now()` instead."""
    return datetime.now(UTC)


def sql_list(items: Iterable[str]) -> str:
    return ", ".join(f"'{item}'" for item in items)


def check_in(
    column: str, items: Iterable[str], name: str, *, nullable: bool = False
) -> CheckConstraint:
    """`CHECK (column IN (...))` (enums are String + CHECK, 02 section 0)."""
    expr = f"{column} IN ({sql_list(items)})"
    if nullable:
        expr = f"{column} IS NULL OR {expr}"
    return CheckConstraint(expr, name=name)


def check_bool(column: str) -> CheckConstraint:
    """Boolean stored as INTEGER 0/1 with CHECK (02 section 0)."""
    return CheckConstraint(f"{column} IN (0, 1)", name=f"{column}_bool")
