# Ultrastar Song Generator v2 — Project Plan

> **Status:** Archived · **Last updated:** 2026-04-03  
> Historical v2 project plan; kept for context.

## Why Starting Fresh

The v1 codebase had:
- Monolithic `main.py` with patched-in fixes causing instability
- PYIN pitch detection (signal processing, inaccurate for singing)
- Fixed 2-beat syllable duration (completely wrong timing)
- No forced alignment (guessing syllable boundaries)
- No visual editor (no way to see or correct results)
- Frequent server crashes due to poor error handling

## What We Keep From v1

- `docs/PIPELINE.md` — Processing pipeline definition (updated below)
- `frontendTest/test_vocal.wav` — Test vocal audio file
- `frontendTest/lyrics.txt` — Test lyrics (U2 - Beautiful Day)
- Lessons learned: GAP calculation, BPM detection, syllable splitting logic

## Competitive Analysis

### UltraSinger (Main Competitor)
Open-source AI tool that creates Ultrastar files from YouTube links or audio files.
Uses Demucs + Whisper + basic pitch detection.

| Feature | UltraSinger | Our Project | Advantage |
|---------|-------------|-------------|-----------|
| Pitch Detection | Basic AI | **CREPE** (deep learning) | Ours |
| Syllable Timing | Whisper timestamps | **MFA** (forced alignment) | Ours |
| Vocal Separation | Demucs | Demucs | Same |
| Visual Editor | None | **Piano Roll Editor** | Ours |
| Correction Learning | None | **Stores corrections** | Ours |
| Reference Learning | None | **Compare with originals** | Ours |
| Lyrics Input | Auto-transcribed (error-prone) | User-provided (accurate) | Ours |
| Auto Hyphenation | None | **Built-in hyphenator** | Ours |
| YouTube Download | Yes | No (not needed for quality) | Theirs |

### Community Best Practices (from UltraStar creators)
- **Lyrics Hyphenator**: Auto-split words into syllables, user can correct
- **GAP Golden Rule**: GAP accuracy within 100ms is critical for playability
- **Pitch Smoothing**: AI often creates too many micro-notes from vibrato
- **YASS Editor**: Gold standard for manual correction (our piano roll replaces this)

---

## New Architecture

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | **Svelte + Vite** | Step-by-step wizard UI + Piano Roll editor |
| Backend | **Python + FastAPI** | API server, thin route layer |
| Pitch Detection | **CREPE** | Deep learning pitch detection (replaces PYIN) |
| Forced Alignment | **Montreal Forced Aligner (MFA)** | Syllable-level timing (replaces fixed 2-beat) |
| Vocal Separation | **Demucs v4** | Extract vocals from full mix |
| Audio Analysis | **librosa** | BPM detection, audio loading |
| Hyphenation | **pyphen** | Auto-syllable splitting for lyrics |
| MIDI | **mido** | MIDI file generation |

### Folder Structure

```
SongCreatorGrok/
├── frontend/                  # Svelte app (separate from backend)
│   ├── src/
│   │   ├── App.svelte
│   │   ├── app.css
│   │   ├── main.ts
│   │   ├── components/
│   │   │   ├── StepNavigation.svelte   # Step wizard with back/forward
│   │   │   ├── Step1Upload.svelte      # Upload audio + vocal extraction
│   │   │   ├── Step2Lyrics.svelte      # Lyrics input + syllable preview
│   │   │   ├── Step3Generate.svelte    # Generate Ultrastar files
│   │   │   ├── Step4Editor.svelte      # Piano Roll visual editor
│   │   │   └── Step5Export.svelte      # Export & download results
│   │   ├── stores/
│   │   │   └── appStore.js             # Shared state (current step, data)
│   │   └── services/
│   │       └── api.js                  # All AJAX calls to backend
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── backend/
│   ├── main.py                         # FastAPI app (routes only, thin)
│   ├── requirements.txt
│   ├── services/
│   │   ├── __init__.py
│   │   ├── pitch_detection.py          # CREPE wrapper
│   │   ├── alignment.py                # MFA wrapper
│   │   ├── vocal_separation.py         # Demucs wrapper
│   │   ├── bpm_detection.py            # librosa BPM
│   │   ├── ultrastar.py                # Ultrastar .txt generation
│   │   ├── hyphenation.py              # Auto-syllable splitting (pyphen)
│   │   ├── reference_comparison.py     # Compare AI output with reference files
│   │   └── midi_export.py              # MIDI file generation
│   ├── workers/
│   │   ├── __init__.py
│   │   └── task_runner.py              # Run AI models in subprocess
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── error_handler.py            # Global error handling middleware
│   │   └── logger.py                   # Structured logging
│   ├── corrections/                    # Stored user corrections (for future learning)
│   ├── reference_songs/                # Verified Ultrastar files + learned biases
│   └── downloads/                      # Generated output files
│
├── frontendTest/                       # Test files (kept from v1)
│   ├── test_vocal.wav
│   └── lyrics.txt
│
├── docs/
│   ├── PIPELINE.md                     # Pipeline definition (from v1, updated)
│   └── PLAN_V2.md                      # This file
│
└── .vscode/
    └── tasks.json                      # Dev server tasks
```

