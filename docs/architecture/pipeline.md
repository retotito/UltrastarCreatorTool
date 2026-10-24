# AI Pipeline

> **Status:** Current · **Last updated:** 2026-10-23

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

**Two languages** (the session has `language2`): Whisper decodes with one language and *translates* lines sung in
another. `services/bilingual_transcription.py` transcribes the vocals once per language in passages of up to 8 s
and keeps, per passage, the version with the higher average log-probability (Whisper's own language detection
mistook several Italian lines of an English/Italian duet for English). About twice the time of one language.
Each language's passages are then aligned with that language's wav2vec2 model.

WhisperX then aligns **its own transcript** with a wav2vec2 model (English: `WAV2VEC2_ASR_BASE_960H`) to get word
and character timestamps, stored in the session. Fallback: vanilla Whisper with `word_timestamps=True` (word level
only, about 200 ms accuracy).

The transcript is shown to the user as a starting point; "Find lyrics online" fetches the published lyrics from
LRCLIB (`services/lyrics_search.py`) into the right field. The user picks which field is used, and corrects words,
line breaks and hyphenation (`services/hyphenation.py`): a pyphen dictionary where one exists for the language,
one syllable per character for Chinese, Japanese and Korean, else a generic vowel rule (Latin script) or no
splitting (scripts without written vowels).

### 3. BPM detection
`services/bpm_detection.py`: essentia when installed, otherwise librosa; octave correction; beat phase from the
original mix. After alignment, `refine_bpm` adjusts the BPM to fit the syllable onsets.

### 4. Pitch detection
`services/pitch_detection.py` `detect_pitches`: **FCPE** (neural pitch estimator for singing, ONNX, MIT, pinned)
over the whole vocal track, a pitch every 10 ms; librosa PYIN as fallback (`ULTRASTAR_PITCH_ENGINE=pyin`).

A syllable's pitch (`syllable_pitch`) is the median of the unrounded pitch over its **last two thirds** (singers
slide into notes from below), rounded to a semitone. Syllables without any pitch take the previous sung
syllable's pitch (`fill_unvoiced`), not a fixed C4.

Then the **octave check** (`fix_octaves`, after Tune Studio's `fixOctaves`) picks for every note a shift of
−1, 0 or +1 octave so the whole song costs least: leaps beyond a fifth between neighbours are expensive (cheaper
after a pause), moving a note costs, and leaving the song's range costs a little. It removes the pitch tracker's
octave slips. One octave at most, as in Tune Studio: with up to three, a duet's low male voice (heard by FCPE an
octave too low) was pulled two octaves up towards the female voice. The price: a note FCPE put several octaves
off (rare) is not brought back. Tune Studio additionally weighs the voice's harmonics per note (whether it really
is that low or high); we don't yet.

Measured on 6 reference songs (pitch class, octave ignored): FCPE 57.6 % exact / 77.3 % within a semitone;
PYIN 52.7 % / 70.5 %. Octave check: notes in the wrong octave 5.2 % → 4.4 %, jumps of more than an octave
inside a line 27 → 0. Melisma syllables can't match yet: one note per syllable (see `~` notes, plan step 4).

### 5. Syllable alignment
`services/syllable_alignment.py` `align_syllables` picks the engine (`ULTRASTAR_ALIGNMENT_ENGINE`, default `ctc`)
and falls back in this order: **forced alignment → WhisperX matching → energy-based**.

**Forced alignment** (`services/forced_alignment.py`, default): the user's final lyrics are timed directly
against the vocals, so a word Whisper missed still gets its real position.

1. Lyrics → words and syllables (`parse_lyrics`); each syllable romanised with **uroman** (any script, with the
   language's rules: "Привет" → "privet", "Mädchen" → "maedchen", as in MMS training) and reduced to the
   aligner's letters (a–z, `'`). Without uroman only Latin script works; others raise `UnsupportedText` → fallback.
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

### 7. Melisma (`~` notes)
`services/melisma.py` `split_melismas`: after GAP, BPM refinement and line assignment (so those see syllables),
long syllables whose pitch moves are split into several timing entries: the syllable's text, then `~` (`~ ` at a
word end). A new note starts only where the pitch stays at least 1 semitone away from the current note for
0.12 s (hysteresis: vibrato doesn't split); first/last parts under 0.25 s are slides into or off the note and
are merged. Each part carries its own `pitch`. One timing entry per note keeps the .txt, MIDI and the editor's
re-quantisation (`rawTimings`) in step. Off with `ULTRASTAR_MELISMA=off`.

Measured on 6 reference songs: frame pitch (right pitch class over time) 42.3 → 44.9 %, within a semitone
53.3 → 56.1 %, syllable pitch 57.4 → 59.0 %; 218 `~` notes against 212 in the charts.

### 8. Output
`main.py` `generate_ultrastar_files` → `services/ultrastar.py`:

- **GAP** = start of the first syllable (beat 0 = first sung syllable).
- Notes are quantised to the beat grid. UltraStar BPM is 4× the musical BPM. See
  [ultrastar-grid-gap.md](ultrastar-grid-gap.md).
- Pitch per note from the PYIN track over the note's time span.
- Line breaks from the lyric lines; trailing spaces after words; apostrophes normalised to `’`; mid-word syllables
  get a trailing `-` on download (after the last `~` of a melisma, never before a `~`).
- Also written: MIDI (`services/midi_export.py`) and a processing summary.

If a reference `.txt` is stored for the song, the result is compared to it automatically
(`services/reference_comparison.py` `compare_timing_ms`).

## Partial pipelines

| Feature | Endpoint | Stages run |
|---|---|---|
| Lyrics-only generation | `generate` (lyrics-only path) | Text and timing placeholders, no audio analysis |
| Segment preview | `segment-preview` | Whisper on a clip, text only |
| Segment regenerate | `segment-generate` | Pitch + alignment + melisma on a clip (Whisper only if forced alignment falls back), see [segment-regenerate.md](../features/segment-regenerate.md) |
| Analyze 5s | Step 4 | Pitch + local Whisper, see [vocal-tracing-strategy.md](../features/vocal-tracing-strategy.md) |
