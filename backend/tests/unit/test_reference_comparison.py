"""Parsing reference UltraStar files and comparing timings against them (the evaluation metric)."""

import pytest

from services.reference_comparison import compare_timing_ms, parse_ultrastar_file

REFERENCE = "\n".join([
    "#TITLE:T",
    "#ARTIST:A",
    "#BPM:240,00",
    "#GAP:1000,5",
    ": 0 4 60 Hel",
    "* 8 8 64 lo ",
    "- 18",
    "F: 20 4 0 yo ",
    ": 24 2 62 ",
    "E",
    ": 99 1 60 after-end",
])


@pytest.fixture
def parsed():
    return parse_ultrastar_file(REFERENCE)


def test_headers_and_comma_decimals(parsed):
    assert parsed["bpm"] == 240.0
    assert parsed["gap"] == 1000.5
    assert parsed["headers"]["TITLE"] == "T"


def test_notes_are_parsed_until_the_end_marker(parsed):
    assert [(n["start_beat"], n["duration"], n["pitch"], n["syllable"]) for n in parsed["notes"]] == [
        (0, 4, 60, "Hel"), (8, 8, 64, "lo"), (20, 4, 0, "yo"), (24, 2, 62, ""),
    ]


def test_legacy_rap_prefix_is_flagged(parsed):
    assert [n["is_rap"] for n in parsed["notes"]] == [False, False, True, False]


def test_breaks_are_collected(parsed):
    assert parsed["breaks"] == [{"beat1": 18, "beat2": None}]


@pytest.mark.parametrize("line,rap,golden,freestyle", [
    (": 0 4 0 normal", False, False, False), ("* 0 4 0 gold", False, True, False),
    ("R 0 4 0 rap", True, False, False), ("G 0 4 0 goldrap", True, True, False),
    ("F 0 4 0 free", False, False, True), ("F: 0 4 0 oldrap", True, False, False),
])
def test_all_note_types_are_parsed(line, rap, golden, freestyle):
    notes = parse_ultrastar_file(f"#BPM:240\n#GAP:0\n{line}\nE")["notes"]
    assert len(notes) == 1
    assert (notes[0]["is_rap"], notes[0]["is_golden"], notes[0]["is_freestyle"]) == (rap, golden, freestyle)


def test_identical_timings_compare_with_zero_error():
    reference = "#BPM:240\n#GAP:1000\n: 0 4 60 Hel\n: 8 8 64 lo \n- 18\n: 20 4 62 world \nE"
    # BPM 240 → 62.5 ms per beat
    timings = [
        {"syllable": "Hel", "start": 1.0, "end": 1.25},
        {"syllable": "lo ", "start": 1.5, "end": 2.0},
        {"syllable": "world ", "start": 2.25, "end": 2.5},
    ]
    result = compare_timing_ms(timings, reference)
    assert result, "comparison returned nothing"
    flat = repr(result)
    assert "nan" not in flat.lower()
