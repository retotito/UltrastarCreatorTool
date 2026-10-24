"""Sung notes from the vocals with GAME (openvpi's Generative Adaptive MIDI Extractor, its released ONNX models).

Per line of lyrics, the line's audio and the syllable starts (as known note boundaries) go in; notes (start, end,
voiced, MIDI pitch) come out. Each syllable then takes its longest voiced note, so a note-level model decides the
syllable's pitch instead of a median over a frame-wise pitch curve.

As Tune Studio runs it (MIT, © 2026 Nico Franke: apps/studio/native/src/game.rs, electron/charting/notes.ts).
The model: github.com/openvpi/GAME, release v1.0.3, CC BY-NC-SA 4.0.
"""

import hashlib
import os
import shutil
import tempfile
import zipfile
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

SAMPLE_RATE = 44100
STEPS = 8                 # the segmenter's diffusion steps
PAD_SEC = 0.2             # audio around a line
MAX_SYLLABLE_SEC = 3.0
LANGUAGES = {"en": 1}     # GAME's own ids (its config.json); every other language is "universal" (0)

# The release as Tune Studio pins it (apps/studio/electron/models/models.ts): the zip and each file it needs.
MODEL_VERSION = "1.0.3"
MODEL_URL = "https://github.com/openvpi/GAME/releases/download/v1.0.3/GAME-1.0.3-large-onnx.zip"
MODEL_SHA256 = "8a5480539fe7d995800dc0efe149b83a1cd4f4e4a36aa2a1f7665f1765dcac08"
MODEL_BYTES = 361_619_205
MODEL_ZIP_FOLDER = "GAME-1.0.3-large-onnx"
MODEL_FILES = {
    "encoder.onnx": (80_398_908, "fbda7df8791d5cafd02ed33c65f9926c5514c750278c27fb8a59259b4c1d7464"),
    "segmenter.onnx": (159_935_922, "bf05ba683f47f605bc154519032bee0141d3630febccb40e9545ab4a92b28e66"),
    "estimator.onnx": (153_459_702, "0d4a6e13bf475f79967e252b401bb5f317aa6b96bbe6665d5f8b14b42b179926"),
    "dur2bd.onnx": (2_632, "49d10d1ea186e43c51fd2c51cedb01a3852d363f1c7056ae77df50f7e8dd0996"),
    "bd2dur.onnx": (4_569, "6672d56b00f27a20e9bfaa92801c15e394bb520e49031d3ed2515b0a6cf27402"),
}

_sessions: Dict[str, dict] = {}


def enabled() -> bool:
    """GAME decides syllable pitches unless ULTRASTAR_NOTE_ENGINE=fcpe (then FCPE's median does)."""
    return os.environ.get("ULTRASTAR_NOTE_ENGINE", "game").strip().lower() != "fcpe"


def model_folder(models_dir: str) -> str:
    return os.path.join(models_dir, f"game-{MODEL_VERSION}")


def is_downloaded(models_dir: str) -> bool:
    folder = model_folder(models_dir)
    return all(os.path.isfile(os.path.join(folder, name)) and os.path.getsize(os.path.join(folder, name)) == size
               for name, (size, _) in MODEL_FILES.items())


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(models_dir: str, on_progress: Optional[Callable[[int, int], None]] = None) -> str:
    """Download and unpack the model (checked: the zip's and every file's SHA-256); returns its folder."""
    import urllib.request
    folder = model_folder(models_dir)
    if is_downloaded(models_dir):
        return folder
    os.makedirs(models_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="game-", dir=models_dir)
    try:
        archive = os.path.join(work, "game.zip")
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response, open(archive, "wb") as out:
            done = 0
            while block := response.read(1 << 20):
                out.write(block)
                done += len(block)
                if on_progress:
                    on_progress(done, MODEL_BYTES)
        if _sha256(archive) != MODEL_SHA256:
            raise RuntimeError("The note model download is damaged (checksum mismatch). Try again.")
        unpacked = os.path.join(work, "files")
        os.makedirs(unpacked)
        with zipfile.ZipFile(archive) as z:
            for name, (size, sha) in MODEL_FILES.items():   # only the known files, by their known names
                target = os.path.join(unpacked, name)
                with z.open(f"{MODEL_ZIP_FOLDER}/{name}") as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if os.path.getsize(target) != size or _sha256(target) != sha:
                    raise RuntimeError(f"The note model's {name} isn't the expected one.")
        shutil.rmtree(folder, ignore_errors=True)
        os.replace(unpacked, folder)
        return folder
    finally:
        shutil.rmtree(work, ignore_errors=True)


