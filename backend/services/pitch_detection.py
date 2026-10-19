"""Pitch detection: FCPE (neural, default) or librosa PYIN, and the pitch of each syllable."""

import time
import numpy as np
import librosa
from utils.logger import log_step

# Settings
CONFIDENCE_THRESHOLD = 0.4
log_step("INIT", "Pitch detection: FCPE (PYIN as fallback)")


def hz_to_midi(frequency: float) -> int:
    """Convert frequency in Hz to MIDI note number."""
    if frequency <= 0 or np.isnan(frequency):
        return 0
    return int(round(69 + 12 * np.log2(frequency / 440.0)))


def midi_to_note_name(midi_note: int) -> str:
    """Convert MIDI note number to note name (e.g., C4, D#5)."""
    if midi_note <= 0:
        return "---"
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi_note // 12) - 1
    note = notes[midi_note % 12]
    return f"{note}{octave}"


def detect_pitches(audio_path: str) -> dict:
    """Pitch track of the vocals: FCPE by default, PYIN if FCPE can't run or ULTRASTAR_PITCH_ENGINE=pyin.

    On 6 reference songs FCPE found the chart's pitch class for 57.6 % of syllables (PYIN 52.7 %),
    77.5 % within a semitone (PYIN 70.5 %), and a pitch for every sung syllable (PYIN: up to 44 % none).
    """
    import os
    if os.environ.get("ULTRASTAR_PITCH_ENGINE", "fcpe").strip().lower() != "pyin":
        try:
            return detect_pitches_fcpe(audio_path)
        except Exception as error:  # model can't be downloaded/loaded, audio too short, ...
            log_step("PITCH", f"FCPE failed ({type(error).__name__}: {error}), using PYIN")
    return detect_pitches_pyin(audio_path)


def detect_pitches_pyin(audio_path: str) -> dict:
    """Detect pitches using librosa PYIN.

    Args:
        audio_path: Path to audio file

    Returns:
        dict with keys: times, frequencies, confidences, midi_notes, sample_rate
    """
    log_step("PITCH", "Loading audio for pitch detection (PYIN)")
    start_time = time.time()

    y, sr = librosa.load(audio_path, sr=22050)
    total_duration = len(y) / sr
    log_step("PITCH", f"Audio loaded: {total_duration:.1f}s at {sr}Hz")

    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, fmin=65, fmax=2093,
        sr=sr, frame_length=2048, hop_length=512
    )
    time_arr = librosa.times_like(f0, sr=sr, hop_length=512)
    frequency = np.where(voiced_flag, f0, 0)
    confidence = voiced_probs

    elapsed = time.time() - start_time
    log_step("PITCH", f"PYIN complete in {elapsed:.1f}s")

    # Convert to MIDI notes
    midi_notes = np.array([hz_to_midi(f) for f in frequency])

    # Stats
    high_conf_mask = confidence >= CONFIDENCE_THRESHOLD
    voiced_count = np.sum(high_conf_mask & (frequency > 0))
    log_step("PITCH", f"Voiced frames: {voiced_count}/{len(time_arr)} ({voiced_count/len(time_arr)*100:.0f}%)")

    return {
        "times": time_arr,
        "frequencies": frequency,
        "confidences": confidence,
        "midi_notes": midi_notes,
        "sample_rate": sr
    }


# Keep old name as alias for backward compatibility
detect_pitches_crepe = detect_pitches

# FCPE: a neural pitch estimator for singing (MIT), ONNX export with its mel spectrogram and decoding
# inside the graph. Input 16 kHz mono, output Hz every 10 ms (0 = unvoiced). Pinned revision.
FCPE_MODEL_ID = "tuneperfect/fcpe-onnx"
FCPE_MODEL_REVISION = "f99224c40e48c8c84fa9935ff2cc6c3e92ec6ccf"
FCPE_MODEL_FILE = "fcpe.onnx"
FCPE_MODEL_BYTES = 47_805_126
FCPE_SAMPLE_RATE = 16_000
FCPE_HOP = 160
_fcpe_cache: dict = {}


def fcpe_model_downloaded() -> bool:
    try:
        import os
        from huggingface_hub import try_to_load_from_cache
        path = try_to_load_from_cache(FCPE_MODEL_ID, FCPE_MODEL_FILE, revision=FCPE_MODEL_REVISION)
        return isinstance(path, str) and os.path.isfile(path) and os.path.getsize(path) == FCPE_MODEL_BYTES
    except Exception:
        return False


def download_fcpe_model() -> None:
    from huggingface_hub import hf_hub_download
    hf_hub_download(FCPE_MODEL_ID, FCPE_MODEL_FILE, revision=FCPE_MODEL_REVISION)


