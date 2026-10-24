# 0003: GAME decides syllable pitches

> **Status:** Accepted · **Date:** 2026-10-24

## Context

A syllable's pitch was the median of FCPE's pitch curve over the syllable, followed by the octave check. Where
two voices overlap (a duet's female voice over the male line, as in "Amada Mia, Amore Mio"), FCPE follows the
louder voice and the right note isn't in its output; no correction afterwards can bring it back. Tune Studio
runs openvpi's GAME (Generative Adaptive MIDI Extractor), a note-level singing transcription model, for this.

## Decision

GAME (release v1.0.3, its ONNX files as released) gives each syllable its longest voiced note, line by line with
the syllable starts as known boundaries (`services/game_notes.py`, as Tune Studio runs it). Syllables GAME finds
nothing in keep FCPE's pitch; melisma parts keep theirs. The octave check and the repeated-line check run after.
`ULTRASTAR_NOTE_ENGINE=fcpe` turns it off.

Measured on the 6 reference songs (eval, engine ctc): pitch class 56 → 64 %, within a semitone 75.7 → 79.7 %,
octave errors 4.5 → 3.0 % (five songs better, one 5.8 → 6.7 %). Amada Mia against Tune Studio's chart: 104 → 123
notes on the same pitch, octave off 47 → 27. It adds about 45 s per song on the CPU.

## Licence

The model is **CC BY-NC-SA 4.0**: non-commercial, like the Tune Studio aligner (0002), and share-alike for
changes to the model (we use it unchanged). It is downloaded at first run from GitHub (pinned release, the zip's
and every file's SHA-256 checked), not bundled. A commercial hosted version would need another note model.

## Alternatives considered

- **Better octave logic on FCPE alone** (one-octave limit, repeated lines, harmonic evidence, spike filter): the
  first two were kept; they can't recover notes FCPE never measured.
- **Harmonic evidence for the octave check** (Tune Studio's odd/even harmonics): measured, no gain.
- **Tune Studio's steps after GAME** (measured 2026-10-24): snapping notes to the song's key (reference songs:
  pitch class 63.3 → 64.3 %, within a semitone 79.7 → 78.8 %) and its learned pitch corrector `notefix.onnx`
  (MIT; with the key: 63.5 %, 78.0 %, octave errors 3.1 → 2.6 %; Amada Mia against Tune Studio's chart 131–133 →
  126–127 notes on the same pitch). Within GAME's run-to-run noise or worse; the corrector was trained on Tune
  Studio's own pipeline (its timing, melisma notes and vocal separation), so it isn't used.

## Consequences

- First-run setup downloads another ~362 MB (`notes` in `/api/setup/status`).
- The segmenter samples randomly (its RandomUniformLike op isn't seeded), so generating the same song twice can
  give slightly different notes. Tune Studio patches that op to a seeded input; we could do the same.
