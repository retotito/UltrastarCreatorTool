"""Timing error metrics: aligned syllables vs reference syllables (same lyrics, same order)."""

from typing import Dict, List

import numpy as np

GROSS_ERROR_SEC = 0.5


def timing_errors(results: List[dict], reference_starts: List[float]) -> np.ndarray:
    """Signed start errors in seconds (aligned − reference), syllable by syllable."""
    if len(results) != len(reference_starts):
        raise ValueError(f"{len(results)} aligned syllables vs {len(reference_starts)} in the reference")
    return np.array([r["start"] for r in results]) - np.array(reference_starts)


def pitch_summary(midi: List[int], unvoiced: List[bool], reference: List[int], sung: List[bool]) -> Dict[str, float]:
    """Pitch against the chart, octave ignored (charts are often an octave off the audio).

    `midi`: our MIDI pitch per syllable; `unvoiced`: no pitch was found (neighbour used);
    `reference`: chart pitch (0 = C4); `sung`: syllables to compare (not rap/freestyle).
    """
    pairs = [(m, r, u) for m, r, u, s in zip(midi, reference, unvoiced, sung) if s and m]
    if not pairs:
        return {"compared": 0, "pitch_class_pct": 0.0, "within_1_pct": 0.0, "unvoiced_pct": 0.0,
                "octave_err_pct": 0.0}
    distance = np.array([min((m - 60 - r) % 12, (r - m + 60) % 12) for m, r, _ in pairs])
    # Octave errors: charts sit in some octave of their own, the same for the whole song. Among notes on
    # (about) the right pitch class, count those in another octave than most of the song's.
    octaves = np.array([int(round((m - 60 - r) / 12)) for m, r, _ in pairs])[distance <= 1]
    usual = np.bincount(octaves - octaves.min()).argmax() + octaves.min() if len(octaves) else 0
    return {
        "compared": len(pairs),
        "pitch_class_pct": float(np.mean(distance == 0) * 100),
        "within_1_pct": float(np.mean(distance <= 1) * 100),
        "unvoiced_pct": float(np.mean([u for _, _, u in pairs]) * 100),
        "octave_err_pct": float(np.mean(octaves != usual) * 100) if len(octaves) else 0.0,
    }


SPLIT_TOLERANCE_SEC = 0.15


def note_parts(notes: List[dict], pitches: List[int]) -> List[List[tuple]]:
    """Our notes grouped per syllable: a note whose text starts with "~" continues the syllable before."""
    groups: List[List[tuple]] = []
    for note, pitch in zip(notes, pitches):
        part = (note["start"], note["end"], pitch)
        if groups and note["syllable"].strip().startswith("~"):
            groups[-1].append(part)
        else:
            groups.append([part])
    return groups


def melisma_summary(ours: List[List[tuple]], reference: list) -> Dict[str, float]:
    """Note splitting against the chart.

    - split points (starts of a syllable's 2nd, 3rd ... note): precision, recall, F1 within ±0.15 s
    - frame pitch: every 10 ms of a sung chart note, is our note there on the same pitch class
      (octave ignored) / within a semitone
    """
    hits = ours_count = ref_count = 0
    for parts, ref in zip(ours, reference):
        mine = [start for start, _, _ in parts[1:]]
        theirs = [start for start, _, _ in ref.parts[1:]]
        ours_count += len(mine)
        ref_count += len(theirs)
        free = list(theirs)
        for t in mine:
            match = min(free, key=lambda r: abs(r - t), default=None)
            if match is not None and abs(match - t) <= SPLIT_TOLERANCE_SEC:
                hits += 1
                free.remove(match)
    precision = hits / ours_count if ours_count else 0.0
    recall = hits / ref_count if ref_count else 0.0
    flat = sorted(p for parts in ours for p in parts)
    starts = np.array([p[0] for p in flat])
    exact = near = frames = 0
    for ref in reference:
        if not ref.sung:
            continue
        for start, end, pitch in ref.parts:
            for t in np.arange(start, end, 0.01):
                frames += 1
                k = int(np.searchsorted(starts, t, side="right")) - 1
                if k < 0 or flat[k][1] < t or not flat[k][2]:
                    continue
                d = (flat[k][2] - 60 - pitch) % 12
                d = min(d, 12 - d)
                exact += d == 0
                near += d <= 1
    return {
        "splits_ours": ours_count, "splits_chart": ref_count,
        "split_precision": precision * 100, "split_recall": recall * 100,
        "split_f1": (2 * precision * recall / (precision + recall) * 100) if precision + recall else 0.0,
        "frame_pitch_pct": exact / frames * 100 if frames else 0.0,
        "frame_pitch_1_pct": near / frames * 100 if frames else 0.0,
    }


def big_jumps(midi: List[int], lines: List[int], limit: int = 12) -> int:
    """Jumps of more than an octave between neighbouring notes of the same line."""
    return sum(1 for a, b, la, lb in zip(midi, midi[1:], lines, lines[1:])
               if la == lb and a and b and abs(a - b) > limit)


def summarize(errors: np.ndarray) -> Dict[str, float]:
    """Median absolute error, share within 50 / 100 / 250 ms, gross errors (> 500 ms), bias."""
    absolute = np.abs(errors)
    bias = float(np.median(errors))
    return {
        "syllables": int(len(errors)),
        "median_ms": float(np.median(absolute) * 1000),
        "within_50ms": float(np.mean(absolute <= 0.05) * 100),
        "within_100ms": float(np.mean(absolute <= 0.10) * 100),
        "within_250ms": float(np.mean(absolute <= 0.25) * 100),
        "gross": int(np.sum(absolute > GROSS_ERROR_SEC)),
        "gross_pct": float(np.mean(absolute > GROSS_ERROR_SEC) * 100),
        "bias_ms": bias * 1000,
        "median_ms_unbiased": float(np.median(np.abs(errors - bias)) * 1000),
    }