def apply(models_dir: str, vocal_path: str, syllable_timings: list, language: str = "en") -> int:
    """Set GAME's pitch on the syllables that have none yet (melisma parts bring their own); returns how many.
    Does nothing when the model isn't downloaded or GAME is turned off."""
    if not enabled() or not is_downloaded(models_dir) or not syllable_timings:
        return 0
    import librosa
    samples, _ = librosa.load(vocal_path, sr=SAMPLE_RATE, mono=True)
    pitches = syllable_pitches(model_folder(models_dir), samples, syllable_timings, language)
    count = 0
    for timing, pitch in zip(syllable_timings, pitches):
        if pitch is not None and not timing.get("pitch") and not timing.get("is_rap"):
            timing["pitch"] = int(round(pitch))
            count += 1
    return count


def _load(folder: str) -> dict:
    if folder not in _sessions:
        import onnxruntime as ort
        _sessions[folder] = {name: ort.InferenceSession(os.path.join(folder, f"{name}.onnx"),
                                                         providers=["CPUExecutionProvider"])
                             for name in ("encoder", "segmenter", "estimator", "dur2bd", "bd2dur")}
    return _sessions[folder]


def extract(folder: str, waveform: np.ndarray, known: Sequence[float], language: str = "en") -> List[tuple]:
    """GAME's notes [(start, end, voiced, midi)] for one stretch of 44.1 kHz audio, with `known` note durations
    (the stretches between syllable starts) as boundaries it keeps."""
    s = _load(folder)
    duration = len(waveform) / SAMPLE_RATE
    x_seg, x_est, mask_t = s["encoder"].run(None, {"waveform": waveform[None].astype(np.float32),
                                                     "duration": np.array([duration], np.float32)})
    frames = mask_t.shape[1]
    known = [d for d in known if d > 0] or [duration]
    if len(known) > 1:
        known_bd = s["dur2bd"].run(None, {"durations": np.array([known], np.float32), "maskT": mask_t})[0]
    else:
        known_bd = np.zeros((1, frames), bool)
    known_bd = known_bd & mask_t
    bd = known_bd.copy()
    for i in range(STEPS):
        bd = s["segmenter"].run(None, {
            "x_seg": x_seg, "language": np.array([LANGUAGES.get(language, 0)], np.int64),
            "known_boundaries": known_bd, "prev_boundaries": bd, "t": np.array([i / STEPS], np.float32),
            "maskT": mask_t, "threshold": np.array(0.2, np.float32), "radius": np.array(2, np.int64)})[0]
    durations, mask_n = s["bd2dur"].run(None, {"boundaries": bd, "maskT": mask_t})
    presence, scores = s["estimator"].run(None, {"x_est": x_est, "boundaries": bd, "maskT": mask_t,
                                                 "maskN": mask_n, "threshold": np.array(0.2, np.float32)})
    notes, t = [], 0.0
    for k in range(mask_n.shape[1]):
        if not mask_n[0, k]:
            break
        d = float(durations[0, k])
        notes.append((t, t + d, bool(presence[0, k]), float(scores[0, k])))
        t += d
    return notes


def syllable_pitches(folder: str, samples: np.ndarray, syllable_timings: list,
                     language: str = "en") -> List[Optional[float]]:
    """GAME's pitch per syllable (its longest voiced note inside the syllable), None where it found none.
    Runs line by line, like Tune Studio."""
    lines: Dict[int, List[int]] = {}
    for i, t in enumerate(syllable_timings):
        lines.setdefault(t.get("line_index", 0), []).append(i)
    out: List[Optional[float]] = [None] * len(syllable_timings)
    total = len(samples) / SAMPLE_RATE
    for members in lines.values():
        spans = [syllable_timings[i] for i in members]
        ends = [min(t["end"], t["start"] + MAX_SYLLABLE_SEC) for t in spans]
        a, b = max(0.0, spans[0]["start"] - PAD_SEC), min(total, ends[-1] + PAD_SEC)
        if b - a < 0.1:
            continue
        cuts = sorted({a, b, *[t["start"] for t in spans if a < t["start"] < b]})
        known = [y - x for x, y in zip(cuts, cuts[1:]) if y > x]
        notes = extract(folder, samples[int(a * SAMPLE_RATE):int(b * SAMPLE_RATE)], known, language)
        for i, t, end in zip(members, spans, ends):
            mine = [n for n in notes if n[2] and t["start"] - 0.02 <= a + (n[0] + n[1]) / 2 < end]
            if mine:
                out[i] = max(mine, key=lambda n: n[1] - n[0])[3]
    return out
