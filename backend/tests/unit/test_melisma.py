"""Melisma splitting: long syllables whose pitch moves become several notes."""

import numpy as np
import pytest

from services import melisma
from services.melisma import split_melismas


def track(*segments, duration=4.0, hop=0.01, vibrato=0.0):
    """A pitch track from (start, end, midi) segments; `vibrato` adds a 5.5 Hz wobble of that many semitones."""
    times = np.arange(0.0, duration, hop)
    midi = np.full(times.shape, np.nan)
    for start, end, note in segments:
        inside = (times >= start) & (times < end)
        midi[inside] = note + vibrato * np.sin(2 * np.pi * 5.5 * times[inside])
    frequencies = np.where(np.isnan(midi), 0.0, 440.0 * 2 ** ((np.nan_to_num(midi) - 69) / 12))
    return {"times": times, "frequencies": frequencies, "confidences": (frequencies > 0).astype(float),
            "midi_notes": np.where(np.isnan(midi), 0, np.round(np.nan_to_num(midi))).astype(int)}


def syl(text, start, end, **extra):
    return {"syllable": text, "start": start, "end": end, "line_index": 0, "is_rap": False, **extra}


def parts(timings):
    return [(t["syllable"], round(t["start"], 2), round(t["end"], 2), t.get("pitch")) for t in timings]


def test_a_steady_note_stays_one_note():
    assert parts(split_melismas([syl("gas ", 1.0, 2.0)], track((1.0, 2.0, 60)))) == [("gas ", 1.0, 2.0, None)]


def test_vibrato_does_not_split():
    pitch = track((1.0, 2.5, 60.4), vibrato=0.45)   # wobbles across the 60/61 boundary
    assert len(split_melismas([syl("gas ", 1.0, 2.5)], pitch)) == 1


def test_clear_steps_become_tilde_notes():
    pitch = track((1.0, 1.4, 60), (1.4, 1.8, 63), (1.8, 2.2, 58))
    result = parts(split_melismas([syl("gas ", 1.0, 2.2)], pitch))
    assert [(text, p) for text, _, _, p in result] == [("gas", 60), ("~", 63), ("~ ", 58)]
    assert result[0][1] == 1.0 and result[-1][2] == 2.2          # the syllable's own edges
    assert all(a[2] == b[1] for a, b in zip(result, result[1:]))  # parts touch


def test_a_slide_into_the_note_is_not_a_note():
    pitch = track((1.0, 1.15, 57), (1.15, 1.9, 60))              # 150 ms scoop from below
    assert len(split_melismas([syl("gas ", 1.0, 1.9)], pitch)) == 1


def test_long_held_syllables_are_split_finer():
    # held 4 s: a 150 ms scoop counts there, and more than 6 notes are allowed (charters who fine-tune write them)
    steps = [(1.0, 1.15, 57)] + [(1.15 + 0.35 * k, 1.5 + 0.35 * k, 60 + 2 * (k % 2)) for k in range(8)]
    pitch = track(*steps)
    parts = split_melismas([syl("sun ", 1.0, 3.95)], pitch)
    assert len(parts) == 9 and parts[0]["end"] == pytest.approx(1.15, abs=0.02)


def test_mid_word_syllables_keep_the_word_going():
    pitch = track((1.0, 1.4, 60), (1.4, 1.8, 64))
    result = split_melismas([syl("beau", 1.0, 1.8)], pitch)
    assert [t["syllable"] for t in result] == ["beau", "~"]


def test_short_syllables_and_rap_are_never_split():
    pitch = track((1.0, 1.1, 60), (1.1, 1.2, 64), (2.0, 2.4, 60), (2.4, 2.8, 64))
    timings = [syl("a ", 1.0, 1.2), syl("yo ", 2.0, 2.8, is_rap=True)]
    assert len(split_melismas(timings, pitch)) == 2


def test_other_fields_are_kept_and_inputs_unchanged():
    pitch = track((1.0, 1.4, 60), (1.4, 1.8, 64))
    original = syl("gas ", 1.0, 1.8, line_index=3, confidence=0.9)
    result = split_melismas([original], pitch)
    assert all(t["line_index"] == 3 and t["confidence"] == 0.9 for t in result)
    assert original["syllable"] == "gas " and "pitch" not in original


def test_writer_uses_each_parts_own_pitch():
    from services.pitch_detection import syllable_pitches
    pitch = track((1.0, 1.4, 60), (1.4, 1.8, 64))
    assert syllable_pitches(pitch, split_melismas([syl("gas ", 1.0, 1.8)], pitch)) == [60, 64]


@pytest.mark.parametrize("value, expected", [(None, True), ("off", False), ("0", False), ("on", True)])
def test_switch(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("ULTRASTAR_MELISMA", raising=False)
    else:
        monkeypatch.setenv("ULTRASTAR_MELISMA", value)
    assert melisma.enabled() is expected
