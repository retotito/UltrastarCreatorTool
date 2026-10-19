"""Syllable alignment: picks the engine and falls back when it can't run.

Order: forced alignment of the user's lyrics ("ctc") → WhisperX word matching ("legacy") →
energy-based. The engine comes from the ULTRASTAR_ALIGNMENT_ENGINE environment variable
(default "ctc"); "legacy" keeps the old behaviour for comparison.
"""

import os
from typing import Callable, List, Optional, Tuple

from utils.logger import log_step

ENGINES = ("ctc", "legacy")
DEFAULT_ENGINE = "ctc"


def configured_engine() -> str:
    engine = os.environ.get("ULTRASTAR_ALIGNMENT_ENGINE", DEFAULT_ENGINE).strip().lower()
    return engine if engine in ENGINES else DEFAULT_ENGINE


def align_syllables(
    audio_path: str,
    lyrics: str,
    language: str = "en",
    pitch_data: Optional[dict] = None,
    whisper_words: Optional[list] = None,
    whisper_chars: Optional[list] = None,
    get_whisper: Optional[Callable[[], Tuple[list, list]]] = None,
    engine: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> Tuple[List[dict], str]:
    """Syllable timings for `lyrics` in `audio_path`, and the engine that made them.

    `whisper_words` / `whisper_chars` are used by the legacy engine. `get_whisper` produces them on
    demand, so callers that only have audio (segment regenerate) transcribe only when needed.
    Returns (timings, engine) with engine "ctc", "legacy" or "energy".
    """
    engine = engine or configured_engine()

    if engine == "ctc":
        try:
            from services.forced_alignment import align_lyrics
            timings = align_lyrics(audio_path, lyrics, pitch_data=pitch_data, cache_dir=cache_dir, language=language)
            if timings:
                return timings, "ctc"
            log_step("ALIGN", "Forced alignment returned nothing, falling back to WhisperX matching")
        except ImportError as error:
            log_step("ALIGN", f"Forced alignment unavailable ({error}), falling back to WhisperX matching")
        except Exception as error:  # AlignmentError, model download/load problems, ...
            log_step("ALIGN", f"Forced alignment failed ({type(error).__name__}: {error}), "
                              "falling back to WhisperX matching")

    if not whisper_words and get_whisper is not None:
        try:
            whisper_words, whisper_chars = get_whisper()
        except Exception as error:
            log_step("ALIGN", f"Transcription for WhisperX matching failed: {error}")
            whisper_words, whisper_chars = [], []

    if whisper_words:
        try:
            from services.alignment_whisper import align_whisper
            timings = align_whisper(lyrics, whisper_words, language,
                                    char_timestamps=whisper_chars or None, audio_path=audio_path)
            if timings:
                return timings, "legacy"
        except Exception as error:
            log_step("ALIGN", f"WhisperX matching failed: {error}")

    log_step("ALIGN", "Using energy-based alignment (fallback)")
    from services.alignment import align_lyrics_to_audio
    return align_lyrics_to_audio(audio_path, lyrics, language), "energy"
