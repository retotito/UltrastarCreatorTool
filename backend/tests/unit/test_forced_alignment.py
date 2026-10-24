"""Forced alignment of user lyrics with synthetic emissions (no model needed)."""

import numpy as np
import pytest

import services.forced_alignment as fa

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
    sounding_frames,
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
    @pytest.mark.parametrize("text, language, expected", [
        ("Beau", "en", "beau"),
        ("don\u2019t", "en", "don't"),
        ("Hello,", "en", "hello"),
        ("Mädchen", "de", "maedchen"),   # as uroman romanized MMS's training text
        ("café", "fr", "cafe"),
        ("123", "en", "onehundredandtwentythree"),
        ("&", "en", "and"),
        ("Привет", "ru", "privet"),
        ("我爱你", "zh", "woaini"),
        ("ありがとう", "ja", "arigatou"),
    ])
    def test_letters(self, text, language, expected):
        assert romanize(text, language) == expected

    def test_without_uroman_accents_are_removed_and_other_scripts_rejected(self, monkeypatch):
        monkeypatch.setitem(fa._uroman_cache, "instance", None)
        assert romanize("Mädchen", "de") == "madchen"
        with pytest.raises(UnsupportedText):
            romanize("Привет", "ru")

    def test_every_app_language_has_an_iso_639_3_code(self):
        import re
        from pathlib import Path
        source = Path(__file__).parents[3] / "frontend" / "src" / "lib" / "languages.ts"
        codes = re.findall(r'code: "([a-z]+)"', source.read_text())
        assert codes and not [c for c in codes if c not in fa.ISO_639_3]


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

    def test_an_ampersand_is_aligned_as_the_sung_and(self):
        log_probs = emissions((None, 10), ("rock", 10), ("and", 10), ("roll", 10), (None, 10))
        results = align_lyrics_to_emissions("rock & roll", log_probs)
        assert [r["syllable"] for r in results] == ["rock ", "& ", "roll "]
        assert results[0]["end"] <= results[1]["start"] < results[2]["start"]
        assert results[1]["confidence"] > 0.5

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


class TestSilenceGate:
    def test_frames_far_below_the_loud_parts_are_silent(self):
        loudness = np.array([-20.0] * 10 + [-70.0] * 20 + [-22.0] * 10)
        sounding = sounding_frames(loudness)
        assert sounding[:13].all() and sounding[-13:].all()  # widened by 3 frames
        assert not sounding[13:27].any()

    def test_quiet_but_sung_frames_stay_sounding(self):
        assert sounding_frames(np.array([-20.0] * 10 + [-45.0] * 10)).all()

    def test_no_syllable_is_placed_in_silence(self):
        """A letter-like sound in the silent stretch (e.g. leftover band bleed) can't take the word."""
        # the first "la" is the clearer one, so without the gate it wins
        log_probs = np.concatenate([emissions((None, 10), ("la", 10), sure=0.97),
                                    emissions((None, 40), ("la", 10), (None, 10), sure=0.8)])
        loudness = np.full(len(log_probs), -20.0)
        loudness[5:25] = -80.0  # the first "la" is not in the vocals
        (ungated,) = align_lyrics_to_emissions("la", log_probs)
        (gated,) = align_lyrics_to_emissions("la", log_probs, loudness_db=loudness)
        assert ungated["start"] == pytest.approx(0.2)
        assert gated["start"] == pytest.approx(1.2)


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


class TestNumbersAndSigns:
    def test_numbers_are_spelled_in_the_songs_language(self):
        from services.forced_alignment import romanize
        assert romanize("12", "en") == "twelve"
        assert romanize("12", "it") == "dodici"
        assert romanize("1977", "en") == "nineteenseventyseven"     # read as a year
        assert romanize("12", "xx") == "twelve"                      # unknown language: English

    def test_signs_without_letters_get_no_note_of_their_own(self):
        from services.alignment_whisper import parse_lyrics
        lines = parse_lyrics("Na-na na, oh! — 12 roses …\n… and then\nbeau-ti-ful - world\n— …")
        assert [[s["text"] for s in line] for line in lines] == [
            ["Na", "na ", "na, ", "oh! — ", "12 ", "roses … "], ["… and ", "then "], ["beau", "ti", "ful ", "world "]]
