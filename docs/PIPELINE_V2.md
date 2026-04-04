# Pipeline V2 — Syllable-First Alignment

## Overview

The core idea: **find each syllable in the audio first, then extract pitch**.
This replaces the old approach of detecting pitches first and guessing syllable boundaries.

**Two key tools, used in sequence:**
1. **Whisper (ASR)** — discovers WHAT words are sung (word recognition)
2. **MFA (Forced Aligner)** — finds exactly WHEN each word/syllable is sung (precise timing)

```
OLD (broken):
  Audio → Detect all pitches → Guess which pitch = which syllable → Wrong timing

NEW (correct):
  Audio → Whisper (what words?) → User corrects → MFA (precise timing) → Extract pitch → Done
```

---

## Prerequisites

- **Python 3.12** (upgrade from 3.9)
- **OpenAI Whisper** — speech recognition, discovers what words are sung
- **Montreal Forced Aligner (MFA)** — precise syllable timing (needs Python 3.10+)

### Upgrade Steps

```bash
# 1. Install Python 3.12 via Homebrew
brew install python@3.12

# 2. Verify
python3.12 --version

# 3. Recreate virtual environment
cd /Users/retokupfer/projects/SongCreatorGrok
rm -rf .venv
python3.12 -m venv .venv

# 4. Install dependencies
.venv/bin/pip install -r backend/requirements.txt

# 5. Install Whisper (ASR — word discovery)
.venv/bin/pip install openai-whisper

# 6. Install MFA (forced alignment — precise timing)
.venv/bin/pip install montreal-forced-aligner

# 7. Download MFA English model
.venv/bin/mfa model download acoustic english_mfa
.venv/bin/mfa model download dictionary english_mfa

# 8. (Optional) Try CREPE again — may work on Python 3.12
.venv/bin/pip install crepe

# 9. (Optional) Try Metal GPU support
.venv/bin/pip install tensorflow-metal
```

---

## Pipeline Steps

### Step 1: Upload Vocal Audio + Select Language

```
Input:  Cleaned vocal audio file (.wav or .mp3) + language selection
Output: vocal.wav stored in session, language stored
```

- User uploads isolated vocal audio (extracted via Demucs or provided directly)
- User selects language (English, German, French, etc.)
- Frontend plays preview so user can confirm it sounds right
- Language is used by both Whisper (ASR) and MFA (alignment)

---

### Step 2: Whisper Transcription → Lyrics Text Field ⭐ KEY STEP

```
Input:  vocal.wav + language
Output: Transcribed lyrics auto-filled in the text area

Example:
  Whisper hears:
    "the heart is a bloom"
    "shoots up through the stony ground"
    "there's no room"
    "no space to rent in this town"
    ...
```

**How it works:**
1. Run Whisper locally on the vocal audio with `word_timestamps=True`
2. Whisper discovers what words are being sung
3. Use Whisper's segment boundaries to insert line breaks after natural phrases
   (Whisper groups words into segments with start/end times — gaps between
   segments indicate phrase boundaries)
4. Auto-fill the lyrics text area with the transcription
5. User reviews and corrects:
   - Fix misspelled words (Whisper may mishear lyrics)
   - Fix line breaks if needed (merge or split phrases)
   - Add any words Whisper missed
   - Remove any words Whisper hallucinated
6. The user is the "reconciliation layer" — they see what Whisper heard
   and fix it to match reality

**Whisper settings:**
- Model: `medium` or `large-v3` (balance accuracy vs speed)
- Language: set explicitly from Step 1 selection
- `word_timestamps=True` for phrase boundary detection
- Runs locally via `openai-whisper` pip package

**Why Whisper + User is better than user-only:**
- Whisper gives you 90%+ correct starting text — much faster than typing
- Since the text comes FROM the audio, it naturally matches what's sung
- User only needs to fix the ~10% Whisper gets wrong
- No more phantom words or missing words causing MFA misalignment

**Why Whisper + User is better than Whisper-only:**
- Whisper can mishear sung words (singing ≠ speech)
- Proper spelling matters for Ultrastar display
- User knows the song and can catch mistakes quickly

---

### Step 3: Auto-Hyphenate + Validate

```
Input:  Corrected lyrics text (from Step 2)
Output: Hyphenated lyrics with syllable markers

Example:
  The heart is a bloom        →  The heart is a bloom
  Shoots up through the       →  Shoots up through the
  stony ground                →  sto-ny ground
  There's no room             →  There's no room
  No space to rent            →  No space to rent
  in this town                →  in this town
  Beautiful day               →  Beau-ti-ful day
```

- Uses `pyphen` library (backend endpoint `/api/hyphenate`)
- Frontend shows side-by-side: original vs hyphenated
- User can manually edit/correct the hyphenation
- Single-syllable words stay as-is (no hyphens needed)
- Each hyphen = one syllable boundary = one Ultrastar note

**Syllable count preview:**
```
  Line 1: "The heart is a bloom"           → 5 syllables
  Line 2: "Shoots up through the sto-ny ground" → 7 syllables
  ...
  Total: 329 syllables → 329 Ultrastar notes
```