def _fcpe_session():
    if "session" not in _fcpe_cache:
        import onnxruntime
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(FCPE_MODEL_ID, FCPE_MODEL_FILE, revision=FCPE_MODEL_REVISION)
        _fcpe_cache["session"] = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])
    return _fcpe_cache["session"]


def detect_pitches_fcpe(audio_path: str) -> dict:
    """Pitch with FCPE, in the same format as `detect_pitches` (PYIN): 10 ms frames.

    FCPE gives no probability, so voiced frames get confidence 1.0 and unvoiced 0.0.
    """
    log_step("PITCH", "Detecting pitch (FCPE)")
    start_time = time.time()
    audio, _ = librosa.load(audio_path, sr=FCPE_SAMPLE_RATE, mono=True)
    if len(audio) < 1024:
        raise ValueError("Audio too short for pitch detection")
    f0 = _fcpe_session().run(["f0"], {"audio": audio.astype(np.float32)[None]})[0][0]
    frequency = np.where(f0 > 0, f0, 0.0).astype(float)
    midi_notes = np.array([hz_to_midi(f) for f in frequency])
    voiced = frequency > 0
    log_step("PITCH", f"FCPE complete in {time.time() - start_time:.1f}s, voiced frames {voiced.mean() * 100:.0f}%")
    return {
        "times": np.arange(len(f0)) * (FCPE_HOP / FCPE_SAMPLE_RATE),
        "frequencies": frequency,
        "confidences": voiced.astype(float),
        "midi_notes": midi_notes,
        "sample_rate": FCPE_SAMPLE_RATE,
    }


def get_pitch_at_time(pitch_data: dict, time_sec: float, window: float = 0.05) -> int:
    """Get the median MIDI pitch at a specific time point.

    Args:
        pitch_data: Result from detect_pitches
        time_sec: Time in seconds
        window: Window size in seconds for averaging

    Returns:
        MIDI note number (0 if no pitch detected)
    """
    times = pitch_data["times"]
    midi_notes = pitch_data["midi_notes"]
    confidences = pitch_data["confidences"]

    mask = (times >= time_sec - window) & (times <= time_sec + window)
    mask &= (midi_notes > 0) & (confidences >= CONFIDENCE_THRESHOLD)

    window_notes = midi_notes[mask]

    if len(window_notes) == 0:
        return 0

    return int(np.median(window_notes))


def get_pitch_for_segment(pitch_data: dict, start_time: float, end_time: float) -> int:
    """Get the median MIDI pitch for a time segment.

    Args:
        pitch_data: Result from detect_pitches
        start_time: Segment start in seconds
        end_time: Segment end in seconds

    Returns:
        MIDI note number (0 if no pitch detected)
    """
    times = pitch_data["times"]
    midi_notes = pitch_data["midi_notes"]
    confidences = pitch_data["confidences"]

    mask = (times >= start_time) & (times <= end_time)
    mask &= (midi_notes > 0) & (confidences >= CONFIDENCE_THRESHOLD)

    segment_notes = midi_notes[mask]

    if len(segment_notes) == 0:
        return 0

    return int(np.median(segment_notes))


# Singers often slide up into a note; the first part of a syllable is left out of its pitch.
SLIDE_IN_SKIP = 1 / 3


def _fractional_midi(pitch_data: dict) -> np.ndarray:
    """Unrounded MIDI per frame, NaN where unvoiced or unsure."""
    frequencies = np.asarray(pitch_data["frequencies"], dtype=float)
    sure = (frequencies > 0) & (np.asarray(pitch_data["confidences"], dtype=float) >= CONFIDENCE_THRESHOLD)
    midi = np.full(frequencies.shape, np.nan)
    midi[sure] = 69 + 12 * np.log2(frequencies[sure] / 440.0)
    return midi


def syllable_pitch(pitch_data: dict, start_time: float, end_time: float) -> int:
    """MIDI pitch of a syllable: median of the unrounded pitch over its last two thirds (skipping the slide
    in), else over the whole syllable, else ±0.1 s around its middle; 0 if nothing is voiced there."""
    midi = _fractional_midi(pitch_data)
    times = np.asarray(pitch_data["times"], dtype=float)
    middle = (start_time + end_time) / 2
    for lo, hi in ((start_time + (end_time - start_time) * SLIDE_IN_SKIP, end_time),
                   (start_time, end_time), (middle - 0.1, middle + 0.1)):
        selected = (times >= lo) & (times <= hi) & ~np.isnan(midi)
        if selected.any():
            return int(round(float(np.median(midi[selected]))))
    return 0


def fill_unvoiced(pitches: list, default: int = 60) -> list:
    """Replace 0 (no pitch found) with the previous sung pitch, or the next one before the first.

    A fixed C4 is usually far off the melody; a neighbour is much closer (Tune Studio does the same).
    `None` entries (rap notes) are kept and skipped.
    """
    out = list(pitches)
    last = None
    for i, pitch in enumerate(out):
        if pitch is None:
            continue
        if pitch > 0:
            last = pitch
        elif last is not None:
            out[i] = last
    first = next((p for p in out if p), default)
    return [first if p == 0 else p for p in out]


