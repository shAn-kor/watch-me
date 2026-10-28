"""UT-UPL-01 (07 section 3.3): UploadReceiver byte counter."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.errors import FileTooLarge, MalformedRequest, UploadIncomplete

BOUNDARY = "unitboundary123"
MIB = 1024 * 1024
LIMIT = 200 * MIB


class FakeRequest:
    """The two things the receiver reads from a request: headers and the stream."""

    def __init__(self, chunks, *, content_length: int | None = None):
        self.headers = {"content-type": f"multipart/form-data; boundary={BOUNDARY}"}
        if content_length is not None:
            self.headers["content-length"] = str(content_length)
        self._chunks = chunks
        self.consumed = 0

    async def stream(self):
        for chunk in self._chunks:
            self.consumed += len(chunk)
            yield chunk


def _head(filename="a.mp4", extra=b"") -> bytes:
    return (
        extra
        + f"--{BOUNDARY}\r\n".encode()
        + f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        + b"Content-Type: video/mp4\r\n\r\n"
    )


TAIL = f"\r\n--{BOUNDARY}--\r\n".encode()


def _zeros(total: int, chunk: int = MIB):
    sent = 0
    while sent < total:
        n = min(chunk, total - sent)
        sent += n
        yield b"\0" * n


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    d = tmp_path / "tmp"
    d.mkdir()
    return d


@pytest.fixture
def receiver(tmp_dir):
    from app.api.upload import UploadReceiver

    counter = iter(range(10_000))
    return UploadReceiver(LIMIT, lambda: tmp_dir / f"u{next(counter)}")


def _run(coro):
    return asyncio.run(coro)


def test_ut_upl_01_aborts_at_the_first_byte_over_the_limit(receiver, tmp_dir):
    def body():
        yield _head()
        yield from _zeros(LIMIT + 1)
        yield TAIL

    req = FakeRequest(body())
    with pytest.raises(FileTooLarge) as err:
        _run(receiver.receive(req))
    assert err.value.details["max_bytes"] == LIMIT
    assert list(tmp_dir.iterdir()) == []  # tmp file removed
    assert req.consumed <= LIMIT + 1 + 2 * MIB + len(_head())  # stopped, not drained


def test_receiver_accepts_the_exact_limit(receiver, tmp_dir):
    def body():
        yield _head(
            extra=f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="client_request_id"\r\n\r\nr9\r\n'.encode()
        )
        yield from _zeros(LIMIT)
        yield TAIL

    got = _run(receiver.receive(FakeRequest(body())))
    assert (
        got.size == LIMIT and got.filename == "a.mp4" and got.client_request_id == "r9"
    )
    assert got.path.stat().st_size == LIMIT


def test_receiver_header_over_limit_reads_nothing(receiver, tmp_dir):
    req = FakeRequest([_head(), b"x", TAIL], content_length=LIMIT + 1)
    with pytest.raises(FileTooLarge):
        _run(receiver.receive(req))
    assert req.consumed == 0 and list(tmp_dir.iterdir()) == []


def test_receiver_short_body_is_incomplete(receiver, tmp_dir):
    chunks = [_head(), b"abc" * 1000]  # the closing boundary never arrives
    with pytest.raises(UploadIncomplete):
        _run(receiver.receive(FakeRequest(chunks)))
    assert list(tmp_dir.iterdir()) == []


def test_receiver_short_body_against_content_length(receiver, tmp_dir):
    chunks = [_head(), b"abc" * 10, TAIL]
    declared = sum(len(c) for c in chunks) + 500
    with pytest.raises(UploadIncomplete):
        _run(receiver.receive(FakeRequest(chunks, content_length=declared)))
    assert list(tmp_dir.iterdir()) == []


def test_receiver_without_file_part_is_malformed(receiver, tmp_dir):
    chunks = [
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="client_request_id"\r\n\r\nr1\r\n--{BOUNDARY}--\r\n'.encode()
    ]
    with pytest.raises(MalformedRequest):
        _run(receiver.receive(FakeRequest(chunks)))
    assert list(tmp_dir.iterdir()) == []


def test_receiver_not_multipart_is_malformed(receiver):
    req = FakeRequest([b"{}"])
    req.headers["content-type"] = "application/json"
    with pytest.raises(MalformedRequest):
        _run(receiver.receive(req))
