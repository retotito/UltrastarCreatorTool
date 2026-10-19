"""Reference UltraStar charts as evaluation targets: syllables with absolute start times.

Each reference note becomes one syllable of the lyrics, so the aligned output and the reference
compare one to one. Melisma notes (`~`) belong to the syllable before them.
"""

import re
from dataclasses import dataclass, field
from typing import List

NOTE = re.compile(r"^([:*FRG]):?\s(-?\d+)\s(\d+)\s(-?\d+)\s?(.*)$")


@dataclass
class RefSyllable:
    text: str           # as written in the chart, without spaces
    start: float        # seconds in the song's audio
    end: float
    word_start: bool
    line: int
    pitch: int = 0      # chart pitch of the syllable's first note (UltraStar: 0 = C4)
    sung: bool = True   # False for rap / freestyle notes (no pitch to compare)
    parts: list = field(default_factory=list)  # (start, end, pitch) of each note, the syllable's first and its ~


def _header(content: str, key: str) -> str:
    match = re.search(rf"^#{key}:(.*)$", content, flags=re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def parse_reference(content: str) -> List[RefSyllable]:
    """Syllables of a chart (absolute times). Supports `:`, `*`, `F`, `R`, `G` notes; stops at `E`."""
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    bpm = float(_header(content, "BPM").replace(",", ".") or 0)
    gap = float(_header(content, "GAP").replace(",", ".") or 0) / 1000.0
    if bpm <= 0:
        raise ValueError("Reference has no BPM")
    if _header(content, "RELATIVE").lower() in ("yes", "1", "true"):
        raise ValueError("Relative charts are not supported")
    beat = 15.0 / bpm

    syllables: List[RefSyllable] = []
    line = 0
    line_has_notes = False
    for raw in content.split("\n"):
        if raw.startswith("E"):
            break
        if raw.startswith("-"):
            if line_has_notes:
                line += 1
                line_has_notes = False
            continue
        match = NOTE.match(raw)
        if not match:
            continue
        kind, start_beat, length, pitch, text = match.groups()
        start = gap + int(start_beat) * beat
        end = start + int(length) * beat
        if text.strip() == "~" or text.strip().startswith("~") and syllables and line_has_notes:
            syllables[-1].end = end
            syllables[-1].parts.append((start, end, int(pitch)))
            continue
        word_start = (not line_has_notes) or text.startswith(" ") or (syllables and syllables[-1].text.endswith(" "))
        syllables.append(RefSyllable(text=text, start=start, end=end, word_start=bool(word_start), line=line,
                                     pitch=int(pitch), sung=kind in (":", "*"), parts=[(start, end, int(pitch))]))
        line_has_notes = True
    for syllable in syllables:
        syllable.text = syllable.text.strip()
    return [s for s in syllables if re.search(r"\w", s.text)]


def lyrics_text(syllables: List[RefSyllable]) -> str:
    """The chart's lyrics in the app's lyric format: one line per phrase, syllables joined with '-'."""
    lines: List[List[str]] = []
    current_line = -1
    for syllable in syllables:
        text = syllable.text.replace("-", "").replace("~", "")
        if syllable.line != current_line:
            lines.append([text])
            current_line = syllable.line
        elif syllable.word_start:
            lines[-1].append(text)
        else:
            lines[-1][-1] += "-" + text
    return "\n".join(" ".join(words) for words in lines)


def audio_file(content: str) -> str:
    """The audio file name the chart refers to (#AUDIO, else #MP3)."""
    return _header(content, "AUDIO") or _header(content, "MP3")
