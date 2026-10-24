"""Consonant trimming: notes start on the voice, end where it fades, leave air before the next syllable."""

import numpy as np
import pytest

from services import consonant_trim as ct


def pitch_track(voiced_spans, until=5.0):
    """FCPE-like pitch data: voiced (MIDI 60) inside `voiced_spans`, unvoiced elsewhere, 10 ms frames."""
    times = np.arange(0, until, 0.01)
    voiced = np.zeros(len(times), bool)
    for a, b in voiced_spans:
        voiced |= (times >= a) & (times < b)
    return {"times": times, "midi_notes": np.where(voiced, 60, 0), "confidences": voiced.astype(float)}


def syl(text, start, end, line=0, **extra):
    return {"syllable": text, "start": start, "end": end, "line_index": line, **extra}


def test_unvoiced_consonants_are_left_out():
    # "sun": the "s" (1.00–1.12) has no pitch, the voice sounds from 1.12 to 1.70, the syllable runs to 1.90
    (out,) = ct.trim([syl("sun ", 1.0, 1.9)], pitch_track([(1.12, 1.7)]))
    assert out["start"] == pytest.approx(1.12) and out["end"] == pytest.approx(1.70)


def test_the_end_follows_the_loudness():
    loudness = np.full(250, -60.0)
    loudness[50:70] = -10.0          # 1.00–1.40 s loud
    loudness[70:90] = -25.0          # then fading, still voiced
    (out,) = ct.trim([syl("la ", 1.0, 1.8)], pitch_track([(1.0, 1.8)]), loudness)
    assert out["end"] == pytest.approx(1.40)


def test_air_before_the_next_syllable_in_the_same_line_only():
    track = pitch_track([(0.0, 3.0)])
    out = ct.trim([syl("one ", 0.0, 1.0), syl("two ", 1.0, 2.0), syl("three ", 2.0, 3.0, line=1)], track)
    assert out[0]["end"] == pytest.approx(1.0 - ct.GAP_SEC)
    assert out[1]["end"] == pytest.approx(2.0)          # the next syllable is in another line


def test_melisma_parts_stay_joined():
    track = pitch_track([(1.1, 2.6)])
    parts = [syl("gas", 1.0, 1.6, melisma_part=0), syl("~", 1.6, 2.1, melisma_part=1), syl("~ ", 2.1, 3.0, melisma_part=2)]
    out = ct.trim(parts, track)
    assert out[0]["start"] == pytest.approx(1.1) and out[2]["end"] == pytest.approx(2.60)
    assert (out[0]["end"], out[1]["start"], out[1]["end"], out[2]["start"]) == (1.6, 1.6, 2.1, 2.1)


def test_rap_and_unvoiced_syllables_keep_their_timing():
    track = pitch_track([(5.0, 5.0)])
    timings = [syl("yo ", 1.0, 1.5, is_rap=True), syl("hm ", 2.0, 2.5)]
    assert ct.trim(timings, track) == timings


def test_switched_off(monkeypatch):
    assert ct.enabled()
    monkeypatch.setenv("ULTRASTAR_TRIM_CONSONANTS", "0")
    assert not ct.enabled()


def test_the_start_waits_for_the_first_sung_letter():
    # "sun": the voice is already "voiced" at 1.02 (breath, bleed), the aligner hears the "u" at 1.10: halfway
    timing = syl("sun ", 1.0, 1.9, letters=[("s", 1.0), ("u", 1.10), ("n", 1.4)])
    (out,) = ct.trim([timing], pitch_track([(1.02, 1.7)]))
    assert out["start"] == pytest.approx(1.02 + ct.LETTER_WEIGHT * 0.08)
    # "love": a sounding consonant, the note starts on the "l"
    (out,) = ct.trim([syl("love ", 2.0, 2.6, letters=[("l", 2.03), ("o", 2.12), ("v", 2.4), ("e", 2.5)])],
                     pitch_track([(2.0, 2.6)]))
    assert out["start"] == pytest.approx(2.0 + ct.LETTER_WEIGHT * 0.03)


def test_short_syllables_keep_their_trimmed_start():
    # "a" from 1.00 to 1.10, the vowel heard at 1.09: halfway would leave 55 ms, so the note keeps its 60 ms minimum
    (out,) = ct.trim([syl("a ", 1.0, 1.10, letters=[("a", 1.09)])], pitch_track([(1.0, 1.10)]))
    assert out["start"] == pytest.approx(1.04) and out["end"] == pytest.approx(1.10)
