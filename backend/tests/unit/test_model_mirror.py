"""Models come from our own repository, checked against the original's size and SHA-256."""

import hashlib

import huggingface_hub
import pytest

from services import model_mirror as mm


@pytest.fixture
def model(tmp_path):
    data = b"model bytes"
    return {"path": "m/m.onnx", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "original_repo": "someone/model", "original_file": "m.onnx", "original_revision": "abc",
            "_data": data, "_dir": tmp_path}


def fake_hub(monkeypatch, model, data=None, cached=None):
    calls = []

    def download(repo, filename, revision=None):
        calls.append((repo, filename, revision))
        path = model["_dir"] / f"{len(calls)}-{filename.replace('/', '_')}"
        path.write_bytes(model["_data"] if data is None else data)
        return str(path)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache",
                        lambda repo, filename, revision=None: (cached or {}).get(repo))
    return calls


def test_downloads_only_from_our_repository(monkeypatch, model):
    calls = fake_hub(monkeypatch, model)
    mm.fetch(model)
    assert calls == [(mm.MODEL_REPO, "m/m.onnx", mm.MODEL_REVISION)]


def test_a_wrong_file_is_refused(monkeypatch, model):
    fake_hub(monkeypatch, model, data=b"something else")
    with pytest.raises(mm.ModelUnavailable):
        mm.fetch(model)


@pytest.mark.parametrize("repo", [mm.MODEL_REPO, "someone/model"])
def test_a_cached_copy_needs_no_download(monkeypatch, model, repo):
    cached = model["_dir"] / "cached.onnx"
    cached.write_bytes(model["_data"])
    calls = fake_hub(monkeypatch, model, cached={repo: str(cached)})
    assert mm.fetch(model) == str(cached) and mm.cached_path(model) == str(cached) and calls == []


def test_an_empty_cached_file_is_not_used(monkeypatch, model):
    empty = model["_dir"] / "empty.onnx"
    empty.write_bytes(b"")
    calls = fake_hub(monkeypatch, model, cached={mm.MODEL_REPO: str(empty)})
    assert mm.cached_path(model) is None
    mm.fetch(model)
    assert len(calls) == 1
