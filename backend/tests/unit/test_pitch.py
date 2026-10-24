"""Pitch per syllable: median over the span, neighbours for unvoiced syllables."""

import pytest

from services.pitch_detection import fix_repeated_lines, fill_unvoiced, fix_octaves, syllable_pitch, syllable_pitches


@pytest.mark.parametrize("raw, expected", [
    ([60, 0, 62], [60, 60, 62]),          # previous sung pitch
    ([0, 0, 64, 0], [64, 64, 64, 64]),    # before the first: the next one
    ([0, 0], [60, 60]),                   # nothing sung at all: C4
    ([62, None, 0], [62, None, 62]),      # rap notes (None) are skipped and kept
])
def test_fill_unvoiced(raw, expected):
    assert fill_unvoiced(raw) == expected


def test_syllable_pitch_is_the_median_and_widens_for_short_syllables(make_pitch_data):
    pitch = make_pitch_data([(1.0, 1.2, 60), (1.2, 1.6, 65)])
    assert syllable_pitch(pitch, 1.0, 1.6) == 65
    # nothing voiced inside 1.75–1.8, but within ±0.1 s of its middle
    assert syllable_pitch(make_pitch_data([(1.6, 1.7, 62)]), 1.75, 1.8) == 62


def test_syllable_pitches_marks_rap_as_none(make_pitch_data):
    timings = [{"start": 1.0, "end": 1.5}, {"start": 2.0, "end": 2.5, "is_rap": True}]
    assert syllable_pitches(make_pitch_data([(1.0, 1.5, 64)]), timings) == [64, None]


def test_the_slide_into_a_note_is_ignored(make_pitch_data):
    # scoops up from 58 for the first 0.2 s, then holds 62 for 0.4 s
    pitch = make_pitch_data([(1.0, 1.2, 58), (1.2, 1.6, 62)])
    assert syllable_pitch(pitch, 1.0, 1.4) == 62  # whole-span median would be 58/62 split


def test_fcpe_failure_falls_back_to_pyin(monkeypatch):
    import services.pitch_detection as pd
    monkeypatch.delenv("ULTRASTAR_PITCH_ENGINE", raising=False)
    monkeypatch.setattr(pd, "detect_pitches_fcpe", lambda path: (_ for _ in ()).throw(RuntimeError("no model")))
    monkeypatch.setattr(pd, "detect_pitches_pyin", lambda path: {"engine": "pyin"})
    assert pd.detect_pitches("v.wav") == {"engine": "pyin"}


def test_pyin_can_be_chosen(monkeypatch):
    import services.pitch_detection as pd
    monkeypatch.setenv("ULTRASTAR_PITCH_ENGINE", "pyin")
    monkeypatch.setattr(pd, "detect_pitches_fcpe", lambda path: {"engine": "fcpe"})
    monkeypatch.setattr(pd, "detect_pitches_pyin", lambda path: {"engine": "pyin"})
    assert pd.detect_pitches("v.wav") == {"engine": "pyin"}


@pytest.mark.slow
def test_fcpe_finds_a_sung_tone(tmp_path):
    """Loads the FCPE model: run with -m slow."""
    import numpy as np
    import soundfile as sf
    from services.pitch_detection import detect_pitches_fcpe
    sr = 16000
    t = np.arange(sr) / sr
    tone = 0.3 * np.sin(2 * np.pi * 440 * t)  # A4 = MIDI 69
    sf.write(tmp_path / "a4.wav", tone, sr)
    track = detect_pitches_fcpe(str(tmp_path / "a4.wav"))
    voiced = track["midi_notes"][track["confidences"] > 0]
    assert len(voiced) > 50 and np.median(voiced) == 69


def timings(*starts, length=0.3):
    return [{"start": s, "end": s + length} for s in starts]


