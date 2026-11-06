"""Exporting a song to a folder or file the user chose."""

import os

import pytest

from services.song_export import ExportTargetError, FolderExists, export_file, export_folder


def test_a_song_folder_holds_text_and_copies(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"audio")
    out = tmp_path / "out"
    out.mkdir()
    path = export_folder(str(out), "A - T", [("A - T.txt", b"chart\r\n"), ("A - T.mp3", str(source))])
    assert path == str(out / "A - T")
    assert (out / "A - T" / "A - T.txt").read_bytes() == b"chart\r\n"   # line endings stay
    assert (out / "A - T" / "A - T.mp3").read_bytes() == b"audio"
    assert os.listdir(out) == ["A - T"]                                  # nothing temporary left


def test_an_existing_folder_is_kept_unless_replacing(tmp_path):
    export_folder(str(tmp_path), "A - T", [("old.txt", b"old")])
    with pytest.raises(FolderExists):
        export_folder(str(tmp_path), "A - T", [("new.txt", b"new")])
    assert os.listdir(tmp_path / "A - T") == ["old.txt"]
    export_folder(str(tmp_path), "A - T", [("new.txt", b"new")], replace=True)
    assert os.listdir(tmp_path / "A - T") == ["new.txt"]
    assert os.listdir(tmp_path) == ["A - T"]


def test_a_failed_export_leaves_the_old_folder(tmp_path):
    export_folder(str(tmp_path), "A - T", [("old.txt", b"old")])
    with pytest.raises(ExportTargetError):
        export_folder(str(tmp_path), "A - T", [("new.txt", str(tmp_path / "missing.mp3"))], replace=True)
    assert (tmp_path / "A - T" / "old.txt").read_bytes() == b"old"
    assert os.listdir(tmp_path) == ["A - T"]


@pytest.mark.parametrize("folder", ["", "relative/path", "/no/such/folder/here"])
def test_only_an_existing_absolute_folder_is_used(folder):
    with pytest.raises(ExportTargetError):
        export_folder(folder, "A - T", [])


def test_a_single_file_replaces_the_target(tmp_path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"old")
    export_file(str(target), b"new")
    assert target.read_bytes() == b"new" and os.listdir(tmp_path) == ["a.txt"]


@pytest.mark.parametrize("path", ["", "a.txt", "/no/such/folder/a.txt"])
def test_a_single_file_needs_a_real_location(path):
    with pytest.raises(ExportTargetError):
        export_file(path, b"x")
