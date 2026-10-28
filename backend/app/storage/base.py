"""Storage protocol (06 sections 1 and 3.4). stdlib only.

Keys are relative, forward-slash paths such as `dogs/{dog_id}/clips/{clip_id}/original.mp4`.
`put_file` writes to `tmp/` then renames (atomic on one volume). Implemented by
`storage/local.py` (lane B).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


class StorageError(Exception):
    """Any storage failure (write, delete, traversal attempt)."""


class StorageFull(StorageError):
    """Disk full. Maps to `storage_unavailable` 503 at upload and to a transient
    `transcode_failed` in the worker."""


@runtime_checkable
class Storage(Protocol):
    def put_file(self, key: str, src_path: Path) -> None:
        """Move or copy `src_path` into the store under `key` atomically."""
        ...

    def open_path(self, key: str) -> Path:
        """Absolute local path of `key` (raises `StorageError` for a bad key)."""
        ...

    def exists(self, key: str) -> bool: ...

    def size(self, key: str) -> int: ...

    def delete(self, key: str) -> None:
        """Delete one key; missing keys are not an error."""
        ...

    def delete_prefix(self, prefix: str) -> int:
        """Delete every key under `prefix`; returns the number of files removed."""
        ...

    def list_prefix(self, prefix: str) -> list[str]: ...

    def new_tmp_path(self) -> Path:
        """A fresh path under `tmp/` on the same volume as the store."""
        ...
