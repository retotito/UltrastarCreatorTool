"""Forced alignment using Montreal Forced Aligner (MFA).

Aligns lyrics text to audio to get per-syllable timing.
Falls back to energy-based detection if MFA is not available.
"""

import os
import json
import re
import tempfile
import subprocess
from typing import List, Tuple, Optional
from utils.logger import log_step, log_progress

# ── Detect MFA via conda environment ──
CONDA_BIN = os.path.expanduser("~/miniconda3/bin/conda")
MFA_ENV = "mfa"

def _check_mfa():
    """Check if MFA is available in the conda environment."""
    if not os.path.exists(CONDA_BIN):
        return False
    try:
        result = subprocess.run(
            [CONDA_BIN, "run", "-n", MFA_ENV, "mfa", "version"],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

MFA_AVAILABLE = _check_mfa()
if MFA_AVAILABLE:
    log_step("INIT", "MFA available via conda (real forced alignment)")
else:
    log_step("INIT", "MFA not found, will use energy-based fallback alignment")


def align_lyrics_to_audio(
    audio_path: str,
    lyrics_text: str,
    language: str = "english"
) -> List[dict]:
    """Align lyrics to audio, returning timing for each syllable.
    
    Args:
        audio_path: Path to vocal audio file
        lyrics_text: Full lyrics text with lines and hyphenated syllables
        language: Language for MFA model
        
    Returns:
        List of dicts: [{"syllable": "beau", "start": 1.23, "end": 1.56, "confidence": 0.95}, ...]
    """
    # Parse lyrics into syllables with line structure
    parsed = parse_lyrics(lyrics_text)
    flat_syllables = [s for line in parsed for s in line]
    
    log_step("ALIGN", f"Parsed {len(flat_syllables)} syllables across {len(parsed)} lines")
    
    if MFA_AVAILABLE:
        try:
            results = align_with_mfa(audio_path, lyrics_text, flat_syllables, language)
            log_step("ALIGN", f"MFA alignment succeeded: {len(results)} syllables")
            if results:
                log_step("ALIGN", f"  First syllable: '{results[0]['syllable']}' at {results[0]['start']:.3f}s (method={results[0]['method']})")
                log_step("ALIGN", f"  Last syllable: '{results[-1]['syllable']}' at {results[-1]['end']:.3f}s")
            # Write debug trace
            _write_alignment_debug(results, "mfa")
            return results
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            log_step("ALIGN", f"MFA failed: {e}")
            log_step("ALIGN", f"MFA traceback:\n{tb}")
            log_step("ALIGN", "Falling back to energy-based alignment")
            # Write error to debug file (separate from mfa_error.txt which has stderr)
            err_path = os.path.join(os.path.dirname(__file__), '..', 'downloads', 'mfa_traceback.txt')
            try:
                with open(err_path, 'w') as ef:
                    ef.write(f"MFA ERROR: {e}\n\n{tb}\n")
            except:
                pass
    
    # Fallback: distribute syllables using energy-based segment detection
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
                    "line_index": len(lines)  # track which line this syllable belongs to
                })
        
        if syllables:
            lines.append(syllables)
    
    return lines


def _clean_lyrics_to_words(lyrics_text: str) -> List[str]:
    """Convert lyrics text into a flat list of clean words for MFA."""
    clean_words = []
    for line in lyrics_text.strip().split('\n'):
        line = line.strip()
        if not line or line.upper() in ['[RAP]', '[/RAP]']:
            continue
        # Remove hyphens (MFA works on whole words)
        clean_line = line.replace('-', '')
        # Normalize curly apostrophes to straight
        clean_line = clean_line.replace('\u2019', "'").replace('\u2018', "'")
        # Strip punctuation except apostrophes (needed for contractions)
        clean_line = re.sub(r"[^\w\s']", '', clean_line)
        # Lowercase for dictionary matching
        clean_line = clean_line.lower()
        words = clean_line.split()
        clean_words.extend(words)
    return clean_words


