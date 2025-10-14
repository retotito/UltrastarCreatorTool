"""
Audio analysis module for advanced syllable detection and timing.
Implements the pipeline specifications from docs/PIPELINE.md
"""

import librosa
import numpy as np
from typing import List, Tuple, Optional
import logging

def detect_syllable_boundaries(audio_path: str, syllables: List[str], sr: int = 22050) -> List[Tuple[float, float, int]]:
    """
    Detect syllable boundaries using onset/offset detection and pitch analysis.
    
    Args:
        audio_path: Path to audio file
        syllables: List of syllables to align
        sr: Sample rate for audio processing
        
    Returns:
        List of (start_time, end_time, pitch) tuples for each syllable
    """
    logging.info(f"Loading audio from {audio_path}")
    
    # Load audio
    y, sr_orig = librosa.load(audio_path, sr=sr)
    
    # Trim leading silence
    y, _ = librosa.effects.trim(y, top_db=20)
    
    logging.info(f"Audio loaded: {len(y)} samples, {len(y)/sr:.2f}s duration")
    
    # Detect onsets for syllable boundaries
    onset_frames = librosa.onset.onset_detect(
        y=y, 
        sr=sr, 
        units='time',
        hop_length=512,
        backtrack=True
    )
    
    logging.info(f"Detected {len(onset_frames)} onset points")
    
    # Detect pitches using PYIN
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y,
        fmin=librosa.note_to_hz('C2'),
        fmax=librosa.note_to_hz('C7'),
        sr=sr,
        frame_length=2048,
        hop_length=512
    )
    
    # Convert frame indices to time
    times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=512)
    
    # Filter out unvoiced frames and group consecutive pitch detections
    voiced_segments = group_pitch_segments(times, f0, voiced_flag, min_duration=0.05)
    
    logging.info(f"Found {len(voiced_segments)} voiced segments")
    
    # Align syllables with audio segments
    syllable_timings = align_syllables_with_audio(syllables, onset_frames, voiced_segments)
    
    return syllable_timings

def group_pitch_segments(times: np.ndarray, f0: np.ndarray, voiced_flag: np.ndarray, 
                        min_duration: float = 0.05) -> List[Tuple[float, float, float]]:
    """
    Group consecutive pitch detections into syllable segments, filtering noise < 50ms.
    
    Returns:
        List of (start_time, end_time, median_pitch) tuples
    """
    segments = []
    current_start = None
    current_pitches = []
    
    for i, (time, pitch, is_voiced) in enumerate(zip(times, f0, voiced_flag)):
        if is_voiced and not np.isnan(pitch):
            if current_start is None:
                current_start = time
                current_pitches = [pitch]
            else:
                current_pitches.append(pitch)
        else:
            # End of voiced segment
            if current_start is not None and len(current_pitches) > 0:
                end_time = times[i-1] if i > 0 else time
                duration = end_time - current_start
                
                # Filter noise shorter than min_duration (50ms)
                if duration >= min_duration:
                    median_pitch = np.median(current_pitches)
                    segments.append((current_start, end_time, median_pitch))
                
                current_start = None
                current_pitches = []
    
    # Handle final segment
    if current_start is not None and len(current_pitches) > 0:
        end_time = times[-1]
        duration = end_time - current_start
        if duration >= min_duration:
            median_pitch = np.median(current_pitches)
            segments.append((current_start, end_time, median_pitch))
    
    return segments

def align_syllables_with_audio(syllables: List[str], onsets: np.ndarray, 
                              voiced_segments: List[Tuple[float, float, float]]) -> List[Tuple[float, float, int]]:
    """
    Align syllables with detected audio segments using onset detection and pitch segments.
    
    Returns:
        List of (start_time, end_time, midi_pitch) for each syllable
    """
    result = []
    
    if len(voiced_segments) == 0:
        logging.warning("No voiced segments found, using BPM fallback")
        return fallback_timing(syllables, total_duration=5.0)  # Default fallback
    
    num_syllables = len(syllables)
    num_segments = len(voiced_segments)
    
    logging.info(f"Aligning {num_syllables} syllables with {num_segments} audio segments")
    
    if num_segments >= num_syllables:
        # More segments than syllables - use first N segments
        for i, syllable in enumerate(syllables):
            if i < len(voiced_segments):
                start_time, end_time, pitch = voiced_segments[i]
                midi_pitch = int(librosa.hz_to_midi(pitch))
                result.append((start_time, end_time, midi_pitch))
            else:
                # Fallback for remaining syllables
                result.extend(fallback_timing(syllables[i:], start_time=result[-1][1] if result else 0))
                break
    else:
        # Fewer segments than syllables - interpolate timing
        total_duration = voiced_segments[-1][1] - voiced_segments[0][0]
        syllable_duration = total_duration / num_syllables
        
        for i, syllable in enumerate(syllables):
            start_time = voiced_segments[0][0] + i * syllable_duration
            end_time = start_time + syllable_duration
            
            # Find closest audio segment for pitch
            closest_segment = min(voiced_segments, 
                                key=lambda seg: abs(seg[0] - start_time))
            pitch = closest_segment[2]
            midi_pitch = int(librosa.hz_to_midi(pitch))
            
            result.append((start_time, end_time, midi_pitch))
    
    return result

def fallback_timing(syllables: List[str], total_duration: float = 5.0, 
                   start_time: float = 0.0, bpm: float = 136.0) -> List[Tuple[float, float, int]]:
    """
    BPM-based even distribution for problem sections.
    """
    result = []
    syllable_duration = total_duration / len(syllables)
    default_pitch = 60  # Middle C
    
    for i, syllable in enumerate(syllables):
        start = start_time + i * syllable_duration
        end = start + syllable_duration
        result.append((start, end, default_pitch))
    
    return result

def calculate_gap_from_first_pitch(voiced_segments: List[Tuple[float, float, float]]) -> int:
    """
    Calculate dynamic GAP from first pitch time in milliseconds.
    """
    if voiced_segments:
        first_pitch_time = voiced_segments[0][0]
        return int(first_pitch_time * 1000)  # Convert to milliseconds
    return 0

def detect_bpm(audio_path: str, sr: int = 22050) -> float:
    """
    Detect BPM using librosa beat tracking.
    """
    y, _ = librosa.load(audio_path, sr=sr)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    
    # Multiply by 2 for Ultrastar precision as specified in pipeline
    ultrastar_bpm = tempo * 2.0
    
    logging.info(f"Detected BPM: {tempo:.2f} -> Ultrastar BPM: {ultrastar_bpm:.2f}")
    
    return ultrastar_bpm