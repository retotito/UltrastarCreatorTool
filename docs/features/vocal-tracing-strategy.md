# New Vocal Tracing Strategy

> **Status:** Current · **Last updated:** 2026-06-08

## Goal

Build a Step 4 editor workflow that analyzes a short window of vocals and proposes usable Ultrastar notes directly in the editor, without depending on the full-song generation pipeline.

This mode is meant to be iterative, local, and debuggable.

## Current Direction

The active prototype is `Analyze 5s` in Step 4.

For each 5 second window it should:

1. Sample pitch from the vocals audio.
2. Run fresh Whisper or WhisperX recognition on only that local audio window.
3. Create note proposals from the detected pitch.
4. Attach recognized words to those notes.
5. Keep placeholder notes for voiced regions where no reliable word is recognized.

## Confirmed Decisions

1. `Analyze 5s` must be independent from Step 2 transcription.
2. Placeholder notes such as `...` are required and should stay.
3. Placeholder notes must not overlap recognized word notes when avoidable.
4. Strong logging is required in frontend and backend so every stage can be inspected.
5. Syllable splitting is deferred until note and word placement are stable.

## What Is Working Now

1. Step 4 can run local 5 second analysis from the cursor.
2. The backend can transcribe only the requested audio window.
3. The frontend creates note proposals and inserts them into the editor.
4. Recognized words are being attached to notes.
5. Unrecognized voiced regions are still represented by placeholder notes.

## Current Problems

1. Placeholder notes can still overlap or crowd recognized word notes.
2. Word note boundaries are usable but still need cleanup in edge cases.
3. Placeholder generation is only pitch based; later it may need loudness or confidence filtering.
4. Syllable splitting is not implemented yet.

## Next Implementation Order

1. Remove or trim placeholder notes that overlap recognized word notes.
2. Tighten note boundaries around recognized words so local windows look cleaner.
3. Add a simple noise or energy filter so low-value voiced fragments stop creating junk placeholders.
4. Add syllable splitting only after overlap cleanup is stable.
5. After that, consider multi-window workflows such as analyze-next or apply-and-advance.

## Overlap Strategy

The current preferred approach is:

1. Keep recognized word notes as the higher priority result.
2. Keep placeholder notes only in gaps that remain after recognized words are placed.
3. If a placeholder partially overlaps a recognized word note, trim the placeholder.
4. If a placeholder is fully covered by a recognized word note, drop it.
5. Only preserve placeholder notes where they represent real voiced material outside recognized words.

## Deferred For Later

1. Full syllable splitting from words to singable Ultrastar syllables.
2. Confidence-based rejection rules for weak recognition.
3. Better pitch contour shaping inside long word notes.
4. Automatic multi-window batch analysis.
5. Merging this flow back into the full-song generation pipeline.

## Working Rule

Before changing this feature, check this file first and keep work aligned with these priorities:

1. Local analysis first.
2. Keep placeholders.
3. Avoid overlaps.
4. Preserve strong logs.
5. Delay syllable splitting until the note layout is trustworthy.