def _detect_vocal_sections(y, sr, min_silence_sec=1.0, min_section_sec=1.0):
    """Detect vocal sections in audio by finding silence gaps.
    
    Returns list of (start_sec, end_sec) tuples for voiced sections.
    
    Pipeline:
    1. Find ALL raw voiced frames (even tiny ones)
    2. Merge segments with gaps < 0.5s (brief breath/dip within a word)
    3. Filter by min_section_sec (drop noise blips)
    4. Merge segments with gaps < min_silence_sec (group phrases into sections)
    """
    import librosa
    import numpy as np
    
    hop_length = 512
    frame_length = 2048
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    
    # Adaptive threshold: 8% of max RMS (lower to catch quieter vocal starts)
    threshold = np.max(rms) * 0.08
    is_voiced = rms > threshold
    
    # Step 1: Find ALL raw voiced segments (no duration filter yet)
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
    
    # Step 2: Merge segments with very short gaps (< 0.5s) — these are
    # brief energy dips within a word/phrase, not real silence
    breath_merged = []
    for seg in raw_segments:
        if breath_merged and seg[0] - breath_merged[-1][1] < 0.5:
            breath_merged[-1] = (breath_merged[-1][0], seg[1])
        else:
            breath_merged.append(seg)
    
    # Step 3: NOW filter by minimum section duration
    filtered = [(s, e) for s, e in breath_merged if e - s >= min_section_sec]
    
    # Step 4: Merge sections with gaps < min_silence_sec
    merged = []
    for seg in filtered:
        if merged and seg[0] - merged[-1][1] < min_silence_sec:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(seg)
    
    return merged


def _group_lyrics_into_sections(lyrics_text: str) -> List[List[str]]:
    """Split lyrics into sections at blank lines.
    
    Returns list of sections, each being a list of non-empty lines.
    If no blank lines, splits into groups of ~4 lines.
    """
    raw_lines = lyrics_text.strip().split('\n')
    
    sections = []
    current = []
    for line in raw_lines:
        stripped = line.strip()
        if stripped.upper() in ['[RAP]', '[/RAP]']:
            continue
        if not stripped:
            if current:
                sections.append(current)
                current = []
        else:
            current.append(stripped)
    if current:
        sections.append(current)
    
    # If only 1 section (no blank lines), split into chunks of ~4 lines
    if len(sections) <= 1 and sections:
        all_lines = sections[0]
        chunk_size = 4
        sections = [all_lines[i:i+chunk_size] for i in range(0, len(all_lines), chunk_size)]
    
    return sections


def _count_words_in_section(lines: List[str]) -> int:
    """Count words in a section of lyrics lines."""
    count = 0
    for line in lines:
        clean = line.replace('-', '')
        clean = re.sub(r"[^\w\s']", '', clean)
        count += len(clean.split())
    return count


