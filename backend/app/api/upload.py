"""UploadReceiver: streams one multipart upload to a tmp file (01 section 5.3, 06).

The api never loads the body into memory. The receiver

1. rejects a `Content-Length` over the limit before it reads a byte,
2. feeds the body to the multipart parser chunk by chunk,
3. counts the file bytes and stops at the first byte over the limit,
4. removes the tmp file on every failure.

The caller (the clip route) has already run the service prechecks, so a body is read
only for a request that may succeed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.errors import FileTooLarge, MalformedRequest, UploadIncomplete

MAX_FIELD_BYTES = 256


class StreamingRequest(Protocol):
    headers: Any

    def stream(self) -> AsyncIterator[bytes]: ...


@dataclass(frozen=True, slots=True)
class ReceivedUpload:
    path: Path
    filename: str
    size: int
    client_request_id: str | None


class _PartState:
    """Collects the callbacks of the multipart parser for one request."""

    def __init__(self) -> None:
        self.field_buf = bytearray()
        self.value_buf = bytearray()
        self.headers: dict[bytes, bytes] = {}
        self.name: str | None = None
        self.filename: str | None = None
        self.is_file = False
        self.capture_file = False
        self.file_seen = False
        self.pending: list[bytes] = []
        self.size = 0
        self.field_data = bytearray()
        self.fields: dict[str, str] = {}
        self.ended = False

    # ------------------------------------------------------- callbacks
    def on_part_begin(self) -> None:
        self.headers = {}
        self.name = self.filename = None
        self.is_file = self.capture_file = False
        self.field_data = bytearray()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self.field_buf += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self.value_buf += data[start:end]

    def on_header_end(self) -> None:
        self.headers[bytes(self.field_buf).lower()] = bytes(self.value_buf)
        self.field_buf = bytearray()
        self.value_buf = bytearray()

    def on_headers_finished(self) -> None:
        disposition = self.headers.get(b"content-disposition", b"")
        _value, options = parse_options_header(disposition)
        raw_name = options.get(b"name")
        raw_file = options.get(b"filename")
        self.name = (
            raw_name.decode("utf-8", "replace") if raw_name is not None else None
        )
        if raw_file is not None:
            self.is_file = True
            self.filename = raw_file.decode("utf-8", "replace")
        if self.is_file and self.name == "file" and not self.file_seen:
            self.file_seen = True
            self.capture_file = True

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        if self.capture_file:
            self.size += len(chunk)
            self.pending.append(chunk)
        elif not self.is_file and len(self.field_data) < MAX_FIELD_BYTES:
            self.field_data += chunk

    def on_part_end(self) -> None:
        if not self.is_file and self.name is not None:
            self.fields[self.name] = bytes(self.field_data).decode("utf-8", "replace")

    def on_end(self) -> None:
        self.ended = True


class UploadReceiver:
    def __init__(self, max_bytes: int, new_tmp_path: Callable[[], Path]):
        self._max = max_bytes
        self._new_tmp_path = new_tmp_path

    async def receive(self, request: StreamingRequest) -> ReceivedUpload:
        headers = request.headers
        content_type = headers.get("content-type", "")
        mime, options = parse_options_header(content_type.encode("latin-1", "replace"))
        boundary = options.get(b"boundary")
        if mime.lower() != b"multipart/form-data" or not boundary:
            raise MalformedRequest()

        declared = self._declared_length(headers.get("content-length"))
        if declared is not None and declared > self._max:
            raise FileTooLarge(details={"max_bytes": self._max})

        state = _PartState()
        parser = MultipartParser(
            boundary,
            {
                "on_part_begin": state.on_part_begin,
                "on_header_field": state.on_header_field,
                "on_header_value": state.on_header_value,
                "on_header_end": state.on_header_end,
                "on_headers_finished": state.on_headers_finished,
                "on_part_data": state.on_part_data,
                "on_part_end": state.on_part_end,
                "on_end": state.on_end,
            },
        )
        path = self._new_tmp_path()
        fh = None
        received = 0
        try:
            fh = await run_in_threadpool(open, path, "wb")
            try:
                async for chunk in request.stream():
                    received += len(chunk)
                    try:
                        parser.write(chunk)
                    except Exception as exc:  # parser raises its own error types
                        raise MalformedRequest() from exc
                    if state.size > self._max:
                        raise FileTooLarge(details={"max_bytes": self._max})
                    if state.pending:
                        data = b"".join(state.pending)
                        state.pending.clear()
                        await run_in_threadpool(fh.write, data)
            except ClientDisconnect as exc:
                raise UploadIncomplete() from exc
            try:
                parser.finalize()
            except Exception as exc:  # noqa: BLE001
                raise MalformedRequest() from exc
            if not state.ended:
                raise UploadIncomplete()
            if declared is not None and received < declared:
                raise UploadIncomplete()
            if not state.file_seen:
                raise MalformedRequest()
            await run_in_threadpool(fh.close)
            fh = None
            request_id = state.fields.get("client_request_id")
            return ReceivedUpload(
                path=path,
                filename=state.filename or "",
                size=state.size,
                client_request_id=request_id,
            )
        except BaseException:
            if fh is not None:
                try:
                    fh.close()
                except OSError:
                    pass
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @staticmethod
    def _declared_length(raw: str | None) -> int | None:
        if raw is None:
            return None
        try:
            value = int(raw.strip())
        except ValueError:
            raise MalformedRequest() from None
        if value < 0:
            raise MalformedRequest()
        return value
