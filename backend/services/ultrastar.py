"""Ultrastar .txt file generation."""

import re
from typing import List, Optional
from utils.logger import log_step

# Headers recognised by USDB/animux.de; everything else is dropped on download.
USDB_KNOWN_HEADERS = {
    'TITLE', 'ARTIST', 'BPM', 'GAP', 'LANGUAGE', 'MP3', 'VOCALS',
    'INSTRUMENTAL', 'COVER', 'BACKGROUND', 'VIDEO', 'VIDEOGAP',
    'GENRE', 'YEAR', 'EDITION', 'CREATOR', 'COMMENT', 'YOUTUBE',
    'START', 'END', 'PREVIEWSTART', 'MEDLEYSTARTBEAT', 'MEDLEYENDBEAT',
    'RELATIVE', 'ENCODING', 'TAGS',
    'P1', 'P2', 'DUETSINGERP1', 'DUETSINGERP2',  # duets
}


def video_assets_from_headers(headers: dict) -> dict:
    """What an imported chart says about its video, as session fields (video_filename, video_gap, youtube_url).

    #VIDEO is a file name, or USDB's tags ("v=<YouTube id>,co=...,p1=..."), which only give the link. #VIDEOGAP may
    have a decimal comma; #YOUTUBE is the link in the app's own charts.
    """
    assets = {}
    video = (headers.get("VIDEO") or "").strip()
    usdb_id = next((part[2:].strip() for part in video.split(",") if part.startswith("v=")), "")
    if video and not re.match(r"^\w+=", video):
        assets["video_filename"] = video
    link = usdb_id or (headers.get("YOUTUBE") or "").strip()
    if link:
        assets["youtube_url"] = f"https://www.youtube.com/watch?v={link}" if len(link) == 11 else link
    try:
        assets["video_gap"] = float((headers.get("VIDEOGAP") or "").strip().replace(",", "."))
    except ValueError:
        pass
    return assets


def video_gap_header(session: dict) -> str | None:
    """The #VIDEOGAP value to write, or None for no header: it belongs to a video (a file or a YouTube link). Without
    a file, a gap of 0 says nothing."""
    gap = session.get("video_gap")
    if gap is None:
        return None
    if session.get("video_filename") or (session.get("youtube_url") and gap):
        return str(gap)
    return None


def _remove_header(content: str, key: str) -> str:
    """Remove all #KEY:... lines from Ultrastar .txt content."""
    lines = [ln for ln in content.split("\n") if not re.match(rf"^#{key}:[^\n]*$", ln)]
    return "\n".join(lines)


# The order of USDB's own charts; the games don't mind.
_HEADER_ORDER = ['ARTIST', 'TITLE', 'MP3', 'VOCALS', 'INSTRUMENTAL', 'CREATOR', 'EDITION', 'COVER', 'BACKGROUND', 'GENRE',
                 'YEAR', 'LANGUAGE', 'BPM', 'GAP', 'VIDEO', 'VIDEOGAP', 'START', 'END', 'PREVIEWSTART', 'MEDLEYSTARTBEAT',
                 'MEDLEYENDBEAT', 'RELATIVE', 'ENCODING', 'TAGS', 'COMMENT', 'YOUTUBE', 'P1', 'P2', 'DUETSINGERP1',
                 'DUETSINGERP2']
_DOWNLOAD_NOTE = re.compile(r'^([:*RFG] \d+ \d+ -?\d+ )(.*)$')
_SPACES = re.compile(r'[\t  -   　]')
_INVISIBLE = re.compile(r'[\u0000-\u001f\u007f-\u009f​⁠﻿]')


def clean_syllable(text: str) -> str:
    """A note's text without what doesn't belong in it: odd spaces (non-breaking, tabs) as plain ones, invisible and
    control characters removed, runs of spaces as one. A trailing space stays: it ends the word. The format forbids no
    other characters; a `-` is the lyrics' own ("three-wheeler")."""
    return re.sub(r' {2,}', ' ', _INVISIBLE.sub('', _SPACES.sub(' ', text)))


