"""Evaluation harness: reference chart parsing and timing metrics."""

import numpy as np
import pytest

from eval.metrics import summarize, timing_errors
from eval.reference import audio_file, lyrics_text, parse_reference

CHART = "\r\n".join([
    "#TITLE:T",
    "#MP3:song.mp3",
    "#BPM:240,00",
    "#GAP:1000",
    ": 0 4 60 Beau",
    ": 4 2 60 ti",
    ": 6 2 60 ful",
    ": 8 4 60  day",
    ": 12 4 62 ~",
    "- 18",
    "R 20 4 0 Yo",
    "F 24 4 0  free",
    "G 28 2 0 ~",
    "* 32 4 64  gold",
    "E",
    ": 99 1 60 ignored",
])


@pytest.fixture
def syllables():
    return parse_reference(CHART)


def test_every_note_type_becomes_a_syllable_and_melisma_extends_the_previous(syllables):
    assert [s.text for s in syllables] == ["Beau", "ti", "ful", "day", "Yo", "free", "gold"]


def test_times_are_absolute_seconds(syllables):
    # BPM 240 → 62.5 ms per beat, GAP 1 s
    assert syllables[0].start == pytest.approx(1.0)
    assert syllables[3].start == pytest.approx(1.5)
    assert syllables[3].end == pytest.approx(2.0)  # extended by the ~ note


def test_lyrics_keep_lines_words_and_syllables(syllables):
    assert lyrics_text(syllables) == "Beau-ti-ful day\nYo free gold"


def test_audio_file_prefers_the_audio_header():
    assert audio_file(CHART) == "song.mp3"
    assert audio_file("#AUDIO:a.ogg\n#MP3:b.mp3") == "a.ogg"


def test_relative_charts_are_rejected():
    with pytest.raises(ValueError):
        parse_reference("#BPM:300\n#RELATIVE:yes\n: 0 1 60 a\nE")


def test_metrics():
    errors = timing_errors([{"start": 1.0}, {"start": 2.05}, {"start": 3.9}], [1.0, 2.0, 3.0])
    summary = summarize(errors)
    assert summary["gross"] == 1
    assert summary["within_100ms"] == pytest.approx(200 / 3)
    assert summary["bias_ms"] == pytest.approx(50)


def test_metrics_need_one_to_one_syllables():
    with pytest.raises(ValueError):
        timing_errors([{"start": 1.0}], [1.0, 2.0])
    assert isinstance(timing_errors([], []), np.ndarray)


def test_reference_keeps_pitch_and_note_kind(syllables):
    assert [(s.pitch, s.sung) for s in syllables] == [
        (60, True), (60, True), (60, True), (60, True), (0, False), (0, False), (64, True),
    ]


def test_pitch_summary_ignores_octaves_and_rap():
    from eval.metrics import pitch_summary
    summary = pitch_summary(midi=[72, 61, 60, 50], unvoiced=[False, False, True, False],
                            reference=[0, 0, 0, 5], sung=[True, True, True, False])
    assert summary["compared"] == 3
    assert summary["pitch_class_pct"] == pytest.approx(200 / 3)   # 72 and 60 are both C
    assert summary["within_1_pct"] == pytest.approx(100)
    assert summary["unvoiced_pct"] == pytest.approx(100 / 3)
