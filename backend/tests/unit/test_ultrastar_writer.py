"""UltraStar .txt generation: headers, beat conversion, line breaks, note types."""

import pytest

from services.ultrastar import (_fmt_bpm, generate_lyrics_only_txt, generate_ultrastar, language_header,
                                parse_language_header)


def syl(text, start, end, line=0, rap=False):
    return {"syllable": text, "start": start, "end": end, "line_index": line, "is_rap": rap, "confidence": 0.9}


def note_lines(content):
    return [ln for ln in content.split("\n") if ln and not ln.startswith("#")]


@pytest.mark.parametrize("bpm, expected", [(612.0, "612"), (612.35, "612.35"), (240.5, "240.5"), (300, "300")])
def test_bpm_is_written_without_trailing_zeros(bpm, expected):
    assert _fmt_bpm(bpm) == expected


def test_header_uses_full_language_name(make_pitch_data):
    content = generate_ultrastar([syl("la ", 1.0, 1.5)], make_pitch_data([]), 240, 1000,
                                 artist="A", title="T", language="de", mp3_filename="A - T.mp3")
    assert content.split("\n")[:6] == [
        "#ARTIST:A", "#TITLE:T", "#BPM:240", "#GAP:1000", "#LANGUAGE:German", "#MP3:A - T.mp3",
    ]


def test_unknown_language_code_is_kept_as_given(make_pitch_data):
    content = generate_ultrastar([syl("la ", 1.0, 1.5)], make_pitch_data([]), 240, 1000, language="Klingon")
    assert "#LANGUAGE:Klingon" in content


def test_two_languages_are_written_as_english_names(make_pitch_data):
    content = generate_ultrastar([syl("la ", 1.0, 1.5)], make_pitch_data([]), 240, 1000, language="en", language2="de")
    assert "#LANGUAGE:English, German" in content
    assert "#LANGUAGE:French, Spanish" in generate_lyrics_only_txt("A", "T", language="fr", language2="es")


@pytest.mark.parametrize("language, language2, expected", [
    ("en", None, "English"), ("en", "de", "English, German"), ("en", "en", "English"), ("", None, "English"),
    ("de", "", "German"), ("pt", "Klingon", "Portuguese, Klingon"),
])
def test_language_header(language, language2, expected):
    assert language_header(language, language2) == expected


@pytest.mark.parametrize("value, expected", [
    ("English, German", ("en", "de")), ("German", ("de", None)), ("de", ("de", None)),
    ("english ,  french", ("en", "fr")), ("", (None, None)), ("Klingon", (None, None)),
])
def test_language_header_is_read_back_as_codes(value, expected):
    assert parse_language_header(value) == expected


def test_times_become_beats_relative_to_gap(make_pitch_data):
    # BPM 240 → one beat = 15 / 240 s = 62.5 ms
    content = generate_ultrastar(
        [syl("Hel", 1.0, 1.25), syl("lo ", 1.5, 2.0)], make_pitch_data([(1.0, 2.0, 64)]), 240, 1000
    )
    assert note_lines(content) == [": 0 4 64 Hel", ": 8 8 64 lo ", "E"]


def test_line_change_inserts_a_break_two_beats_after_the_last_note(make_pitch_data):
    content = generate_ultrastar(
        [syl("one ", 1.0, 1.5, line=0), syl("two ", 3.0, 3.5, line=1)], make_pitch_data([(0, 4, 60)]), 240, 1000
    )
    assert note_lines(content) == [": 0 8 60 one ", "- 10", ": 32 8 60 two ", "E"]


def test_overlapping_notes_are_pushed_apart(make_pitch_data):
    content = generate_ultrastar(
        [syl("a ", 1.0, 1.5), syl("b ", 1.25, 1.75)], make_pitch_data([(0, 2, 60)]), 240, 1000
    )
    first, second, _ = note_lines(content)
    _, start1, dur1, *_ = first.split(" ")
    _, start2, *_ = second.split(" ")
    assert int(start2) > int(start1) + int(dur1) - 1


def test_rap_syllables_are_written_as_R_with_pitch_zero(make_pitch_data):
    content = generate_ultrastar([syl("yo ", 1.0, 1.5, rap=True)], make_pitch_data([(0, 2, 70)]), 240, 1000)
    assert note_lines(content)[0] == "R 0 8 0 yo "


def test_unvoiced_syllable_falls_back_to_c4(make_pitch_data):
    content = generate_ultrastar([syl("ah ", 1.0, 1.5)], make_pitch_data([]), 240, 1000)
    assert note_lines(content)[0] == ": 0 8 60 ah "


def test_pitch_is_the_median_inside_the_syllable(make_pitch_data):
    pitch = make_pitch_data([(1.0, 1.1, 62), (1.1, 1.5, 65)])
    content = generate_ultrastar([syl("la ", 1.0, 1.5)], pitch, 240, 1000)
    assert note_lines(content)[0] == ": 0 8 65 la "


def test_non_breaking_spaces_are_replaced(make_pitch_data):
    content = generate_ultrastar([syl("la ", 1.0, 1.5)], make_pitch_data([]), 240, 1000, title="A B")
    assert " " not in content


def test_lyrics_only_file_has_headers_and_end_marker_only():
    content = generate_lyrics_only_txt(artist="A", title="T", bpm=300, gap_ms=0, language="en")
    assert content.endswith("#MP3:song.mp3\nE")
    assert "#LANGUAGE:English" in content


def test_unvoiced_syllable_takes_the_previous_pitch(make_pitch_data):
    pitch = make_pitch_data([(1.0, 1.5, 64)])
    content = generate_ultrastar([syl("la ", 1.0, 1.5), syl("ah ", 2.0, 2.5)], pitch, 240, 1000)
    assert note_lines(content)[:2] == [": 0 8 64 la ", ": 16 8 64 ah "]


def test_unvoiced_first_syllables_take_the_next_pitch(make_pitch_data):
    pitch = make_pitch_data([(2.0, 2.5, 67)])
    content = generate_ultrastar([syl("ah ", 1.0, 1.5), syl("la ", 2.0, 2.5)], pitch, 240, 1000)
    assert [ln.split(" ")[3] for ln in note_lines(content)[:2]] == ["67", "67"]
