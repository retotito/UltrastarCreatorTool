"""WhisperX-based alignment: uses phoneme-aligned word timestamps + character timestamps
for precise syllable splitting.

When WhisperX is used, we get:
- Word-level timestamps with ~50ms accuracy (from wav2vec2 forced alignment)
- Character-level timestamps for sub-word precision

When vanilla Whisper is used (fallback), we get:
- Word-level timestamps with ~200ms accuracy
- No character timestamps (proportional splitting as before)

Algorithm:
1. Parse lyrics into syllables (reuse parse_lyrics)
2. Reconstruct words from syllable groups
3. Match lyrics words to Whisper/X word timestamps (fuzzy sequential matching)
4. For matched words with char timestamps: use char boundaries for syllable splits
5. For matched words without char timestamps: proportional splitting by char count
6. For unmatched gap sections: energy-based sub-alignment on the audio segment
7. Interpolate any remaining small gaps from neighbors
"""

import re
from typing import List, Optional
from utils.logger import log_step


def parse_lyrics(lyrics_text: str) -> List[List[dict]]:
    """Parse lyrics text into list of lines, each containing syllables.
    
    Duplicated from alignment.py to avoid triggering the slow MFA check
    that runs at import time in that module.
    
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
        
        if line.upper() == '[RAP]':
            is_rap = True
            continue
        if line.upper() == '[/RAP]':
            is_rap = False
            continue
        
        syllables = []
        words = line.split()
        for i, word in enumerate(words):
            parts = word.split('-')
            for j, part in enumerate(parts):
                if not part:
                    continue
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


def align_whisper(
    lyrics_text: str,
    whisper_words: List[dict],
    language: str = "english",
    char_timestamps: Optional[List[dict]] = None,
    audio_path: Optional[str] = None,
) -> List[dict]:
    """Align lyrics to audio using Whisper/WhisperX word timestamps.
    
    Args:
        lyrics_text: Full lyrics text with lines and hyphenated syllables
        whisper_words: List of {word, start, end} from Whisper/WhisperX
        language: Language (unused for now, reserved for future)
        char_timestamps: Optional list of {char, start, end} from WhisperX
                        forced alignment. When present, enables precise
                        character-level syllable splitting.
        audio_path: Optional path to vocal audio file. When provided, enables
                   energy-based sub-alignment for unmatched gap sections
                   (much better than blind interpolation for repetitive lyrics).
        
    Returns:
        List of dicts matching alignment.py format:
        [{"syllable": "beau", "start": 1.23, "end": 1.56, "confidence": 0.85,
          "is_rap": False, "method": "whisperx", "line_index": 0}, ...]
    """
    parsed = parse_lyrics(lyrics_text)
    flat_syllables = [s for line in parsed for s in line]
    
    if not flat_syllables:
        log_step("ALIGN", "No syllables parsed from lyrics")
        return []
    
    if not whisper_words:
        log_step("ALIGN", "No Whisper words available, cannot align")
        return []
    
    method_name = "whisperx" if char_timestamps else "whisper"
    log_step("ALIGN", f"{method_name} alignment: {len(flat_syllables)} syllables, "
             f"{len(whisper_words)} words, {len(char_timestamps or [])} chars")
    
    # Build char-timestamp lookup for character-level syllable splitting
    char_lookup = _build_char_lookup(char_timestamps) if char_timestamps else None
    
    # ── Step 1: Build word groups from syllables ──
    word_groups = _build_word_groups(flat_syllables)
    log_step("ALIGN", f"Built {len(word_groups)} word groups from syllables")
    
    # ── Step 2: Match lyrics words to Whisper words ──
    matches = _match_words(word_groups, whisper_words)
    matched_count = sum(1 for m in matches if m is not None)
    log_step("ALIGN", f"Matched {matched_count}/{len(word_groups)} words to timestamps")
    
    # ── Debug: dump match state before gap filling ──
    _dump_alignment_debug(word_groups, matches, whisper_words, "pre_gap_fill")
    
    # ── Step 3: Hybrid gap alignment ──
    # For large gaps of unmatched words, use energy-based sub-alignment
    # on the audio segment instead of blind interpolation.
    _fill_gaps_hybrid(word_groups, matches, whisper_words, audio_path)
    
    # ── Debug: dump match state after gap filling ──
    _dump_alignment_debug(word_groups, matches, whisper_words, "post_gap_fill")
    
    # ── Step 4: Distribute syllables within each word's time span ──
    results = _distribute_syllables(word_groups, matches, char_lookup, method_name)
    
    log_step("ALIGN", f"Alignment complete: {len(results)} syllables ({method_name})")
    if results:
        log_step("ALIGN", f"  First: '{results[0]['syllable']}' at {results[0]['start']:.3f}s")
        log_step("ALIGN", f"  Last:  '{results[-1]['syllable']}' at {results[-1]['end']:.3f}s")
        # Count char-split vs proportional
        char_split = sum(1 for r in results if r.get("split_method") == "char")
        prop_split = sum(1 for r in results if r.get("split_method") == "proportional")
        if char_split > 0:
            log_step("ALIGN", f"  Char-level splits: {char_split}, Proportional: {prop_split}")
    
    return results


def _build_char_lookup(char_timestamps: List[dict]) -> dict:
    """Build a time-indexed lookup from character timestamps.
    
    Returns a dict mapping approximate time ranges to character info,
    enabling us to find character boundaries within a word's time span.
    
    The lookup is structured as a sorted list of (time, char) tuples
    for efficient binary search.
    """
    if not char_timestamps:
        return {"chars": [], "by_time": []}
    
    # Build sorted list of (start_time, end_time, char) for binary search
    by_time = []
    for c in char_timestamps:
        start = c.get("start")
        end = c.get("end")
        char = c.get("char", "")
        if start is not None and end is not None:
            by_time.append((start, end, char))
    
    by_time.sort(key=lambda x: x[0])
    
    return {"chars": char_timestamps, "by_time": by_time}


def _find_chars_in_range(char_lookup: dict, start: float, end: float) -> list:
    """Find all characters within a time range.
    
    Returns list of (start, end, char) tuples within [start-tolerance, end+tolerance].
    """
    if not char_lookup or not char_lookup["by_time"]:
        return []
    
    by_time = char_lookup["by_time"]
    tolerance = 0.05  # 50ms tolerance for boundary matching
    
    result = []
    for t_start, t_end, char in by_time:
        if t_start >= end + tolerance:
            break
        if t_end <= start - tolerance:
            continue
        result.append((t_start, t_end, char))
    
    return result


def _build_word_groups(flat_syllables: list) -> list:
    """Group syllables into words based on is_word_start markers.
    
    Returns list of word groups:
    [{"word": "beautiful", "clean": "beautiful", "syllables": [...], 
      "line_index": 0, "is_rap": False}, ...]
    """
    groups = []
    current = None
    
    for syl in flat_syllables:
        if syl["is_word_start"] or current is None:
            if current is not None:
                groups.append(current)
            # Reconstruct clean word from the "word" field (has hyphens)
            raw_word = syl.get("word", syl["text"])
            clean = _clean_word(raw_word)
            current = {
                "word": raw_word,
                "clean": clean,
                "syllables": [syl],
                "line_index": syl.get("line_index", 0),
                "is_rap": syl.get("is_rap", False),
            }
        else:
            current["syllables"].append(syl)
    
    if current is not None:
        groups.append(current)
    
    return groups


def _clean_word(word: str) -> str:
    """Normalize word for matching: lowercase, remove punctuation except apostrophes, remove hyphens."""
    w = word.replace('-', '').lower().strip()
    # Normalize curly apostrophes
    w = w.replace('\u2019', "'").replace('\u2018', "'")
    # Remove all punctuation except apostrophes
    w = re.sub(r"[^\w']", '', w)
    return w


def _match_words(word_groups: list, whisper_words: list) -> list:
    """Match lyrics words to Whisper words sequentially with lookahead.
    
    Returns a list parallel to word_groups, where each element is either:
    - A dict {start, end, whisper_idx} for matched words
    - None for unmatched words
    """
    matches = [None] * len(word_groups)
    w_idx = 0  # Whisper index
    
    for g_idx, group in enumerate(word_groups):
        if w_idx >= len(whisper_words):
            break
        
        g_clean = group["clean"]
        
        # Direct match
        ww = whisper_words[w_idx]
        ww_clean = _clean_word(ww.get("word", ""))
        
        if g_clean == ww_clean:
            matches[g_idx] = {
                "start": ww["start"],
                "end": ww["end"],
                "whisper_idx": w_idx,
                "confidence": 0.9,
            }
            w_idx += 1
            continue
        
        # Lookahead in Whisper words (skip Whisper words not in lyrics)
        found = False
        for look_w in range(1, 20):
            if w_idx + look_w >= len(whisper_words):
                break
            if _clean_word(whisper_words[w_idx + look_w].get("word", "")) == g_clean:
                w_idx += look_w
                matches[g_idx] = {
                    "start": whisper_words[w_idx]["start"],
                    "end": whisper_words[w_idx]["end"],
                    "whisper_idx": w_idx,
                    "confidence": 0.8,
                }
                w_idx += 1
                found = True
                break
        
        if found:
            continue
        
        # Lookahead in lyrics words (skip lyrics words not in Whisper)
        for look_g in range(1, 20):
            if g_idx + look_g >= len(word_groups):
                break
            if word_groups[g_idx + look_g]["clean"] == ww_clean:
                # Don't advance w_idx — let the future group match it
                break
        
        # This word is unmatched, try next Whisper word
        # Don't advance w_idx (Whisper word might match a later lyrics word)
    
    return matches


def _interpolate_unmatched(word_groups: list, matches: list, whisper_words: list):
    """Fill in timing for unmatched words by interpolating from neighbors.
    
    Modifies matches in-place.
    """
    n = len(matches)
    
    # Build list of (index, start_time) for matched words
    anchors = [(i, m["start"], m["end"]) for i, m in enumerate(matches) if m is not None]
    
    if not anchors:
        # No matches at all — distribute evenly across audio
        if whisper_words:
            audio_start = whisper_words[0]["start"]
            audio_end = whisper_words[-1]["end"]
        else:
            audio_start = 0.0
            audio_end = 60.0
        
        dur_per_word = (audio_end - audio_start) / max(1, n)
        for i in range(n):
            matches[i] = {
                "start": audio_start + i * dur_per_word,
                "end": audio_start + (i + 1) * dur_per_word,
                "whisper_idx": -1,
                "confidence": 0.3,
            }
        return
    
    for i in range(n):
        if matches[i] is not None:
            continue
        
        # Find nearest anchors before and after
        prev_anchor = None
        next_anchor = None
        
        for idx, start, end in anchors:
            if idx < i:
                prev_anchor = (idx, start, end)
            elif idx > i and next_anchor is None:
                next_anchor = (idx, start, end)
                break
        
        if prev_anchor and next_anchor:
            # Interpolate between neighbors
            p_idx, p_start, p_end = prev_anchor
            n_idx, n_start, n_end = next_anchor
            # Position proportionally between prev and next
            frac = (i - p_idx) / (n_idx - p_idx)
            t_start = p_end + frac * (n_start - p_end)
            t_end = t_start + (n_end - n_start) / max(1, n_idx - p_idx)
            # Ensure end doesn't exceed next anchor start
            t_end = min(t_end, n_start)
            if t_end <= t_start:
                t_end = t_start + 0.05  # minimum 50ms
        elif prev_anchor:
            # After last anchor — extrapolate forward
            p_idx, p_start, p_end = prev_anchor
            gap = i - p_idx
            avg_word_dur = (p_end - p_start)
            t_start = p_end + (gap - 1) * avg_word_dur * 0.5
            t_end = t_start + avg_word_dur
        elif next_anchor:
            # Before first anchor — extrapolate backward
            n_idx, n_start, n_end = next_anchor
            gap = n_idx - i
            avg_word_dur = (n_end - n_start)
            t_start = n_start - gap * avg_word_dur
            t_end = t_start + avg_word_dur
            if t_start < 0:
                t_start = 0.0
        else:
            continue
        
        matches[i] = {
            "start": t_start,
            "end": t_end,
            "whisper_idx": -1,
            "confidence": 0.4,  # lower confidence for interpolated
        }


def _find_whisper_silent_regions(whisper_words: list, min_gap: float = 2.0) -> list:
    """Find regions in the audio where WhisperX detected nothing.
    
    These are gaps between consecutive WhisperX words exceeding min_gap seconds.
    These regions typically contain vocals that WhisperX failed to transcribe
    (e.g., repetitive "La-da-dee" or "Ah!" sections).
    
    Returns: list of (start_time, end_time) tuples, sorted chronologically.
    """
    if not whisper_words or len(whisper_words) < 2:
        return []
    
    regions = []
    for i in range(len(whisper_words) - 1):
        gap_start = whisper_words[i]["end"]
        gap_end = whisper_words[i + 1]["start"]
        if gap_end - gap_start >= min_gap:
            regions.append((gap_start, gap_end))
    
    return regions


def _fill_gaps_hybrid(word_groups: list, matches: list, whisper_words: list,
                      audio_path: Optional[str] = None):
    """Fill unmatched word gaps using energy-based sub-alignment when possible.
    
    Key improvement: when anchor-bounded time for a gap is too small (e.g.,
    WhisperX detected words on both sides of the lyrics gap but they're
    chronologically adjacent), we look for WhisperX-silent regions in the
    audio timeline and remap the gap there. This handles repetitive choruses
    that WhisperX can't transcribe.
    
    For large gaps (3+ consecutive unmatched words), loads the audio segment
    and uses vocal energy detection to distribute syllables where there's
    actually sound.
    
    For small gaps (1-2 words), falls back to simple interpolation.
    
    Modifies matches in-place.
    """
    n = len(matches)
    
    # Build anchors (matched words with known timestamps)
    anchors = [(i, m["start"], m["end"]) for i, m in enumerate(matches) if m is not None]
    
    if not anchors:
        # No matches at all — use full audio range with energy alignment
        if whisper_words:
            audio_start = whisper_words[0]["start"]
            audio_end = whisper_words[-1]["end"]
        else:
            audio_start = 0.0
            audio_end = 60.0
        
        if audio_path:
            _energy_align_range(word_groups, matches, 0, n - 1, audio_start, audio_end, audio_path)
        else:
            dur_per_word = (audio_end - audio_start) / max(1, n)
            for i in range(n):
                matches[i] = {
                    "start": audio_start + i * dur_per_word,
                    "end": audio_start + (i + 1) * dur_per_word,
                    "whisper_idx": -1,
                    "confidence": 0.3,
                }
        return
    
    # Find WhisperX-silent regions (gaps > 2s in whisper timeline)
    # These are where WhisperX failed to transcribe — likely repetitive vocals
    silent_regions = _find_whisper_silent_regions(whisper_words, min_gap=2.0)
    silent_region_idx = 0  # Track consumed regions (process in order)
    
    if silent_regions:
        log_step("ALIGN", f"Found {len(silent_regions)} WhisperX-silent regions: "
                 + ", ".join(f"{s:.1f}-{e:.1f}s" for s, e in silent_regions))
    
    # Find contiguous runs of unmatched words (gaps)
    gaps = []  # list of (gap_start_idx, gap_end_idx) inclusive
    i = 0
    while i < n:
        if matches[i] is None:
            gap_start = i
            while i < n and matches[i] is None:
                i += 1
            gaps.append((gap_start, i - 1))
        else:
            i += 1
    
    for gap_start, gap_end in gaps:
        gap_size = gap_end - gap_start + 1
        
        # Find the bounding anchors for this gap
        prev_anchor = None
        next_anchor = None
        for idx, start, end in anchors:
            if idx < gap_start:
                prev_anchor = (idx, start, end)
            elif idx > gap_end and next_anchor is None:
                next_anchor = (idx, start, end)
                break
        
        # Determine the audio time range for this gap from anchors
        if prev_anchor and next_anchor:
            time_start = prev_anchor[2]  # end of previous matched word
            time_end = next_anchor[1]    # start of next matched word
        elif prev_anchor:
            time_start = prev_anchor[2]
            avg_dur = _avg_matched_word_duration(matches)
            time_end = time_start + gap_size * avg_dur
            if whisper_words:
                # Cap at end of audio, but never less than time_start + some minimum
                audio_end = whisper_words[-1]["end"]
                # Allow extending beyond last whisper word up to audio duration
                time_end = min(time_end, audio_end + 15.0)
                # Ensure minimum duration for the gap
                time_end = max(time_end, time_start + gap_size * 0.15)
        elif next_anchor:
            time_end = next_anchor[1]
            avg_dur = _avg_matched_word_duration(matches)
            time_start = max(0.0, time_end - gap_size * avg_dur)
        else:
            continue
        
        if time_end <= time_start:
            time_end = time_start + 0.1 * gap_size
        
        gap_duration = time_end - time_start
        min_needed = gap_size * 0.12  # ~120ms per word minimum for singing
        
        # ── Check if gap has sufficient time ──
        # When bounding anchors are too close (e.g., WhisperX transcribed words
        # on both sides but missed the chorus in between), remap to a
        # WhisperX-silent region where the actual vocals likely are.
        if gap_size >= 3 and gap_duration < min_needed and silent_regions:
            # Find the nearest WhisperX-silent region at or after the gap's time
            best_region = None
            for sr_idx in range(silent_region_idx, len(silent_regions)):
                sr_start, sr_end = silent_regions[sr_idx]
                # Region should be near the gap's anchors (within 30s forward)
                if sr_start >= time_start - 2.0 and sr_start <= time_start + 30.0:
                    best_region = (sr_idx, sr_start, sr_end)
                    break
                # Also accept regions that overlap with the gap time
                if sr_end >= time_start and sr_start <= time_end + 30.0:
                    best_region = (sr_idx, sr_start, sr_end)
                    break
            
            if best_region:
                sr_idx, new_start, new_end = best_region
                
                # If the selected region is still too small for this gap,
                # combine with subsequent silent regions to get enough time.
                combined_end = new_end
                combined_idx = sr_idx
                combined_duration = combined_end - new_start
                while combined_duration < min_needed and combined_idx + 1 < len(silent_regions):
                    combined_idx += 1
                    _, next_end = silent_regions[combined_idx]
                    combined_end = next_end
                    combined_duration = combined_end - new_start
                
                silent_region_idx = combined_idx + 1  # consume all used regions
                log_step("ALIGN", f"Gap [{gap_start}..{gap_end}] ({gap_size} words): "
                         f"anchor time too small ({gap_duration:.2f}s < {min_needed:.2f}s needed), "
                         f"remapped to WhisperX-silent region {new_start:.2f}s - {combined_end:.2f}s")
                time_start = new_start
                time_end = combined_end
                gap_duration = time_end - time_start
        
        # For large gaps with audio available: use energy-based sub-alignment
        if gap_size >= 3 and audio_path:
            log_step("ALIGN", f"Gap of {gap_size} unmatched words [{gap_start}..{gap_end}] "
                     f"→ energy sub-alignment ({time_start:.2f}s - {time_end:.2f}s)")
            _energy_align_range(word_groups, matches, gap_start, gap_end,
                               time_start, time_end, audio_path)
        else:
            # Small gaps: simple interpolation
            for idx in range(gap_start, gap_end + 1):
                frac = (idx - gap_start) / max(1, gap_size)
                t_start = time_start + frac * (time_end - time_start)
                t_end = time_start + (frac + 1.0 / gap_size) * (time_end - time_start)
                t_end = min(t_end, time_end)
                if t_end <= t_start:
                    t_end = t_start + 0.05
                matches[idx] = {
                    "start": t_start,
                    "end": t_end,
                    "whisper_idx": -1,
                    "confidence": 0.4,
                }


def _avg_matched_word_duration(matches: list) -> float:
    """Calculate average duration of matched words."""
    durations = [m["end"] - m["start"] for m in matches if m is not None]
    if durations:
        return sum(durations) / len(durations)
    return 0.3  # default 300ms


def _dump_alignment_debug(word_groups: list, matches: list, whisper_words: list, phase: str):
    """Write a debug dump file showing the match state for each word group."""
    import os
    debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads")
    os.makedirs(debug_dir, exist_ok=True)
    debug_path = os.path.join(debug_dir, f"alignment_whisper_debug_{phase}.txt")
    
    try:
        with open(debug_path, "w") as f:
            f.write(f"ALIGNMENT WHISPER DEBUG — {phase}\n")
            f.write(f"{'='*70}\n")
            f.write(f"Word groups: {len(word_groups)}, WhisperX words: {len(whisper_words)}\n")
            matched = sum(1 for m in matches if m is not None)
            f.write(f"Matched: {matched}/{len(word_groups)}\n\n")
            
            # List all word groups with their match status
            f.write(f"{'#':>4} {'Word':<20} {'Matched?':>8} {'Start':>8} {'End':>8} {'Conf':>5} {'Line':>4}\n")
            f.write(f"{'-'*70}\n")
            
            gap_count = 0
            in_gap = False
            for i, (wg, m) in enumerate(zip(word_groups, matches)):
                word = wg['word'][:20]
                line_idx = wg.get('line_index', '?')
                if m is not None:
                    if in_gap:
                        f.write(f"  --- end gap ({gap_count} words) ---\n")
                        in_gap = False
                        gap_count = 0
                    f.write(f"{i:4d} {word:<20} {'YES':>8} {m['start']:8.3f} {m['end']:8.3f} {m.get('confidence', 0):5.2f} {line_idx:>4}\n")
                else:
                    if not in_gap:
                        f.write(f"  --- gap start ---\n")
                        in_gap = True
                    gap_count += 1
                    f.write(f"{i:4d} {word:<20} {'---':>8} {'':>8} {'':>8} {'':>5} {line_idx:>4}\n")
            
            if in_gap:
                f.write(f"  --- end gap ({gap_count} words) ---\n")
            
            # List WhisperX-silent regions
            f.write(f"\n{'='*70}\n")
            f.write(f"WHISPERX-SILENT REGIONS (gaps > 2s in whisper timeline):\n")
            regions = _find_whisper_silent_regions(whisper_words, min_gap=2.0)
            for i, (s, e) in enumerate(regions):
                f.write(f"  Region {i+1}: {s:.2f}s - {e:.2f}s ({e-s:.1f}s)\n")
            if not regions:
                f.write(f"  (none)\n")
    except Exception as e:
        log_step("ALIGN", f"Debug dump failed: {e}")


def _energy_align_range(word_groups: list, matches: list,
                        gap_start: int, gap_end: int,
                        time_start: float, time_end: float,
                        audio_path: str):
    """Use energy-based alignment to place unmatched words in an audio segment.
    
    Loads the audio segment, detects vocal energy, finds micro-sections
    where there's sound, and distributes the gap words across those sections.
    This handles repetitive lyrics (La-da-dee x10, Ah! x16) much better
    than linear interpolation.
    """
    import librosa
    import numpy as np
    
    gap_size = gap_end - gap_start + 1
    segment_duration = time_end - time_start
    
    if segment_duration < 0.1:
        # Segment too short — just distribute evenly
        _even_distribute(matches, gap_start, gap_end, time_start, time_end)
        return
    
    try:
        # Load only the relevant audio segment
        y, sr = librosa.load(audio_path, sr=16000, mono=True,
                             offset=time_start, duration=segment_duration)
        
        if len(y) == 0:
            _even_distribute(matches, gap_start, gap_end, time_start, time_end)
            return
        
        # Detect energy using RMS
        hop_length = 256
        frame_length = 1024
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
        
        if len(rms) == 0:
            _even_distribute(matches, gap_start, gap_end, time_start, time_end)
            return
        
        # Adaptive threshold: 10% of max RMS
        threshold = np.max(rms) * 0.10
        is_voiced = rms > threshold
        
        # Find voiced micro-segments with small gap merging
        raw_segments = []
        in_seg = False
        seg_start_t = 0.0
        
        for i in range(len(is_voiced)):
            if is_voiced[i] and not in_seg:
                seg_start_t = times[i]
                in_seg = True
            elif not is_voiced[i] and in_seg:
                raw_segments.append((seg_start_t, times[i]))
                in_seg = False
        if in_seg:
            raw_segments.append((seg_start_t, times[-1] if len(times) > 0 else segment_duration))
        
        # Merge segments with short gaps (< 0.3s) — breathing gaps within phrases
        merged = []
        for seg in raw_segments:
            if merged and seg[0] - merged[-1][1] < 0.3:
                merged[-1] = (merged[-1][0], seg[1])
            else:
                merged.append(seg)
        
        # Filter tiny segments (< 0.08s)
        segments = [(s, e) for s, e in merged if e - s >= 0.08]
        
        if not segments:
            _even_distribute(matches, gap_start, gap_end, time_start, time_end)
            return
        
        # Convert relative times to absolute times
        segments = [(s + time_start, e + time_start) for s, e in segments]
        
        total_voiced_time = sum(e - s for s, e in segments)
        log_step("ALIGN", f"  Energy sub-alignment: {len(segments)} voiced sections, "
                 f"{total_voiced_time:.2f}s voiced / {segment_duration:.2f}s total")
        
        # Build line groups for the gap words to detect phrase breaks
        # Words on the same lyrics line should be in the same segment
        line_groups = []  # list of (line_idx, word_indices)
        current_line = None
        current_indices = []
        for idx in range(gap_start, gap_end + 1):
            line_idx = word_groups[idx]["line_index"]
            if current_line is not None and line_idx != current_line:
                line_groups.append((current_line, current_indices))
                current_indices = []
            current_line = line_idx
            current_indices.append(idx)
        if current_indices:
            line_groups.append((current_line, current_indices))
        
        # Distribute line groups across voiced segments proportionally
        # (by syllable count per group vs segment duration)
        total_syllables = sum(len(word_groups[idx]["syllables"]) for idx in range(gap_start, gap_end + 1))
        
        # Assign line groups to segments proportionally by voiced duration
        seg_durations = [e - s for s, e in segments]
        total_seg_dur = sum(seg_durations)
        
        # Calculate how many syllables each segment "should" hold
        seg_capacities = [(dur / total_seg_dur) * total_syllables for dur in seg_durations]
        
        # Greedily assign line groups to segments
        assignments = []  # (word_idx, seg_start, seg_end) for each gap word
        seg_idx = 0
        seg_used = 0.0  # syllables assigned to current segment
        
        for line_idx, word_indices in line_groups:
            group_syllables = sum(len(word_groups[idx]["syllables"]) for idx in word_indices)
            
            # Move to next segment if current is full (allow 50% overflow to keep lines together)
            while (seg_idx < len(segments) - 1 and
                   seg_used > 0 and
                   seg_used + group_syllables > seg_capacities[seg_idx] * 1.5):
                seg_idx += 1
                seg_used = 0.0
            
            seg_s, seg_e = segments[min(seg_idx, len(segments) - 1)]
            for word_idx in word_indices:
                assignments.append((word_idx, seg_s, seg_e))
            seg_used += group_syllables
        
        # Now distribute words within their assigned segments
        # Group by segment to calculate timing
        from collections import defaultdict
        seg_words = defaultdict(list)
        for word_idx, seg_s, seg_e in assignments:
            seg_words[(seg_s, seg_e)].append(word_idx)
        
        for (seg_s, seg_e), word_indices in seg_words.items():
            seg_dur = seg_e - seg_s
            total_syls = sum(len(word_groups[idx]["syllables"]) for idx in word_indices)
            if total_syls == 0:
                continue
            
            # Distribute time across words proportional to their syllable count
            current_t = seg_s
            for word_idx in word_indices:
                n_syls = len(word_groups[word_idx]["syllables"])
                word_dur = seg_dur * (n_syls / total_syls)
                matches[word_idx] = {
                    "start": current_t,
                    "end": current_t + word_dur,
                    "whisper_idx": -1,
                    "confidence": 0.55,  # better than blind interpolation (0.4) but worse than WhisperX match (0.9)
                }
                current_t += word_dur
        
        # Fill any remaining unmatched (shouldn't happen but safety)
        for idx in range(gap_start, gap_end + 1):
            if matches[idx] is None:
                _even_distribute(matches, idx, idx, time_start, time_end)
        
    except Exception as e:
        log_step("ALIGN", f"  Energy sub-alignment failed: {e}, falling back to interpolation")
        _even_distribute(matches, gap_start, gap_end, time_start, time_end)


def _even_distribute(matches: list, gap_start: int, gap_end: int,
                     time_start: float, time_end: float):
    """Evenly distribute unmatched words across a time range (last resort)."""
    gap_size = gap_end - gap_start + 1
    dur_per_word = (time_end - time_start) / max(1, gap_size)
    for i in range(gap_start, gap_end + 1):
        offset = i - gap_start
        matches[i] = {
            "start": time_start + offset * dur_per_word,
            "end": time_start + (offset + 1) * dur_per_word,
            "whisper_idx": -1,
            "confidence": 0.3,
        }


def _distribute_syllables(word_groups: list, matches: list,
                          char_lookup: Optional[dict] = None,
                          method_name: str = "whisper") -> list:
    """Distribute syllables within each word's time span.
    
    When char_lookup is available (from WhisperX):
    - Uses character-level timestamps to split syllables at exact char boundaries
    - Much more accurate than proportional splitting
    
    Fallback (no char_lookup):
    - Proportional splitting by character count (same as before)
    """
    results = []
    
    for g_idx, group in enumerate(word_groups):
        match = matches[g_idx]
        if match is None:
            continue
        
        syllables = group["syllables"]
        word_start = match["start"]
        word_end = match["end"]
        word_dur = word_end - word_start
        confidence = match.get("confidence", 0.5)
        
        if len(syllables) == 1:
            # Single syllable — use full word span
            results.append({
                "syllable": syllables[0]["text"],
                "start": word_start,
                "end": word_end,
                "confidence": confidence,
                "is_rap": syllables[0].get("is_rap", False),
                "method": method_name,
                "line_index": group["line_index"],
                "split_method": "single",
            })
        elif char_lookup and char_lookup["by_time"]:
            # ── Character-level splitting (WhisperX) ──
            _distribute_by_chars(
                results, syllables, group, match,
                word_start, word_end, confidence,
                char_lookup, method_name,
            )
        else:
            # ── Proportional splitting (fallback) ──
            _distribute_proportional(
                results, syllables, group, match,
                word_start, word_end, word_dur, confidence,
                method_name,
            )
    
    return results


def _distribute_by_chars(
    results: list, syllables: list, group: dict, match: dict,
    word_start: float, word_end: float, confidence: float,
    char_lookup: dict, method_name: str,
):
    """Split syllables using character-level timestamps from WhisperX.
    
    For each syllable, find the characters that belong to it (by counting
    characters through the word), then use those characters' time range.
    """
    # Get chars in this word's time range
    word_chars = _find_chars_in_range(char_lookup, word_start, word_end)
    
    if not word_chars:
        # No char data for this word — fall back to proportional
        word_dur = word_end - word_start
        _distribute_proportional(
            results, syllables, group, match,
            word_start, word_end, word_dur, confidence,
            method_name,
        )
        return
    
    # Map syllables to character spans
    # Reconstruct the clean word from syllables to count characters
    syl_texts = []
    for syl in syllables:
        text = syl["text"].strip().lower()
        text = re.sub(r"[^\w']", '', text)
        syl_texts.append(text)
    
    # Build character position → syllable index mapping
    char_to_syl = []
    for syl_idx, text in enumerate(syl_texts):
        for _ in text:
            char_to_syl.append(syl_idx)
    
    # Match word_chars to syllable indices
    # word_chars are the WhisperX characters, char_to_syl maps position to syllable
    syl_time_ranges = {}  # syl_idx -> (min_start, max_end)
    
    # Filter word_chars to only alphabetical chars for matching
    alpha_chars = [(s, e, c) for s, e, c in word_chars if c.strip() and c.isalpha()]
    
    for pos, (c_start, c_end, c_char) in enumerate(alpha_chars):
        if pos < len(char_to_syl):
            syl_idx = char_to_syl[pos]
            if syl_idx not in syl_time_ranges:
                syl_time_ranges[syl_idx] = (c_start, c_end)
            else:
                prev_start, prev_end = syl_time_ranges[syl_idx]
                syl_time_ranges[syl_idx] = (min(prev_start, c_start), max(prev_end, c_end))
    
    # Build results using char-derived boundaries
    used_char_split = False
    for syl_idx, syl in enumerate(syllables):
        if syl_idx in syl_time_ranges:
            syl_start, syl_end = syl_time_ranges[syl_idx]
            # Clamp to word boundaries
            syl_start = max(syl_start, word_start)
            syl_end = min(syl_end, word_end)
            if syl_end <= syl_start:
                syl_end = syl_start + 0.02  # minimum 20ms
            used_char_split = True
            split_method = "char"
        else:
            # This syllable has no char matches — estimate from neighbors
            syl_start = word_start if syl_idx == 0 else results[-1]["end"] if results else word_start
            syl_end = word_end if syl_idx == len(syllables) - 1 else syl_start + 0.05
            split_method = "proportional"
        
        results.append({
            "syllable": syl["text"],
            "start": syl_start,
            "end": syl_end,
            "confidence": confidence * (0.95 if split_method == "char" else 0.85),
            "is_rap": syl.get("is_rap", False),
            "method": method_name,
            "line_index": group["line_index"],
            "split_method": split_method,
        })
    
    # Fix gaps/overlaps between syllables within this word
    word_results = results[-(len(syllables)):]
    for i in range(1, len(word_results)):
        # Close gaps: set start of next to end of previous
        if word_results[i]["start"] > word_results[i-1]["end"]:
            # Small gap — close it by extending previous syllable
            word_results[i-1]["end"] = word_results[i]["start"]
        elif word_results[i]["start"] < word_results[i-1]["end"]:
            # Overlap — split at midpoint
            mid = (word_results[i]["start"] + word_results[i-1]["end"]) / 2
            word_results[i-1]["end"] = mid
            word_results[i]["start"] = mid
    
    # Ensure first syllable starts at word_start and last ends at word_end
    if word_results:
        word_results[0]["start"] = word_start
        word_results[-1]["end"] = word_end


def _distribute_proportional(
    results: list, syllables: list, group: dict, match: dict,
    word_start: float, word_end: float, word_dur: float,
    confidence: float, method_name: str,
):
    """Distribute syllables proportionally by character count (fallback)."""
    weights = []
    for syl in syllables:
        text = syl["text"].strip()
        w = max(1, len(text))
        weights.append(w)
    
    total_weight = sum(weights)
    current_time = word_start
    
    for syl_idx, syl in enumerate(syllables):
        syl_dur = word_dur * weights[syl_idx] / total_weight
        syl_start = current_time
        syl_end = current_time + syl_dur
        
        if syl_idx == len(syllables) - 1:
            syl_end = word_end
        
        results.append({
            "syllable": syl["text"],
            "start": syl_start,
            "end": syl_end,
            "confidence": confidence * 0.9,
            "is_rap": syl.get("is_rap", False),
            "method": method_name,
            "line_index": group["line_index"],
            "split_method": "proportional",
        })
        
        current_time = syl_end
