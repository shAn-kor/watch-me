"""LocalStorage: files under one root directory (06 sections 1 and 3.4).

stdlib only. Keys are relative forward-slash paths. Every key is checked
against the root after symlinks resolve, so `..`, absolute paths and symlink
escapes are rejected. `put_file` copies into `tmp/` then renames, so a failed
copy never leaves a final file.
"""

from __future__ import annotations

import errno
import os
import shutil
import uuid
from pathlib import Path

from app.storage.base import StorageError, StorageFull

TMP_DIR = "tmp"


class LocalStorage:
    def __init__(self, root: str | os.PathLike[str]):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._root = self._root.resolve()
        self._tmp = self._root / TMP_DIR
        self._tmp.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ key guard
    def _resolve(self, key: str) -> Path:
        if not isinstance(key, str) or not key:
            raise StorageError("empty storage key")
        if "\0" in key or "\\" in key or key.startswith("/"):
            raise StorageError(f"invalid storage key: {key!r}")
        parts = key.split("/")
        if any(p in ("", ".", "..") for p in parts):
            raise StorageError(f"invalid storage key: {key!r}")
        try:
            path = (self._root / key).resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise StorageError(f"invalid storage key: {key!r}") from exc
        if path == self._root or not path.is_relative_to(self._root):
            raise StorageError(f"storage key escapes the root: {key!r}")
        return path

    def _key_of(self, path: Path) -> str:
        return path.relative_to(self._root).as_posix()

    # ------------------------------------------------------------------ api
    def put_file(self, key: str, src_path: Path) -> None:
        dest = self._resolve(key)
        tmp = self.new_tmp_path()
        try:
            shutil.copyfile(src_path, tmp)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, dest)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise StorageFull("no space left on device") from exc
            raise StorageError(f"could not store {key!r}: {exc}") from exc
        finally:
            tmp.unlink(missing_ok=True)

    def open_path(self, key: str) -> Path:
        return self._resolve(key)

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def size(self, key: str) -> int:
        try:
            return self._resolve(key).stat().st_size
        except OSError as exc:
            raise StorageError(f"cannot stat {key!r}: {exc}") from exc

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(f"could not delete {key!r}: {exc}") from exc

    def list_prefix(self, prefix: str) -> list[str]:
        base = self._resolve(prefix.rstrip("/"))
        if base.is_file():
            return [self._key_of(base)]
        if not base.is_dir():
            return []
        return sorted(self._key_of(p) for p in base.rglob("*") if p.is_file())

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list_prefix(prefix)
        count = 0
        for key in keys:
            try:
                self._resolve(key).unlink(missing_ok=True)
                count += 1
            except OSError as exc:
                raise StorageError(f"could not delete {key!r}: {exc}") from exc
        base = self._resolve(prefix.rstrip("/"))
        if base.is_dir():
            # remove now-empty directories, deepest first
            for d in sorted((p for p in base.rglob("*") if p.is_dir()), reverse=True):
                try:
                    d.rmdir()
                except OSError:
                    pass
            try:
                base.rmdir()
            except OSError:
                pass
        return count

    def new_tmp_path(self) -> Path:
        self._tmp.mkdir(parents=True, exist_ok=True)
        return self._tmp / uuid.uuid4().hex