def strip_added_hyphens(content: str) -> str:
    """Removes the `-` older versions of this app put on mid-word syllables on download ("gon-" + "na "), recognised by
    a chart whose mid-word syllables nearly all have one. A `-` in the lyrics ("three-" + "wheeler ") stays in any other
    chart, whose mid-word syllables have no ending. `~-` is never right."""
    lines = content.split('\n')
    notes = [(i, m) for i, m in ((i, _DOWNLOAD_NOTE.match(ln.rstrip('\r'))) for i, ln in enumerate(lines)) if m]
    hyphens = open_ended = 0
    for k, (_, m) in enumerate(notes):
        text = m.group(2)
        if text.endswith('-'):
            hyphens += 1
        elif (not text.endswith(' ') and text.strip() != '~' and k + 1 < len(notes)
              and not notes[k + 1][1].group(2).lstrip().startswith('~')):
            open_ended += 1
    strip_all = hyphens >= 5 and open_ended <= hyphens * 0.5   # at most half: 38 of USDB's 28,868 charts
    for i, m in notes:
        text = m.group(2)
        if text.endswith('-') and (strip_all or text.rstrip('-').strip() == '~'):
            lines[i] = lines[i].replace(m.group(0), m.group(1) + text.rstrip('-'))
    return '\n'.join(lines)


