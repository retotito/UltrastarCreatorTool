"""Shared fixtures for backend tests.

The default test run must not need torch, model downloads or audio files:
tests that do are marked `slow` or `eval` and skipped unless selected with `-m`.
"""

import numpy as np
import pytest


@pytest.fixture
def make_pitch_data():
    """Build a pitch track in the format of `detect_pitches()` from (start, end, midi) spans.

    Frames every 10 ms up to `duration`; frames outside every span are unvoiced.
    """
    def _make(spans, duration=10.0, hop=0.01, confidence=0.9):
        times = np.arange(0.0, duration, hop)
        midi = np.zeros_like(times, dtype=int)
        for start, end, note in spans:
            midi[(times >= start) & (times <= end)] = note
        frequencies = np.where(midi > 0, 440.0 * 2 ** ((midi - 69) / 12), 0.0)
        return {
            "times": times,
            "frequencies": frequencies,
            "confidences": np.full_like(times, confidence),
            "midi_notes": midi,
            "sample_rate": 22050,
        }
    return _make


def pytest_collection_modifyitems(config, items):
    """Skip `slow` and `eval` tests unless they were selected explicitly with -m."""
    selected = config.getoption("-m") or ""
    for marker in ("slow", "eval"):
        if marker in selected:
            continue
        skip = pytest.mark.skip(reason=f"{marker} test: run with -m {marker}")
        for item in items:
            if marker in item.keywords:
                item.add_marker(skip)
