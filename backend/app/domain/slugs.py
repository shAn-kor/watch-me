"""Public slug generator (REV-5, NFR-5): 12 characters of [a-z2-9] without the
look-alikes 0 1 l o. Random, never derived from the dog's name."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence

SLUG_ALPHABET = "".join(c for c in "abcdefghijklmnopqrstuvwxyz23456789" if c not in "01lo")
SLUG_LENGTH = 12


def generate_slug(choice: Callable[[Sequence[str]], str] = secrets.choice) -> str:
    return "".join(choice(SLUG_ALPHABET) for _ in range(SLUG_LENGTH))
