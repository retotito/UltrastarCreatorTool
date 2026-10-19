# Pipeline Definition

> **Status:** Archived · **Last updated:** 2026-04-03  
> Superseded by [architecture/pipeline.md](../architecture/pipeline.md).

To ensure consistency and avoid breaking changes, here's a clear definition of the processing pipeline for generating Ultrastar files. This covers the `/reprocess_with_corrected` endpoint (and aligns with `/process_audio2` where applicable). All changes must be checked against this plan.

## Processing Pipeline Steps:
1. **Input Handling**: Receive corrected vocal audio, lyrics (required), artist, title, voice_type, language.
2. **Audio Analysis**:
   - Load audio with librosa (sr=22050), trim leading silence (top_db=20).
   - Detect BPM using [`librosa.beat.beat_track`](.venv/lib/python3.9/site-packages/librosa/__init__.py ) (output: [`bpm`](backend/main.py )).
   - Detect pitches using PYIN (fmin=C2, fmax=C7, frame_length=2048, hop_length=512).
   - Convert pitches to MIDI notes (round to nearest).
   - Calculate [`first_pitch_time`](backend/main.py ) as the earliest voiced time (for GAP).
3. **Lyrics Handling**:
   - Lyrics are always provided by the user (required input).
   - The corrected vocal audio should contain only the vocals to be sung in the game (no background singers).
   - Each line of lyrics represents a phrase that will be separated in Ultrastar by break lines (`- start end`).
   - Empty lines are ignored/removed during processing.
   - Syllables within words are already separated by the user using `-` character (e.g., `beau-ti-ful`).
   - Rap sections can be marked in lyrics with special markers (e.g., `[RAP]` start, `[/RAP]` end).
   - Split each word on `-` to get individual syllables for note generation.
   - Each syllable becomes one note line in the Ultrastar format (`: start duration pitch syllable` for singing, `F: start duration 0 syllable` for rap).
4. **Timing and Alignment**:
   - **Syllable Duration Calculation**:
     - Use onset/offset detection to find syllable boundaries in audio
     - Group consecutive pitch detections into syllable segments (filter noise < 50ms)
     - For each syllable: detect start_time and end_time from audio analysis
     - Handle multiple pitches per syllable: use average/median pitch for MIDI note (approximate pitch)
     - For unrecognized syllables: interpolate timing between recognized neighbors
     - Fallback for silent/unclear sections: distribute syllables evenly based on BPM timing
     - Convert: `duration_beats = ((end_time - start_time) * bpm * 2) / 60`
   - **Break Line Timing**:
     - `start` = end beat of last syllable + padding (2-8 beats)
     - `end` = start beat of next syllable - padding (2-8 beats)
     - Creates buffer zones to prevent words running together in game display
     - Some breaks may have no end time (format: `- start` only)
     - Format: `- [padded_end_beat] [padded_start_beat]`
5. **Output Generation**:
   - Generate MIDI file from pitches.
   - Generate Ultrastar .txt: #ARTIST, #TITLE, #BPM (bpm), #GAP (gap_ms), note lines (with line breaks).
   - Return download URLs for .txt, vocals, MIDI, summary.

## Logging and Debugging:
- **BPM detection**: "Detected BPM: 136.2 -> Ultrastar BPM: 272"
- **GAP calculation**: "First pitch detected at: 1.23s -> GAP: 1230ms"
- **Syllable alignment**: "Found 45 syllables in lyrics, detected 38 vocal segments"
- **Missing syllables**: "Syllables 12-15 ('beau-ti-ful-day') not found in audio - using BPM fallback"
- **Timing fallbacks**: "Used interpolation for syllables 23-25 (silent section)"
- **Final validation**: "Generated 45 notes, total duration: 3:24, audio duration: 3:26"
- **Summary file**: Include list of approximated syllables and timing methods used

## Important Parameters (Must Match Original/Test File):
- **#BPM**: ~272 (calculated from librosa; multiply by 2 for Ultrastar precision).
- **#GAP**: Calculated from first pitch time in milliseconds (dynamic, not fixed 13208).
- **First Beat**: Always 0.
- **Last Beat**: Accumulates to match total duration.
- **Pitches**: MIDI notes from PYIN; round to int.
- **Voice Type**: Determines line prefix (`:` for normal singing, `F:` for rap sections with pitch=0).
- **Language**: Used for pyphen syllable splitting (fallback only; user provides pre-split syllables).

## Edge Cases and Robustness:
- **Multiple pitches per syllable**: Use median/average for stable MIDI note
- **Pitch detection noise**: Filter segments shorter than 50ms
- **Unrecognized syllables**: Interpolate timing between known neighbors
- **Missing vocal segments**: Use BPM-based fallback distribution
- **Break line padding**: Prevents word concatenation in game display
- **Manual editing expected**: YASS editor can refine timing and pitch post-generation

## Checklist for Improvements:
- [x] Implement onset/offset detection for syllable boundaries.
- [x] Group consecutive pitch detections, filter noise < 50ms.
- [x] Calculate dynamic GAP from first pitch time.
- [ ] Add break line padding (2-8 beats) to prevent word concatenation.
- [x] Implement fallback timing for unrecognized syllables.
- [x] Use median/average pitch for multi-pitch syllables.
- [ ] Ensure overall length matches audio duration (within 10s tolerance).
- [ ] Validate break line timing against reference files.
- [ ] Test edge cases: silent sections, pitch detection failures.