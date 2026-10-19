# 0002: Forced alignment of user lyrics

> **Status:** Accepted · **Date:** 2026-10-19 (model choice updated the same day, see "Model")

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

### Model

The default model is **Tune Studio's singing fine-tune** of the MMS aligner,
[`tuneperfect/tunestudio-aligner`](https://huggingface.co/tuneperfect/tunestudio-aligner) (ONNX, pinned revision,
CC-BY-NC-4.0, same terms as the base model), run with onnxruntime. Measured on 6 reference songs (1,799 syllables),
share of syllables more than 500 ms off the reference chart:

| Engine | Misplaced |
|---|---|
| WhisperX matching (before) | 56.6 % |
| Forced alignment, stock MMS | 27.7 % |
| Forced alignment, singing fine-tune | **6.8 %** |

The stock MMS model stays available for evaluation (`model_name="mms"`).

## Alternatives considered

- **Better matching heuristics in `alignment_whisper.py`.** Can't fix missing information: words Whisper didn't
  hear have no timestamps.
- **WhisperX's wav2vec2 aligner on the user's text.** Permissive licence, but trained on read speech, a small model
  and limited languages. Kept as a possible fallback engine.

## Consequences

- **Licence:** the aligner weights (MMS and Tune Studio's fine-tune) are **CC-BY-NC-4.0** (non-commercial).
  Accepted because the app is distributed free of charge. Tune Studio and the base model are credited in the
  README and the setup screen. The app must not be sold while it uses these weights.
- New model download (about 1.2 GB) in the setup screen. No new Python dependency: onnxruntime comes with
  faster-whisper (and is now bundled by `backend.spec`).
- All 98 app languages can be aligned: lyrics are romanised with uroman (as MMS was trained). Only English is
  measured so far; the singing fine-tune saw English and German charts only, so other languages may be weaker.
- The alignment engine is swappable (`ULTRASTAR_ALIGNMENT_ENGINE=ctc|legacy`), so a singing-tuned or permissively licensed model can
  replace it later.
