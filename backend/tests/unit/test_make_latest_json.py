"""The update manifest of a release."""

import importlib.util
import json
import os

import pytest

_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".ci", "make_latest_json.py")
_spec = importlib.util.spec_from_file_location("make_latest_json", _path)
latest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(latest)

FILES = {"App_aarch64.app.tar.gz": "", "App_aarch64.app.tar.gz.sig": "SIGARM\n", "App_x64.app.tar.gz": "",
         "App_x64.app.tar.gz.sig": "SIGINTEL", "App_5.0.0_x64_en-US.msi": "", "App_5.0.0_x64_en-US.msi.sig": "SIGWIN",
         "App_5.0.0_aarch64.dmg": "", "other.txt": ""}


def write(folder, files):
    for name, content in files.items():
        (folder / name).write_text(content)
    (folder.parent / "notes.md").write_text("### New\n- Things\n")



def test_every_signed_platform_is_listed(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    write(out, FILES)
    latest.main(str(out), "v5.0.0", "5.0.0", str(tmp_path / "notes.md"))
    data = json.loads((out / "latest.json").read_text())
    assert data["version"] == "5.0.0" and data["notes"] == "### New\n- Things"
    assert set(data["platforms"]) == {"darwin-aarch64", "darwin-x86_64", "windows-x86_64"}
    arm = data["platforms"]["darwin-aarch64"]
    assert arm["signature"] == "SIGARM"
    assert arm["url"] == "https://github.com/retotito/UltrastarCreatorTool/releases/download/v5.0.0/App_aarch64.app.tar.gz"


def test_an_unsigned_file_is_not_offered():
    data = latest.manifest({"App_x64.app.tar.gz"}, lambda name: "", "v1", "1", "", "now")
    assert data["platforms"] == {}


def test_a_missing_platform_leaves_the_others():
    names = {"App_5_x64_en-US.msi", "App_5_x64_en-US.msi.sig"}
    assert set(latest.manifest(names, lambda name: "S", "v1", "1", "", "now")["platforms"]) == {"windows-x86_64"}


def test_names_with_spaces_become_valid_links():
    names = {"My App.msi", "My App.msi.sig"}
    url = latest.manifest(names, lambda name: "S", "v1", "1", "", "now")["platforms"]["windows-x86_64"]["url"]
    assert url.endswith("/v1/My%20App.msi")


def test_a_release_without_signed_files_fails(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (tmp_path / "notes.md").write_text("x")
    with pytest.raises(SystemExit):
        latest.main(str(out), "v1", "1", str(tmp_path / "notes.md"))