def to_relative_pitches(content: str) -> str:
    """The app's MIDI pitches (C4 = 60) as the format wants them (0 = C4). The other direction of `to_midi_pitches`;
    a chart that already is relative stays."""
    pitches = [int(m.group(2)) for m in map(_NOTE_LINE.match, content.splitlines()) if m]
    if not pitches or sorted(pitches)[len(pitches) // 2] < 30:
        return content
    lines = []
    for line in content.split("\n"):
        m = _NOTE_LINE.match(line)
        lines.append(f"{m.group(1)}{int(m.group(2)) - MIDI_C4}{m.group(3)}" if m else line)
    return "\n".join(lines)


def _clean_note_lines(content: str) -> str:
    """Every note's text cleaned; a leading space moved to the end of the note before, where the word ends."""
    lines = content.split('\n')
    previous = None
    for i, line in enumerate(lines):
        m = _DOWNLOAD_NOTE.match(line)
        if not m:
            continue
        text = clean_syllable(m.group(2))
        if text.startswith(' '):
            text = text.lstrip()
            if previous is not None and not lines[previous].endswith(' '):
                lines[previous] += ' '
        lines[i] = m.group(1) + text
        previous = i
    return '\n'.join(lines)


def format_for_download(content: str, include_vocals: bool = True, include_instrumental: bool = True,
                        include_video: bool = True) -> str:
    """Turn a stored .txt into the file the user downloads, as the UltraStar format and USDB's charts have it.

    - YASS-style line breaks (``- 12 14`` → ``- 12``)
    - ``#MP3`` / ``#VOCALS`` always point to ``.mp3``
    - apostrophes in note lines normalised to ``’`` (U+2019)
    - note texts cleaned (`clean_syllable`), no `-` from older versions (`strip_added_hyphens`)
    - pitches relative to C4 = 0 (the app works in MIDI numbers)
    - unknown and duplicate headers removed, values trimmed, in USDB's order; no blank lines; CRLF line endings
    """
    content = re.sub(r'\r\n?', '\n', content)
    content = re.sub(r'^(- \d+) \d+$', r'\1', content, flags=re.MULTILINE)

    def _force_mp3_ext(m):
        return m.group(1) + re.sub(r'\.[^.]+$', '.mp3', m.group(2))
    content = re.sub(r'^(#MP3:)(.+)$', _force_mp3_ext, content, flags=re.MULTILINE)
    content = re.sub(r'^(#VOCALS:)(.+)$', _force_mp3_ext, content, flags=re.MULTILINE)

    def _fix_apostrophes(m):
        return re.sub(r"['`´ʼ‘‚]", "’", m.group(0))
    content = re.sub(r'^[^#].*$', _fix_apostrophes, content, flags=re.MULTILINE)

    content = to_relative_pitches(_clean_note_lines(strip_added_hyphens(content)))

    if not include_vocals:
        content = _remove_header(content, "VOCALS")
    if not include_instrumental:
        content = _remove_header(content, "INSTRUMENTAL")
    if not include_video:
        content = _remove_header(content, "VIDEO")

    headers = {}
    body = []
    for ln in content.split('\n'):
        if ln.startswith('#'):
            key, _, value = ln[1:].partition(':')
            key, value = key.upper(), clean_syllable(value).strip()
            if key == 'VIDEOGAP':
                value = re.sub(r'\.0+$', '', value)
            if key in USDB_KNOWN_HEADERS and key not in headers and value:
                headers[key] = f"#{ln[1:].partition(':')[0]}:{value}"
        elif ln.strip():   # no blank lines, also from a file stored with doubled line endings
            body.append(ln)
    ordered = [headers[key] for key in _HEADER_ORDER if key in headers]
    content = '\r\n'.join(ordered + body)
    if not content.endswith('\r\n'):
        content += '\r\n'
    return content


def format_for_usdb(content: str, youtube_id: Optional[str]) -> str:
    """The downloaded .txt for uploading to USDB. It differs from the file for the game only where USDB's tools need it:
    `#VIDEO` holds the YouTube id (`v=…`, the one thing USDB Syncer finds the video by) instead of a file name, no
    `#YOUTUBE`, no vocals and instrumental files. A duet has its singers in the tags and [DUET] in the title."""
    from services.duet import DUET_HEADERS, is_duet, singer_names
    headers = {ln[1:].partition(':')[0].upper(): ln[1:].partition(':')[2].strip()
               for ln in content.splitlines() if ln.startswith('#')}
    tags = [f"v={youtube_id}"] if youtube_id else []
    if is_duet(content):
        names = singer_names(headers)
        tags += [f"p1={names['p1'].replace(',', '%2C')}", f"p2={names['p2'].replace(',', '%2C')}"]
        title = headers.get('TITLE', '')
        if '[DUET]' not in title.upper():
            content = re.sub(r'^#TITLE:.*$', lambda m: f"#TITLE:{title} [DUET]", content, flags=re.MULTILINE)
    for key in ('VIDEO', 'YOUTUBE', *DUET_HEADERS):
        content = _remove_header(content, key)
    if not youtube_id:
        content = _remove_header(content, 'VIDEOGAP')
    if tags:
        content = f"#VIDEO:{','.join(tags)}\n{content}"
    return format_for_download(content, include_vocals=False, include_instrumental=False)


def _fmt_bpm(bpm: float) -> str:
    """Format BPM without unnecessary trailing zeros (e.g. 612.0 → '612', 612.35 → '612.35')."""
    s = f"{bpm:.2f}".rstrip('0').rstrip('.')
    return s

# ISO 639-1 code → English language name for the #LANGUAGE header (the format wants English names).
_ISO_TO_LANGUAGE_NAME = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "az": "Azerbaijani",
    "ba": "Bashkir", "be": "Belarusian", "bg": "Bulgarian", "bn": "Bengali",
    "bo": "Tibetan", "br": "Breton", "bs": "Bosnian", "ca": "Catalan",
    "cs": "Czech", "cy": "Welsh", "da": "Danish", "de": "German",
    "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian",
    "eu": "Basque", "fa": "Persian", "fi": "Finnish", "fo": "Faroese",
    "fr": "French", "ga": "Irish", "gl": "Galician", "gu": "Gujarati",
    "ha": "Hausa", "haw": "Hawaiian", "he": "Hebrew", "hi": "Hindi",
    "hr": "Croatian", "ht": "Haitian Creole", "hu": "Hungarian", "hy": "Armenian",
    "id": "Indonesian", "is": "Icelandic", "it": "Italian", "ja": "Japanese",
    "jw": "Javanese", "ka": "Georgian", "kk": "Kazakh", "km": "Khmer",
    "kn": "Kannada", "ko": "Korean", "la": "Latin", "lb": "Luxembourgish",
    "ln": "Lingala", "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian",
    "mg": "Malagasy", "mi": "Maori", "mk": "Macedonian", "ml": "Malayalam",
    "mn": "Mongolian", "mr": "Marathi", "ms": "Malay", "mt": "Maltese",
    "my": "Myanmar", "ne": "Nepali", "nl": "Dutch", "nn": "Nynorsk",
    "no": "Norwegian", "oc": "Occitan", "pa": "Punjabi", "pl": "Polish",
    "ps": "Pashto", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "sa": "Sanskrit", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "sn": "Shona", "so": "Somali", "sq": "Albanian",
    "sr": "Serbian", "su": "Sundanese", "sv": "Swedish", "sw": "Swahili",
    "ta": "Tamil", "te": "Telugu", "tg": "Tajik", "th": "Thai",
    "tk": "Turkmen", "tl": "Tagalog", "tr": "Turkish", "tt": "Tatar",
    "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese",
    "yi": "Yiddish", "yo": "Yoruba", "zh": "Chinese",
}
_LANGUAGE_NAME_TO_ISO = {name.lower(): code for code, name in _ISO_TO_LANGUAGE_NAME.items()}


