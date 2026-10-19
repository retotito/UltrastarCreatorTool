"""Current WhisperX-based alignment: word matching and syllable splitting.

These are characterization tests. They pin down today's behaviour so that the forced-alignment work
(docs/plans/forced-alignment.md) can reuse the syllable split and replace the matching knowingly.
"""

import pytest

from services.alignment_whisper import (
    _build_char_lookup,
    _build_word_groups,
    _distribute_syllables,
    _match_words,
    align_whisper,
    parse_lyrics,
)


def groups_for(lyrics):
    return _build_word_groups([s for line in parse_lyrics(lyrics) for s in line])


def word(text, start, end):
    return {"word": text, "start": start, "end": end}


class TestWordGroups:
    def test_syllables_are_grouped_back_into_words(self):
        groups = groups_for("Beau-ti-ful day")
        assert [g["word"] for g in groups] == ["Beau-ti-ful", "day"]
        assert [len(g["syllables"]) for g in groups] == [3, 1]

    def test_clean_form_is_lowercase_without_hyphens_or_punctuation(self):
        groups = groups_for("Beau-ti-ful, DON'T")
        assert [g["clean"] for g in groups] == ["beautiful", "don't"]

    def test_curly_apostrophes_are_normalised_for_matching(self):
        assert groups_for("don’t")[0]["clean"] == "don't"


class TestMatchWords:
    def test_identical_sequences_match_one_to_one(self):
        groups = groups_for("the heart is")
        matches = _match_words(groups, [word("The", 1.0, 1.2), word("heart", 1.3, 1.6), word("is", 1.7, 1.8)])
        assert [m["whisper_idx"] for m in matches] == [0, 1, 2]
        assert matches[1]["start"] == 1.3

    def test_extra_whisper_words_are_skipped(self):
        groups = groups_for("the heart")
        matches = _match_words(groups, [word("the", 1.0, 1.2), word("uh", 1.25, 1.3), word("heart", 1.3, 1.6)])
        assert [m["whisper_idx"] for m in matches] == [0, 2]

    def test_lyric_words_whisper_did_not_hear_stay_unmatched(self):
        """The root cause of misplaced notes: these words get no timestamp from Whisper."""
        groups = groups_for("la da dee the heart")
        matches = _match_words(groups, [word("the", 5.0, 5.2), word("heart", 5.3, 5.6)])
        assert matches[:3] == [None, None, None]
        assert [m["whisper_idx"] for m in matches[3:]] == [0, 1]


class TestDistributeSyllables:
    def test_single_syllable_word_takes_the_whole_word_span(self):
        groups = groups_for("day")
        (result,) = _distribute_syllables(groups, [{"start": 2.0, "end": 2.5, "confidence": 0.9}])
        assert (result["start"], result["end"], result["split_method"]) == (2.0, 2.5, "single")

    def test_without_char_timestamps_syllables_split_by_letter_count(self):
        groups = groups_for("sto-ny")  # "sto" = 3 letters, "ny " = 2 letters after strip
        results = _distribute_syllables(groups, [{"start": 0.0, "end": 1.0, "confidence": 0.9}])
        assert [r["split_method"] for r in results] == ["proportional", "proportional"]
        assert results[0]["end"] == pytest.approx(0.6)
        assert results[1]["start"] == pytest.approx(0.6)
        assert results[1]["end"] == 1.0

    def test_char_timestamps_set_the_syllable_boundary(self):
        groups = groups_for("sto-ny")
        chars = [
            {"char": c, "start": s, "end": s + 0.05}
            for c, s in zip("stony", [0.00, 0.10, 0.20, 0.70, 0.80])
        ]
        results = _distribute_syllables(
            groups, [{"start": 0.0, "end": 1.0, "confidence": 0.9}], _build_char_lookup(chars)
        )
        assert [r["split_method"] for r in results] == ["char", "char"]
        # "ny" starts at its first letter; the gap after "sto" is closed by extending "sto"
        assert results[1]["start"] == pytest.approx(0.70)
        assert results[0]["end"] == pytest.approx(0.70)
        assert (results[0]["start"], results[1]["end"]) == (0.0, 1.0)

    def test_unmatched_words_produce_no_syllables(self):
        groups = groups_for("la day")
        results = _distribute_syllables(groups, [None, {"start": 1.0, "end": 1.4, "confidence": 0.9}])
        assert [r["syllable"] for r in results] == ["day "]


class TestAlignWhisper:
    def test_every_syllable_gets_a_timing_when_whisper_heard_every_word(self):
        lyrics = "the heart is a bloom\nshoots up through the sto-ny ground"
        heard = "the heart is a bloom shoots up through the stony ground".split()
        whisper_words = [word(w, 1.0 + i * 0.5, 1.4 + i * 0.5) for i, w in enumerate(heard)]
        results = align_whisper(lyrics, whisper_words)
        assert len(results) == 12
        assert [r["line_index"] for r in results] == [0] * 5 + [1] * 7
        assert all(r["end"] > r["start"] for r in results)
        assert [r["start"] for r in results] == sorted(r["start"] for r in results)

    def test_no_whisper_words_returns_nothing(self):
        assert align_whisper("la la", []) == []
