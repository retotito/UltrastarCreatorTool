"""Trim notes the way charters fine-tune them by hand: a note starts where the voice gets a pitch, ends where it
fades, and leaves some air before the next syllable.

- start: the first voiced frame (pitch tracker) inside the syllable, so unvoiced consonants ("s", "sh", "f", "t",
  "k", "p", "h") are left out ("sun" starts on the "u"); voiced ones ("m", "n", "l", "r") have a pitch and stay,
- end: the last voiced frame, and no later than where the loudness drops END_DROP_DB below the note's peak,
- gap: inside a line, a note ends at least GAP_SEC before the next syllable starts.

Melisma parts ("~") of a syllable stay joined: only the first part's start and the last part's end move.
Measured on two charts fine-tuned this way (Ben Harper "She's Only Happy in the Sun", Robert Post "Got None"):
start error 52/54 → 41/47 ms, end error 164/139 → 61/45 ms, ends more than 100 ms off 121/254 → 45/77.
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
        end = min(last["end"], max(float(inside[-1]) + FRAME_SEC, last["end"] - MAX_END_TRIM_SEC))
        if loudness_db is not None:
            end = _loudness_end(loudness_db, start, end)
        if len(g) > 1:   # the parts stay inside their own spans
            start = min(start, out[g[1]]["start"] - MIN_NOTE_SEC)
            end = max(end, last["start"] + MIN_NOTE_SEC)
        if end - start >= MIN_NOTE_SEC:
            first["start"], last["end"] = start, end
    for g, nxt in zip(groups, groups[1:]):
        last, following = out[g[-1]], out[nxt[0]]
        if last.get("is_rap") or following.get("line_index") != last.get("line_index"):
            continue
        if following["start"] - last["end"] < GAP_SEC:
            last["end"] = max(last["start"] + MIN_NOTE_SEC, min(last["end"], following["start"] - GAP_SEC))
    return out
