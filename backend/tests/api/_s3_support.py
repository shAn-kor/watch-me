"""Shared helpers of the lane S3 API tests (07 section 3.9).

Nothing here is imported by the app. Uploads are built by hand when a test needs
control over the byte stream (`FakeUploadStream`), and through httpx `files=`
otherwise. Generated media comes from `tools.make_fixtures` (git-ignored cache).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.models import Clip, FilmingSession, Job
from tools.make_fixtures import get as fixture

BOUNDARY = "wmtestboundary7MA4YWxkTrZu0gW"
MAX_BYTES = 209_715_200
MIB = 1024 * 1024


def csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def media(key: str) -> Path:
    return fixture(key)


@pytest.fixture
def world(seed):
    return seed.standard_world()


@pytest.fixture
def open_session(seed, world):
    """`s1` of 07 3.9: an `open` session of `vol1` on `dog_empty`."""
    return seed.session(world.dog_empty, world.vol1, status="open")


def upload_file(
    client,
    token: str,
    session_id: str,
    key: str,
    *,
    filename: str | None = None,
    content_type: str = "video/mp4",
    fields: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
):
    """POST one fixture as multipart through httpx."""
    path = media(key)
    with path.open("rb") as fh:
        return client.post(
            f"/api/sessions/{session_id}/clips",
            files={"file": (filename or path.name, fh, content_type)},
            data=fields or {},
            headers={**csrf(token), **(headers or {})},
        )


def upload_bytes(
    client,
    token: str,
    session_id: str,
    data: bytes,
    filename: str,
    *,
    content_type: str = "video/mp4",
    fields: dict[str, str] | None = None,
):
    return client.post(
        f"/api/sessions/{session_id}/clips",
        files={"file": (filename, data, content_type)},
        data=fields or {},
        headers=csrf(token),
    )


def part_head(filename: bytes | str, *, content_type: str = "video/mp4") -> bytes:
    name = filename if isinstance(filename, bytes) else filename.encode()
    return (
        f"--{BOUNDARY}\r\n".encode()
        + b'Content-Disposition: form-data; name="file"; filename="'
        + name
        + b'"\r\n'
        + f"Content-Type: {content_type}\r\n\r\n".encode()
    )


def field_part(name: str, value: str) -> bytes:
    return (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
    ).encode()


TAIL = f"\r\n--{BOUNDARY}--\r\n".encode()


class FakeUploadStream:
    """A request body built chunk by chunk (07 1.3).

    `size` is the file size in bytes. `prefix` is the real start of the file (for
    example a valid MP4); the rest is zero padding. `declare` is the Content-Length
    header: `"honest"` (the whole body), an int (a lie), or `None` (chunked).
    `abort_at` ends the body after that fraction of the file (a dropped connection).
    """

    def __init__(
        self,
        size: int,
        *,
        filename: bytes | str = "big.mp4",
        prefix: bytes = b"",
        declare: str | int | None = "honest",
        abort_at: float | None = None,
        fields: dict[str, str] | None = None,
        chunk: int = MIB,
    ):
        self.size = size
        self.prefix = prefix
        self.declare = declare
        self.abort_at = abort_at
        self.chunk = chunk
        self.sent = 0  # file bytes handed to the server
        self._head = b"".join(field_part(k, v) for k, v in (fields or {}).items())
        self._head += part_head(filename)

    @property
    def total(self) -> int:
        return len(self._head) + self.size + len(TAIL)

    def headers(self, token: str) -> dict[str, str]:
        h = {
            "Content-Type": f"multipart/form-data; boundary={BOUNDARY}",
            **csrf(token),
        }
        if self.declare == "honest":
            h["Content-Length"] = str(self.total)
        elif isinstance(self.declare, int):
            h["Content-Length"] = str(self.declare)
        return h

    def __iter__(self) -> Iterator[bytes]:
        yield self._head
        limit = self.size if self.abort_at is None else int(self.size * self.abort_at)
        pos = 0
        while pos < limit:
            n = min(self.chunk, limit - pos)
            if pos < len(self.prefix):
                piece = self.prefix[pos : pos + n]
                piece += b"\0" * (n - len(piece))
            else:
                piece = b"\0" * n
            pos += n
            self.sent += n
            yield piece
        if self.abort_at is None:
            yield TAIL

    def post(self, client, token: str, session_id: str):
        return client.post(
            f"/api/sessions/{session_id}/clips",
            content=iter(self),
            headers=self.headers(token),
        )


def tmp_files(container) -> list[Path]:
    tmp = container.storage.new_tmp_path().parent
    return [p for p in tmp.rglob("*") if p.is_file()]


def stored_keys(container, prefix: str = "dogs") -> list[str]:
    return container.storage.list_prefix(prefix)


def jobs(db, **where: Any) -> list[Job]:
    db.rollback()  # end the read snapshot, then expire
    stmt = select(Job).order_by(Job.id)
    for k, v in where.items():
        stmt = stmt.where(getattr(Job, k) == v)
    return list(db.scalars(stmt))


def clips_of(db, session_id: str) -> list[Clip]:
    db.rollback()  # end the read snapshot, then expire
    return list(
        db.scalars(
            select(Clip).where(Clip.session_id == session_id).order_by(Clip.ordinal)
        )
    )


def session_row(db, session_id: str) -> FilmingSession:
    db.rollback()  # end the read snapshot, then expire
    return db.get(FilmingSession, session_id)
