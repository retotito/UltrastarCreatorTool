"""Pitch detection using librosa PYIN."""

import time
import numpy as np
import librosa
from utils.logger import log_step

# Settings
CONFIDENCE_THRESHOLD = 0.4
log_step("INIT", "Using librosa PYIN for pitch detection")


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
