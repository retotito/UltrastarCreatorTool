"""Lyrics parsing: lines, syllables, word boundaries, rap markers."""

from services.alignment_whisper import parse_lyrics


def texts(lines):
    return [[s["text"] for s in line] for line in lines]


def test_hyphens_split_syllables_and_words_end_with_a_space():
    lines = parse_lyrics("Beau-ti-ful day")
    assert texts(lines) == [["Beau", "ti", "ful ", "day "]]


def test_word_start_flags_mark_the_first_syllable_of_each_word():
    (line,) = parse_lyrics("sto-ny ground")
    assert [s["is_word_start"] for s in line] == [True, False, True]
    assert [s["word"] for s in line] == ["sto-ny", "sto-ny", "ground"]


def test_empty_lines_are_ignored_and_line_indexes_stay_consecutive():
    lines = parse_lyrics("first line\n\n\nsecond line\n")
    assert texts(lines) == [["first ", "line "], ["second ", "line "]]
    assert [line[0]["line_index"] for line in lines] == [0, 1]


def test_rap_markers_flag_the_lines_between_them():
    lines = parse_lyrics("sung\n[RAP]\nspo-ken\n[/RAP]\nsung a-gain")
    assert [[s["is_rap"] for s in line] for line in lines] == [[False], [True, True], [False, False, False]]
    assert len(lines) == 3  # marker lines produce no syllables


def test_rap_markers_are_case_insensitive():
    lines = parse_lyrics("[rap]\nyo\n[/Rap]\nla")
    assert [line[0]["is_rap"] for line in lines] == [True, False]


def test_trailing_hyphen_does_not_create_an_empty_syllable():
    (line,) = parse_lyrics("oh- yeah")
    assert [s["text"] for s in line] == ["oh ", "yeah "]


def test_apostrophes_and_punctuation_stay_in_the_syllable_text():
    (line,) = parse_lyrics("don't stop, ba-by!")
    assert [s["text"] for s in line] == ["don't ", "stop, ", "ba", "by! "]
