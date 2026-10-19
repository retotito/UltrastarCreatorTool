"""Engine choice and fallbacks of align_syllables (engines replaced by fakes)."""

import pytest

import services.alignment as energy
import services.alignment_whisper as legacy
import services.forced_alignment as ctc
from services.syllable_alignment import align_syllables, configured_engine

TIMING = [{"syllable": "la ", "start": 1.0, "end": 1.5}]
WORDS = [{"word": "la", "start": 1.0, "end": 1.5}]


@pytest.fixture
def engines(monkeypatch):
    calls = []

    def fake(name, result=TIMING):
        def run(*args, **kwargs):
            calls.append(name)
            if isinstance(result, Exception):
                raise result
            return result
        return run

    def install(ctc_result=TIMING, legacy_result=TIMING):
        monkeypatch.setattr(ctc, "align_lyrics", fake("ctc", ctc_result))
        monkeypatch.setattr(legacy, "align_whisper", fake("legacy", legacy_result))
        monkeypatch.setattr(energy, "align_lyrics_to_audio", fake("energy"))
        return calls
    return install


def test_ctc_is_used_by_default(engines):
    calls = engines()
    assert align_syllables("v.wav", "la", whisper_words=WORDS) == (TIMING, "ctc")
    assert calls == ["ctc"]


def test_ctc_failure_falls_back_to_whisper_matching(engines):
    calls = engines(ctc_result=ctc.AlignmentError("too long"))
    assert align_syllables("v.wav", "la", whisper_words=WORDS)[1] == "legacy"
    assert calls == ["ctc", "legacy"]


def test_whisper_is_only_transcribed_when_the_fallback_needs_it(engines):
    calls = engines()
    transcribed = []
    align_syllables("v.wav", "la", get_whisper=lambda: transcribed.append(1) or (WORDS, []))
    assert transcribed == []

    calls = engines(ctc_result=ctc.AlignmentError("x"))
    assert align_syllables("v.wav", "la", get_whisper=lambda: (WORDS, []))[1] == "legacy"


def test_energy_is_the_last_resort(engines):
    calls = engines(ctc_result=RuntimeError("no model"))
    assert align_syllables("v.wav", "la", whisper_words=[])[1] == "energy"
    assert calls == ["ctc", "energy"]


def test_legacy_engine_skips_forced_alignment(engines):
    calls = engines()
    assert align_syllables("v.wav", "la", whisper_words=WORDS, engine="legacy")[1] == "legacy"
    assert calls == ["legacy"]


@pytest.mark.parametrize("value, expected", [(None, "ctc"), ("legacy", "legacy"), (" CTC ", "ctc"), ("bogus", "ctc")])
def test_engine_from_environment(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("ULTRASTAR_ALIGNMENT_ENGINE", raising=False)
    else:
        monkeypatch.setenv("ULTRASTAR_ALIGNMENT_ENGINE", value)
    assert configured_engine() == expected
