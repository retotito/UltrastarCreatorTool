"""Whisper on songs sung in two languages (Step 2's Vocals tab).

Whisper decodes with one language. Told "English", it *translates* the Italian lines of a duet into English
("Sono umane situazioni" → "are bad situations"). So, when a song has a second language, the vocals are
transcribed once in each language, in short passages (about a line), and each passage keeps the version Whisper
is more confident about (higher average log-probability): forced into the wrong language, Whisper is clearly
less sure. This beat Whisper's own language detection on a test duet (Cose della vita, English/Italian), which
mistook several Italian lines for English. It takes about twice as long as one language.
"""

from typing import List

PASSAGE_SEC = 8   # voice-detected passages merged up to this length: about a line or two


def pick_passages(first: List[dict], second: List[dict], language: str, language2: str) -> List[dict]:
    """Per passage, the more confident of the two transcriptions, each tagged with its "language".

    Both lists come from the same audio and voice detection, so their passages line up; one without a
    partner (starting more than half a second from any) is kept as it is."""
    second_by_start = {round(s["start"], 1): s for s in second}
    picked, used = [], set()
    for a in first:
        b = second_by_start.get(round(a["start"], 1))
        if b is None:
            b = next((s for s in second if abs(s["start"] - a["start"]) <= 0.5), None)
        if b is not None:
            used.add(id(b))
        if b is not None and b.get("avg_logprob", -99.0) > a.get("avg_logprob", -99.0):
            picked.append({**b, "language": language2})
        else:
            picked.append({**a, "language": language})
    picked += [{**s, "language": language2} for s in second if id(s) not in used]
    return sorted(picked, key=lambda s: s["start"])


def transcribe_two_languages(pipeline, audio, language: str, language2: str, batch_size: int = 4) -> dict:
    """Like WhisperX's `pipeline.transcribe`, for a song in two languages: {"segments" (each with its
    "language"), "language" (the first)}."""
    runs = [pipeline.transcribe(audio, batch_size=batch_size, language=code, chunk_size=PASSAGE_SEC)["segments"]
            for code in (language, language2)]
    return {"segments": pick_passages(runs[0], runs[1], language, language2), "language": language}
