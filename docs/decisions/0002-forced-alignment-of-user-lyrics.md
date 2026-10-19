# 0002: Forced alignment of user lyrics

> **Status:** Accepted · **Date:** 2026-10-19

## Context

Syllable timing is taken from WhisperX's transcript and matched to the user's corrected lyrics. Wherever Whisper
missed or misheard words, the matching leaves gaps that are filled by interpolation and energy heuristics. That
produces misplaced notes ("hallucinations"), see [known-issues.md](../known-issues.md).

## Decision

Time the **user's final lyrics** directly against the vocal audio with CTC forced alignment, using
[`ctc-forced-aligner`](https://github.com/MahmoudAshraf97/ctc-forced-aligner) (BSD-2) and the
`MahmoudAshraf/mms-300m-1130-forced-aligner` model (Meta MMS). Whisper only provides the lyric suggestion.

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
- New model download (about 1.2 GB) and a new PyInstaller dependency.
- Language support grows to the about 1,100 MMS languages (through romanisation).
- The alignment engine is swappable (`alignment_engine` setting), so a singing-tuned or permissively licensed model can
  replace it later.