---

### Step 4: MFA Forced Alignment (Precise Timing)

```
Input:  vocal.wav + hyphenated lyrics (verified by user)
Output: Start time + end time for each syllable

Example:
  "The"   → 14.20s - 14.75s  (duration: 0.55s)
  "heart" → 14.80s - 15.25s  (duration: 0.45s)
  "is"    → 15.30s - 15.45s  (duration: 0.15s)
  "a"     → 15.50s - 15.65s  (duration: 0.15s)
  "bloom" → 15.70s - 16.80s  (duration: 1.10s)
  [silence gap 2.5s]
  "Shoots" → 19.30s - 19.75s (duration: 0.45s)
  ...
```

**How MFA works:**
1. Takes the vocal audio + user-verified text transcript
2. Uses an acoustic model trained on speech/singing
3. Knows what each phoneme sounds like (e.g., "th", "eh", "h", "aa", "r", "t")
4. Walks through the audio finding where each phoneme occurs
5. Groups phonemes back into syllables/words
6. Returns precise timestamps (~10-20ms accuracy)

**Because lyrics were transcribed FROM the audio and verified by user,
MFA gets a perfect word match → accurate timing.**

**Whisper vs MFA — different jobs:**
- Whisper: "What words are sung?" (word discovery, ~100-200ms timing)
- MFA: "When exactly is each phoneme?" (precise timing, ~10-20ms)
- We need Whisper's word discovery + MFA's timing precision

**Fallback if MFA fails:**
- If MFA can't align a segment, fall back to energy-based detection
- Log a warning so user knows which sections need manual review

---

### Step 5: Detect BPM

```
Input:  vocal.wav (or original full mix for better beat detection)
Output: BPM value (e.g., 272.56)
```

- Uses `librosa.beat.beat_track()`
- Multiply by 2 for Ultrastar convention (if needed)
- Compare with reference file BPM if available
- This is independent of syllable alignment — just needs the audio

---

### Step 6: Extract Pitch Per Syllable

```
Input:  vocal.wav + syllable timestamps from Step 4
Output: MIDI note number for each syllable

Example:
  "The"   (14.20s - 14.75s) → analyze pitch in this window → E4 (MIDI 64)
  "heart" (14.80s - 15.25s) → analyze pitch in this window → E4 (MIDI 64)
  "is"    (15.30s - 15.45s) → analyze pitch in this window → B3 (MIDI 59)
  "a"     (15.50s - 15.65s) → analyze pitch in this window → E4 (MIDI 64)
  "bloom" (15.70s - 16.80s) → analyze pitch in this window → E4 (MIDI 64)
```

**How it works:**
1. For each syllable, extract the audio segment between start_time and end_time
2. Run pitch detection (PYIN or CREPE) on just that segment
3. Take the **median** pitch value (filters out vibrato/noise)
4. Convert Hz → MIDI note number
5. Round to nearest semitone

**Pitch smoothing (post-processing):**
- If adjacent syllables differ by only 1 semitone, snap to the more common pitch
- If a syllable has very low pitch confidence, interpolate from neighbors
- Flag uncertain pitches for manual review in Piano Roll

---

### Step 7: Calculate GAP

```
Input:  First syllable start time from Step 4
Output: GAP value in milliseconds

Example:
  First syllable "The" starts at 14.20s
  GAP = 14200ms (or 14.20 × 1000)
```

- **Golden Rule**: Must be accurate within 100ms
- MFA alignment gives us precise first-syllable timing
- Compare with reference GAP if available
- Log warning if gap seems unusually large (> 30s) or small (< 1s)

---

### Step 8: Convert to Ultrastar Beats

```
Input:  Syllable timestamps (seconds) + BPM + GAP
Output: Ultrastar beat positions and durations

Formula:
  start_beat = (start_time - GAP/1000) × (BPM / 60)
  duration_beats = (end_time - start_time) × (BPM / 60)

  Minimum duration: 1 beat
  Round to nearest integer

Example (BPM=272.56, GAP=14200ms):
  "The"   start=14.20s → beat 0,  duration = 0.55s × 4.54 = 2.5 → 3 beats
  "heart" start=14.80s → beat 3,  duration = 0.45s × 4.54 = 2.0 → 2 beats
  "is"    start=15.30s → beat 5,  duration = 0.15s × 4.54 = 0.7 → 1 beat
  "a"     start=15.50s → beat 6,  duration = 0.15s × 4.54 = 0.7 → 1 beat
  "bloom" start=15.70s → beat 7,  duration = 1.10s × 4.54 = 5.0 → 5 beats
```

---

### Step 9: Generate Break Lines

```
Input:  Syllable timestamps + line boundaries from lyrics
Output: Break line markers between phrases

Rule:
  If time gap between last syllable of line N and first syllable of line N+1 > 0.5s
  → Insert break line: "- break_beat"

Example:
  "bloom" ends at 16.80s (beat 12)
  "Shoots" starts at 19.30s (beat 23)
  Gap = 2.5s → Insert: "- 14" (2 beats after "bloom" ends)
```

