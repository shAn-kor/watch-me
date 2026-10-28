"""UT-STO-01..03: LocalStorage (07 section 3.3)."""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path

import pytest

from app.storage.base import Storage, StorageError, StorageFull


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "root"
    r.mkdir()
    return r


@pytest.fixture
def store(root):
    from app.storage.local import LocalStorage

    return LocalStorage(root)


def _src(tmp_path: Path, name: str = "src.bin", data: bytes = b"hello") -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _all_files(path: Path) -> list[Path]:
    return [p for p in path.rglob("*") if p.is_file()]


def test_ut_sto_01_traversal_rejected(store, root, tmp_path):
    assert isinstance(store, Storage)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    src = _src(tmp_path)
    bad_keys = ["../x", "/etc/passwd", "a/../../b", "link/x", "", "a\\..\\b", "a/\0b", ".."]
    for key in bad_keys:
        with pytest.raises(StorageError):
            store.put_file(key, src)
        with pytest.raises(StorageError):
            store.open_path(key)
    assert list(outside.iterdir()) == []
    assert not (tmp_path / "x").exists()
    assert not (tmp_path / "b").exists()
    assert _all_files(root) == []


def test_ut_sto_01_traversal_rejected_for_other_ops(store):
    for op in (store.exists, store.size, store.delete, store.delete_prefix, store.list_prefix):
        with pytest.raises(StorageError):
            op("../x")


def test_ut_sto_01_valid_key_opens(store, root, tmp_path):
    store.put_file("dogs/d1/clips/c1/original.mp4", _src(tmp_path))
    p = store.open_path("dogs/d1/clips/c1/original.mp4")
    assert p.is_absolute()
    assert p.read_bytes() == b"hello"
    assert store.exists("dogs/d1/clips/c1/original.mp4")
    assert store.size("dogs/d1/clips/c1/original.mp4") == 5
    assert not store.exists("dogs/none")
    store.delete("dogs/d1/clips/c1/original.mp4")
    store.delete("dogs/d1/clips/c1/original.mp4")  # missing is fine
    assert not store.exists("dogs/d1/clips/c1/original.mp4")


def test_ut_sto_02_prefix_ops(store, tmp_path):
    for n in ("a", "b", "c"):
        store.put_file(f"dogs/d1/clips/{n}.bin", _src(tmp_path, n))
    store.put_file("dogs/d2/keep.bin", _src(tmp_path, "k"))
    assert sorted(store.list_prefix("dogs/d1")) == [
        "dogs/d1/clips/a.bin",
        "dogs/d1/clips/b.bin",
        "dogs/d1/clips/c.bin",
    ]
    assert store.delete_prefix("dogs/d1") == 3
    assert store.list_prefix("dogs/d1") == []
    assert store.list_prefix("dogs/d2") == ["dogs/d2/keep.bin"]
    assert store.delete_prefix("dogs/d1") == 0


def test_ut_sto_02_prefix_is_path_segment_based(store, tmp_path):
    store.put_file("dogs/d1/x.bin", _src(tmp_path))
    store.put_file("dogs/d10/x.bin", _src(tmp_path, "y"))
    assert store.list_prefix("dogs/d1") == ["dogs/d1/x.bin"]
    assert store.delete_prefix("dogs/d1") == 1
    assert store.exists("dogs/d10/x.bin")


def test_ut_sto_02_partial_put_leaves_no_final_file(store, root, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError(errno.EIO, "copy failed")

    monkeypatch.setattr(shutil, "copyfile", boom)
    with pytest.raises(StorageError):
        store.put_file("dogs/d1/x.bin", _src(tmp_path))
    assert not store.exists("dogs/d1/x.bin")
    assert _all_files(root / "dogs") == [] if (root / "dogs").exists() else True
    assert _all_files(root / "tmp") == []


def test_ut_sto_02_put_replaces_atomically_and_keeps_src(store, tmp_path):
    src = _src(tmp_path, data=b"one")
    store.put_file("k/a.bin", src)
    store.put_file("k/a.bin", _src(tmp_path, "s2", b"second"))
    assert store.open_path("k/a.bin").read_bytes() == b"second"
    assert src.exists()


def test_ut_sto_02_new_tmp_path_is_under_tmp_same_volume(store, root):
    p = store.new_tmp_path()
    assert p.parent == (root / "tmp").resolve() or p.parent == root / "tmp"
    assert p.parent.is_dir()
    assert not p.exists()
    assert store.new_tmp_path() != p
    assert os.stat(p.parent).st_dev == os.stat(root).st_dev


def test_ut_sto_03_enospc_maps_to_storage_full(store, tmp_path, monkeypatch):
    def full(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(shutil, "copyfile", full)
    with pytest.raises(StorageFull):
        store.put_file("dogs/d1/x.bin", _src(tmp_path))
    assert not store.exists("dogs/d1/x.bin")
