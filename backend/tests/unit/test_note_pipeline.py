"""The note steps shared by the whole song and a range: melisma, GAME, frozen pitches, consonant trimming."""

import numpy as np

from services import game_notes
from services.note_pipeline import build_notes


def test_pitches_are_frozen_before_the_notes_are_trimmed(make_pitch_data, monkeypatch, tmp_path):
    monkeypatch.setenv("ULTRASTAR_MELISMA", "0")
    monkeypatch.setattr(game_notes, "apply", lambda *a, **k: 0)
    import services.forced_alignment as fa
    monkeypatch.setattr(fa, "frame_loudness", lambda path: np.full(1000, -20.0))
    pitch = make_pitch_data([(1.10, 1.60, 62), (2.00, 2.50, 64)])
    timings = [{"syllable": "sun ", "start": 1.0, "end": 1.9, "line_index": 0},
               {"syllable": "day ", "start": 1.9, "end": 2.6, "line_index": 0}]
    notes, info = build_notes("vocals.wav", timings, pitch, "en", str(tmp_path), "ctc")
    assert [n["pitch"] for n in notes] == [62, 64] and all(n["pitch_final"] for n in notes)
    assert notes[0]["start"] >= 1.10 and notes[0]["end"] <= 1.9 - 0.13   # trimmed: voiced part, air before "day"
    assert info["trimmed"] and timings[0]["start"] == 1.0                 # the input is left alone


def test_no_trimming_without_forced_alignment(make_pitch_data, monkeypatch, tmp_path):
    monkeypatch.setenv("ULTRASTAR_MELISMA", "0")
    monkeypatch.setattr(game_notes, "apply", lambda *a, **k: 0)
    timings = [{"syllable": "la ", "start": 1.0, "end": 1.9, "line_index": 0}]
    notes, info = build_notes("vocals.wav", timings, make_pitch_data([(1.2, 1.5, 60)]), "en", str(tmp_path), "legacy")
    assert (notes[0]["start"], notes[0]["end"], notes[0]["pitch"]) == (1.0, 1.9, 60) and not info["trimmed"]
