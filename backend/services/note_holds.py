"""Held notes: a syllable lasts as long as the voice keeps singing it.

The lyrics aligner places letters; a long-held vowel adds no new letter, so it often ends a word at its last
consonant, and the last note before a pause comes out far too short (Ben Harper's final "sun": held 5.3 s,
aligned 0.1 s; Robert Post's "me": 5.6 s, 0.6 s). Here a syllable's end moves on while the voice continues: the
pitch tracker hears a pitch that moves smoothly from frame to frame (no jump to another voice or instrument), the
voice is no quieter than HOLD_DROP_DB below the syllable's loudest point, and the next syllable is GAP_SEC away.
Melisma splitting then turns the long note into its "~" parts. ULTRASTAR_HOLD_NOTES=0 turns it off.
"""

import os
from typing import List, Optional

import numpy as np

MAX_HOLD_SEC = 10.0          # a note grows at most this much
MAX_SILENT_SEC = 0.2         # unvoiced frames tolerated inside a hold (breathy moments)
MAX_STEP_SEMITONES = 4.0     # a bigger jump between voiced frames: another voice, not this note
HOLD_DROP_DB = 20.0
LOUDNESS_WINDOW_SEC = 0.06   # judged on the next 60 ms: after a short break the voice comes back quiet for a frame
                             # or two (Ben Harper's "sun" at 3:25.8: −34 dB, 40 ms later −16 dB)
GAP_SEC = 0.14               # as services/consonant_trim
MIN_ROOM_SEC = 0.4           # only before a pause: inside a line the notes keep their air (consonant trimming)
LOUDNESS_FRAME_SEC = 0.02    # services/forced_alignment.frame_loudness


def enabled() -> bool:
    return os.environ.get("ULTRASTAR_HOLD_NOTES", "1").strip().lower() not in ("0", "false", "off", "no")


def extend_holds(syllable_timings: List[dict], pitch_data: dict, loudness_db: Optional[np.ndarray] = None,
                 audio_end: Optional[float] = None) -> List[dict]:
    """The timings (copies) with each sung syllable's end moved on while its voice continues; extended ones get
    "held_from" (the aligner's end)."""
    from services.pitch_detection import _fractional_midi
    midi = _fractional_midi(pitch_data)
    times = np.asarray(pitch_data["times"], dtype=float)
    if not len(times):
        return [dict(t) for t in syllable_timings]
    hop = float(times[1] - times[0]) if len(times) > 1 else 0.01
    end_of_audio = audio_end if audio_end is not None else float(times[-1]) + hop
    out = [dict(t) for t in syllable_timings]
    for i, t in enumerate(out):
        if t.get("is_rap"):
            continue
        limit = min(out[i + 1]["start"] - GAP_SEC if i + 1 < len(out) else end_of_audio, t["end"] + MAX_HOLD_SEC)
        if limit <= t["end"] or limit - t["end"] < MIN_ROOM_SEC - GAP_SEC:
            continue
        own = (times >= t["start"]) & (times < t["end"]) & ~np.isnan(midi)
        if not own.any():
            continue
        peak = None
        if loudness_db is not None:
            a, b = int(t["start"] / LOUDNESS_FRAME_SEC), max(int(t["start"] / LOUDNESS_FRAME_SEC) + 1, int(t["end"] / LOUDNESS_FRAME_SEC))
            segment = loudness_db[a:b]
            peak = float(segment.max()) if len(segment) else None
        last_pitch = float(midi[own][-1])
        last_voiced = float(times[own][-1])
        k = int(np.searchsorted(times, t["end"]))
        while k < len(times) and times[k] < limit:
            now = float(times[k])
            if now - last_voiced > MAX_SILENT_SEC:
                break
            if not np.isnan(midi[k]):
                if abs(midi[k] - last_pitch) > MAX_STEP_SEMITONES:
                    break
                if peak is not None:
                    frame = int(now / LOUDNESS_FRAME_SEC)
                    window = loudness_db[frame:frame + max(1, int(round(LOUDNESS_WINDOW_SEC / LOUDNESS_FRAME_SEC)))]
                    if len(window) and window.max() < peak - HOLD_DROP_DB:
                        break
                last_pitch, last_voiced = float(midi[k]), now
            k += 1
        new_end = min(limit, last_voiced + hop)
        if new_end > t["end"] + 2 * hop:
            t["held_from"] = t["end"]
            t["end"] = new_end
    return out
