"""BPM detection using multi-method ensemble (essentia + librosa).

Uses the original audio mix (with instruments) when available, since
drums/bass provide much stronger rhythmic cues than vocals alone.
"""

import librosa
import numpy as np
from utils.logger import log_step

# Optional: essentia for more accurate BPM detection
try:
    import essentia.standard as _es
    _HAS_ESSENTIA = True
except ImportError:
    _HAS_ESSENTIA = False


def _to_float(tempo) -> float:
    """Extract scalar BPM from librosa's tempo return value."""
    return float(tempo[0]) if hasattr(tempo, '__len__') else float(tempo)


def _octave_fix(bpm: float) -> float:
    """Normalize BPM into the 80–180 range (standard pop/rock range).
    
    Beat detectors often return half-time (~75 BPM) or double-time
    (~300 BPM).  Doubling / halving maps them back to the likely
    musical tempo.
    """
    while bpm < 80:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return bpm


def _detect_bpm_essentia(audio_path: str) -> list[float]:
    """Return BPM candidates from essentia (PercivalBpmEstimator +
    RhythmExtractor2013 degara)."""
    if not _HAS_ESSENTIA:
        return []
    
    candidates = []
    try:
        audio = _es.MonoLoader(filename=audio_path, sampleRate=44100)()
        
        # Percival — robust single-value estimator
        try:
            bpm = _es.PercivalBpmEstimator()(audio)
            if bpm > 0:
                candidates.append(("essentia-percival", float(bpm)))
        except Exception:
            pass
        
        # RhythmExtractor2013 degara — good for pop/rock
        try:
            bpm, _, _, _, _ = _es.RhythmExtractor2013(method="degara")(audio)
            if bpm > 0:
                candidates.append(("essentia-degara", float(bpm)))
        except Exception:
            pass
        
    except Exception as e:
        log_step("BPM", f"essentia failed: {e}")
    
    return candidates


def _detect_bpm_librosa(y, sr) -> list[float]:
    """Return BPM candidates from librosa."""
    candidates = []
    
    # Method 1: beat_track (default)
    try:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        bpm = _to_float(tempo)
        candidates.append(("librosa-beat_track", bpm))
        
        # Refine using beat-position regression (more precise than
        # the tempogram resolution)
        if len(beat_frames) > 10:
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)
            indices = np.arange(len(beat_times))
            slope, _ = np.polyfit(indices, beat_times, 1)
            bpm_reg = 60.0 / slope
            candidates.append(("librosa-regression", bpm_reg))
    except Exception:
        pass
    
    # Method 2: beat_track with start_bpm=120
    try:
        tempo2, _ = librosa.beat.beat_track(y=y, sr=sr, start_bpm=120)
        bpm2 = _to_float(tempo2)
        if abs(bpm2 - candidates[0][1]) > 2:  # only add if different
            candidates.append(("librosa-start120", bpm2))
    except Exception:
        pass
    
    return candidates


