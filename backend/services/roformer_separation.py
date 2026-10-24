"""Vocal separation with Mel-Band RoFormer (Kimberley Jensen's vocals model, ONNX export by audiojs, MIT).

The model works on spectrograms: the song goes through it in 8 s chunks (every 6 s, crossfaded over 0.8 s),
each chunk as a torch-style STFT (n_fft 2048, hop 441, periodic Hann, reflect padding) of both channels, real
and imaginary parts as 4 channels. As Tune Studio runs it (MIT, © 2026 Nico Franke:
apps/studio/native/src/separate.rs), after Music-Source-Separation-Training's `demix()`.
"""

import hashlib
import os
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE = 44100
N_FFT = 2048
HOP = 441
BINS = N_FFT // 2 + 1
CHUNK = 352_800                 # 8 s
FRAMES = CHUNK // HOP + 1
STEP = CHUNK * 3 // 4           # a chunk every 6 s
FADE = CHUNK // 10

MODEL_URL = ("https://huggingface.co/audiojs/mel-roformer/resolve/c1aba02c00a0bee852d6754fe6ede8164f90a4b3/"
             "mel-roformer.fp16.onnx")
MODEL_SHA256 = "adcbbb826f12453fbb86652b503242d565a9c81cdef1bca2fe0e54752eba91ef"
MODEL_BYTES = 464_050_097
MODEL_FILE = os.path.join("mel-roformer-c1aba02", "mel-roformer.fp16.onnx")


class Cancelled(Exception):
    pass

_sessions: dict = {}
_WINDOW = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)   # periodic Hann


def _reflect(signal: np.ndarray, pad: int) -> np.ndarray:
    return np.pad(signal, (pad, pad), mode="reflect")


def stft(chunk: np.ndarray) -> np.ndarray:
    """torch.stft(center=True, pad_mode="reflect"): (FRAMES, BINS) complex."""
    padded = _reflect(chunk, N_FFT // 2)
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP][:FRAMES]
    return np.fft.rfft(frames * _WINDOW, axis=1)


