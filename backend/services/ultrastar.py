"""Ultrastar .txt file generation."""

import re
from typing import List, Optional
from utils.logger import log_step

# Headers recognised by USDB/animux.de; everything else is dropped on download.
USDB_KNOWN_HEADERS = {
    'TITLE', 'ARTIST', 'BPM', 'GAP', 'LANGUAGE', 'MP3', 'VOCALS',
    'INSTRUMENTAL', 'COVER', 'BACKGROUND', 'VIDEO', 'VIDEOGAP',
    'GENRE', 'YEAR', 'EDITION', 'CREATOR', 'COMMENT', 'YOUTUBE',
    'END', 'PREVIEWSTART', 'MEDLEYSTARTBEAT', 'MEDLEYENDBEAT',
    'RELATIVE', 'ENCODING', 'TAGS',
}


def _remove_header(content: str, key: str) -> str:
    """Remove all #KEY:... lines from Ultrastar .txt content."""
    lines = [ln for ln in content.split("\n") if not re.match(rf"^#{key}:[^\n]*$", ln)]
    return "\n".join(lines)


def format_for_download(content: str, include_vocals: bool = True, include_instrumental: bool = True) -> str:
    """Turn a stored .txt into the file the user downloads (USDB conventions).

    - YASS-style line breaks (``- 12 14`` → ``- 12``)
    - ``#MP3`` / ``#VOCALS`` always point to ``.mp3``
    - apostrophes in note lines normalised to ``’`` (U+2019)
    - mid-word syllables (no trailing space) get a trailing ``-``
    - unknown and duplicate headers removed; CRLF line endings
    """
    content = re.sub(r'^(- \d+) \d+$', r'\1', content, flags=re.MULTILINE)

    def _force_mp3_ext(m):
        return m.group(1) + re.sub(r'\.[^.]+$', '.mp3', m.group(2))
    content = re.sub(r'^(#MP3:)(.+)$', _force_mp3_ext, content, flags=re.MULTILINE)
    content = re.sub(r'^(#VOCALS:)(.+)$', _force_mp3_ext, content, flags=re.MULTILINE)

    def _fix_apostrophes(m):
        return re.sub(r"['`´ʼ‘‚]", "’", m.group(0))
    content = re.sub(r'^[^#].*$', _fix_apostrophes, content, flags=re.MULTILINE)

    # Note lines: "PREFIX BEAT DUR PITCH SYLLABLE"; no trailing space = word continues.
    def _fix_hyphens(m):
        line = m.group(0)
        if not line.endswith(' '):
            line = line + '-'
        return line
    content = re.sub(r'^[:*RF] \d+ \d+ \d+ .*$', _fix_hyphens, content, flags=re.MULTILINE)

    if not include_vocals:
        content = _remove_header(content, "VOCALS")
    if not include_instrumental:
        content = _remove_header(content, "INSTRUMENTAL")

    seen_keys = set()
    filtered_lines = []
    for ln in content.splitlines():
        if ln.startswith('#'):
            key_part = ln[1:].split(':')[0].upper()
            if key_part not in USDB_KNOWN_HEADERS:
                continue
            if key_part in seen_keys:
                continue
            seen_keys.add(key_part)
        filtered_lines.append(ln)
    content = '\r\n'.join(filtered_lines)
    if not content.endswith('\r\n'):
        content += '\r\n'
    return content


def _fmt_bpm(bpm: float) -> str:
    """Format BPM without unnecessary trailing zeros (e.g. 612.0 → '612', 612.35 → '612.35')."""
    s = f"{bpm:.2f}".rstrip('0').rstrip('.')
    return s

