"""Helpers of the lane S5 API tests (07 sections 3.11 and 3.13)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Clip, Dog, Fact

PROFILE = "/api/public/dogs/{slug}"
UNKNOWN_SLUG = "zzzzzzzzzzzz"


def put_file(container: Any, key: str, data: bytes) -> None:
    """Write `data` under the storage root at `key` (what the pipeline would do)."""
    path = container.settings.storage_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def put_clip_file(container: Any, clip: Any, data: bytes = b"\x00" * 1000) -> str:
    """Write the playback file of a seeded clip; returns its key."""
    key = clip.playback_path or f"dogs/{clip.dog_id}/clips/{clip.id}/playback.mp4"
    put_file(container, key, data)
    return key


def set_fact(db: Session, fact_id: str, **values: Any) -> None:
    db.execute(update(Fact).where(Fact.id == fact_id).values(**values))
    db.commit()


def set_dog(db: Session, dog_id: str, **values: Any) -> None:
    db.execute(update(Dog).where(Dog.id == dog_id).values(**values))
    db.commit()


def set_clip(db: Session, clip_id: str, **values: Any) -> None:
    db.execute(update(Clip).where(Clip.id == clip_id).values(**values))
    db.commit()


def all_keys(node: Any) -> set[str]:
    """Every dict key anywhere in a JSON value."""
    out: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(k)
            out |= all_keys(v)
    elif isinstance(node, list):
        for v in node:
            out |= all_keys(v)
    return out


def ids_of(db: Session, dog_id: str) -> set[str]:
    return set(db.scalars(select(Fact.id).where(Fact.dog_id == dog_id)))


def comparable(response: Any) -> tuple[int, bytes, dict[str, str]]:
    """Status, body and headers without the per-request id."""
    headers = {
        k.lower(): v for k, v in response.headers.items() if k.lower() != "x-request-id"
    }
    return response.status_code, response.content, headers