# Octave check weights (Tune Studio's fixOctaves): a leap beyond a fifth costs LEAP per semitone, less
# after a pause; moving a note costs STAY per octave; leaving the song's range (median ± 9) costs CENTER
# per semitone. Notes may move up to three octaves: FCPE sometimes lands that far off on noisy frames
# (Freak Power: "out" at 80 in a line around 43).
OCTAVE_LEAP = 0.6
OCTAVE_STAY = 2.0
OCTAVE_CENTER = 0.3
OCTAVE_PAUSE_SEC = 0.5


def fix_octaves(pitches: list, syllable_timings: list) -> list:
    """Move notes an octave up or down where the pitch tracker jumped an octave (in a copy).

    For every sung note one of {-12, 0, +12} is chosen so that the whole song costs the least: big
    leaps between neighbouring notes are expensive (cheaper after a pause, where a phrase may start
    elsewhere), moving a note and leaving the song's range cost a little. `None` (rap) is skipped.
    """
    sung = [i for i, p in enumerate(pitches) if p]
    if len(sung) < 2:
        return list(pitches)
    shifts = (-36, -24, -12, 0, 12, 24, 36)
    middle = float(np.median([pitches[i] for i in sung]))

    def own(i, shift):
        return OCTAVE_STAY * abs(shift) / 12 + OCTAVE_CENTER * max(0.0, abs(pitches[i] + shift - middle) - 9)

    def move(prev, i, s0, s1):
        jump = abs(pitches[i] + s1 - pitches[prev] - s0)
        pause = max(0.0, syllable_timings[i]["start"] - syllable_timings[prev]["end"])
        return OCTAVE_LEAP * max(0, jump - 7) / (1 + pause / OCTAVE_PAUSE_SEC)

    cost = [own(sung[0], s) for s in shifts]
    back = []
    for prev, i in zip(sung, sung[1:]):
        options = [[cost[a] + move(prev, i, s0, s1) for a, s0 in enumerate(shifts)] for s1 in shifts]
        best = [min(range(len(shifts)), key=row.__getitem__) for row in options]
        back.append(best)
        cost = [options[k][best[k]] + own(i, s) for k, s in enumerate(shifts)]
    out = list(pitches)
    k = min(range(len(shifts)), key=cost.__getitem__)
    for n in range(len(sung) - 1, -1, -1):
        out[sung[n]] = pitches[sung[n]] + shifts[k]
        if n:
            k = back[n - 1][k]
    return out


def syllable_pitches(pitch_data: dict, syllable_timings: list) -> list:
    """MIDI pitch per syllable (None for rap): unvoiced syllables take a neighbour's pitch, octave jumps of
    the pitch tracker are corrected."""
    if not syllable_timings:
        return []
    raw = [None if t.get("is_rap")
           else int(t["pitch"]) if t.get("pitch")          # a melisma part brings its own pitch
           else syllable_pitch(pitch_data, t["start"], t["end"])
           for t in syllable_timings]
    return fix_octaves(fill_unvoiced(raw), syllable_timings)