# ISO 639-1 code → full English language name for #LANGUAGE header
_ISO_TO_LANGUAGE_NAME = {
    "af": "Afrikaans", "sq": "Albanian", "ar": "Arabic", "hy": "Armenian",
    "az": "Azerbaijani", "eu": "Basque", "be": "Belarusian", "bn": "Bengali",
    "bs": "Bosnian", "bg": "Bulgarian", "ca": "Catalan", "zh": "Chinese",
    "hr": "Croatian", "cs": "Czech", "da": "Danish", "nl": "Dutch",
    "en": "English", "et": "Estonian", "fi": "Finnish", "fr": "French",
    "gl": "Galician", "ka": "Georgian", "de": "German", "el": "Greek",
    "gu": "Gujarati", "ht": "Haitian Creole", "ha": "Hausa", "he": "Hebrew",
    "hi": "Hindi", "hu": "Hungarian", "is": "Icelandic", "id": "Indonesian",
    "ga": "Irish", "it": "Italian", "ja": "Japanese", "kn": "Kannada",
    "kk": "Kazakh", "ko": "Korean", "lv": "Latvian", "lt": "Lithuanian",
    "mk": "Macedonian", "ms": "Malay", "ml": "Malayalam", "mt": "Maltese",
    "mi": "Maori", "mr": "Marathi", "mn": "Mongolian", "ne": "Nepali",
    "no": "Norwegian", "fa": "Persian", "pl": "Polish", "pt": "Portuguese",
    "pa": "Punjabi", "ro": "Romanian", "ru": "Russian", "sr": "Serbian",
    "sk": "Slovak", "sl": "Slovenian", "so": "Somali", "es": "Spanish",
    "sw": "Swahili", "sv": "Swedish", "tl": "Filipino", "ta": "Tamil",
    "te": "Telugu", "th": "Thai", "tr": "Turkish", "uk": "Ukrainian",
    "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese", "cy": "Welsh",
    "yi": "Yiddish", "yo": "Yoruba",
}


def generate_ultrastar(
    syllable_timings: List[dict],
    pitch_data: dict,
    bpm: float,
    gap_ms: int,
    artist: str = "Unknown Artist",
    title: str = "Unknown Song",
    language: str = "English",
    mp3_filename: str = "song.mp3"
) -> str:
    """Generate Ultrastar .txt file content.
    
    Args:
        syllable_timings: List from alignment service [{syllable, start, end, confidence, is_rap, line_index}, ...]
        pitch_data: Result from pitch detection service
        bpm: Ultrastar BPM (already doubled)
        gap_ms: GAP in milliseconds
        artist: Artist name
        title: Song title
        language: Language
        mp3_filename: MP3 filename for header
        
    Returns:
        Complete Ultrastar .txt file content as string
    """
    from services.pitch_detection import get_pitch_for_segment
    
    log_step("ULTRASTAR", f"Generating file: {len(syllable_timings)} syllables, BPM={bpm:.2f}, GAP={gap_ms}ms")
    
    # Convert ISO code to full English name for #LANGUAGE header (e.g. "en" → "English")
    language_name = _ISO_TO_LANGUAGE_NAME.get(language.lower(), language) if language else "English"
    
    # Header
    header = (
        f"#ARTIST:{artist}\n"
        f"#TITLE:{title}\n"
        f"#BPM:{_fmt_bpm(bpm)}\n"
        f"#GAP:{gap_ms}\n"
        f"#LANGUAGE:{language_name}\n"
        f"#MP3:{mp3_filename}\n"
    )
    
    note_lines = []
    gap_sec = gap_ms / 1000.0
    prev_line_index = None
    last_end_beat = 0
    
    for i, timing in enumerate(syllable_timings):
        syllable = timing["syllable"]
        start_sec = timing["start"]
        end_sec = timing["end"]
        is_rap = timing.get("is_rap", False)
        line_index = timing.get("line_index", 0)
        confidence = timing.get("confidence", 0.5)
        
        # Convert time to beats relative to GAP
        # Standard Ultrastar: beats are quarter-beats (16th note resolution)
        # Formula: beat = (time - gap) * BPM * 4 / 60 = (time - gap) * BPM / 15
        start_beat = max(0, int(((start_sec - gap_sec) * bpm) / 15))
        end_beat = max(start_beat + 1, int(((end_sec - gap_sec) * bpm) / 15))
        duration_beats = max(1, end_beat - start_beat)
        
        # Ensure beats don't overlap with previous note
        if start_beat <= last_end_beat and i > 0:
            start_beat = last_end_beat + 1
            end_beat = max(start_beat + 1, end_beat)
            duration_beats = max(1, end_beat - start_beat)
        
        # Get pitch for this syllable's time window
        if is_rap:
            midi_pitch = 0
            prefix = "R"
        else:
            midi_pitch = get_pitch_for_segment(pitch_data, start_sec, end_sec)
            if midi_pitch == 0:
                # Try wider window
                mid_time = (start_sec + end_sec) / 2
                midi_pitch = get_pitch_for_segment(pitch_data, mid_time - 0.1, mid_time + 0.1)
            if midi_pitch == 0:
                midi_pitch = 60  # Default to C4 if no pitch detected
            prefix = ":"
        
        # Add break line between phrases (YASS-style: single number = end of last line)
        if prev_line_index is not None and line_index != prev_line_index:
            break_start = last_end_beat + 2  # 2 beat padding after last note
            note_lines.append(f"- {break_start}")
        
        syllable = syllable.replace("\u00a0", " ")
        note_lines.append(f"{prefix} {start_beat} {duration_beats} {midi_pitch} {syllable}")
        
        last_end_beat = start_beat + duration_beats
        prev_line_index = line_index
    
    # Footer
    note_lines.append("E")
    
    content = header + "\n".join(note_lines)
    # Normalize any non-breaking spaces that may have come from lyrics/metadata
    content = content.replace("\u00a0", " ")
    
    log_step("ULTRASTAR", f"Generated {len(note_lines) - 1} note lines")
    
    return content