def language_name(language: str) -> str:
    """"en" → "English"; a name or an unknown code is kept as it is."""
    if not language:
        return ""
    return _ISO_TO_LANGUAGE_NAME.get(language.strip().lower(), language.strip())


# UltraStar's note pitch is relative (0 = C4) in most charts (USDB); this app's charts and its editor use MIDI numbers
# (60 = C4), so the editor's pitch line, MIDI tones and pitch tools match them. The games mostly score the pitch
# class, so both play the same.
_NOTE_LINE = re.compile(r"^(\s*(?:[:*FRG]|F:|R:)\s+-?\d+\s+\d+\s+)(-?\d+)(.*)$")
MIDI_C4 = 60


def to_midi_pitches(content: str) -> tuple:
    """A chart with relative pitches (median below 30, a C4 of 0) moved up to MIDI numbers (+60), other lines and
    the text untouched. Returns (content, shifted)."""
    pitches = [int(m.group(2)) for m in map(_NOTE_LINE.match, content.splitlines()) if m]
    if not pitches or sorted(pitches)[len(pitches) // 2] >= 30:
        return content, False
    lines = []
    for line in content.split("\n"):
        m = _NOTE_LINE.match(line)
        lines.append(f"{m.group(1)}{int(m.group(2)) + MIDI_C4}{m.group(3)}" if m else line)
    return "\n".join(lines), True


def language_header(language: str, language2: Optional[str] = None) -> str:
    """The #LANGUAGE value: one or two English language names, comma-separated ("English, German"), as the
    UltraStar format allows. English when nothing is set."""
    names = []
    for code in (language, language2):
        name = language_name(code or "")
        if name and name not in names:
            names.append(name)
    return ", ".join(names) or "English"


def parse_language_header(value: str) -> tuple:
    """(code, second code or None) from a #LANGUAGE value like "English, German" or "de"."""
    codes = []
    for part in (value or "").split(","):
        part = part.strip().lower()
        code = _LANGUAGE_NAME_TO_ISO.get(part) or (part if part in _ISO_TO_LANGUAGE_NAME else None)
        if code and code not in codes:
            codes.append(code)
    return (codes[0] if codes else None, codes[1] if len(codes) > 1 else None)


def generate_ultrastar(
    syllable_timings: List[dict],
    pitch_data: dict,
    bpm: float,
    gap_ms: int,
    artist: str = "Unknown Artist",
    title: str = "Unknown Song",
    language: str = "English",
    mp3_filename: str = "song.mp3",
    language2: Optional[str] = None,
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
    from services.pitch_detection import syllable_pitches
    
    log_step("ULTRASTAR", f"Generating file: {len(syllable_timings)} syllables, BPM={bpm:.2f}, GAP={gap_ms}ms")
    
    language_value = language_header(language, language2)  # "English" or "English, German"
    
    # Header
    header = (
        f"#ARTIST:{artist}\n"
        f"#TITLE:{title}\n"
        f"#BPM:{_fmt_bpm(bpm)}\n"
        f"#GAP:{gap_ms}\n"
        f"#LANGUAGE:{language_value}\n"
        f"#MP3:{mp3_filename}\n"
    )
    
    note_lines = []
    gap_sec = gap_ms / 1000.0
    pitches = syllable_pitches(pitch_data, syllable_timings)
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
            midi_pitch = pitches[i]
            prefix = ":"
        
        # Add break line between phrases (YASS-style: single number = end of last line)
        if prev_line_index is not None and line_index != prev_line_index:
            break_start = last_end_beat + 2  # 2 beat padding after last note
            note_lines.append(f"- {break_start}")
        
        syllable = clean_syllable(syllable)
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
    language2: Optional[str] = None,
) -> str:
    """Generate a minimal Ultrastar .txt file with headers only (no notes).

    This is used as a lightweight starting point for manual note creation in
    the editor while preserving song metadata and timing headers.
    """
    language_value = language_header(language, language2)  # "English" or "English, German"

    header = (
        f"#ARTIST:{artist}\n"
        f"#TITLE:{title}\n"
        f"#BPM:{_fmt_bpm(bpm)}\n"
        f"#GAP:{gap_ms}\n"
        f"#LANGUAGE:{language_value}\n"
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
