"""Lyrics alignment — energy-based fallback.

Aligns lyrics text to audio to get per-syllable timing.
Primary alignment is via WhisperX (see alignment_whisper.py).
This module provides the energy-based fallback when WhisperX returns nothing.
"""

import os
from typing import List
from utils.logger import log_step


def align_lyrics_to_audio(
    audio_path: str,
    lyrics_text: str,
    language: str = "english",
    whisper_words: list = None
) -> List[dict]:
    """Align lyrics to audio using energy-based fallback.
    
    This is only called when WhisperX alignment fails or returns nothing.
    
    Args:
        audio_path: Path to vocal audio file
        lyrics_text: Full lyrics text with lines and hyphenated syllables
        
    Returns:
        List of dicts: [{"syllable": "beau", "start": 1.23, "end": 1.56, "confidence": 0.95}, ...]
    """
    parsed = parse_lyrics(lyrics_text)
    flat_syllables = [s for line in parsed for s in line]
    
    log_step("ALIGN", f"Parsed {len(flat_syllables)} syllables across {len(parsed)} lines")
    log_step("ALIGN", "Using energy-based fallback alignment")
    
    results = align_fallback(audio_path, parsed)
    if results:
        log_step("ALIGN", f"  First syllable: '{results[0]['syllable']}' at {results[0]['start']:.3f}s")
        log_step("ALIGN", f"  Last syllable: '{results[-1]['syllable']}' at {results[-1]['end']:.3f}s")
    _write_alignment_debug(results, "fallback")
    return results


def _write_alignment_debug(results: list, method: str):
    """Write alignment results to a debug file for tracing."""
    debug_path = os.path.join(os.path.dirname(__file__), '..', 'downloads', 'alignment_debug.txt')
    try:
        with open(debug_path, 'w') as f:
            f.write(f"ALIGNMENT DEBUG TRACE (method={method})\n")
            f.write(f"{'='*70}\n")
            f.write(f"Total syllables: {len(results)}\n\n")
            f.write(f"{'#':<5} {'Syllable':<18} {'Start':>10} {'End':>10} {'Dur':>8} {'Conf':>6} {'Method':<20}\n")
            f.write(f"{'-'*77}\n")
            for i, r in enumerate(results):
                dur = r['end'] - r['start']
                f.write(f"{i:<5} {r['syllable']:<18} {r['start']:>10.4f} {r['end']:>10.4f} {dur:>8.4f} {r['confidence']:>6.2f} {r.get('method','?'):<20}\n")
        log_step("ALIGN", f"Debug trace written to {debug_path}")
    except Exception as e:
        log_step("ALIGN", f"Could not write debug trace: {e}")


def parse_lyrics(lyrics_text: str) -> List[List[str]]:
    """Parse lyrics text into list of lines, each containing syllables.
    
    Rules:
    - Each line = one phrase
    - Hyphens split syllables: "beau-ti-ful" -> ["beau", "ti", "ful"]
    - [RAP] / [/RAP] markers preserved
    - Empty lines ignored
    """
    lines = []
    is_rap = False
    
    for line in lyrics_text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Check for RAP markers
        if line.upper() == '[RAP]':
            is_rap = True
            continue
        if line.upper() == '[/RAP]':
            is_rap = False
            continue
        
        syllables = []
        words = line.split()
        for i, word in enumerate(words):
            # Split on hyphens for syllables
            parts = word.split('-')
            for j, part in enumerate(parts):
                if not part:
                    continue
                # Add space before word (except first syllable of first word)
                prefix = " " if (j == 0 and len(syllables) > 0) else ""
                syllables.append({
                    "text": prefix + part,
                    "is_rap": is_rap,
                    "is_word_start": j == 0,
                    "word": word,
                    "line_index": len(lines)
                })
        
        if syllables:
            lines.append(syllables)
    
    return lines


def _detect_vocal_sections(y, sr, min_silence_sec=1.0, min_section_sec=1.0):
    """Detect vocal sections in audio by finding silence gaps.
    
    Returns list of (start_sec, end_sec) tuples for voiced sections.
    """
    import librosa
    import numpy as np
    
    hop_length = 512
    frame_length = 2048
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    
    # Adaptive threshold: 8% of max RMS
    threshold = np.max(rms) * 0.08
    is_voiced = rms > threshold
    
    # Step 1: Find all raw voiced segments
    raw_segments = []
    in_seg = False
    seg_start = 0.0
    
    for i in range(len(is_voiced)):
        if is_voiced[i] and not in_seg:
            seg_start = times[i]
            in_seg = True
        elif not is_voiced[i] and in_seg:
            seg_end = times[i]
            raw_segments.append((seg_start, seg_end))
            in_seg = False
    if in_seg:
        seg_end = times[-1]
        raw_segments.append((seg_start, seg_end))
    
    # Step 2: Merge segments with very short gaps (< 0.5s)
    breath_merged = []
    for seg in raw_segments:
        if breath_merged and seg[0] - breath_merged[-1][1] < 0.5:
            breath_merged[-1] = (breath_merged[-1][0], seg[1])
        else:
            breath_merged.append(seg)
    
    # Step 3: Filter by minimum section duration
    filtered = [(s, e) for s, e in breath_merged if e - s >= min_section_sec]
    
    # Step 4: Merge sections with gaps < min_silence_sec
    merged = []
    for seg in filtered:
        if merged and seg[0] - merged[-1][1] < min_silence_sec:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(seg)
    
    return merged


