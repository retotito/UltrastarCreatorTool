import os

import pytest

from services.hf_cache import replace_snapshot_links, store_plain_files


def _cache_with_link(tmp_path):
    repo = tmp_path / "models--owner--name"
    blob = repo / "blobs" / "abc123"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"weights")
    snap = repo / "snapshots" / "rev1" / "sub"
    snap.mkdir(parents=True)
    link = snap / "model.bin"
    os.symlink(os.path.join("..", "..", "..", "blobs", "abc123"), link)
    return blob, link


def test_links_become_plain_files_with_the_blob(tmp_path):
    blob, link = _cache_with_link(tmp_path)
    assert replace_snapshot_links(str(tmp_path)) == 1
    assert not os.path.islink(link)
    assert link.read_bytes() == b"weights"
    assert os.path.samefile(link, blob)   # a hard link: no second copy on disk
    assert replace_snapshot_links(str(tmp_path)) == 0


def test_dangling_link_is_left(tmp_path):
    blob, link = _cache_with_link(tmp_path)
    blob.unlink()
    assert replace_snapshot_links(str(tmp_path)) == 0
    assert os.path.islink(link)


def test_missing_cache(tmp_path):
    assert replace_snapshot_links(str(tmp_path / "nothing")) == 0


def test_plain_files_only_on_windows(monkeypatch):
    file_download = pytest.importorskip("huggingface_hub.file_download")
    monkeypatch.setattr(file_download, "are_symlinks_supported", file_download.are_symlinks_supported)
    assert store_plain_files("darwin") is False
    assert store_plain_files("win32") is True
    assert file_download.are_symlinks_supported("anywhere") is False
