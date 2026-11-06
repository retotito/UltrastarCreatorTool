"""The .txt as the user downloads it (USDB conventions), see `format_for_download`."""

import pytest

from services.ultrastar import clean_syllable, format_for_download, format_for_usdb, strip_added_hyphens, to_midi_pitches

STORED = "\n".join([
    "#ARTIST:A",
    "#TITLE:T",
    "#BPM:240",
    "#GAP:1000",
    "#MP3:A - T.m4a",
    "#VOCALS:A - T [Vocals].wav",
    "#INSTRUMENTAL:A - T [Instrumental].mp3",
    "#DOWNBEATOFFSET:3",
    "#TITLE:duplicate",
    ": 0 4 60 Beau",
    ": 4 4 60 ti",
    ": 8 4 60 ful ",
    "- 14 16",
    ": 16 4 62 don't ",
    "E",
])


@pytest.fixture
def downloaded():
    return format_for_download(STORED)


def lines(content):
    return content.split("\r\n")


def test_uses_crlf_line_endings_and_ends_with_one(downloaded):
    assert downloaded.endswith("E\r\n")
    assert "\n" not in downloaded.replace("\r\n", "")


def test_line_breaks_are_yass_style(downloaded):
    assert "- 14" in lines(downloaded)
    assert "- 14 16" not in downloaded


def test_audio_headers_point_to_mp3(downloaded):
    assert "#MP3:A - T.mp3" in lines(downloaded)
    assert "#VOCALS:A - T [Vocals].mp3" in lines(downloaded)


def test_unknown_and_duplicate_headers_are_dropped(downloaded):
    assert "#DOWNBEATOFFSET:3" not in downloaded
    assert [ln for ln in lines(downloaded) if ln.startswith("#TITLE")] == ["#TITLE:T"]


def test_vocals_and_instrumental_headers_can_be_left_out():
    content = format_for_download(STORED, include_vocals=False, include_instrumental=False)
    assert "#VOCALS" not in content
    assert "#INSTRUMENTAL" not in content


def test_apostrophes_in_headers_are_kept():
    content = format_for_download("#TITLE:Don't Stop\n: 0 1 60 a \nE")
    assert "#TITLE:Don't Stop" in content


def test_formatting_a_download_again_changes_nothing(downloaded):
    """A downloaded file imported and downloaded again must not get 'Beau--'."""
    assert format_for_download(downloaded.replace("\r\n", "\n")) == downloaded


def test_start_and_video_gap_are_kept():
    chart = "#ARTIST:A\n#TITLE:T\n#BPM:240\n#GAP:0\n#START:12.5\n#END:90000\n#VIDEOGAP:2.5\n#XYZ:1\n: 0 1 60 a\nE\n"
    out = format_for_download(chart)
    assert "#START:12.5" in out and "#END:90000" in out and "#VIDEOGAP:2.5" in out and "#XYZ" not in out


def test_the_video_header_can_be_left_out():
    chart = "#ARTIST:A\n#TITLE:T\n#BPM:240\n#GAP:0\n#VIDEO:A - T.mp4\n: 0 1 60 a\nE\n"
    assert "#VIDEO:A - T.mp4" in format_for_download(chart)
    assert "#VIDEO" not in format_for_download(chart, include_video=False)


def note_lines(content):
    return [ln for ln in lines(content) if ln[:1] in (":", "*", "R", "F", "G")]


def test_mid_word_syllables_have_no_ending_and_pitches_start_at_c4(downloaded):
    assert note_lines(downloaded)[:3] == [": 0 4 0 Beau", ": 4 4 0 ti", ": 8 4 0 ful "]


def test_apostrophes_in_notes_become_typographic(downloaded):
    assert ": 16 4 2 don’t " in lines(downloaded)


def test_headers_are_in_usdbs_order_and_trimmed():
    out = format_for_download("#TITLE:T\n#BPM:240\n#CREATOR: me \n#ARTIST:A\n#VIDEOGAP:0.0\n#GAP:0\n: 0 1 60 a \nE\n")
    assert lines(out)[:6] == ["#ARTIST:A", "#TITLE:T", "#CREATOR:me", "#BPM:240", "#GAP:0", "#VIDEOGAP:0"]


@pytest.mark.parametrize("text, expected", [
    ("gon\u00a0", "gon "),
    ("a\u200b\tb  c ", "a b c "),
    ("three-", "three-"),                 # the lyrics' own hyphen
    ("don’t~ ", "don’t~ "),
    ("می\u200cخواهم ", "می\u200cخواهم "),   # a joiner that is part of the spelling stays
])
def test_clean_syllable(text, expected):
    assert clean_syllable(text) == expected


