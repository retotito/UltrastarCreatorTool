"""The .txt as the user downloads it (USDB conventions), see `format_for_download`."""

import pytest

from services.ultrastar import format_for_download

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


def test_mid_word_syllables_get_a_trailing_hyphen(downloaded):
    assert lines(downloaded)[7:10] == [": 0 4 60 Beau-", ": 4 4 60 ti-", ": 8 4 60 ful "]


def test_line_breaks_are_yass_style(downloaded):
    assert "- 14" in lines(downloaded)
    assert "- 14 16" not in downloaded


def test_apostrophes_in_notes_become_typographic(downloaded):
    assert ": 16 4 62 don’t " in lines(downloaded)


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


def test_melisma_notes_get_no_hyphen_before_their_continuation():
    content = format_for_download(": 0 4 49 gas\n: 4 4 47 ~\n: 8 4 45 ~ \n: 12 2 50 beau\n: 14 2 52 ~\n: 16 2 50 ti\n: 18 2 50 ful \nE")
    assert lines(content)[:7] == [
        ": 0 4 49 gas", ": 4 4 47 ~", ": 8 4 45 ~ ",          # one word: no hyphens
        ": 12 2 50 beau", ": 14 2 52 ~-", ": 16 2 50 ti-", ": 18 2 50 ful ",  # mid-word: hyphen after the ~
    ]


def test_freestyle_and_rap_notes_get_hyphens_too():
    content = format_for_download("F 0 4 0 free\nR 4 4 0 rap\nE")
    assert lines(content)[:2] == ["F 0 4 0 free-", "R 4 4 0 rap-"]


@pytest.mark.xfail(reason="Known gap: golden rap notes (G) are not matched by the hyphen rule", strict=True)
def test_golden_rap_notes_get_hyphens():
    content = format_for_download("G 0 4 0 gold\nE")
    assert lines(content)[0] == "G 0 4 0 gold-"