---

## Application Flow

### Overview

```
Step 1          Step 2          Step 3          Step 4          Step 5
Upload &        Lyrics          Generate        Piano Roll      Export &
Extraction  ──► Input       ──► Ultrastar   ──► Editor      ──► Download
            ◄──             ◄──             ◄──             ◄──
         (back/forward navigation between all steps)
```

### Step 1: Upload & Vocal Extraction

```
User uploads MP3/WAV
    │
    ├── Full song? ──► Demucs v4 separates vocals
    │                  ──► Preview extracted vocals
    │                  ──► "Sounds good?" or "Download & fix externally"
    │
    └── Already isolated vocals? ──► Skip extraction, use directly
    │
    ──► Store vocal audio in session
    ──► Optionally upload reference Ultrastar .txt (for learning)
    ──► [Next →]
```

**API Endpoints:**
- `POST /api/upload` — Upload audio file
- `POST /api/extract-vocals` — Run Demucs separation
- `GET /api/preview-audio/{id}` — Stream audio for preview
- `POST /api/reference/upload/{id}` — Upload verified reference Ultrastar file

### Step 2: Lyrics Input

```
User provides lyrics:
    ├── Type/paste lyrics manually
    ├── Upload .txt file
    └── Load test lyrics (dev mode)

Auto-Hyphenation:
    ├── User pastes plain lyrics: "It is a beautiful day"
    ├── Click "Auto-Hyphenate" → "It is a beau-ti-ful day"
    ├── User can review and correct hyphenation
    └── Supports multiple languages via pyphen

Syllable rules:
    ├── Each line = one phrase (becomes a break line in Ultrastar)
    ├── Hyphens split syllables within words: "beau-ti-ful"
    ├── [RAP] / [/RAP] markers for rap sections
    └── Empty lines are ignored

Preview:
    ├── Show parsed syllable count
    ├── Highlight syllable splits visually
    └── Show line-by-line breakdown

──► Store lyrics in session
──► [Next →]
```

**API Endpoints:**
- `POST /api/lyrics` — Submit and validate lyrics
- `POST /api/hyphenate` — Auto-hyphenate lyrics via pyphen
- `GET /api/test-lyrics` — Load test lyrics (dev mode)

### Step 3: Generate Ultrastar Files

```
Processing pipeline (all via AJAX with progress updates):

1. BPM Detection
   └── librosa beat_track → BPM × 2 for Ultrastar

2. Pitch Detection (CREPE)
   └── AI-based pitch → MIDI notes (much more accurate than PYIN)

3. Forced Alignment (MFA)
   └── Align lyrics syllables to audio timestamps
   └── Each syllable gets: start_time, end_time, confidence

4. GAP Calculation
   └── First aligned syllable start time → milliseconds

5. Note Generation
   └── For each syllable:
       ├── start_beat = (start_time - gap) × bpm × 2 / 60
       ├── duration_beats = (end_time - start_time) × bpm × 2 / 60
       ├── pitch = CREPE MIDI note at syllable midpoint
       └── Format: ": start duration pitch syllable"

6. Break Lines
   └── Between lyric lines: "- end_beat start_beat" with 2-8 beat padding

7. Validation
   └── Total duration vs audio duration (within 10s tolerance)
   └── Flag low-confidence syllables for manual review

──► Show processing log in real-time
──► Auto-compare with reference file if uploaded
──► [Next →]
```