def detect_bpm(audio_path: str, original_audio_path: str = None) -> float:
    """Detect BPM from audio using multi-method ensemble.
    
    Uses original audio (with instruments) when available, since
    drums/bass provide much better rhythmic cues than vocals alone.
    
    Returns Ultrastar BPM (detected BPM × 2 for precision).
    """
    # Prefer original mix for beat detection (has drums/bass)
    detect_path = original_audio_path or audio_path
    source = "original mix" if original_audio_path else "vocals"
    log_step("BPM", f"Loading audio ({source}): {detect_path}")
    
    y, sr = librosa.load(detect_path, sr=22050)
    y_trimmed, _ = librosa.effects.trim(y, top_db=20)
    log_step("BPM", f"Audio loaded: {len(y_trimmed)/sr:.1f}s at {sr}Hz")
    
    # ── Collect candidates from all methods ──
    all_candidates = []
    
    # essentia (uses its own audio loading)
    essentia_cands = _detect_bpm_essentia(detect_path)
    all_candidates.extend(essentia_cands)
    
    # librosa
    librosa_cands = _detect_bpm_librosa(y_trimmed, sr)
    all_candidates.extend(librosa_cands)
    
    if not all_candidates:
        log_step("BPM", "WARNING: No BPM detected, defaulting to 120")
        return 240.0  # 120 × 2
    
    # Log all raw candidates
    for method, bpm in all_candidates:
        log_step("BPM", f"  {method}: {bpm:.1f}")
    
    # ── Octave-normalize all candidates to 80–180 BPM ──
    normalized = []
    for method, bpm in all_candidates:
        fixed = _octave_fix(bpm)
        normalized.append(fixed)
        if abs(fixed - bpm) > 0.1:
            log_step("BPM", f"  {method}: {bpm:.1f} -> {fixed:.1f} (octave fix)")
    
    # ── Select: use median of normalized candidates ──
    median_bpm = float(np.median(normalized))
    
    # Round to nearest 0.5 BPM (songs almost always use round values)
    bpm_rounded = round(median_bpm * 2) / 2
    
    ultrastar_bpm = round(bpm_rounded * 2, 1)
    
    log_step("BPM", f"Candidates (normalized): {[round(b, 1) for b in sorted(normalized)]}")
    log_step("BPM", f"Median: {median_bpm:.1f} -> rounded: {bpm_rounded:.1f} -> Ultrastar BPM: {ultrastar_bpm:.1f}")
    
    return ultrastar_bpm


def detect_beat_phase(audio_path: str, ultrastar_bpm: float) -> float:
    """Detect where musical beats fall in the audio (beat phase).
    
    Uses librosa beat tracking to find actual beat positions, then
    computes the phase offset — the time of the first beat modulo
    the beat period.
    
    Args:
        audio_path: Path to audio file (prefer original mix with drums)
        ultrastar_bpm: Ultrastar BPM (2x musical BPM)
    
    Returns:
        Phase offset in seconds (0 <= phase < beat_period).
        The musical beat grid is: phase, phase + period, phase + 2*period, ...
    """
    musical_bpm = ultrastar_bpm / 2.0
    beat_period = 60.0 / musical_bpm  # seconds per musical beat
    
    y, sr = librosa.load(audio_path, sr=22050)
    
    # Use librosa beat tracker with BPM hint
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, bpm=musical_bpm)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    
    if len(beat_times) < 4:
        log_step("BPM", "Not enough beats for phase estimation, defaulting to 0")
        return 0.0
    
    # Compute phase using circular mean (handles wrap-around at beat boundaries)
    angles = [2 * np.pi * (bt % beat_period) / beat_period for bt in beat_times]
    sin_mean = float(np.mean(np.sin(angles)))
    cos_mean = float(np.mean(np.cos(angles)))
    phase_angle = np.arctan2(sin_mean, cos_mean)
    if phase_angle < 0:
        phase_angle += 2 * np.pi
    phase = phase_angle / (2 * np.pi) * beat_period
    
    log_step("BPM", f"Beat phase: {phase:.3f}s (period={beat_period:.3f}s, "
             f"from {len(beat_times)} detected beats)")
    return phase


