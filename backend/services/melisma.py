"""Melisma: split a long syllable into notes where the sung pitch moves ("gas" → gas ~ ~).

Works on the syllable timings, so a split syllable becomes several timing entries (the first with
the syllable's text, the others "~"). The .txt writer, the MIDI export and the editor's
re-quantisation (one note per timing entry) then all stay in step.

A new note starts only where the pitch moves at least MIN_STEP semitones away from the current note
and stays there for MIN_NOTE seconds (hysteresis), so vibrato and short wobbles don't split.
"""

from typing import List

import numpy as np

from services.pitch_detection import _fractional_midi

MIN_SYLLABLE_SEC = 0.25   # shorter syllables are never split
MIN_NOTE_SEC = 0.12       # a new note must last at least this long
MIN_STEP = 1.0            # ... and be this many semitones away from the current one
SMOOTH_FRAMES = 5         # running median over 50 ms before looking for steps
MAX_PARTS = 6
FRAME_SEC = 0.01
# A first or last part shorter than this is a slide into or off the note, not a note of its own:
# chart authors don't write those (0 = keep them).
EDGE_SLIDE_SEC = 0.25
# Chosen on 6 reference songs (eval/run_eval.py, engine ctc-split): frame pitch 42.3 → 44.9 %,
# within a semitone 53.3 → 56.1 %, syllable pitch 57.4 → 59.0 %, 218 "~" notes vs 212 in the charts.


def _running_median(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1 or len(values) < width:
        return values
    half = width // 2
    padded = np.pad(values, half, mode="edge")
    return np.array([np.median(padded[i:i + width]) for i in range(len(values))])


def segment(times: np.ndarray, midi: np.ndarray, start: float, end: float,
            min_note: float = MIN_NOTE_SEC, min_step: float = MIN_STEP) -> List[tuple]:
    """(start, end, midi) parts of one syllable; a single part when the pitch doesn't clearly move."""
    inside = (times >= start) & (times < end) & ~np.isnan(midi)
    t, m = times[inside], midi[inside]
    need = max(2, int(round(min_note / FRAME_SEC)))
    if len(m) < 2 * need:
        return [(start, end, None)]
    m = _running_median(m, SMOOTH_FRAMES)

    cuts = [0]
    current = float(np.median(m[:need]))
    i = need
    while i <= len(m) - need:
        window = m[i:i + need]
        level = float(np.median(window))
        # a step: the next min_note seconds sit clearly away from the current note
        if abs(level - current) >= min_step and np.all(np.abs(window - level) < min_step):
            cuts.append(i)
            current = level
            i += need
        else:
            i += 1
    pieces = [(cuts[k], cuts[k + 1] if k + 1 < len(cuts) else len(m)) for k in range(len(cuts))]
    parts = [[t[a], t[b - 1] + FRAME_SEC, int(round(float(np.median(m[a:b]))))] for a, b in pieces]

    merged = [parts[0]]
    for part in parts[1:]:
        if part[2] == merged[-1][2]:
            merged[-1][1] = part[1]
        else:
            merged.append(part)
    while len(merged) > 1 and EDGE_SLIDE_SEC and merged[0][1] - merged[0][0] < EDGE_SLIDE_SEC:
        merged[1][0] = merged[0][0]
        del merged[0]
    while len(merged) > 1 and EDGE_SLIDE_SEC and merged[-1][1] - merged[-1][0] < EDGE_SLIDE_SEC:
        merged[-2][1] = merged[-1][1]
        del merged[-1]
    while len(merged) > MAX_PARTS:
        shortest = min(range(len(merged)), key=lambda k: merged[k][1] - merged[k][0])
        into = shortest - 1 if shortest > 0 else 1
        merged[into][0] = min(merged[into][0], merged[shortest][0])
        merged[into][1] = max(merged[into][1], merged[shortest][1])
        del merged[shortest]
    if len(merged) == 1:
        return [(start, end, None)]
    # Parts touch: each runs until the next starts; the syllable's own edges are kept.
    merged[0][0] = start
    for a, b in zip(merged, merged[1:]):
        a[1] = b[0]
    merged[-1][1] = end
    return [tuple(p) for p in merged]


def enabled() -> bool:
    """Melisma splitting is on unless ULTRASTAR_MELISMA=off."""
    import os
    return os.environ.get("ULTRASTAR_MELISMA", "on").strip().lower() not in ("off", "0", "false", "no")


def split_melismas(syllable_timings: List[dict], pitch_data: dict,
                   min_note: float = MIN_NOTE_SEC, min_step: float = MIN_STEP) -> List[dict]:
    """Timings with long, moving syllables split into notes (new list; inputs unchanged).

    Each extra note is a copy of its syllable's timing with `syllable` "~" ("~ " for the last part of
    a word), its own start/end, and `pitch` (MIDI) so the writer uses the part's own pitch. The
    first part keeps the syllable's text without the word-end space. Rap syllables are not split.
    """
    if not syllable_timings:
        return []
    midi = _fractional_midi(pitch_data)
    times = np.asarray(pitch_data["times"], dtype=float)
    out = []
    for timing in syllable_timings:
        if timing.get("is_rap") or timing["end"] - timing["start"] < MIN_SYLLABLE_SEC:
            out.append(timing)
            continue
        parts = segment(times, midi, timing["start"], timing["end"], min_note, min_step)
        if len(parts) == 1:
            out.append(timing)
            continue
        text = timing["syllable"]
        word_end = text.endswith(" ")
        for k, (start, end, pitch) in enumerate(parts):
            entry = dict(timing)
            entry.update(start=float(start), end=float(end), pitch=int(pitch), melisma_part=k)
            if k == 0:
                entry["syllable"] = text.rstrip(" ")
            else:
                entry["syllable"] = "~ " if (word_end and k == len(parts) - 1) else "~"
            out.append(entry)
    return out