**API Endpoints:**
- `POST /api/generate` — Start full generation pipeline
- `GET /api/generate/status/{id}` — Poll processing progress
- `GET /api/generate/result/{id}` — Get generated files
- `POST /api/reference/compare/{id}` — Compare AI output with reference

### Step 4: Piano Roll Editor

```
Visual display:
    ┌────────────────────────────────────────────────┐
    │ C5 │  ████              ██████████             │
    │ B4 │        ████████                           │
    │ A4 │                             ████████      │
    │ G4 │                                      ████ │
    │    │  The   heart  is    a      bloom          │
    │    0────5────10────15────20────25────30─────────│
    │         ▲ playback cursor                      │
    │    [▶ Play] [⏸ Pause] [⏹ Stop]                │
    └────────────────────────────────────────────────┘

Features:
    ├── Scroll horizontally through the song
    ├── Zoom in/out on timeline
    ├── Click note to select
    ├── Drag note to adjust pitch (vertical) or timing (horizontal)
    ├── Drag note edges to adjust duration
    ├── Playback with cursor sync
    ├── Highlight low-confidence notes (from MFA)
    ├── Reference note overlay (ghost notes from verified file)
    ├── Undo/redo
    └── Break line indicators between phrases

──► Store corrections (AI output vs user correction pairs)
──► [Next →]
```

**API Endpoints:**
- `POST /api/corrections` — Save user corrections for future learning
- `GET /api/reference/notes/{id}` — Get reference notes for overlay

### Step 5: Export & Download

```
Available downloads:
    ├── Ultrastar .txt file (with user corrections applied)
    ├── MIDI file
    ├── Vocal audio (.wav)
    ├── Processing summary (confidence scores, warnings)
    └── Full package (.zip with all files)

Options:
    ├── [Download All as ZIP]
    ├── [Download .txt only]
    ├── [Copy to clipboard] (Ultrastar text)
    └── [Start Over] (go back to Step 1)
```

**API Endpoints:**
- `POST /api/export` — Generate final files with corrections
- `GET /api/download/{type}/{id}` — Download specific file
- `GET /api/download/zip/{id}` — Download all as ZIP

---

## AI Models Detail

### CREPE (Pitch Detection)
- **What**: Deep learning model for monophonic pitch detection
- **Input**: Audio waveform
- **Output**: Pitch (Hz) + confidence per time frame
- **Why better**: Trained on millions of samples, handles singing voice well
- **Install**: `pip install crepe`

### Montreal Forced Aligner (MFA)
- **What**: Aligns text transcription to audio at phoneme/word level
- **Input**: Audio + text transcript
- **Output**: Start time, end time, confidence per word/phoneme
- **Why better**: Gives actual syllable timing instead of guessing
- **Install**: `pip install montreal-forced-aligner`
- **Note**: Requires acoustic model download (`mfa model download acoustic english_mfa`)

### Demucs v4 (Vocal Separation)
- **What**: AI model to separate audio into stems (vocals, drums, bass, other)
- **Input**: Full song audio
- **Output**: Isolated vocal track
- **Install**: `pip install demucs`

---

## Learning System

### Three Sources of Training Data

1. **Reference Ultrastar Files** (Highest Value)
   - User uploads a verified/original Ultrastar .txt alongside the audio
   - System compares AI output vs reference note-by-note
   - Tracks pitch, timing, and duration biases
   - Stored in `backend/reference_songs/`

2. **Piano Roll Corrections** (Medium Value)
   - User edits notes in Step 4 editor
   - System stores AI output vs user correction pairs
   - Stored in `backend/corrections/`

3. **Bulk Reference Import** (Future)
   - Import a library of verified Ultrastar files
   - Run pipeline on each, compare with verified result

### Learning Phases

| Phase | Data Required | What It Does |
|-------|-------------|--------------|
| Phase 1 (now) | 0 songs | Store all comparisons, no adjustments |
| Phase 2 | 5+ reference songs | Calculate average biases, apply simple offsets |
| Phase 3 | 20+ reference songs | Genre-specific corrections |
| Phase 4 | 100+ reference songs | Train neural network for post-processing |

### Reference Comparison Format

```json
{
  "session_id": "abc123",
  "source": "reference",
  "metadata": { "artist": "U2", "title": "Beautiful Day" },
  "comparison": {
    "summary": {
      "matched_notes": 321,
      "avg_pitch_diff": 1.4,
      "avg_duration_diff": -2.8,
      "avg_start_diff": -3.2,
      "pitch_bias": "slightly_high",
      "duration_bias": "low",
      "timing_bias": "low"
    }
  }
}
```

