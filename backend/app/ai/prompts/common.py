"""Shared prompt helpers: the per-request nonce and untrusted-text handling
(04 section 1 rule 2, section 4.5, AI-8)."""

from __future__ import annotations

import json
import secrets
from typing import Any


def new_nonce() -> str:
    """16 random hex characters, new for each request."""
    return secrets.token_hex(8)


def neutralize(text: str, nonce: str) -> str:
    """Make untrusted text unable to close or fake the data block: no `<`, `>`
    and no nonce string."""
    return text.replace("<", "‹").replace(">", "›").replace(nonce, "")


def json_line(obj: dict[str, Any], nonce: str, *, drop: bool = False) -> str | None:
    """One JSON object per line, UTF-8 kept, `<` and `>` replaced in strings.
    A line that contains the nonce is dropped when `drop` (transcripts, 04 section
    4.5); otherwise the nonce string is removed from the text (facts, questions)."""
    safe = {k: (neutralize(v, nonce) if isinstance(v, str) else v) for k, v in obj.items()}
    if drop and any(isinstance(v, str) and nonce in v for v in obj.values()):
        return None
    return json.dumps(safe, ensure_ascii=False)


def fill(template: str, **values: object) -> str:
    """Replace `{name}` markers. `str.format` is not used: the prompts hold JSON braces."""
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def response_format(name: str, schema: dict[str, Any], strict: bool) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": strict, "schema": schema},
    }