def istft(spec: np.ndarray) -> np.ndarray:
    """torch.istft(center=True, length=CHUNK): overlap-add with the squared window as envelope."""
    total = N_FFT + HOP * (FRAMES - 1)
    frames = np.fft.irfft(spec, n=N_FFT, axis=1) * _WINDOW
    signal = np.zeros(total, np.float64)
    envelope = np.zeros(total, np.float64)
    for f in range(FRAMES):
        signal[f * HOP:f * HOP + N_FFT] += frames[f]
        envelope[f * HOP:f * HOP + N_FFT] += _WINDOW ** 2
    out = signal[N_FFT // 2:N_FFT // 2 + CHUNK]
    env = envelope[N_FFT // 2:N_FFT // 2 + CHUNK]
    return np.where(env > 1e-11, out / np.maximum(env, 1e-11), 0.0).astype(np.float32)


def _session(model_path: str):
    if model_path not in _sessions:
        import onnxruntime as ort
        _sessions[model_path] = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    return _sessions[model_path]


def run_chunk(model_path: str, left: np.ndarray, right: np.ndarray) -> tuple:
    specs = [stft(left), stft(right)]
    data = np.stack([specs[0].real.T, specs[0].imag.T, specs[1].real.T, specs[1].imag.T])[None].astype(np.float32)
    out = _session(model_path).run(["stems_spec"], {"mix_spec": data})[0].reshape(4, BINS, FRAMES)
    return istft((out[0] + 1j * out[1]).T), istft((out[2] + 1j * out[3]).T)


def _chunk_window(first: bool, last: bool) -> np.ndarray:
    window = np.ones(CHUNK, np.float32)
    ramp = np.arange(FADE, dtype=np.float32) / (FADE - 1)
    if not first:
        window[:FADE] = ramp
    if not last:
        window[CHUNK - FADE:] = 1 - ramp
    return window


def separate(model_path: str, left: np.ndarray, right: np.ndarray,
             on_progress: Optional[Callable[[int], None]] = None,
             cancelled: Optional[Callable[[], bool]] = None) -> tuple:
    """The vocals (left, right) of a 44.1 kHz stereo song. `cancelled()` is asked before every chunk."""
    length = len(left)
    border = CHUNK - STEP
    offset = border if length > 2 * border else 0
    if offset:
        left, right = _reflect(left, border), _reflect(right, border)
    total = len(left)
    result = np.zeros((2, total), np.float32)
    weight = np.zeros(total, np.float32)
    starts = list(range(0, total, STEP))
    for k, start in enumerate(starts):
        if cancelled and cancelled():
            raise Cancelled()
        end = min(start + CHUNK, total)
        piece = lambda x: np.pad(x[start:end], (0, CHUNK - (end - start)))
        vl, vr = run_chunk(model_path, piece(left), piece(right))
        window = _chunk_window(start == 0, start + CHUNK >= total)[:end - start]
        result[0, start:end] += vl[:end - start] * window
        result[1, start:end] += vr[:end - start] * window
        weight[start:end] += window
        if on_progress:
            on_progress((k + 1) * 100 // len(starts))
    w = weight[offset:offset + length]
    safe = np.where(w > 0, w, 1)
    return (np.where(w > 0, result[0, offset:offset + length] / safe, 0),
            np.where(w > 0, result[1, offset:offset + length] / safe, 0))


def model_path(models_dir: str) -> str:
    return os.path.join(models_dir, MODEL_FILE)


def is_downloaded(models_dir: str) -> bool:
    path = model_path(models_dir)
    return os.path.isfile(path) and os.path.getsize(path) == MODEL_BYTES


def download(models_dir: str, on_progress: Optional[Callable[[int, int], None]] = None,
             cancelled: Optional[Callable[[], bool]] = None) -> str:
    """Download the model (pinned revision, SHA-256 checked) once; returns its path."""
    import urllib.request
    target = model_path(models_dir)
    if is_downloaded(models_dir):
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    partial = target + ".part"
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response, open(partial, "wb") as out:
            done = 0
            while block := response.read(1 << 20):
                if cancelled and cancelled():
                    raise Cancelled()
                out.write(block)
                digest.update(block)
                done += len(block)
                if on_progress:
                    on_progress(done, MODEL_BYTES)
        if digest.hexdigest() != MODEL_SHA256:
            raise RuntimeError("The separation model download is damaged (checksum mismatch). Try again.")
        os.replace(partial, target)
        return target
    finally:
        if os.path.exists(partial):
            os.remove(partial)


def separate_vocals(mix_path: str, output_dir: str, models_dir: str,
                    on_progress: Optional[Callable[[int], None]] = None,
                    cancelled: Optional[Callable[[], bool]] = None) -> tuple:
    """Like services/vocal_separation.separate_vocals, with Mel-Band RoFormer: (vocals, instrumental) WAVs in
    `output_dir`, named after the mix. The instrumental is the mix minus the vocals (the model gives vocals only)."""
    import librosa
    import soundfile as sf
    audio, _ = librosa.load(mix_path, sr=SAMPLE_RATE, mono=False)
    if audio.ndim == 1:
        audio = np.stack([audio, audio])
    audio = audio[:2].astype(np.float32)
    left, right = separate(model_path(models_dir), audio[0], audio[1], on_progress, cancelled)
    vocals = np.stack([left, right], axis=1).astype(np.float32)
    stem = os.path.splitext(os.path.basename(mix_path))[0]
    vocal_path = os.path.join(output_dir, f"{stem}_vocals.wav")
    instrumental_path = os.path.join(output_dir, f"{stem}_no_vocals.wav")
    sf.write(vocal_path, vocals, SAMPLE_RATE)
    sf.write(instrumental_path, audio.T - vocals, SAMPLE_RATE)
    return vocal_path, instrumental_path


def separate_file(model_path: str, mix_path: str, out_path: str,
                  on_progress: Optional[Callable[[int], None]] = None) -> str:
    """Separate `mix_path` into a stereo 44.1 kHz WAV of the vocals at `out_path`."""
    import librosa
    import soundfile as sf
    audio, _ = librosa.load(mix_path, sr=SAMPLE_RATE, mono=False)
    if audio.ndim == 1:
        audio = np.stack([audio, audio])
    left, right = separate(model_path, audio[0].astype(np.float32), audio[1].astype(np.float32), on_progress)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sf.write(out_path, np.stack([left, right], axis=1), SAMPLE_RATE)
    return out_path
