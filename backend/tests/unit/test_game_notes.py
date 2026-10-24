"""GAME notes: the model download is checked, and each syllable takes its longest voiced note."""

import hashlib
import zipfile

import numpy as np
import pytest

import services.game_notes as game


def syl(start, end, line=0, **extra):
    return {"syllable": "la", "start": start, "end": end, "line_index": line, **extra}


@pytest.fixture
def fake_release(tmp_path, monkeypatch):
    """A tiny release zip in the real layout, with the constants pointing at it."""
    content = {"encoder.onnx": b"enc", "segmenter.onnx": b"seg", "estimator.onnx": b"est",
               "dur2bd.onnx": b"d2b", "bd2dur.onnx": b"b2d"}
    archive = tmp_path / "game.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name, data in content.items():
            z.writestr(f"{game.MODEL_ZIP_FOLDER}/{name}", data)
        z.writestr(f"{game.MODEL_ZIP_FOLDER}/../evil.onnx", b"x")   # never unpacked: only known names are
    monkeypatch.setattr(game, "MODEL_URL", archive.as_uri())
    monkeypatch.setattr(game, "MODEL_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(game, "MODEL_BYTES", archive.stat().st_size)
    monkeypatch.setattr(game, "MODEL_FILES", {n: (len(d), hashlib.sha256(d).hexdigest()) for n, d in content.items()})
    return tmp_path / "models"


class TestDownload:
    def test_installs_the_checked_files(self, fake_release):
        assert not game.is_downloaded(str(fake_release))
        folder = game.download(str(fake_release))
        assert game.is_downloaded(str(fake_release))
        assert sorted(p.name for p in (fake_release / f"game-{game.MODEL_VERSION}").iterdir()) == sorted(game.MODEL_FILES)
        assert folder.endswith(f"game-{game.MODEL_VERSION}")
        assert [p.name for p in fake_release.iterdir()] == [f"game-{game.MODEL_VERSION}"]   # no leftovers

    def test_a_damaged_download_is_refused(self, fake_release, monkeypatch):
        monkeypatch.setattr(game, "MODEL_SHA256", "0" * 64)
        with pytest.raises(RuntimeError, match="damaged"):
            game.download(str(fake_release))
        assert not game.is_downloaded(str(fake_release))

    def test_an_unexpected_file_is_refused(self, fake_release, monkeypatch):
        files = dict(game.MODEL_FILES)
        files["encoder.onnx"] = (3, "0" * 64)
        monkeypatch.setattr(game, "MODEL_FILES", files)
        with pytest.raises(RuntimeError, match="encoder.onnx"):
            game.download(str(fake_release))
        assert not game.is_downloaded(str(fake_release))


class TestSyllablePitches:
    def test_each_syllable_takes_its_longest_voiced_note(self, monkeypatch):
        requests = []

        def extract(folder, waveform, known, language):
            requests.append((round(len(waveform) / game.SAMPLE_RATE, 2), [round(k, 2) for k in known], language))
            # times relative to the line's audio, which starts 0.2 s before the first syllable (at 0.8 s)
            return [(0.2, 0.3, True, 50.0), (0.3, 0.6, True, 52.4),   # syllable 1: the longer one wins
                    (0.7, 1.0, False, 70.0),                          # syllable 2: unvoiced only
                    (1.2, 1.4, True, 64.0)]                           # syllable 3
        monkeypatch.setattr(game, "extract", extract)
        samples = np.zeros(5 * game.SAMPLE_RATE, np.float32)
        pitches = game.syllable_pitches("folder", samples, [syl(1.0, 1.4), syl(1.5, 1.9), syl(2.0, 2.3)], "it")
        assert pitches == [52.4, None, 64.0]
        assert requests == [(1.7, [0.2, 0.5, 0.5, 0.5], "it")]   # one request per line, syllable starts known

    def test_apply_leaves_melisma_parts_and_rap_alone(self, monkeypatch, tmp_path):
        monkeypatch.setattr(game, "is_downloaded", lambda models_dir: True)
        monkeypatch.setattr(game, "syllable_pitches", lambda *a: [51.6, 70.0, 60.0, None])
        import librosa
        monkeypatch.setattr(librosa, "load", lambda *a, **k: (np.zeros(10), game.SAMPLE_RATE))
        timings = [syl(0, 1), syl(1, 2, pitch=64), syl(2, 3, is_rap=True), syl(3, 4)]
        assert game.apply(str(tmp_path), "vocals.wav", timings, "en") == 1
        assert [t.get("pitch") for t in timings] == [52, 64, None, None]

    def test_turned_off_or_not_downloaded_does_nothing(self, monkeypatch, tmp_path):
        timings = [syl(0, 1)]
        assert game.apply(str(tmp_path), "vocals.wav", timings) == 0   # not downloaded
        monkeypatch.setenv("ULTRASTAR_NOTE_ENGINE", "fcpe")
        monkeypatch.setattr(game, "is_downloaded", lambda models_dir: True)
        assert game.apply(str(tmp_path), "vocals.wav", timings) == 0 and "pitch" not in timings[0]
