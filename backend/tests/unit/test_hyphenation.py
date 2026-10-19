"""Automatic hyphenation of lyrics (pyphen + custom overrides)."""

import pytest

from services.hyphenation import hyphenate_lyrics


def hyphenate(text, language="en"):
    return hyphenate_lyrics(text, language)["hyphenated"]


@pytest.mark.parametrize("word, expected", [
    ("beautiful", "beau-ti-ful"),
    ("everywhere", "ev-er-y-where"),
    ("morning", "morn-ing"),
    ("stony", "sto-ny"),
    ("together", "to-geth-er"),
    ("because", "be-cause"),
    ("fire", "fire"),
    ("don't", "don't"),
    ("you're", "you're"),
])
def test_english_words(word, expected):
    assert hyphenate(word) == expected


def test_german_words_use_german_rules():
    assert hyphenate("singen", "de") == "sin-gen"


def test_punctuation_stays_outside_the_syllables():
    assert hyphenate("Hello, world!") == "Hel-lo, world!"


def test_capitalisation_is_kept():
    assert hyphenate("Beautiful").startswith("Beau")


def test_lines_that_already_have_hyphens_are_left_alone():
    result = hyphenate_lyrics("Wun-der-bar\nsingen", "de")
    assert result["hyphenated"] == "Wun-der-bar\nsin-gen"
    assert [line["syllable_count"] for line in result["lines"]] == [3, 2]


def test_marker_lines_and_empty_lines_are_kept_and_not_counted():
    result = hyphenate_lyrics("[RAP]\n\nyo", "en")
    assert result["hyphenated"] == "[RAP]\n\nyo"
    assert result["total_syllables"] == 1


def test_unknown_language_falls_back_to_english():
    assert hyphenate("beautiful", "xx") == "beau-ti-ful"
