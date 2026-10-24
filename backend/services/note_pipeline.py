"""From aligned syllables to the chart's notes: the steps after the lyrics timing, the same for the whole song
(Generate) and for a range of it (the editor's "AI generate notes" on a loop, /api/segment-generate).

0. held notes: a syllable lasts while the voice keeps singing it (the aligner ends long-held vowels early),
   services/note_holds.py,
1. melisma: long syllables whose pitch moves become several notes ("gas ~ ~"), services/melisma.py,
2. GAME's sung note per syllable (FCPE's median where it finds none), services/game_notes.py,
3. the final pitch per note (octave check, repeated lines) decided on the whole syllables and frozen,
4. consonant trimming (forced alignment only), services/consonant_trim.py.

Each step can be turned off (ULTRASTAR_HOLD_NOTES, ULTRASTAR_MELISMA, ULTRASTAR_NOTE_ENGINE,
ULTRASTAR_TRIM_CONSONANTS) and a failing GAME leaves FCPE's pitch.
"""

import time
from typing import Callable, List, Optional, Tuple

from utils.logger import log_step


def build_notes(vocal_path: str, syllable_timings: List[dict], pitch_data: dict, language: str, models_dir: str,
                align_engine: str = "ctc", check_cancelled: Optional[Callable[[], None]] = None,
                tag: str = "GENERATE") -> Tuple[List[dict], dict]:
    """The timings as notes (one entry per note, each with its frozen "pitch"; None for rap) and what was done:
    {"held_notes", "melisma_notes", "game_found", "trimmed"}."""
    from services import consonant_trim, game_notes, melisma, note_holds
    from services.pitch_detection import freeze_pitches
    info = {"held_notes": 0, "melisma_notes": 0, "game_found": 0, "trimmed": False}
    if not syllable_timings:
        return syllable_timings, info
    loudness = None
    if align_engine == "ctc" and (note_holds.enabled() or consonant_trim.enabled()):
        from services.forced_alignment import frame_loudness
        loudness = frame_loudness(vocal_path)

    if note_holds.enabled() and align_engine == "ctc":
        syllable_timings = note_holds.extend_holds(syllable_timings, pitch_data, loudness)
        info["held_notes"] = sum(1 for t in syllable_timings if "held_from" in t)
        log_step(tag, f"Held notes: {info['held_notes']} extended")

    if melisma.enabled():
        count = len(syllable_timings)
        syllable_timings = melisma.split_melismas(syllable_timings, pitch_data)
        info["melisma_notes"] = len(syllable_timings) - count
        log_step(tag, f"Melisma: {info['melisma_notes']} extra notes")

    if check_cancelled:
        check_cancelled()
    try:
        started = time.time()
        info["game_found"] = game_notes.apply(models_dir, vocal_path, syllable_timings, language)
        log_step(tag, f"Notes (GAME): {info['game_found']}/{len(syllable_timings)} syllables in {time.time() - started:.0f}s")
    except Exception as e:  # the model can't run: FCPE's pitch stays
        log_step(tag, f"Notes (GAME) skipped: {type(e).__name__}: {e}")

    # The pitch is decided on the whole syllables before trimming (shorter notes made it slightly worse).
    syllable_timings = freeze_pitches(pitch_data, syllable_timings)
    if consonant_trim.enabled() and align_engine == "ctc":
        syllable_timings = consonant_trim.trim(syllable_timings, pitch_data, loudness)
        info["trimmed"] = True
        log_step(tag, "Consonant trimming applied")
    return syllable_timings, info
