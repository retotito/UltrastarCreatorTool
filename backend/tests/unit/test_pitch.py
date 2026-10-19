"""Pitch per syllable: median over the span, neighbours for unvoiced syllables."""

import pytest

from services.pitch_detection import fill_unvoiced, syllable_pitch, syllable_pitches


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
