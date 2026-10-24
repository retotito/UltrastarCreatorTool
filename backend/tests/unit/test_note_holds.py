"""Held notes: a syllable lasts as long as the voice keeps singing it."""

import numpy as np
import pytest

from services import note_holds as nh


def track(spans, until=12.0):
    """FCPE-like pitch data from (start, end, midi or callable(t) -> midi) spans, 10 ms frames."""
    times = np.arange(0, until, 0.01)
    midi = np.zeros(len(times))
    for a, b, m in spans:
        inside = (times >= a) & (times < b)
        midi[inside] = m(times[inside]) if callable(m) else m
    freq = np.where(midi > 0, 440.0 * 2 ** ((midi - 69) / 12), 0.0)
    return {"times": times, "frequencies": freq, "midi_notes": np.round(midi).astype(int),
            "confidences": (midi > 0).astype(float)}


def syl(text, start, end, line=0):
    return {"syllable": text, "start": start, "end": end, "line_index": line}


def test_a_held_vowel_before_a_pause_keeps_its_length():
    # "sun" aligned 1.0–1.3, sung (gliding 66 → 64) until 6.0, the next line at 8.0
    pitch = track([(1.0, 6.0, lambda t: 66 - 2 * (t - 1) / 5), (8.0, 8.5, 60)])
    out = nh.extend_holds([syl("sun ", 1.0, 1.3), syl("next ", 8.0, 8.5, line=1)], pitch)
    assert out[0]["end"] == pytest.approx(6.0, abs=0.02) and out[0]["held_from"] == 1.3
    assert out[1]["end"] == 8.5


def test_the_hold_stops_at_another_voice_silence_or_the_next_syllable():
    jump = track([(1.0, 2.0, 60), (2.0, 4.0, 72)])                     # an octave up: another voice
    assert nh.extend_holds([syl("la ", 1.0, 1.3)], jump)[0]["end"] == pytest.approx(2.0, abs=0.02)
    pause = track([(1.0, 2.0, 60), (2.5, 4.0, 60)])                    # 0.5 s silent
    assert nh.extend_holds([syl("la ", 1.0, 1.3)], pause)[0]["end"] == pytest.approx(2.0, abs=0.02)
    held = track([(1.0, 6.0, 60)])
    out = nh.extend_holds([syl("la ", 1.0, 1.3), syl("da ", 3.0, 3.5)], held)
    assert out[0]["end"] == pytest.approx(3.0 - nh.GAP_SEC)


def test_inside_a_line_notes_keep_their_air():
    held = track([(1.0, 3.0, 60)])
    out = nh.extend_holds([syl("la ", 1.0, 1.3), syl("da ", 1.6, 2.0)], held)   # 0.3 s to the next: no hold
    assert out[0]["end"] == 1.3 and "held_from" not in out[0]


def test_switched_off(monkeypatch):
    monkeypatch.setenv("ULTRASTAR_HOLD_NOTES", "0")
    assert not nh.enabled()
