"""Whisper on two-language songs: each passage keeps the transcription Whisper is more confident about."""

from services.bilingual_transcription import PASSAGE_SEC, pick_passages, transcribe_two_languages


def seg(start, text, logprob):
    return {"start": start, "end": start + 4.0, "text": text, "avg_logprob": logprob}


def test_each_passage_keeps_the_more_confident_language():
    english = [seg(55.6, "are bad situations", -1.20), seg(103.7, "Feeling happy, feeling sad", -0.30)]
    italian = [seg(55.6, "sono umane situazioni", -0.45), seg(103.7, "fili napi fili sad", -0.63)]
    picked = pick_passages(english, italian, "en", "it")
    assert [(s["language"], s["text"]) for s in picked] == [
        ("it", "sono umane situazioni"), ("en", "Feeling happy, feeling sad")]


def test_passages_without_a_partner_are_kept_in_time_order():
    picked = pick_passages([seg(10.0, "a", -0.5)], [seg(10.3, "b", -0.9), seg(20.0, "c", -0.4)], "en", "it")
    assert [(s["language"], s["text"]) for s in picked] == [("en", "a"), ("it", "c")]


def test_both_languages_are_transcribed_in_short_passages():
    calls = []

    class Pipeline:
        def transcribe(self, audio, batch_size, language, chunk_size):
            calls.append((language, chunk_size))
            return {"segments": [seg(0.0, f"{language} text", -0.2 if language == "it" else -0.8)]}

    result = transcribe_two_languages(Pipeline(), [0.0], "en", "it")
    assert calls == [("en", PASSAGE_SEC), ("it", PASSAGE_SEC)]
    assert result == {"language": "en", "segments": [{**seg(0.0, "it text", -0.2), "language": "it"}]}