def align_fallback(audio_path: str, parsed_lines: List[List[dict]]) -> List[dict]:
    """Fallback alignment using energy-based voiced segment detection.
    
    Finds segments where there's vocal energy and places syllables
    within those segments — leaving gaps where the audio is silent.
    """
    import librosa
    import numpy as np
    
    y, sr = librosa.load(audio_path, sr=16000, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    
    log_step("ALIGN", f"Energy-based fallback alignment ({duration:.1f}s audio)")
    
    flat_syllables = [s for line in parsed_lines for s in line]
    total_syllables = len(flat_syllables)
    
    if total_syllables == 0:
        return []
    
    # Detect voiced sections
    segments = _detect_vocal_sections(y, sr, min_silence_sec=1.5, min_section_sec=1.0)
    
    total_voiced_time = sum(end - start for start, end in segments)
    log_step("ALIGN", f"Found {len(segments)} voiced segments, total voiced time: {total_voiced_time:.1f}s")
    
    if len(segments) == 0:
        log_step("ALIGN", "No voiced segments found, using simple distribution")
        return _align_even(y, sr, parsed_lines)
    
    # Distribute lines across segments
    num_lines = len(parsed_lines)
    results = []
    
    if num_lines <= len(segments):
        seg_durations = [end - start for start, end in segments]
        total_seg_dur = sum(seg_durations)
        
        line_segment_map = []
        for seg_idx, seg_dur in enumerate(seg_durations):
            proportion = seg_dur / total_seg_dur
            n_lines = proportion * num_lines
            line_segment_map.append({
                'seg_idx': seg_idx,
                'start': segments[seg_idx][0],
                'end': segments[seg_idx][1],
                'line_count': n_lines,
            })
        
        line_assignments = []
        line_idx = 0
        fractional_acc = 0.0
        for seg_info in line_segment_map:
            fractional_acc += seg_info['line_count']
            while line_idx < num_lines and line_idx < round(fractional_acc):
                line_assignments.append((line_idx, seg_info['start'], seg_info['end']))
                line_idx += 1
        
        while line_idx < num_lines:
            last = segments[-1]
            line_assignments.append((line_idx, last[0], last[1]))
            line_idx += 1
    else:
        lines_per_seg = num_lines / len(segments)
        line_assignments = []
        for line_idx in range(num_lines):
            seg_idx = min(int(line_idx / lines_per_seg), len(segments) - 1)
            line_assignments.append((line_idx, segments[seg_idx][0], segments[seg_idx][1]))
    
    # Place syllables within assigned segments
    from collections import defaultdict
    seg_lines = defaultdict(list)
    for line_idx, seg_start, seg_end in line_assignments:
        seg_lines[(seg_start, seg_end)].append(line_idx)
    
    for (seg_start, seg_end), line_indices in seg_lines.items():
        seg_duration = seg_end - seg_start
        
        seg_syllables = []
        for li in line_indices:
            for syl in parsed_lines[li]:
                seg_syllables.append((li, syl))
        
        if not seg_syllables:
            continue
        
        num_line_breaks = len(set(li for li, _ in seg_syllables)) - 1
        gap_total = seg_duration * 0.05 * num_line_breaks / max(1, len(seg_syllables))
        syllable_time = (seg_duration - gap_total * num_line_breaks) / len(seg_syllables)
        syllable_time = max(0.1, syllable_time)
        
        current_time = seg_start
        prev_line_idx = seg_syllables[0][0] if seg_syllables else None
        
        for li, syl in seg_syllables:
            if prev_line_idx is not None and li != prev_line_idx:
                current_time += gap_total
            
            start = current_time
            end = min(current_time + syllable_time, seg_end)
            
            results.append({
                "syllable": syl["text"],
                "start": start,
                "end": end,
                "confidence": 0.4,
                "is_rap": syl.get("is_rap", False),
                "method": "fallback_energy",
                "line_index": li
            })
            
            current_time = end
            prev_line_idx = li
    
    results.sort(key=lambda r: r["start"])
    
    log_step("ALIGN", f"Energy fallback: placed {len(results)} syllables in {len(segments)} voiced segments")
    if results:
        log_step("ALIGN", f"  Time range: {results[0]['start']:.1f}s - {results[-1]['end']:.1f}s")
    
    return results


def _align_even(y, sr, parsed_lines):
    """Simple even distribution fallback (last resort)."""
    import librosa
    
    duration = librosa.get_duration(y=y, sr=sr)
    y_trimmed, trim_indices = librosa.effects.trim(y, top_db=20)
    trim_start = trim_indices[0] / sr
    trim_end = trim_indices[1] / sr
    active_duration = trim_end - trim_start
    
    flat_syllables = [s for line in parsed_lines for s in line]
    total_syllables = len(flat_syllables)
    
    if total_syllables == 0:
        return []
    
    num_lines = len(parsed_lines)
    line_gap_time = active_duration * 0.10 / max(1, num_lines - 1) if num_lines > 1 else 0
    syllable_time = active_duration * 0.90 / total_syllables
    
    results = []
    current_time = trim_start
    
    for line_idx, line in enumerate(parsed_lines):
        for syl in line:
            start = current_time
            end = current_time + syllable_time
            
            results.append({
                "syllable": syl["text"],
                "start": start,
                "end": end,
                "confidence": 0.3,
                "is_rap": syl.get("is_rap", False),
                "method": "fallback_even",
                "line_index": line_idx
            })
            
            current_time = end
        
        if line_idx < num_lines - 1:
            current_time += line_gap_time
    
    return results
