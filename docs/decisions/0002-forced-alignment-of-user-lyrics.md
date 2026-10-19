# 0002: Forced alignment of user lyrics

> **Status:** Accepted · **Date:** 2026-10-19

## Context

Syllable timing is taken from WhisperX's transcript and matched to the user's corrected lyrics. Wherever Whisper
missed or misheard words, the matching leaves gaps that are filled by interpolation and energy heuristics. That
produces misplaced notes ("hallucinations"), see [known-issues.md](../known-issues.md).

## Decision

Time the **user's final lyrics** directly against the vocal audio with CTC forced alignment, using the
`MahmoudAshraf/mms-300m-1130-forced-aligner` model (Meta MMS, pinned revision) loaded with `transformers`, and our
own Viterbi search in numpy (`backend/services/forced_alignment.py`). Whisper only provides the lyric suggestion.

We don't use a forced-alignment package:
- `ctc-forced-aligner` on PyPI (1.0.2) is a different fork (Deskpai) with its own licence ("DOSL") and its own
  ONNX model download, and it would upgrade librosa to 1.0.
- The original [`ctc-forced-aligner`](https://github.com/MahmoudAshraf97/ctc-forced-aligner) is itself
  CC-BY-NC-4.0, isn't on PyPI and needs a C++ build, which would complicate PyInstaller.
- The search is about 50 lines of numpy and is unit-tested with synthetic emissions.

The implementation plan is in [plans/forced-alignment.md](../plans/forced-alignment.md).

## Alternatives considered

- **Better matching heuristics in `alignment_whisper.py`.** Can't fix missing information: words Whisper didn't
  hear have no timestamps.
- **WhisperX's wav2vec2 aligner on the user's text.** Permissive licence, but trained on read speech, a small model
  and limited languages. Kept as a possible fallback engine.

## Consequences

- **Licence:** the MMS weights are **CC-BY-NC-4.0** (non-commercial). Accepted because the app is distributed free
  of charge. The model must be credited in the README and the setup screen. The app must not be sold while it
  uses these weights.
- New model download (about 1.3 GB) in the setup screen. No new Python dependency: torch and transformers
  come with WhisperX.
- Latin-script languages work now (accents are removed: "Mädchen" → "madchen"). Other scripts need
  romanisation (uroman) and fall back to the old alignment until then.
- The alignment engine is swappable (`ULTRASTAR_ALIGNMENT_ENGINE=ctc|legacy`), so a singing-tuned or permissively licensed model can
  replace it later.
