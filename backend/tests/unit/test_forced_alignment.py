"""Forced alignment of user lyrics with synthetic emissions (no model needed)."""

import numpy as np
import pytest

from services.forced_alignment import (
    BLANK,
    FRAME_SEC,
    NUM_CLASSES,
    VOCAB,
    AlignmentError,
    UnsupportedText,
    WordTiming,
    align_lyrics_to_emissions,
    forced_align,
    pull_in_edges,
    romanize,
    snap_to_voice,
)


def emissions(*spans, sure=0.9):
    """Log-probabilities from (text or None, frames) spans, shaped like real CTC output.

    A text span gives each letter an equal slot whose first frame "spikes" on the letter and whose
    other frames are blank, as CTC models do; None is silence (blank).
    """
    rows = []
    for text, frames in spans:
        labels = [BLANK] * frames
        if text is not None:
            for i, letter in enumerate(text):
                labels[i * frames // len(text)] = VOCAB[letter]
        for label in labels:
            row = np.full(NUM_CLASSES, (1 - sure) / (NUM_CLASSES - 1))
            row[label] = sure
            rows.append(np.log(row))
    return np.array(rows, dtype=np.float32)


def starts(results):
    return [round(r["start"], 2) for r in results]


class TestRomanize:
    @pytest.mark.parametrize("text, expected", [
        ("Beau", "beau"),
        ("don’t", "don't"),
        ("Hello,", "hello"),
        ("Mädchen", "madchen"),
        ("Straße", "strasse"),
        ("café", "cafe"),
        ("123", ""),
        ("&", ""),
    ])
    def test_letters(self, text, expected):
        assert romanize(text) == expected

    def test_other_scripts_are_rejected_for_now(self):
        with pytest.raises(UnsupportedText):
            romanize("Привет")


class TestForcedAlign:
    def test_follows_the_likely_letters(self):
        log_probs = np.log(np.array([
            [0.1, 0.8, 0.1], [0.1, 0.8, 0.1], [0.8, 0.1, 0.1], [0.1, 0.1, 0.8], [0.1, 0.1, 0.8],
        ], dtype=np.float32))
        # columns: blank, a, b → targets use column ids 1 and 2
        path = forced_align(log_probs, [1, 2])
        assert path.tolist() == [1, 1, 2, 3, 3]  # a a blank b b

    def test_repeated_letters_need_a_blank_between(self):
        log_probs = np.log(np.full((3, 2), [0.1, 0.9], dtype=np.float32))
        assert forced_align(log_probs, [1, 1]).tolist() == [1, 2, 3]
        with pytest.raises(AlignmentError):
            forced_align(log_probs[:2], [1, 1])

    def test_long_texts_with_hundreds_of_states(self):
        """Real songs have thousands of states; the backtrack must not overflow its int8 steps."""
        words = " ".join(["la"] * 100)
        log_probs = emissions((None, 5), *[span for _ in range(100) for span in (("la", 4), (None, 2))])
        results = align_lyrics_to_emissions(words, log_probs)
        assert len(results) == 100
        assert starts(results)[:3] == [0.1, 0.22, 0.34]

    def test_no_text_is_an_error(self):
        with pytest.raises(AlignmentError):
            forced_align(np.zeros((5, 3), dtype=np.float32), [])


class TestAlignLyrics:
    def test_words_land_where_they_are_sung(self):
        log_probs = emissions((None, 50), ("la", 10), (None, 15), ("da", 10), (None, 20))
        results = align_lyrics_to_emissions("la da", log_probs)
        assert starts(results) == [1.0, 1.5]

    def test_sound_that_is_not_in_the_lyrics_does_not_move_words(self):
        """An ad-lib between the words ("hey") is absorbed, "da" still lands on its own sound."""
        log_probs = emissions((None, 50), ("la", 10), (None, 5), ("hey", 9), (None, 6), ("da", 10), (None, 20))
        results = align_lyrics_to_emissions("la da", log_probs)
        assert starts(results) == [1.0, 1.6]

    def test_syllables_split_at_their_first_letter(self):
        log_probs = emissions((None, 10), ("sto", 15), (None, 5), ("ny", 10), (None, 10))
        results = align_lyrics_to_emissions("sto-ny", log_probs)
        assert [r["syllable"] for r in results] == ["sto", "ny "]
        assert starts(results) == [0.2, 0.6]
        assert results[0]["end"] == pytest.approx(results[1]["start"])

    def test_offset_shifts_all_times(self):
        log_probs = emissions((None, 10), ("la", 10), (None, 10))
        assert starts(align_lyrics_to_emissions("la", log_probs, offset=30.0)) == [30.2]

    def test_output_has_the_pipeline_format(self):
        log_probs = emissions((None, 10), ("yo", 10), (None, 10), ("la", 10), (None, 10))
        results = align_lyrics_to_emissions("[RAP]\nyo\n[/RAP]\nla", log_probs)
        assert {"syllable", "start", "end", "confidence", "is_rap", "method", "line_index"} <= results[0].keys()
        assert [(r["is_rap"], r["line_index"], r["method"]) for r in results] == [(True, 0, "ctc"), (False, 1, "ctc")]

    def test_clear_letters_give_high_confidence(self):
        log_probs = emissions((None, 10), ("la", 10), (None, 10))
        (result,) = align_lyrics_to_emissions("la", log_probs)
        assert result["confidence"] > 0.8
        assert result["low_confidence"] is False

    def test_words_without_letters_sit_after_the_previous_word(self):
        log_probs = emissions((None, 10), ("rock", 10), (None, 10), ("roll", 10), (None, 10))
        results = align_lyrics_to_emissions("rock & roll", log_probs)
        assert [r["syllable"] for r in results] == ["rock ", "& ", "roll "]
        assert results[0]["end"] <= results[1]["start"] < results[2]["start"]

    def test_notes_are_ordered_and_do_not_overlap(self):
        log_probs = emissions((None, 5), ("abc", 6), ("def", 6), (None, 5))
        results = align_lyrics_to_emissions("abc def", log_probs)
        for prev, cur in zip(results, results[1:]):
            assert prev["start"] <= prev["end"] <= cur["start"] < cur["end"]

    def test_lyrics_longer_than_the_audio_fail_loudly(self):
        with pytest.raises(AlignmentError):
            align_lyrics_to_emissions("a very long line of lyrics", emissions(("la", 4)))

    def test_snap_to_voice_moves_starts_to_the_first_voiced_frame(self, make_pitch_data):
        log_probs = emissions((None, 50), ("sun", 20), (None, 30))
        pitch = make_pitch_data([(1.1, 1.4, 60)], duration=2.0)
        (result,) = align_lyrics_to_emissions("sun", log_probs, pitch_data=pitch)
        assert result["start"] == pytest.approx(1.1, abs=0.02)
        (unsnapped,) = align_lyrics_to_emissions("sun", log_probs, pitch_data=pitch, snap_voice=False)
        assert unsnapped["start"] == pytest.approx(1.0)


class TestCleanups:
    def test_far_first_word_is_pulled_next_to_the_line(self):
        words = [WordTiming(1.0, 1.2, 0.0, [(1.0, 1.2)]), WordTiming(5.0, 5.3, 0.0), WordTiming(5.4, 5.8, 0.0)]
        pull_in_edges(words)
        assert (words[0].start, words[0].end, words[0].letters) == (4.7, 5.0, [])

    def test_far_last_word_is_pulled_next_to_the_line(self):
        words = [WordTiming(1.0, 1.2, 0.0), WordTiming(1.3, 1.5, 0.0), WordTiming(6.0, 6.4, 0.0)]
        pull_in_edges(words)
        # starts right after the line; a last word may be held, but at most 2 s
        assert (words[2].start, words[2].end) == (1.5, 3.5)

    def test_close_words_are_left_alone(self):
        words = [WordTiming(1.0, 1.2, 0.0), WordTiming(1.5, 1.8, 0.0)]
        pull_in_edges(words)
        assert (words[0].start, words[1].start) == (1.0, 1.5)

    def test_snap_to_voice_ignores_voicing_outside_the_word(self):
        word = WordTiming(1.0, 1.5, 0.0)
        snap_to_voice(word, np.array([0.5, 2.0]))
        assert word.start == 1.0


def test_frame_rate_is_50_per_second():
    assert FRAME_SEC == 0.02