def align_with_mfa(
    audio_path: str,
    lyrics_text: str,
    flat_syllables: list,
    language: str
) -> List[dict]:
    """Use MFA to align lyrics to audio via conda environment.
    
    Strategy: Send full audio + all lyrics as a single file to MFA.
    MFA handles silence/instrumental gaps naturally — it will align words
    to the voiced regions and leave silence as empty intervals.
    """
    import librosa
    import soundfile as sf

    # Map short language codes to MFA model names
    MFA_LANG_MAP = {
        "en": "english",
        "de": "german",
        "fr": "french",
        "es": "spanish",
        "it": "italian",
        "pt": "portuguese",
        "nl": "dutch",
        "ja": "japanese",
        "ko": "korean",
        "zh": "mandarin_china",
    }
    mfa_lang = MFA_LANG_MAP.get(language, language)
    
    log_step("ALIGN", f"Running Montreal Forced Aligner (single-pass, lang={mfa_lang})...")
    
    # ── Load audio at 16kHz (MFA standard) ──
    y, sr = librosa.load(audio_path, sr=16000, mono=True)
    audio_duration = len(y) / sr
    log_step("ALIGN", f"Audio loaded: {audio_duration:.1f}s at 16kHz")
    
    # ── Build clean transcript (all words, single string) ──
    clean_words = _clean_lyrics_to_words(lyrics_text)
    transcript = ' '.join(clean_words)
    log_step("ALIGN", f"Transcript: {len(clean_words)} words")
    
    # ── Run MFA ──
    with tempfile.TemporaryDirectory() as temp_dir:
        corpus_dir = os.path.join(temp_dir, "corpus")
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(corpus_dir)
        os.makedirs(output_dir)
        
        # Write single audio + transcript pair
        wav_path = os.path.join(corpus_dir, "song.wav")
        sf.write(wav_path, y, sr)
        
        txt_path = os.path.join(corpus_dir, "song.txt")
        with open(txt_path, 'w') as f:
            f.write(transcript)
        
        # Also save transcript for debugging
        debug_dir = os.path.join(os.path.dirname(__file__), '..', 'downloads')
        try:
            with open(os.path.join(debug_dir, 'mfa_transcript.txt'), 'w') as f:
                f.write(transcript)
        except:
            pass
        
        cmd = [
            CONDA_BIN, "run", "-n", MFA_ENV,
            "mfa", "align",
            corpus_dir,
            f"{mfa_lang}_mfa",       # dictionary
            f"{mfa_lang}_mfa",       # acoustic model
            output_dir,
            "--clean",
            "--single_speaker",
            "--beam", "100",         # wider beam for sung vocals
            "--retry_beam", "400",
        ]
        
        log_step("ALIGN", f"Running MFA align on {len(clean_words)} words, {audio_duration:.1f}s audio...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            log_step("ALIGN", f"MFA failed (exit {result.returncode})")
            if result.stderr:
                log_step("ALIGN", f"MFA stderr (last 500): {result.stderr[-500:]}")
            # Dump full stderr for debugging
            try:
                with open(os.path.join(debug_dir, 'mfa_error.txt'), 'w') as f:
                    f.write(f"Exit code: {result.returncode}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}\n")
            except:
                pass
            raise RuntimeError(f"MFA alignment failed: {result.stderr[-200:]}")
        
        log_step("ALIGN", "MFA completed successfully")
        if result.stderr:
            # Log timing info from MFA
            for line in result.stderr.split('\n'):
                if 'Everything took' in line or 'Done' in line:
                    log_step("ALIGN", f"  {line.strip()}")
        
        # ── Find and parse the TextGrid output ──
        tg_path = None
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                if f.endswith('.TextGrid'):
                    tg_path = os.path.join(root, f)
                    break
        
        if not tg_path:
            raise RuntimeError("MFA produced no TextGrid output")
        
        all_word_intervals = _parse_textgrid_words(tg_path)
        phones = _parse_textgrid_phones(tg_path)
        log_step("ALIGN", f"MFA output: {len(all_word_intervals)} words, {len(phones)} phones")
        
        if all_word_intervals:
            log_step("ALIGN", f"  First word: '{all_word_intervals[0]['text']}' at {all_word_intervals[0]['start']:.3f}s")
            log_step("ALIGN", f"  Last word: '{all_word_intervals[-1]['text']}' at {all_word_intervals[-1]['end']:.3f}s")
    
    # ── Map word intervals to syllables ──
    return _map_mfa_words_to_syllables(all_word_intervals, flat_syllables, lyrics_text, phones)


def _parse_textgrid_words(textgrid_path: str) -> List[dict]:
    """Parse word intervals from TextGrid file."""
    with open(textgrid_path, 'r') as f:
        content = f.read()
    
    # Find the "words" tier
    # TextGrid has two tiers: "words" and "phones"
    # We want the words tier
    tiers = content.split('item [')
    word_tier = None
    for tier in tiers:
        if '"words"' in tier:
            word_tier = tier
            break
    
    if not word_tier:
        # Fall back to first tier
        word_tier = content
    
    pattern = r'xmin = ([\d.]+)\s+xmax = ([\d.]+)\s+text = "([^"]*)"'
    matches = re.findall(pattern, word_tier)
    
    intervals = []
    for xmin, xmax, text in matches:
        text = text.strip()
        if text:  # Skip empty intervals (silence)
            intervals.append({
                "start": float(xmin),
                "end": float(xmax),
                "text": text.lower()
            })
    
    return intervals


def _parse_textgrid_phones(textgrid_path: str) -> List[dict]:
    """Parse phone intervals from TextGrid file."""
    with open(textgrid_path, 'r') as f:
        content = f.read()
    
    tiers = content.split('item [')
    phone_tier = None
    for tier in tiers:
        if '"phones"' in tier:
            phone_tier = tier
            break
    
    if not phone_tier:
        return []
    
    pattern = r'xmin = ([\d.]+)\s+xmax = ([\d.]+)\s+text = "([^"]*)"'
    matches = re.findall(pattern, phone_tier)
    
    intervals = []
    for xmin, xmax, text in matches:
        text = text.strip()
        if text:
            intervals.append({
                "start": float(xmin),
                "end": float(xmax),
                "text": text
            })
    
    return intervals


def _trim_word_intervals_with_phones(
    word_intervals: List[dict],
    phones: List[dict]
) -> List[dict]:
    """Trim word end times using phone data.
    
    MFA word intervals span from start of word to start of next word,
    including silence gaps. This function uses phone-level data to find
    the actual pronunciation end (last phone) within each word, so that
    notes don't include trailing silence.
    
    We allow a small grace period (0.15s) after the last phone to avoid
    cutting off word endings too aggressively.
    """
    if not phones:
        return word_intervals
    
    GRACE = 0.15  # seconds to add after last phone
    
    trimmed = []
    for word in word_intervals:
        ws = word["start"]
        we = word["end"]
        
        # Find all phones within this word's time range
        word_phones = [
            p for p in phones
            if p["start"] >= ws - 0.01 and p["end"] <= we + 0.01
        ]
        
        if word_phones:
            last_phone_end = max(p["end"] for p in word_phones)
            # Trim the word's end to last phone end + grace, but don't extend
            trimmed_end = min(we, last_phone_end + GRACE)
            # Don't trim below minimum duration (at least the phones)
            trimmed_end = max(trimmed_end, last_phone_end)
            trimmed.append({
                **word,
                "end": trimmed_end,
                "original_end": we
            })
        else:
            # No phones found for this word — keep as-is
            trimmed.append(word)
    
    # Log trimming stats
    total_trimmed_sec = sum(
        (w.get("original_end", w["end"]) - w["end"]) for w in trimmed
    )
    big_trims = [
        w for w in trimmed
        if (w.get("original_end", w["end"]) - w["end"]) > 0.5
    ]
    if big_trims:
        log_step("ALIGN", f"Phone-trimmed {len(big_trims)} bloated words (total {total_trimmed_sec:.1f}s removed)")
        for w in big_trims[:5]:
            trim_amt = w["original_end"] - w["end"]
            log_step("ALIGN", f"  '{w['text']}': {w['original_end'] - w['end'] + w['end'] - w['start']:.2f}s -> {w['end'] - w['start']:.2f}s (trimmed {trim_amt:.2f}s)")
    
    return trimmed


# Vowel phones in the English MFA phone set (ARPAbet-based)
_VOWEL_PHONES = {
    'aa', 'ae', 'ah', 'ao', 'aw', 'ay', 'eh', 'er', 'ey',
    'ih', 'iy', 'ow', 'oy', 'uh', 'uw',
    # Also match numbered variants (aa0, aa1, aa2, etc.)
}


def _is_vowel_phone(phone_text: str) -> bool:
    """Check if a phone is a vowel (syllable nucleus)."""
    base = phone_text.lower().rstrip('012')
    return base in _VOWEL_PHONES


def _get_syllable_boundaries_from_phones(
    word_start: float,
    word_end: float,
    num_syllables: int,
    phones: List[dict]
) -> list:
    """Use phone data to find syllable boundaries within a word.
    
    Strategy: Find vowel nuclei in the phone sequence. Each vowel marks
    a syllable onset. Split the phone sequence at consonant clusters
    between vowels, assigning onset consonants to the following syllable.
    
    Returns list of (start, end) tuples, one per syllable, or None if
    phone data is insufficient.
    """
    if not phones or num_syllables <= 1:
        return None
    
    # Get phones within this word's time range
    word_phones = [
        p for p in phones
        if p["start"] >= word_start - 0.01 and p["end"] <= word_end + 0.01
        and p["text"].strip()  # skip empty/silence
    ]
    
    if not word_phones:
        return None
    
    # Find vowel positions (syllable nuclei)
    vowel_indices = [
        i for i, p in enumerate(word_phones)
        if _is_vowel_phone(p["text"])
    ]
    
    if len(vowel_indices) < num_syllables:
        # Not enough vowels found — fall back to equal distribution
        return None
    
    # If more vowels than syllables (diphthongs counted as separate?),
    # take the first num_syllables vowels
    if len(vowel_indices) > num_syllables:
        vowel_indices = vowel_indices[:num_syllables]
    
    # Build syllable boundaries:
    # Each syllable starts at the consonant(s) before its vowel
    # (or at the word start for the first syllable)
    boundaries = []
    
    for s in range(num_syllables):
        vowel_idx = vowel_indices[s]
        
        if s == 0:
            # First syllable starts at word start
            syl_start = word_phones[0]["start"]
        else:
            # Find the split point between previous vowel and this vowel
            prev_vowel_idx = vowel_indices[s - 1]
            # Split at the midpoint of consonants between the two vowels
            consonant_start_idx = prev_vowel_idx + 1
            if consonant_start_idx <= vowel_idx:
                # Split: give first consonant to previous syllable, rest to this
                # (onset maximization principle)
                split_idx = consonant_start_idx
                if vowel_idx - consonant_start_idx >= 2:
                    # Multiple consonants: split in the middle, giving more to onset
                    split_idx = vowel_idx - 1
                syl_start = word_phones[split_idx]["start"]
            else:
                # Adjacent vowels (hiatus)
                syl_start = word_phones[vowel_idx]["start"]
        
        if s < num_syllables - 1:
            # End at the start of next syllable (will be computed in next iteration)
            # For now, set to next vowel's consonant onset
            next_vowel_idx = vowel_indices[s + 1]
            consonant_start_idx = vowel_idx + 1
            if consonant_start_idx <= next_vowel_idx:
                split_idx = consonant_start_idx
                if next_vowel_idx - consonant_start_idx >= 2:
                    split_idx = next_vowel_idx - 1
                syl_end = word_phones[split_idx]["start"]
            else:
                syl_end = word_phones[next_vowel_idx]["start"]
        else:
            # Last syllable ends at word end
            syl_end = word_phones[-1]["end"]
        
        boundaries.append((syl_start, max(syl_start + 0.01, syl_end)))
    
    return boundaries


def _map_mfa_words_to_syllables(
    word_intervals: List[dict],
    flat_syllables: list,
    lyrics_text: str,
    phones: List[dict] = None
) -> List[dict]:
    """Map MFA word-level timestamps back to syllable-level timestamps.
    
    Strategy:
    1. Match each MFA word to the corresponding word in our lyrics
    2. Use phone data to trim inflated word durations (MFA word intervals
       span until the next word, including silence gaps)
    3. For multi-syllable words, distribute the word's time proportionally
    4. Track line_index for break line generation
    """
    # ── Pre-process: trim word intervals using phone data ──
    # MFA word intervals span from word start to next word start, including
    # silence gaps. Use phone data to find actual pronunciation end.
    if phones:
        word_intervals = _trim_word_intervals_with_phones(word_intervals, phones)
    # Build a list of (word, syllable_count, syllable_indices) from flat_syllables
    word_groups = []  # [{word, syllables: [idx, ...], line_index}]
    current_word_syls = []
    current_line_idx = 0
    
    for i, syl in enumerate(flat_syllables):
        line_idx = syl.get("line_index", current_line_idx)
        if syl.get("is_word_start", True) and current_word_syls:
            # Close previous word group
            word_groups.append({
                "syllable_indices": current_word_syls[:],
                "line_index": current_line_idx
            })
            current_word_syls = []
        current_word_syls.append(i)
        current_line_idx = line_idx
    
    if current_word_syls:
        word_groups.append({
            "syllable_indices": current_word_syls[:],
            "line_index": current_line_idx
        })
    
    log_step("ALIGN", f"Word groups from lyrics: {len(word_groups)}, MFA words: {len(word_intervals)}")
    
    # ── Match word groups to MFA intervals ──
    # Use sequential matching: walk through both lists in order
    results = [None] * len(flat_syllables)
    mfa_idx = 0
    
    for wg in word_groups:
        syl_indices = wg["syllable_indices"]
        line_idx = wg["line_index"]
        num_syls = len(syl_indices)
        
        if mfa_idx < len(word_intervals):
            mfa_word = word_intervals[mfa_idx]
            word_start = mfa_word["start"]
            word_end = mfa_word["end"]
            word_duration = word_end - word_start
            mfa_idx += 1
            confidence = 0.9
            method = "mfa"
        else:
            # No more MFA words — extrapolate from last known position
            if results and any(r for r in results if r is not None):
                last = [r for r in results if r is not None][-1]
                word_start = last["end"] + 0.05
            else:
                word_start = 0.0
            word_duration = 0.3 * num_syls
            word_end = word_start + word_duration
            confidence = 0.3
            method = "mfa_extrapolated"
        
        # Distribute time across syllables using phone data when possible
        syl_boundaries = _get_syllable_boundaries_from_phones(
            word_start, word_end, num_syls, phones
        ) if phones and num_syls > 1 else None
        
        if syl_boundaries and len(syl_boundaries) == num_syls:
            # Use phone-derived boundaries
            for j, syl_idx in enumerate(syl_indices):
                syl = flat_syllables[syl_idx]
                start, end = syl_boundaries[j]
                results[syl_idx] = {
                    "syllable": syl["text"],
                    "start": round(start, 4),
                    "end": round(end, 4),
                    "confidence": confidence,
                    "is_rap": syl.get("is_rap", False),
                    "method": method,
                    "line_index": line_idx
                }
        else:
            # Fall back to equal distribution
            syl_duration = word_duration / num_syls
            for j, syl_idx in enumerate(syl_indices):
                syl = flat_syllables[syl_idx]
                start = word_start + j * syl_duration
                end = word_start + (j + 1) * syl_duration
                results[syl_idx] = {
                    "syllable": syl["text"],
                    "start": round(start, 4),
                    "end": round(end, 4),
                    "confidence": confidence,
                    "is_rap": syl.get("is_rap", False),
                    "method": method,
                    "line_index": line_idx
                }
    
    # Fill any gaps (shouldn't happen, but safety net)
    filled = [r for r in results if r is not None]
    if len(filled) < len(results):
        log_step("ALIGN", f"Warning: {len(results) - len(filled)} syllables unmapped, filling gaps")
        for i in range(len(results)):
            if results[i] is None:
                # Interpolate from neighbors
                prev = results[i-1] if i > 0 and results[i-1] else {"end": 0.0}
                results[i] = {
                    "syllable": flat_syllables[i]["text"],
                    "start": prev["end"],
                    "end": prev["end"] + 0.2,
                    "confidence": 0.2,
                    "is_rap": flat_syllables[i].get("is_rap", False),
                    "method": "interpolated",
                    "line_index": flat_syllables[i].get("line_index", 0)
                }
    
    log_step("ALIGN", f"Mapped {len(results)} syllables from MFA alignment")
    if results:
        log_step("ALIGN", f"  Time range: {results[0]['start']:.2f}s - {results[-1]['end']:.2f}s")
    
    # ── Post-process: fix bloated syllables ──
    results = _fix_bloated_syllables(results)
    
    return results


def _fix_bloated_syllables(results: List[dict]) -> List[dict]:
    """Fix syllables with inflated durations from MFA.
    
    MFA sometimes assigns silence/held-note gaps to the preceding word,
    making it much longer than it should be. This happens especially at
    phrase boundaries where the singer holds a note before an instrumental
    gap.
    
    Strategy:
    1. Compute median syllable duration
    2. Find syllables that are > 4x the median AND > 1.5s absolute
    3. For each bloated syllable, check if it's followed by compressed
       syllables (< 0.1s). If so, the MFA likely extended this syllable
       into what should be a silence gap.
    4. Cap the bloated syllable and shift compressed followers earlier
       into natural positions.
    """
    import numpy as np
    
    if not results or len(results) < 10:
        return results
    
    durations = [r["end"] - r["start"] for r in results]
    median_dur = float(np.median(durations))
    
    # Threshold: syllable is "bloated" if > max(4x median, 1.5s)
    bloat_threshold = max(median_dur * 4, 1.5)
    
    fixes_applied = 0
    
    for i in range(len(results)):
        dur = results[i]["end"] - results[i]["start"]
        
        if dur <= bloat_threshold:
            continue
        
        # Check: is this followed by compressed syllables?
        # Count how many following syllables have very short duration
        compressed_count = 0
        for j in range(i + 1, min(i + 10, len(results))):
            jdur = results[j]["end"] - results[j]["start"]
            if jdur < 0.12:
                compressed_count += 1
            else:
                break
        
        # Also check if there's a gap after this syllable to the next line
        # (phrase boundary detection)
        has_line_break = False
        if i + 1 < len(results):
            has_line_break = results[i].get("line_index", 0) != results[i + 1].get("line_index", 0)
        
        # Determine reasonable max duration for this syllable
        # Short words (1-4 chars): max ~0.8s
        # Longer words: max ~1.2s  
        # At phrase end (line break following): slightly more generous
        syl_text = results[i]["syllable"].strip().rstrip(",.'!?")
        if len(syl_text) <= 4:
            max_dur = 1.0 if has_line_break else 0.8
        else:
            max_dur = 1.5 if has_line_break else 1.2
        
        if dur <= max_dur:
            continue
        
        # Cap this syllable's duration
        new_end = results[i]["start"] + max_dur
        old_end = results[i]["end"]
        results[i]["end"] = round(new_end, 4)
        
        # The gap we freed up: old_end - new_end
        # If there are compressed syllables following, they were crammed
        # because MFA was forced to fit them after the bloated word.
        # Don't shift them — they have their own MFA timing which is
        # correct relative to the audio. The bloated syllable just had
        # silence appended; the following syllables are at their correct
        # audio positions.
        
        fixes_applied += 1
        log_step("ALIGN", f"  Trimmed '{results[i]['syllable'].strip()}' from {dur:.2f}s to {max_dur:.1f}s (freed {dur - max_dur:.2f}s)")
    
    if fixes_applied:
        log_step("ALIGN", f"Fixed {fixes_applied} bloated syllables (threshold: {bloat_threshold:.2f}s, median: {median_dur:.3f}s)")
    
    return results


def align_fallback(audio_path: str, parsed_lines: List[List[dict]]) -> List[dict]:
    """Fallback alignment using energy-based voiced segment detection.
    
    Instead of distributing syllables evenly across the full audio,
    this finds segments where there's vocal energy and places syllables
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
    
    # ── Step 1: Use shared vocal section detection ──
    segments = _detect_vocal_sections(y, sr, min_silence_sec=1.5, min_section_sec=1.0)
    
    total_voiced_time = sum(end - start for start, end in segments)
    log_step("ALIGN", f"Found {len(segments)} voiced segments, total voiced time: {total_voiced_time:.1f}s")
    if segments:
        log_step("ALIGN", f"  First segment: {segments[0][0]:.2f}s - {segments[0][1]:.2f}s")
        log_step("ALIGN", f"  Last segment:  {segments[-1][0]:.2f}s - {segments[-1][1]:.2f}s")
    
    if len(segments) == 0:
        # Fallback to simple even distribution if no segments found
        log_step("ALIGN", "No voiced segments found, using simple distribution")
        return _align_even(y, sr, parsed_lines)
    
    # ── Step 3: Distribute lines across segments ──
    # Strategy: map each lyrics line to the nearest voiced segment(s)
    num_lines = len(parsed_lines)
    results = []
    
    if num_lines <= len(segments):
        # More segments than lines: assign each line to a segment proportionally
        # Distribute lines across segments weighted by segment duration
        seg_durations = [end - start for start, end in segments]
        total_seg_dur = sum(seg_durations)
        
        # Assign lines to segments proportionally to segment duration
        line_segment_map = []
        cumulative_lines = 0
        for seg_idx, seg_dur in enumerate(seg_durations):
            # How many lines belong to this segment?
            proportion = seg_dur / total_seg_dur
            n_lines = proportion * num_lines
            
            # At least assign fractional lines
            line_segment_map.append({
                'seg_idx': seg_idx,
                'start': segments[seg_idx][0],
                'end': segments[seg_idx][1],
                'line_count': n_lines,
            })
        
        # Now round-robin assign lines to segments
        line_assignments = []  # (line_idx, seg_start, seg_end)
        line_idx = 0
        
        # Sort by proportional assignment
        fractional_acc = 0.0
        for seg_info in line_segment_map:
            fractional_acc += seg_info['line_count']
            while line_idx < num_lines and line_idx < round(fractional_acc):
                line_assignments.append((line_idx, seg_info['start'], seg_info['end']))
                line_idx += 1
        
        # Assign remaining lines to last segment
        while line_idx < num_lines:
            last = segments[-1]
            line_assignments.append((line_idx, last[0], last[1]))
            line_idx += 1
    else:
        # More lines than segments: distribute multiple lines per segment
        lines_per_seg = num_lines / len(segments)
        line_assignments = []
        for line_idx in range(num_lines):
            seg_idx = min(int(line_idx / lines_per_seg), len(segments) - 1)
            line_assignments.append((line_idx, segments[seg_idx][0], segments[seg_idx][1]))
    
    # ── Step 4: Place syllables within assigned segments ──
    # Group assignments by segment
    from collections import defaultdict
    seg_lines = defaultdict(list)
    for line_idx, seg_start, seg_end in line_assignments:
        seg_lines[(seg_start, seg_end)].append(line_idx)
    
    for (seg_start, seg_end), line_indices in seg_lines.items():
        seg_duration = seg_end - seg_start
        
        # Count total syllables across all lines in this segment
        seg_syllables = []
        for li in line_indices:
            for syl in parsed_lines[li]:
                seg_syllables.append((li, syl))
        
        if not seg_syllables:
            continue
        
        # Leave 5% gap between lines within the segment
        num_line_breaks = len(set(li for li, _ in seg_syllables)) - 1
        gap_total = seg_duration * 0.05 * num_line_breaks / max(1, len(seg_syllables))
        syllable_time = (seg_duration - gap_total * num_line_breaks) / len(seg_syllables)
        syllable_time = max(0.1, syllable_time)  # minimum 100ms per syllable
        
        current_time = seg_start
        prev_line_idx = seg_syllables[0][0] if seg_syllables else None
        
        for li, syl in seg_syllables:
            # Add gap between lines
            if prev_line_idx is not None and li != prev_line_idx:
                current_time += gap_total
            
            start = current_time
            end = min(current_time + syllable_time, seg_end)
            
            results.append({
                "syllable": syl["text"],
                "start": start,
                "end": end,
                "confidence": 0.4,  # Slightly better than pure even
                "is_rap": syl.get("is_rap", False),
                "method": "fallback_energy",
                "line_index": li
            })
            
            current_time = end
            prev_line_idx = li
    
    # Sort by start time (segments may not be perfectly ordered)
    results.sort(key=lambda r: r["start"])
    
    log_step("ALIGN", f"Energy fallback: placed {len(results)} syllables in {len(segments)} voiced segments")
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
