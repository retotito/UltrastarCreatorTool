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


def test_words_the_user_split_are_kept_and_the_rest_of_the_line_is_hyphenated():
    result = hyphenate_lyrics("Wun-der-bar singen\nOh-oh-oh, beautiful day", "de")
    assert result["hyphenated"].split("\n")[0] == "Wun-der-bar sin-gen"
    assert result["lines"][0]["syllable_count"] == 5
    assert hyphenate("Oh-oh-oh, beautiful day") == "Oh-oh-oh, beau-ti-ful day"


def test_hyphenating_twice_changes_nothing():
    once = hyphenate("Shoots up through the stony ground, beautiful day")
    assert hyphenate(once) == once


def test_marker_lines_and_empty_lines_are_kept_and_not_counted():
    result = hyphenate_lyrics("[RAP]\n\nyo", "en")
    assert result["hyphenated"] == "[RAP]\n\nyo"
    assert result["total_syllables"] == 1


@pytest.mark.parametrize("language, text, expected", [
    ("ru", "Привет любовь", "При-вет лю-бовь"),   # pyphen dictionaries beyond the old 17 languages
    ("zh", "我爱你", "我-爱-你"),                   # one syllable per character
    ("ko", "안녕하세요", "안-녕-하-세-요"),
    ("ja", "きょう", "きょ-う"),                   # small kana stay with the character before
])
def test_more_languages(language, text, expected):
    assert hyphenate(text, language) == expected


@pytest.mark.parametrize("language, text, expected", [
    ("tr", "merhaba", "mer-ha-ba"),
    ("sw", "habari yako", "ha-ba-ri ya-ko"),
    ("fi", "rakkaus", "rak-kaus"),
])
def test_languages_without_a_dictionary_use_the_vowel_rule(language, text, expected):
    result = hyphenate_lyrics(text, language)
    assert result["hyphenated"] == expected
    assert result["method"].startswith("generic")


def test_scripts_without_written_vowels_are_left_whole():
    assert hyphenate("مرحبا", "ar") == "مرحبا"


def test_english_special_cases_only_apply_to_english():
    assert hyphenate("away", "en") == "a-way"
    assert hyphenate("away", "de") == "away"


@pytest.mark.parametrize("word, expected", [
    ("singing", "sing-ing"), ("pieces", "pie-ces"), ("bandages", "ban-da-ges"), ("unpredictable", "un-pre-dic-ta-ble"),
    ("maimed", "maimed"), ("times", "times"), ("wanted", "want-ed"), ("lovely", "love-ly"), ("someone", "some-one"),
    ("yesterday", "yes-ter-day"), ("toy", "toy"), ("little", "lit-tle"), ("dances", "dan-ces"), ("crying", "cry-ing"),
])
def test_english_words_split_into_sung_syllables(word, expected):
    # pyphen hyphenates for typesetting and leaves sung syllables together ("singing", "pieces")
    assert hyphenate_lyrics(word, "en")["hyphenated"] == expected


def test_a_two_language_song_is_split_line_by_line_with_each_languages_rules():
    from services.hyphenation import line_languages
    lyrics = "They're just human contradictions\nSono cose della vita\nVanno prese un po così\nSto pensando a te\nTake my hand and never let me go"
    assert line_languages(lyrics.split("\n"), "en", "it") == ["en", "it", "it", "it", "en"]
    result = hyphenate_lyrics(lyrics, "en", "it")["hyphenated"].split("\n")
    assert result[1] == "So-no co-se del-la vi-ta"           # English rules would leave "cose" whole
    assert result[2] == "Van-no pre-se un po co-sì"
    assert result[4] == "Take my hand and nev-er let me go"


def test_one_language_and_unclear_lines():
    from services.hyphenation import line_languages
    assert line_languages(["Sono cose della vita"], "en") == ["en"]          # no second language: no detection
    assert line_languages(["Sono cose della vita", "", "123"], "it", "en") == ["it", "it", "it"]  # nothing to judge: the line before
