"""Duet charts: P1/P2 tracks read into one list with a singer per note, and written back as tracks."""

from services import duet
from services.reference_comparison import parse_ultrastar_file

CHART = """#TITLE:Song
#BPM:300
#GAP:1000
#P1:Anna
#P2:Ben
P1
: 0 4 10 Hel
: 4 4 12 lo
- 10
: 12 4 10 to
: 16 4 10 gether
P2
: 12 4 10 to
: 16 4 5 gether
- 22
: 24 4 7 Hi
E
"""


def editor_notes():
    """What the editor holds for CHART: shared notes once, as 'both'."""
    return [
        {"startBeat": 0, "duration": 4, "pitch": 10, "syllable": "Hel", "singer": 1},
        {"startBeat": 4, "duration": 4, "pitch": 12, "syllable": "lo", "singer": 1},
        {"type": "break", "startBeat": 10, "singer": 1},
        {"startBeat": 12, "duration": 4, "pitch": 10, "syllable": "to", "singer": "both"},
        {"startBeat": 16, "duration": 4, "pitch": 10, "syllable": "gether", "singer": 1},
        {"startBeat": 16, "duration": 4, "pitch": 5, "syllable": "gether", "singer": 2},
        {"type": "break", "startBeat": 22, "singer": 2},
        {"startBeat": 24, "duration": 4, "pitch": 7, "syllable": "Hi", "singer": 2},
    ]


def test_track_markers():
    assert duet.track_marker("P1") == 1 and duet.track_marker("P 2") == 2 and duet.track_marker("P3") == "both"
    assert duet.track_marker(": 0 4 10 P1") is None and duet.track_marker("P4") is None
    assert duet.is_duet(CHART) and not duet.is_duet(": 0 4 10 la\nE")


def test_parser_tags_each_note_with_its_singer():
    parsed = parse_ultrastar_file(CHART)
    assert [n["singer"] for n in parsed["notes"]] == [1, 1, 1, 1, 2, 2, 2]
    assert [b["singer"] for b in parsed["breaks"]] == [1, 2]
    assert parsed["duet"] == {"p1": "Anna", "p2": "Ben"}
    assert parse_ultrastar_file(": 0 4 10 la\nE")["duet"] is None


def test_names_fall_back_to_old_headers_usdb_video_and_defaults():
    assert duet.singer_names({"DUETSINGERP1": "A", "DUETSINGERP2": "B"}) == {"p1": "A", "p2": "B"}
    assert duet.singer_names({"VIDEO": "v=x,p1=Whitney Houston,p2=Mariah Carey"}) == \
        {"p1": "Whitney Houston", "p2": "Mariah Carey"}
    assert duet.singer_names({"P1": "Anna"}) == {"p1": "Anna", "p2": "Singer 2"}


def test_identical_notes_in_both_tracks_become_one_both_note():
    tracks = [
        {"startBeat": 12, "duration": 4, "pitch": 10, "syllable": "to", "singer": 1},
        {"startBeat": 16, "duration": 4, "pitch": 10, "syllable": "gether", "singer": 1},
        {"startBeat": 12, "duration": 4, "pitch": 10, "syllable": "to", "singer": 2},
        {"startBeat": 16, "duration": 4, "pitch": 5, "syllable": "gether", "singer": 2},  # other pitch: stays apart
    ]
    merged = duet.merge_shared(tracks)
    assert [(n["startBeat"], n["singer"]) for n in merged] == [(12, "both"), (16, 1), (16, 2)]
    assert tracks[0]["singer"] == 1  # the input is not changed


def test_written_as_two_tracks_with_both_notes_in_each():
    assert duet.body_lines(editor_notes()) == [
        "P1", ": 0 4 10 Hel", ": 4 4 12 lo", "- 10", ": 12 4 10 to", ": 16 4 10 gether",
        "P2", ": 12 4 10 to", ": 16 4 5 gether", "- 22", ": 24 4 7 Hi",
    ]


def test_a_break_without_notes_of_that_singer_on_both_sides_is_left_out():
    notes = [
        {"startBeat": 0, "duration": 4, "pitch": 1, "syllable": "a", "singer": 1},
        {"type": "break", "startBeat": 6, "singer": "both"},
        {"startBeat": 8, "duration": 4, "pitch": 1, "syllable": "b", "singer": 2},
        {"type": "break", "startBeat": 14, "singer": "both"},
        {"startBeat": 16, "duration": 4, "pitch": 1, "syllable": "c", "singer": 1},
    ]
    assert duet.body_lines(notes) == ["P1", ": 0 4 1 a", "- 6", ": 16 4 1 c", "P2", ": 8 4 1 b"]


def test_a_note_without_singer_in_a_duet_is_kept_for_both():
    notes = [{"startBeat": 0, "duration": 4, "pitch": 1, "syllable": "a", "singer": 1},
             {"startBeat": 8, "duration": 4, "pitch": 2, "syllable": "new"}]
    assert duet.body_lines(notes) == ["P1", ": 0 4 1 a", ": 8 4 2 new", "P2", ": 8 4 2 new"]


def test_solo_charts_are_written_as_before():
    notes = [{"startBeat": 0, "duration": 4, "pitch": 1, "syllable": "a", "isGolden": True},
             {"type": "break", "startBeat": 6},
             {"startBeat": 8, "duration": 2, "pitch": 3, "syllable": " b", "isRap": True}]
    assert duet.body_lines(notes) == ["* 0 4 1 a", "- 6", "R 8 2 3  b"]


def test_header_lines_for_new_and_old_games():
    assert duet.header_lines({"p1": "Anna", "p2": "Ben"}) == \
        ["#P1:Anna", "#P2:Ben", "#DUETSINGERP1:Anna", "#DUETSINGERP2:Ben"]
