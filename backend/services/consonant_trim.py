"""Trim notes the way charters fine-tune them by hand: a note starts where the voice gets a pitch, ends where it
fades, and leaves some air before the next syllable.

- start: after the first voiced frame (pitch tracker), moved halfway towards where the aligner hears the syllable's
  first vowel or sounding consonant ("l", "m", "n", "r", "w"; LETTER_WEIGHT): unvoiced consonants ("s", "sh", "f",
  "t", "k", "p", "h") are mostly left out,
- end: the last voiced frame, and no later than where the loudness drops END_DROP_DB below the note's peak,
- gap: inside a line, a note ends at least GAP_SEC before the next syllable starts.

Melisma parts ("~") of a syllable stay joined: only the first part's start and the last part's end move.
Measured on two charts fine-tuned this way (Ben Harper "She's Only Happy in the Sun", Robert Post "Got None"):
end error 187/85 → 73/46 ms, ends more than 100 ms off 125/152 → 50/81; start error 50/53 → 52/35 ms.
Community charts mostly keep consonants and join notes, so this is a style: ULTRASTAR_TRIM_CONSONANTS=0 turns it off.
"""

import os
from typing import List, Optional

import numpy as np

MAX_START_TRIM_SEC = 0.25   # a start moves at most this much later (further: the voicing belongs elsewhere)
MAX_END_TRIM_SEC = 0.40     # an end moves at most this much earlier by voicing
END_DROP_DB = 6.0
GAP_SEC = 0.14
MIN_NOTE_SEC = 0.06
SUNG_LETTERS = set("aeiouylmnrw")
# How far a start moves from the voiced start towards the first sung letter (0…1). The two fine-tuned charts
# disagree: Robert Post (BPM 612) starts after the consonant (start error 48 → 35 ms with 1.0), Ben Harper (BPM 178,
# an 84 ms grid) rather on it (44 → 69 ms with 1.0). 0.5 is best for both together (weighted 46.8 → 40.2 ms).
LETTER_WEIGHT = 0.5   # a note may start on these (the aligner's letters, see services/forced_alignment)
FRAME_SEC = 0.01            # one pitch frame: the last voiced frame still sounds for its length
LOUDNESS_FRAME_SEC = 0.02   # services/forced_alignment.frame_loudness


def enabled() -> bool:
    return os.environ.get("ULTRASTAR_TRIM_CONSONANTS", "1").strip().lower() not in ("0", "false", "off", "no")


def voiced_times(pitch_data: dict) -> np.ndarray:
    """Times of the frames where the pitch tracker heard a pitch."""
    from services.pitch_detection import CONFIDENCE_THRESHOLD
    voiced = (np.asarray(pitch_data["midi_notes"]) > 0) & \
             (np.asarray(pitch_data["confidences"], dtype=float) >= CONFIDENCE_THRESHOLD)
    return np.asarray(pitch_data["times"], dtype=float)[voiced]


def _groups(timings: List[dict]) -> List[List[int]]:
    """Indices per syllable: a syllable and its melisma parts ("~", melisma_part > 0)."""
    groups: List[List[int]] = []
    for i, t in enumerate(timings):
        if groups and t.get("melisma_part", 0) > 0:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def _loudness_end(loudness_db: np.ndarray, start: float, end: float) -> float:
    """Where the loudness between `start` and `end` last is within END_DROP_DB of its peak."""
    a = int(start / LOUDNESS_FRAME_SEC)
    b = max(a + 1, int(end / LOUDNESS_FRAME_SEC))
    segment = loudness_db[a:b]
    if len(segment) <= 2:
        return end
    loud = np.nonzero(segment >= segment.max() - END_DROP_DB)[0]
    return min(end, (a + loud[-1] + 1) * LOUDNESS_FRAME_SEC)


def trim(syllable_timings: List[dict], pitch_data: dict, loudness_db: Optional[np.ndarray] = None) -> List[dict]:
    """The timings trimmed as described above (copies). Rap syllables keep their start and end."""
    times = voiced_times(pitch_data)
    out = [dict(t) for t in syllable_timings]
    groups = _groups(out)
    for g in groups:
        first, last = out[g[0]], out[g[-1]]
        if first.get("is_rap"):
            continue
        inside = times[(times >= first["start"]) & (times < last["end"])]
        if not len(inside):
            continue
        start = min(float(inside[0]), first["start"] + MAX_START_TRIM_SEC)
        sung = next((at for letter, at in first.get("letters") or [] if letter in SUNG_LETTERS), None)
        if sung is not None and sung - start <= MAX_START_TRIM_SEC:   # at most this far past the voiced start
            start = max(start, start + LETTER_WEIGHT * (sung - start))
        end = min(last["end"], max(float(inside[-1]) + FRAME_SEC, last["end"] - MAX_END_TRIM_SEC))
        if loudness_db is not None:
            end = _loudness_end(loudness_db, start, end)
        if len(g) > 1:   # the parts stay inside their own spans
            start = min(start, out[g[1]]["start"] - MIN_NOTE_SEC)
            end = max(end, last["start"] + MIN_NOTE_SEC)
        if end - start < MIN_NOTE_SEC:   # short syllables ("I", "a"): keep the start, give the note its minimum
            end = min(last["end"], start + MIN_NOTE_SEC)
            start = max(first["start"], min(start, end - MIN_NOTE_SEC))
        first["start"], last["end"] = start, end
    for g, nxt in zip(groups, groups[1:]):
        last, following = out[g[-1]], out[nxt[0]]
        if last.get("is_rap") or following.get("line_index") != last.get("line_index"):
            continue
        if following["start"] - last["end"] < GAP_SEC:
            last["end"] = max(last["start"] + MIN_NOTE_SEC, min(last["end"], following["start"] - GAP_SEC))
    return out
