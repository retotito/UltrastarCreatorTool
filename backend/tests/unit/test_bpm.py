"""The chart BPM: the detected UltraStar BPM brought near 600 by doubling or halving."""

import pytest


@pytest.mark.parametrize("bpm, expected", [
    (356, 712),      # Ben Harper (89 musical): doubled, a beat 21 ms instead of 42 ms
    (494, 494),      # Robert Post (123.5): already near 600
    (300, 600), (240, 480), (430, 430), (800, 800), (1040, 520), (180, 720),
])
def test_chart_bpm_lands_near_600_by_doubling_or_halving(bpm, expected):
    from services.bpm_detection import chart_bpm
    assert chart_bpm(bpm) == expected


def test_chart_bpm_keeps_a_missing_bpm():
    from services.bpm_detection import chart_bpm
    assert chart_bpm(0) == 0
