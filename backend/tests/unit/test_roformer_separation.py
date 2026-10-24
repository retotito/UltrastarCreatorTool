"""Mel-Band RoFormer separation: the spectrogram round trip, the chunk stitching, the model download, cancelling."""

import hashlib

import numpy as np
import pytest

import services.roformer_separation as rs


def test_stft_and_istft_give_the_chunk_back():
    x = np.random.default_rng(0).standard_normal(rs.CHUNK).astype(np.float32)
    assert np.abs(rs.istft(rs.stft(x)) - x).max() < 1e-4


def test_chunks_are_stitched_back_seamlessly(monkeypatch):
    # a model that returns the mix itself: the stitched result must be the input again (crossfades sum to 1)
    monkeypatch.setattr(rs, "run_chunk", lambda model, left, right: (left, right))
    n = int(rs.SAMPLE_RATE * 21.3)
    left = np.sin(np.arange(n) / 50).astype(np.float32)
    right = np.cos(np.arange(n) / 70).astype(np.float32)
    seen = []
    out_left, out_right = rs.separate("model", left, right, on_progress=seen.append)
    assert len(out_left) == n and np.abs(out_left - left).max() < 1e-5 and np.abs(out_right - right).max() < 1e-5
    assert seen[-1] == 100


def test_cancel_stops_between_chunks(monkeypatch):
    monkeypatch.setattr(rs, "run_chunk", lambda model, left, right: (left, right))
    with pytest.raises(rs.Cancelled):
        rs.separate("model", np.zeros(rs.CHUNK * 3, np.float32), np.zeros(rs.CHUNK * 3, np.float32), cancelled=lambda: True)


class TestDownload:
    def fake(self, tmp_path, monkeypatch, data=b"model bytes"):
        source = tmp_path / "model.onnx"
        source.write_bytes(data)
        monkeypatch.setattr(rs, "MODEL_URL", source.as_uri())
        monkeypatch.setattr(rs, "MODEL_SHA256", hashlib.sha256(data).hexdigest())
        monkeypatch.setattr(rs, "MODEL_BYTES", len(data))
        return str(tmp_path / "models")

    def test_installs_the_checked_model(self, tmp_path, monkeypatch):
        models = self.fake(tmp_path, monkeypatch)
        assert not rs.is_downloaded(models)
        assert rs.download(models) == rs.model_path(models) and rs.is_downloaded(models)

    def test_a_damaged_download_is_refused_and_removed(self, tmp_path, monkeypatch):
        models = self.fake(tmp_path, monkeypatch)
        monkeypatch.setattr(rs, "MODEL_SHA256", "0" * 64)
        with pytest.raises(RuntimeError, match="damaged"):
            rs.download(models)
        assert not rs.is_downloaded(models) and not (tmp_path / "models" / rs.MODEL_FILE).with_suffix(".onnx.part").exists()