def get_pitch_subsegments(
    pitch_data: dict,
    start_time: float,
    end_time: float,
    min_duration_sec: float = 0.24,
    target_slice_sec: float = 0.18,
    max_segments: int = 4,
    min_pitch_span_semitones: int = 2,
    min_run_frames: int = 1,
) -> list:
    """Extract intra-syllable pitch subsegments from detected pitch runs.

    The algorithm first builds contiguous same-pitch runs, optionally smooths
    very short runs, then reduces to a segment budget while preserving larger
    pitch transitions.
    """
    duration = max(0.0, float(end_time) - float(start_time))
    if duration < min_duration_sec:
        return []

    times = pitch_data["times"]
    midi_notes = pitch_data["midi_notes"]
    confidences = pitch_data["confidences"]

    base_mask = (times >= start_time) & (times <= end_time)
    base_mask &= (midi_notes > 0) & (confidences >= CONFIDENCE_THRESHOLD)

    seg_times = times[base_mask]
    seg_notes = midi_notes[base_mask]

    if len(seg_notes) < 4:
        return []

    pitch_span = int(np.max(seg_notes) - np.min(seg_notes))
    if pitch_span < int(min_pitch_span_semitones):
        return []

    seg_times = np.asarray(seg_times, dtype=float)
    seg_notes = np.asarray(seg_notes, dtype=int)

    if len(seg_times) < 2:
        return []

    # Build contiguous runs from framewise quantized MIDI notes.
    runs = []
    run_start = float(seg_times[0])
    run_pitch = int(seg_notes[0])
    run_frames = 1
    for i in range(1, len(seg_notes)):
        p = int(seg_notes[i])
        if p == run_pitch:
            run_frames += 1
            continue
        runs.append(
            {
                "start": run_start,
                "end": float(seg_times[i - 1]),
                "pitch": run_pitch,
                "frames": run_frames,
            }
        )
        run_start = float(seg_times[i])
        run_pitch = p
        run_frames = 1
    runs.append(
        {
            "start": run_start,
            "end": float(seg_times[-1]),
            "pitch": run_pitch,
            "frames": run_frames,
        }
    )

    # Convert tiny one-frame end times into proper touching ranges.
    if len(runs) > 1:
        for i in range(len(runs) - 1):
            runs[i]["end"] = runs[i + 1]["start"]
        runs[-1]["end"] = float(end_time)
    else:
        runs[0]["start"] = float(start_time)
        runs[0]["end"] = float(end_time)

    if len(runs) < 2:
        return []

    def _merge_same_pitch(items: list) -> list:
        if not items:
            return []
        out = [dict(items[0])]
        for item in items[1:]:
            prev = out[-1]
            if int(item["pitch"]) == int(prev["pitch"]):
                prev["end"] = item["end"]
                prev["frames"] = int(prev.get("frames", 1)) + int(item.get("frames", 1))
            else:
                out.append(dict(item))
        return out

    # Remove very short runs by merging into neighbors.
    min_frames = max(1, int(min_run_frames))
    runs = _merge_same_pitch(runs)
    i = 0
    while i < len(runs):
        if len(runs) <= 2:
            break
        frames = int(runs[i].get("frames", 1))
        if frames >= min_frames:
            i += 1
            continue

        if 0 < i < len(runs) - 1 and int(runs[i - 1]["pitch"]) == int(runs[i + 1]["pitch"]):
            runs[i - 1]["end"] = runs[i + 1]["end"]
            runs[i - 1]["frames"] = (
                int(runs[i - 1].get("frames", 1))
                + int(runs[i].get("frames", 1))
                + int(runs[i + 1].get("frames", 1))
            )
            del runs[i : i + 2]
            i = max(0, i - 1)
            continue

        if i == 0:
            runs[1]["start"] = runs[0]["start"]
            runs[1]["frames"] = int(runs[1].get("frames", 1)) + int(runs[0].get("frames", 1))
            del runs[0]
            i = 0
            continue

        if i == len(runs) - 1:
            runs[-2]["end"] = runs[-1]["end"]
            runs[-2]["frames"] = int(runs[-2].get("frames", 1)) + int(runs[-1].get("frames", 1))
            runs.pop()
            i = max(0, i - 1)
            continue

        left = runs[i - 1]
        right = runs[i + 1]
        left_delta = abs(int(runs[i]["pitch"]) - int(left["pitch"]))
        right_delta = abs(int(runs[i]["pitch"]) - int(right["pitch"]))
        merge_left = left_delta <= right_delta
        if merge_left:
            left["end"] = runs[i]["end"]
            left["frames"] = int(left.get("frames", 1)) + int(runs[i].get("frames", 1))
        else:
            right["start"] = runs[i]["start"]
            right["frames"] = int(right.get("frames", 1)) + int(runs[i].get("frames", 1))
        del runs[i]
        i = max(0, i - 1)

    runs = _merge_same_pitch(runs)
    if len(runs) < 2:
        return []

    # Enforce segment budget while preserving larger pitch movements.
    budget = max(2, min(int(max_segments), len(runs)))
    while len(runs) > budget:
        best_idx = 0
        best_score = None
        for j in range(len(runs) - 1):
            a = runs[j]
            b = runs[j + 1]
            pitch_jump = abs(int(a["pitch"]) - int(b["pitch"]))
            size = int(a.get("frames", 1)) + int(b.get("frames", 1))
            score = (pitch_jump * 1000) + size
            if best_score is None or score < best_score:
                best_score = score
                best_idx = j

        left = runs[best_idx]
        right = runs[best_idx + 1]
        merged_pitch = int(left["pitch"]) if int(left.get("frames", 1)) >= int(right.get("frames", 1)) else int(right["pitch"])
        merged = {
            "start": left["start"],
            "end": right["end"],
            "pitch": merged_pitch,
            "frames": int(left.get("frames", 1)) + int(right.get("frames", 1)),
        }
        runs[best_idx : best_idx + 2] = [merged]

    runs = _merge_same_pitch(runs)
    if len(runs) < 2:
        return []

    merged_span = int(max(c["pitch"] for c in runs) - min(c["pitch"] for c in runs))
    if merged_span < int(min_pitch_span_semitones):
        return []

    return [{"start": float(r["start"]), "end": float(r["end"]), "pitch": int(r["pitch"])} for r in runs]