def test_a_leading_space_moves_to_the_note_before():
    out = format_for_download("#TITLE:T\n: 0 1 60 out\n: 2 1 60  ~\nE\n")
    assert note_lines(out) == [": 0 1 0 out ", ": 2 1 0 ~"]


OLD_DOWNLOAD = "\n".join([f": {i} 1 60 syl-" for i in range(6)] + [": 9 1 60 end ", ": 10 1 60 ~-", "E"])


def test_hyphens_of_older_downloads_are_removed():
    assert strip_added_hyphens(OLD_DOWNLOAD).split("\n")[:2] == [": 0 1 60 syl", ": 1 1 60 syl"]
    assert ": 10 1 60 ~" in strip_added_hyphens(OLD_DOWNLOAD).split("\n")


def test_hyphens_of_a_download_edited_afterwards_are_removed_too():
    chart = "\n".join([f": {i} 1 60 syl-" for i in range(21)] + [f": {i} 1 60 mid" for i in range(30, 36)] + ["E"])
    assert "-" not in strip_added_hyphens(chart).replace("60 ", "")


def test_hyphens_in_the_lyrics_stay():
    chart = "\n".join([": 0 1 60 three-", ": 1 1 60 wheel ", ": 2 1 60 long-", ": 3 1 60 shot "]
                      + [f": {i} 1 60 mid" for i in range(4, 12)] + ["E"])
    assert strip_added_hyphens(chart) == chart


def test_a_tilde_never_keeps_a_hyphen():
    assert strip_added_hyphens(": 0 1 60 ~-\nE") == ": 0 1 60 ~\nE"


def test_all_note_types_are_formatted():
    out = format_for_download("#TITLE:T\n: 0 1 60 a\n* 1 1 62 b\nR 2 1 60 c\nF 3 1 60 d\nG 4 1 60 e \nE\n")
    assert note_lines(out) == [": 0 1 0 a", "* 1 1 2 b", "R 2 1 0 c", "F 3 1 0 d", "G 4 1 0 e "]


def test_an_exported_chart_is_read_back_at_the_same_pitch():
    midi, shifted = to_midi_pitches(format_for_download("#TITLE:T\n: 0 1 57 a \n: 1 1 69 b \nE\n").replace("\r\n", "\n"))
    assert shifted and ": 0 1 57 a " in midi and ": 1 1 69 b " in midi


CHART = "\n".join(["#ARTIST:A", "#TITLE:T", "#MP3:A - T.m4a", "#VOCALS:A - T [Vocals].wav", "#BPM:240", "#GAP:0",
                   "#VIDEO:A - T.mp4", "#VIDEOGAP:1.5", "#YOUTUBE:https://youtu.be/dQw4w9WgXcQ", ": 0 1 60 a ", "E"])


def test_the_usdb_file_has_the_youtube_id_instead_of_a_file_name():
    heads = [ln for ln in lines(format_for_usdb(CHART, "dQw4w9WgXcQ")) if ln.startswith("#")]
    assert "#VIDEO:v=dQw4w9WgXcQ" in heads and "#VIDEOGAP:1.5" in heads
    assert not [h for h in heads if h.startswith(("#YOUTUBE", "#VOCALS")) or "mp4" in h]


def test_the_usdb_file_without_a_link_has_no_video_headers():
    assert "#VIDEO" not in format_for_usdb(CHART, None)


def test_the_usdb_file_of_a_duet_has_its_singers_in_the_tags():
    duet = "\n".join(["#ARTIST:A", "#TITLE:T", "#BPM:240", "#GAP:0", "#P1:Ann, Jr", "#P2:Ben",
                      "P1", ": 0 1 60 a ", "P2", ": 1 1 62 b ", "E"])
    out = format_for_usdb(duet, "dQw4w9WgXcQ")
    assert "#VIDEO:v=dQw4w9WgXcQ,p1=Ann%2C Jr,p2=Ben" in lines(out) and "#TITLE:T [DUET]" in lines(out)
    assert "#P1:" not in out and "P1" in lines(out) and "P2" in lines(out)
    assert format_for_usdb(out.replace("\r\n", "\n"), "dQw4w9WgXcQ").count("[DUET]") == 1


@pytest.mark.parametrize("ending", ["\r\r\n", "\n\n", "\r\n\r\n", "\r"])
def test_blank_and_doubled_lines_are_gone(ending):
    stored = ending.join(["#ARTIST:A", "#TITLE:T", "#BPM:240", "#GAP:0", ": 0 1 60 a ", "- 3", ": 4 1 62 b", "E", ""])
    assert format_for_download(stored) == "#ARTIST:A\r\n#TITLE:T\r\n#BPM:240\r\n#GAP:0\r\n: 0 1 0 a \r\n- 3\r\n: 4 1 2 b\r\nE\r\n"