def refine_bpm(syllable_timings: list, gap_ms: int, initial_bpm: float) -> float:
    """Refine BPM using syllable timestamps after alignment.
    
    Tries nearby BPM values and picks the one that minimizes
    quantization error when snapping notes to the beat grid.
    This can recover the exact BPM when detection is off by a few BPM.
    
    Only applies the refinement when the grid fit is convincingly good
    (avg error < 0.15 beats per note).  Songs with intentional swing,
    groove, or rubato will *not* pass this threshold, so their BPM
    stays at the detector's estimate — which is the correct behaviour,
    because forcing a tight grid on expressive timing would be wrong.
    
    Args:
        syllable_timings: List of dicts with 'start' (seconds)
        gap_ms: GAP in milliseconds
        initial_bpm: Initial Ultrastar BPM (already ×2)
    
    Returns:
        Refined Ultrastar BPM (×2).
    """
    if not syllable_timings or initial_bpm <= 0:
        return initial_bpm
    
    # Extract start times (in ms)
    times_ms = [s["start"] * 1000 for s in syllable_timings if s.get("start") is not None]
    if len(times_ms) < 10:
        return initial_bpm
    
    n_notes = len(times_ms)
    
    # ── Coarse search: ±10% in 0.1 steps ──
    base = initial_bpm
    low = base * 0.90
    high = base * 1.10
    
    # Build candidate grid: fine step + all integer and half-integer values
    # (songs almost always have round BPM values)
    candidates = set()
    for ubpm_x10 in range(int(low * 10), int(high * 10) + 1):
        candidates.add(ubpm_x10 / 10.0)
    # Ensure all integer UBPMs are in the set
    for i in range(int(low), int(high) + 1):
        candidates.add(float(i))
        candidates.add(i + 0.5)
    
    best_bpm = initial_bpm
    best_error = float('inf')
    
    for ubpm in sorted(candidates):
        if ubpm <= 0:
            continue
        _, total_error = _compute_grid_error(times_ms, gap_ms, ubpm)
        if total_error < best_error:
            best_error = total_error
            best_bpm = ubpm
    
    # ── Fine search around best: ±1 BPM in 0.02 steps ──
    fine_low = best_bpm - 1.0
    fine_high = best_bpm + 1.0
    for ubpm_x100 in range(int(fine_low * 100), int(fine_high * 100) + 1, 2):
        ubpm = ubpm_x100 / 100.0
        if ubpm <= 0:
            continue
        _, total_error = _compute_grid_error(times_ms, gap_ms, ubpm)
        if total_error < best_error:
            best_error = total_error
            best_bpm = ubpm
    
    # Round to nearest 0.1
    best_bpm = round(best_bpm, 1)
    
    _, initial_error = _compute_grid_error(times_ms, gap_ms, initial_bpm)
    _, refined_error = _compute_grid_error(times_ms, gap_ms, best_bpm)
    
    avg_error = refined_error / n_notes  # avg quantization error per note (0–0.5 beats)
    
    # ── Confidence gate ──
    # A note perfectly on the grid has error 0.  Random timing → avg ~0.25.
    # Swing / groove / rubato → avg 0.15–0.25.
    # Clean pop/rock grid → avg < 0.10.
    #
    # Only refine when:
    #   1. The best-fit grid is convincingly good (avg < 0.15)
    #   2. AND the improvement over initial is > 5%
    #
    # This prevents false refinement on groovy/swung songs where a
    # slightly wrong BPM might coincidentally score better.
    MAX_AVG_ERROR = 0.15  # beats (= 7.5ms at 300 Ultrastar BPM)
    
    if avg_error < MAX_AVG_ERROR and refined_error < initial_error * 0.95:
        log_step("BPM", f"Refined BPM: {initial_bpm:.1f} -> {best_bpm:.1f} "
                 f"(grid error: {initial_error:.1f} -> {refined_error:.1f}, "
                 f"avg={avg_error:.3f} beats/note, {n_notes} notes)")
        return best_bpm
    else:
        reason = "low confidence (swing/groove?)" if avg_error >= MAX_AVG_ERROR else "no significant improvement"
        log_step("BPM", f"BPM refinement skipped: {reason} "
                 f"({initial_bpm:.1f}, avg_error={avg_error:.3f}, "
                 f"threshold={MAX_AVG_ERROR})")
        return initial_bpm


def _compute_grid_error(times_ms, gap_ms, ultrastar_bpm):
    """Compute total quantization error for a BPM value."""
    beats = [(t - gap_ms) * ultrastar_bpm / 15000 for t in times_ms]
    errors = [abs(b - round(b)) for b in beats]
    return beats, sum(errors)


def get_audio_duration(audio_path: str) -> float:
    """Get the duration of an audio file in seconds."""
    y, sr = librosa.load(audio_path, sr=22050)
    return librosa.get_duration(y=y, sr=sr)
