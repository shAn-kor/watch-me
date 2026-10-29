"""The `Literal` vocabularies of the response schemas equal the domain enums (01/02)."""

from __future__ import annotations

from typing import get_args

import pytest

from app.api.schemas import vocab
from app.domain import enums
from app.domain.confirm_policy import (
    CONSENT_REQUIRED,
    FLAGS_UNACKNOWLEDGED,
    FORBIDDEN_ROLE,
    INVALID_STATE,
    NOT_FOUND,
    NOT_OWN_SESSION,
    PLAYBACK_REQUIRED,
    PUBLISH_CHECKLIST_INCOMPLETE,
    STAFF_ONLY_SITUATION,
)


def _same(alias: object, expected: set[str]) -> None:
    assert set(get_args(alias)) == expected
    assert len(get_args(alias)) == len(expected)


@pytest.mark.parametrize(
    ("alias", "enum"),
    [
        (vocab.RoleName, enums.Role),
        (vocab.Sex, enums.Sex),
        (vocab.Size, enums.Size),
        (vocab.DogStatus, enums.DogStatus),
        (vocab.SessionStatus, enums.SessionStatus),
        (vocab.ClipStatus, enums.ClipStatus),
        (vocab.ClipStep, enums.ClipStep),
        (vocab.FactOrigin, enums.Origin),
        (vocab.FactSource, enums.Source),
        (vocab.FlagCode, enums.FlagCode),
        (vocab.FlagSeverity, enums.FlagSeverity),
        (vocab.FlagSource, enums.FlagSource),
        (vocab.SituationCode, enums.Situation),
    ],
)
def test_alias_equals_enum(alias: object, enum: type[enums.StrEnum]) -> None:
    _same(alias, set(enums.values(enum)))


def test_derived_vocabularies() -> None:
    _same(vocab.FactStatus, set(enums.values(enums.FactStatus)) - {"deleted"})
    _same(vocab.AskOutcome, set(enums.values(enums.QaOutcome)) - {"error"})
    _same(vocab.ClipFailCode, {c.value for c in enums.CLIP_FAIL_CODES})
    _same(vocab.SessionFailCode, {c.value for c in enums.SESSION_FAIL_CODES})
    _same(
        vocab.BlockedReason,
        {
            NOT_FOUND,
            CONSENT_REQUIRED,
            INVALID_STATE,
            STAFF_ONLY_SITUATION,
            NOT_OWN_SESSION,
            FORBIDDEN_ROLE,
            PLAYBACK_REQUIRED,
            FLAGS_UNACKNOWLEDGED,
            PUBLISH_CHECKLIST_INCOMPLETE,
        },
    )