class TestFixOctaves:
    def test_a_single_octave_jump_inside_a_phrase_is_moved_back(self):
        pitches = [45, 44, 44, 40, 43, 56]
        fixed = fix_octaves(pitches, timings(0.0, 0.4, 0.8, 1.2, 1.6, 2.0))
        assert fixed == [45, 44, 44, 40, 43, 44]

    def test_notes_move_one_octave_at_most(self):
        # Known limit: "out" detected three octaves too high (Freak Power, test2) can't be brought back
        pitches = [45, 44, 44, 40, 43, 80]
        fixed = fix_octaves(pitches, timings(0.0, 0.4, 0.8, 1.2, 1.6, 2.0))
        assert all(abs(f - p) <= 12 for f, p in zip(fixed, pitches)) and fixed[5] >= 68

    def test_a_low_voice_in_a_duet_is_not_pulled_two_octaves_up(self):
        # Amada Mia, Amore Mio: FCPE heard the male voice an octave low (~40, Tune Studio's chart: ~52) between
        # high female lines (~72); with up to three octaves he was moved to ~64
        male, female = [40, 40, 39, 40], [72, 74, 74, 72, 71, 71]
        fixed = fix_octaves(male + female + male, timings(*[0.4 * i for i in range(14)]))
        assert all(abs(f - p) <= 12 for f, p in zip(fixed, male + female + male))
        assert all(f < 60 for f in fixed[:4] + fixed[10:])

    def test_an_octave_too_low_is_moved_up(self):
        assert fix_octaves([52, 53, 41, 52], timings(0, 0.4, 0.8, 1.2)) == [52, 53, 53, 52]

    def test_small_leaps_are_left_alone(self):
        pitches = [45, 52, 47, 55, 50]
        assert fix_octaves(pitches, timings(0, 0.4, 0.8, 1.2, 1.6)) == pitches

    def test_a_new_phrase_after_a_long_pause_may_start_in_another_register(self):
        pitches = [45, 46, 45, 58, 59, 58]   # a fifth-plus leap up after a 4 s pause
        assert fix_octaves(pitches, timings(0, 0.4, 0.8, 5.0, 5.4, 5.8)) == pitches

    def test_rap_notes_are_skipped(self):
        assert fix_octaves([45, None, 56, 44], timings(0, 0.4, 0.8, 1.2)) == [45, None, 44, 44]

    def test_too_few_notes_are_returned_unchanged(self):
        assert fix_octaves([80], timings(0)) == [80]


def line(texts, pitches, index, start):
    return [{"syllable": t, "start": start + 0.4 * k, "end": start + 0.4 * k + 0.3, "line_index": index}
            for k, t in enumerate(texts)], pitches


class TestRepeatedLines:
    WORDS = ["A", "ma", "da", "mi", "a"]

    def song(self, *lines_pitches):
        when, pitches = [], []
        for n, p in enumerate(lines_pitches):
            w, _ = line(self.WORDS, p, n, 10.0 * n)
            when += w
            pitches += p
        return when, pitches

    def test_an_octave_off_note_takes_its_repetitions_octave(self):
        when, pitches = self.song([51, 52, 52, 51, 52], [51, 52, 52, 51, 52], [63, 52, 52, 51, 64], [51, 52, 52, 51, 52])
        assert fix_repeated_lines(pitches, when)[10:15] == [51, 52, 52, 51, 52]

    def test_nothing_moves_where_the_repetitions_disagree(self):
        # half of the repetitions sung in another register: no clear melody to move towards
        when, pitches = self.song([51, 52, 52, 51, 52], [63, 64, 64, 63, 64], [51, 52, 52, 51, 52], [63, 64, 64, 63, 64])
        assert fix_repeated_lines(pitches, when) == pitches

    def test_a_repetition_sung_elsewhere_is_left_alone(self):
        # the whole line an octave up (another singer): only its notes would agree with each other
        when, pitches = self.song([51, 52, 52, 51, 52], [51, 52, 52, 51, 52], [51, 52, 52, 51, 52], [63, 64, 64, 63, 64])
        assert fix_repeated_lines(pitches, when)[15:20] == [63, 64, 64, 63, 64]
