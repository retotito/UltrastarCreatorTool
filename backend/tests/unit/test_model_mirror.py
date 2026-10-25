"""Models with a fallback to our mirror: only when the original is gone, and only the expected file."""

import hashlib

import huggingface_hub
import pytest
from huggingface_hub import errors

from services import model_mirror as mm


@pytest.fixture
def model(tmp_path):
    data = b"model bytes"
    return {"repo": "someone/model", "file": "m.onnx", "revision": "abc", "mirror_file": "m/m.onnx",
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "_data": data, "_dir": tmp_path}


def fake_hub(monkeypatch, model, original_error=None, mirror_data=None):
    calls = []

    def download(repo, filename, revision=None):
        calls.append(repo)
        if repo == model["repo"]:
            if original_error:
                raise original_error
            data = model["_data"]
        else:
            data = model["_data"] if mirror_data is None else mirror_data
        path = model["_dir"] / f"{len(calls)}-{filename.replace('/', '_')}"
        path.write_bytes(data)
        return str(path)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", lambda *a, **k: None)
    return calls


def gone_error():
    return errors.RepositoryNotFoundError("404 Repository Not Found", response=None)


def test_the_original_is_used_when_it_is_there(monkeypatch, model):
    calls = fake_hub(monkeypatch, model)
    assert mm.fetch(model).endswith("m.onnx") and calls == ["someone/model"]


def test_the_mirror_steps_in_when_the_original_is_gone(monkeypatch, model):
    calls = fake_hub(monkeypatch, model, original_error=gone_error())
    mm.fetch(model)
    assert calls == ["someone/model", mm.MIRROR_REPO]


def test_no_mirror_when_the_network_is_down(monkeypatch, model):
    calls = fake_hub(monkeypatch, model, original_error=ConnectionError("offline"))
    with pytest.raises(ConnectionError):
        mm.fetch(model)
    assert calls == ["someone/model"]


def test_a_wrong_file_on_the_mirror_is_refused(monkeypatch, model):
    fake_hub(monkeypatch, model, original_error=gone_error(), mirror_data=b"something else")
    with pytest.raises(mm.ModelUnavailable):
        mm.fetch(model)


def test_a_cached_copy_needs_no_network(monkeypatch, model):
    cached = model["_dir"] / "cached.onnx"
    cached.write_bytes(model["_data"])
    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache",
                        lambda repo, filename, revision=None: str(cached) if repo == mm.MIRROR_REPO else None)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", lambda *a, **k: pytest.fail("no download expected"))
    assert mm.fetch(model) == str(cached) and mm.cached_path(model) == str(cached)