- Break beat = last_note_end + 2 beats (padding)
- If gap is less than 0.5s, no break (same phrase continues)
- Break lines create the visual line separation in Ultrastar games

---

### Step 10: Assemble Ultrastar File

```
Output format:

#ARTIST:U2
#TITLE:Beautiful Day
#BPM:272.56
#GAP:14200
#LANGUAGE:English
#MP3:song.mp3

: 0 3 64 The
: 3 2 64  heart
: 5 1 59  is
: 6 1 64  a
: 7 5 64  bloom
- 14
: 23 2 58 Shoots
: 25 2 58  up
...
E
```

---

### Step 11: Compare with Reference (Optional)

```
Input:  Generated .txt + Reference .txt
Output: Note-by-note diff with statistics

Comparison:
  Syllable | Ref Start | Gen Start | Diff | Ref Pitch | Gen Pitch | Diff
  "The"    | 0         | 0         | 0    | 52        | 64        | +12
  "heart"  | 16        | 3         | -13  | 52        | 64        | +12
  ...

Summary:
  - Average pitch offset: +12 semitones (one octave — possible octave error)
  - Average timing offset: -8 beats (generated too early)
  - GAP difference: -8ms (excellent)
```

- Helps identify systematic biases
- Stored for future learning (Phase 2+)
- Displayed in Piano Roll as overlay

---

### Step 12: Piano Roll Editor (Manual Corrections)

```
Display generated notes on a piano roll:
  - X axis: time (mm:ss)
  - Y axis: MIDI pitch
  - Each note = colored rectangle
  - Reference notes shown as transparent overlay

User can:
  - Drag notes to adjust pitch/timing
  - Resize notes to adjust duration
  - Play audio synced to cursor position
  - See low-confidence notes highlighted
  - Undo/redo changes
```

- All corrections stored as AI-output vs user-correction pairs
- Used for future learning system

---

### Step 13: Export

```
Output files:
  - Ultrastar .txt (with corrections applied)
  - MIDI file
  - Vocal audio (.wav)
  - Processing summary
  - Full package (.zip)
```

---

## Pipeline Diagram

```
┌────────────────────────────────────┐
│ 1. Upload Vocal Audio              │
│    + Select Language               │
└──────┬─────────────────────────────┘
       │
┌──────▼─────────────────────────────┐
│ 2. Whisper ASR Transcription ⭐     │
│    → Auto-fill lyrics text field   │
│    → User reviews & corrects       │
│    (text comes FROM audio =        │
│     naturally matches what's sung)  │
└──────┬─────────────────────────────┘
       │
┌──────▼─────────────────────────────┐
│ 3. Auto-Hyphenate + Validate       │
│    → Syllable markers for Ultrastar│
└──────┬─────────────────────────────┘
       │
┌──────▼─────────────────────────────┐
│ 4. MFA Forced Alignment            │
│    Audio + verified lyrics         │
│    → precise timing per syllable   │
└──────┬─────────────────────────────┘
       │
┌──────▼───────┐    ┌──────────────┐
│ 5. Detect    │    │ 6. Extract   │
│    BPM       │    │    Pitch per │
│              │    │    Syllable  │
└──────┬───────┘    └──────┬───────┘
       │                   │
┌──────▼───────────────────▼───────┐
│  7. Calculate GAP                │
│  8. Convert to Ultrastar Beats   │
│  9. Generate Break Lines         │
│ 10. Assemble Ultrastar File      │
└──────┬───────────────────────────┘
       │
┌──────▼───────────────────────────┐
│ 11. Compare with Reference (opt) │
└──────┬───────────────────────────┘
       │
┌──────▼───────────────────────────┐
│ 12. Piano Roll Editor            │
│     Manual corrections           │
└──────┬───────────────────────────┘
       │
┌──────▼───────────────────────────┐
│ 13. Export                       │
│     .txt, MIDI, .wav, .zip       │
└──────────────────────────────────┘
```

---

## Upgrade Checklist

- [x] Install Python 3.12 via Homebrew
- [x] Recreate .venv with Python 3.12
- [x] Reinstall all pip dependencies
- [x] Install MFA + download English acoustic model
- [x] Test MFA with test_vocal.wav + lyrics.txt
- [ ] Install Whisper (`pip install openai-whisper`)
- [ ] Implement Whisper transcription backend endpoint
- [ ] Auto-fill lyrics text field from Whisper output
- [ ] Add language selector to Step 1 UI
- [ ] Add phrase-level line breaks from Whisper segments
- [ ] Remove old band-aids (_remove_phantom_words, _fix_bloated_syllables)
- [ ] Test CREPE on Python 3.12 (may work now)
- [ ] Test tensorflow-metal GPU (may work now)
- [x] Update alignment.py to use real MFA
- [ ] Update pitch_detection.py to extract pitch per syllable window
- [x] Update ultrastar.py to use MFA timestamps
- [ ] Update COMMANDS.md with new Python version
- [ ] Test full pipeline end-to-end
- [ ] Compare output with reference U2 Beautiful Day