---

## Build Checklist

### Phase 1: Project Setup
- [x] Clean workspace (remove old files, keep frontendTest/ and docs/)
- [x] Create new folder structure (frontend/, backend/)
- [x] Set up Python virtual environment + install dependencies
- [x] Set up Svelte + Vite frontend
- [x] Configure VS Code tasks (frontend dev, backend dev)
- [x] Verify both servers start without errors

### Phase 2: Backend Core
- [x] `main.py` — FastAPI app with CORS, error handling middleware
- [x] `utils/logger.py` — Structured logging
- [x] `utils/error_handler.py` — Global error handler (never crash server)
- [x] `services/bpm_detection.py` — BPM detection with librosa
- [x] `services/pitch_detection.py` — CREPE pitch detection wrapper
- [x] `services/alignment.py` — MFA forced alignment wrapper
- [x] `services/vocal_separation.py` — Demucs vocal extraction
- [x] `services/hyphenation.py` — Auto-syllable splitting (pyphen)
- [x] `services/reference_comparison.py` — Compare AI vs reference files
- [x] `services/ultrastar.py` — Ultrastar .txt file generation
- [x] `services/midi_export.py` — MIDI file generation
- [x] `workers/task_runner.py` — Run AI in isolated subprocess
- [ ] Test each service independently with test_vocal.wav

### Phase 3: API Endpoints
- [x] `POST /api/upload` — File upload handling
- [x] `POST /api/extract-vocals` — Vocal separation endpoint
- [x] `GET /api/preview-audio/{id}` — Audio streaming
- [x] `POST /api/lyrics` — Lyrics validation
- [x] `POST /api/hyphenate` — Auto-hyphenation
- [x] `GET /api/test-lyrics` — Test lyrics loader
- [x] `GET /api/test-vocal` — Test vocal loader
- [x] `POST /api/generate` — Full pipeline generation
- [x] `GET /api/generate/result/{id}` — Result retrieval
- [x] `POST /api/reference/upload/{id}` — Upload reference Ultrastar file
- [x] `POST /api/reference/compare/{id}` — Compare AI vs reference
- [x] `GET /api/reference/stats` — View learned biases
- [x] `GET /api/reference/notes/{id}` — Reference notes for editor overlay
- [x] `POST /api/corrections` — Save user corrections
- [x] `POST /api/export` — Export with corrections
- [x] `GET /api/download/{type}/{id}` — File download

### Phase 4: Frontend — Step Wizard
- [x] `App.svelte` — Main layout with step navigation + backend health indicator
- [x] `stores/appStore.js` — Shared state management + referenceData store
- [x] `services/api.js` — AJAX helper with error handling
- [x] `StepNavigation.svelte` — Back/forward/step indicator
- [x] `Step1Upload.svelte` — File upload + vocal preview + reference upload
- [x] `Step2Lyrics.svelte` — Lyrics input + auto-hyphenation + syllable preview
- [x] `Step3Generate.svelte` — Generate with progress + reference comparison display
- [x] `Step5Export.svelte` — Download results

### Phase 5: Piano Roll Editor
- [x] Canvas-based note rendering
- [x] Horizontal scrolling + zoom
- [x] Note selection + drag to edit
- [x] Duration adjustment (drag edges)
- [x] Audio playback with cursor sync
- [x] Reference note overlay (ghost notes from verified file)
- [ ] Undo/redo system
- [ ] Low-confidence note highlighting
- [x] Break line visualization

### Phase 6: Integration & Testing
- [ ] End-to-end test with test_vocal.wav + lyrics.txt
- [ ] Test with reference Ultrastar file comparison
- [ ] Verify Ultrastar output matches expected format
- [ ] Test error handling (missing files, bad audio, etc.)
- [ ] Verify correction storage works
- [ ] Verify reference comparison storage works
- [ ] Performance test (large files, long songs)

### Phase 7: Polish
- [ ] Loading states and progress indicators
- [ ] Error messages (user-friendly)
- [ ] Responsive design
- [ ] Keyboard shortcuts for piano roll
- [x] README with setup instructions
- [ ] Git clean history + push to GitHub