def generate_lyrics_only_txt(
    artist: str = "Unknown Artist",
    title: str = "Unknown Song",
    bpm: float = 120.0,
    gap_ms: int = 0,
    language: str = "English",
    mp3_filename: str = "song.mp3",
) -> str:
    """Generate a minimal Ultrastar .txt file with headers only (no notes).

    This is used as a lightweight starting point for manual note creation in
    the editor while preserving song metadata and timing headers.
    """
    language_name = _ISO_TO_LANGUAGE_NAME.get(language.lower(), language) if language else "English"

    header = (
        f"#ARTIST:{artist}\n"
        f"#TITLE:{title}\n"
        f"#BPM:{_fmt_bpm(bpm)}\n"
        f"#GAP:{gap_ms}\n"
        f"#LANGUAGE:{language_name}\n"
        f"#MP3:{mp3_filename}\n"
    )

    # Valid Ultrastar footer; no note lines yet.
    return header + "E"


def generate_processing_summary(
    syllable_timings: List[dict],
    bpm: float,
    gap_ms: int,
    audio_duration: float,
    pitch_method: str = "PYIN",
    alignment_method: str = "WhisperX"
) -> str:
    """Generate a human-readable processing summary.
    
    Includes details about each syllable's timing, pitch, and confidence.
    Highlights low-confidence detections for manual review.
    """
    lines = [
        "=" * 60,
        "ULTRASTAR PROCESSING SUMMARY",
        "=" * 60,
        f"BPM: {bpm:.2f} (Ultrastar doubled)",
        f"GAP: {gap_ms}ms",
        f"Audio Duration: {audio_duration:.1f}s",
        f"Pitch Detection: {pitch_method}",
        f"Alignment: {alignment_method}",
        f"Total Syllables: {len(syllable_timings)}",
        "",
        "SYLLABLE DETAILS:",
        "-" * 60,
        f"{'#':>4} {'Syllable':<15} {'Start':>8} {'End':>8} {'Conf':>6} {'Method':<20}",
        "-" * 60,
    ]
    
    low_confidence = []
    
    for i, t in enumerate(syllable_timings):
        conf = t.get("confidence", 0)
        method = t.get("method", "unknown")
        line = f"{i+1:4d} {t['syllable']:<15} {t['start']:8.3f} {t['end']:8.3f} {conf:6.2f} {method:<20}"
        lines.append(line)
        
        if conf < 0.5:
            low_confidence.append((i + 1, t["syllable"], conf, method))
    
    if low_confidence:
        lines.append("")
        lines.append("WARNINGS - Low confidence syllables (may need manual correction):")
        lines.append("-" * 60)
        for num, syl, conf, method in low_confidence:
            lines.append(f"  #{num}: '{syl}' (confidence: {conf:.2f}, method: {method})")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)
