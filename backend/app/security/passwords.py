"""PasswordHasher: argon2id (06 section 3.5, ORG-0)."""

from __future__ import annotations

from argon2 import PasswordHasher as _Argon2
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError


class PasswordHasher:
    def __init__(self) -> None:
        self._ph = _Argon2(type=Type.ID)

    def hash(self, password: str) -> str:
        return self._ph.hash(password)

    def verify(self, hash: str, password: str) -> bool:
        try:
            return self._ph.verify(hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, hash: str) -> bool:
        try:
            return self._ph.check_needs_rehash(hash)
        except InvalidHashError:
            return True
