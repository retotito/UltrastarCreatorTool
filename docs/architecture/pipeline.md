# AI Pipeline

> **Status:** Current · **Last updated:** 2026-10-19

How audio and lyrics become an UltraStar `.txt`, as implemented today. The planned change of the alignment stage is
described in [plans/forced-alignment.md](../plans/forced-alignment.md).

## Overview

```
song.mp3 ──► Demucs ──► vocals.wav ──┬─► WhisperX ASR ─► lyric suggestion ─► user edits + hyphenation ─┐
                                     │        └─► wav2vec2 align ─► whisper_words (fallback only)       │
                                     ├─► BPM + beat phase                                               ▼
                                     ├─► PYIN pitch ─────────────►  syllable alignment ◄───── final lyrics
                                     └─► aligner emissions ──────►  (forced alignment)
                                                                               │
                                                     GAP, BPM refinement, notes ─► .txt  .mid  summary
```

## Stages

### 1. Vocal separation
`services/vocal_separation.py`: Demucs v4 `htdemucs` with `--two-stems vocals`. The vocal output is trimmed or
padded to the exact length of the original. Can be skipped by uploading vocals directly.

### 2. Transcription (lyric suggestion)
`main.py` `transcribe_stream`: WhisperX (faster-whisper, CPU, int8, batch size 4) with the model from the UI preset:
`fast` = small, `balanced` = medium, otherwise large-v3. WhisperX defaults apply: pyannote voice activity
detection, beam size 5, `condition_on_previous_text=False`.

WhisperX then aligns **its own transcript** with a wav2vec2 model (English: `WAV2VEC2_ASR_BASE_960H`) to get word
and character timestamps, stored in the session. Fallback: vanilla Whisper with `word_timestamps=True` (word level
only, about 200 ms accuracy).

The transcript is shown to the user as a starting point. The user corrects words, line breaks and hyphenation
(`services/hyphenation.py`, pyphen).

### 3. BPM detection
`services/bpm_detection.py`: essentia when installed, otherwise librosa; octave correction; beat phase from the
original mix. After alignment, `refine_bpm` adjusts the BPM to fit the syllable onsets.

### 4. Pitch detection
`services/pitch_detection.py`: librosa PYIN, confidence threshold 0.4, converted to MIDI note numbers.

### 5. Syllable alignment
`services/syllable_alignment.py` `align_syllables` picks the engine (`ULTRASTAR_ALIGNMENT_ENGINE`, default `ctc`)
and falls back in this order: **forced alignment → WhisperX matching → energy-based**.

**Forced alignment** (`services/forced_alignment.py`, default): the user's final lyrics are timed directly
against the vocals, so a word Whisper missed still gets its real position.

1. Lyrics → words and syllables (`parse_lyrics`); each syllable romanised to the aligner's letters (a–z, `'`;
   accents removed; non-Latin scripts raise `UnsupportedText` → fallback).
2. **Emissions**: Tune Studio's singing fine-tune of the MMS aligner (`tuneperfect/tunestudio-aligner`, ONNX,
   pinned) over the whole vocal track in 30 s windows with 2 s context → letter log-probabilities every 20 ms.
   Cached per audio file in the session's `cache/` folder.
3. **Silence gate**: frames more than 30 dB below the song's loud singing (widened by 60 ms) can't hold letters.
4. **Viterbi search** (`forced_align`) for the best path of all letters, in order. A free `<star>` token before
   every word and after the last absorbs sound that isn't in the lyrics (ad-libs, outros).
5. Word times from the letter spikes; syllables split where their first letter is; a line's first or last word
   more than 0.8 s from its neighbour is pulled back (`pull_in_edges`). (`snap_to_voice` exists but is off: it
   measured worse.)
6. `confidence` = exp(mean log-probability) per word; `low_confidence` when it is below −2.

**WhisperX matching** (`services/alignment_whisper.py`, `legacy`):

1. Rebuild words from syllables and match each lyric word to a Whisper word in order, with up to 20 words of
   lookahead (`_match_words`).
2. Fill runs of unmatched words (`_fill_gaps_hybrid`) by interpolation or energy-based sub-alignment.
3. Split each word into syllables by WhisperX character timestamps, else proportionally.

> **Known limitation (legacy).** Timing comes from Whisper's transcript, not from the corrected lyrics. Where
> Whisper missed or misheard words, step 2 guesses their positions, which causes misplaced notes.
>
> **Known limitation (forced alignment).** Repetitive vocalise ("la la dee", "ooh") and backing vocals that
> repeat the lead can still make a section drift until the next clearly sung words, much less with the singing
> model than with the stock one. Lyrics that differ from what is sung ("la la dee" typed, "la da dee" sung) make it
> worse. See [known-issues.md](../known-issues.md).

### 6. Onset snapping
`services/onset_snapping.py`: moves each syllable start to the nearest spectral onset within a window. Only
applied after WhisperX matching; forced alignment snaps to the voice itself (onset snapping measured worse on it).

### 7. Output
`main.py` `generate_ultrastar_files` → `services/ultrastar.py`:

- **GAP** = start of the first syllable (beat 0 = first sung syllable).
- Notes are quantised to the beat grid. UltraStar BPM is 4× the musical BPM. See
  [ultrastar-grid-gap.md](ultrastar-grid-gap.md).
- Pitch per note from the PYIN track over the note's time span.
- Line breaks from the lyric lines; trailing spaces after words; apostrophes normalised to `’`; mid-word syllables
  get a trailing `-` on download.
- Also written: MIDI (`services/midi_export.py`) and a processing summary.

If a reference `.txt` is stored for the song, the result is compared to it automatically
(`services/reference_comparison.py` `compare_timing_ms`).

## Partial pipelines

| Feature | Endpoint | Stages run |
|---|---|---|
| Lyrics-only generation | `generate` (lyrics-only path) | Text and timing placeholders, no audio analysis |
| Segment preview | `segment-preview` | Whisper on a clip, text only |
| Segment regenerate | `segment-generate` | Pitch + alignment on a clip (Whisper only if forced alignment falls back), see [segment-regenerate.md](../features/segment-regenerate.md) |
| Analyze 5s | Step 4 | Pitch + local Whisper, see [vocal-tracing-strategy.md](../features/vocal-tracing-strategy.md) |
