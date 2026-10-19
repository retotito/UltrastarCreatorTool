# AI Pipeline

> **Status:** Current · **Last updated:** 2026-10-19

How audio and lyrics become an UltraStar `.txt`, as implemented today. The planned change of the alignment stage is
described in [plans/forced-alignment.md](../plans/forced-alignment.md).

## Overview

```
song.mp3 ──► Demucs ──► vocals.wav ──┬─► WhisperX ASR ─► lyric suggestion ─► user edits + hyphenation ─┐
                                     │        └─► wav2vec2 align ─► whisper_words / whisper_chars       │
                                     │                                         │                       │
                                     ├─► BPM + beat phase                      ▼                       ▼
                                     ├─► PYIN pitch ─────────────►  syllable alignment ◄───── final lyrics
                                     │                                         │
                                     └─────────────────────────────► onset snapping
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
`services/alignment_whisper.py` `align_whisper`:

1. Parse the final lyrics into lines and syllables (`parse_lyrics`: hyphens split syllables, `[RAP]`/`[/RAP]` markers).
2. Rebuild words from syllables.
3. Match each lyric word to a Whisper word in order, with up to 20 words of lookahead (`_match_words`).
4. Fill runs of unmatched words (`_fill_gaps_hybrid`): small gaps are interpolated between neighbours; gaps of 3+
   words use energy-based sub-alignment, and are moved into "Whisper-silent regions" when the neighbours are too
   close together.
5. Split each word's time span into syllables by character timestamps when available, else proportionally.

Fallback when there are no Whisper words: `services/alignment.py` (energy-based).

> **Known limitation.** Timing comes from Whisper's transcript, not from the corrected lyrics. Where Whisper
> missed or misheard words, step 4 guesses their positions, which causes misplaced notes. See
> [known-issues.md](../known-issues.md) and [ADR 0002](../decisions/0002-forced-alignment-of-user-lyrics.md).

### 6. Onset snapping
`services/onset_snapping.py`: moves each syllable start to the nearest spectral onset within a window.

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
| Segment regenerate | `segment-generate` | Whisper + alignment on a clip, see [segment-regenerate.md](../features/segment-regenerate.md) |
| Analyze 5s | Step 4 | Pitch + local Whisper, see [vocal-tracing-strategy.md](../features/vocal-tracing-strategy.md) |
