# Ultrastar Creator Tool

<p align="center">
  <img src="frontend/src-tauri/icons/icon.png" alt="Ultrastar Creator Icon" width="128" />
</p>

> **Latest release: v2.0.4** — Custom app icon, negative beat support, metronome divisor, CRLF import fix, m4a support, and more. See [Changelog](#changelog) below.

A tool to create **Ultrastar karaoke songs** with the help of AI. It guides you through 4 steps — from uploading audio to exporting a ready-to-play Ultrastar .txt file — using automatic vocal separation, pitch detection, and lyrics alignment to do the heavy lifting, while you fine-tune the result in a built-in piano roll editor.

**Goal**: Make it easy for anyone to create Ultrastar songs, so more people sing together. 🎤

## Download

> **Early access — not yet code-signed.** See instructions below to open it on macOS.

| Platform | Status | Link |
|----------|--------|------|
| macOS (Apple Silicon / ARM) | ✅ Available | [Google Drive](https://drive.google.com/drive/folders/1sFrLy6YNSMU56L0XAZ8I3tmb6WcEh1Oc?usp=sharing) |
| macOS (Intel x86) | ✅ Available | [Google Drive](https://drive.google.com/drive/folders/1sFrLy6YNSMU56L0XAZ8I3tmb6WcEh1Oc?usp=sharing) |
| Windows | 🔜 Coming soon | Same folder above |
| Linux | 🔜 Coming soon | Same folder above |

### Opening on macOS (Gatekeeper bypass)

Because the app is not yet code-signed, macOS will block it on first launch. To open it:

1. Double-click the `.dmg` and drag **Ultrastar Creator** to your Applications folder.
2. Try to open it — macOS will show a *"cannot be opened because the developer cannot be verified"* message. Click **Cancel**.
3. Go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to the Ultrastar Creator entry.
4. Confirm by clicking **Open** in the dialog that appears.

You only need to do this once.

### Troubleshooting / Debug Logs

If something goes wrong inside the app, you can view the backend log in real time:

```bash
tail -f ~/Library/Logs/com.ultrastar.creator/backend.log
```

This shows all processing steps — vocal separation progress, transcription, pitch detection, and any errors.

## How it Works

| Step | What you do | What the tool does |
|------|-------------|-------------------|
| **1. Upload** | Upload a song (full mix or vocals-only) | Optionally separates vocals using Demucs |
| **2. Lyrics & Generate** | Review/edit lyrics, then click "Generate" | Auto-hyphenates syllables, detects BPM, analyzes pitch, aligns syllables to audio, produces Ultrastar file |
| **3. Editor** | Review and adjust notes in the piano roll | Shows waveform, plays MIDI pitches, supports grid snap, BPM calibration |
| **4. Export** | Add cover/background art, video info, download your files | Exports ZIP with Ultrastar .txt (including asset headers), MIDI, images, and audio |

## Screenshots

### Home — Project Launcher
![Project Launcher](docs/screenshots/Step0-Homescreen.png)

### Step 1 — Upload Audio & Extract Vocals
![Step 1 - Upload](docs/screenshots/Step1-upload%20audio%20and%20extract%20vocals.png)

### Step 2 — Edit Lyrics & Generate Ultrastar File
![Step 2 - Lyrics & Generate](docs/screenshots/Step2-extract%20and%20edit%20lyrics%20and%20generate%20ultrastar%20file.png)

### Step 3 — Piano Roll Editor
![Step 3 - Editor](docs/screenshots/Step3-Piano%20Roll%20Editor.png)
![Step 3 - Edit Note](docs/screenshots/Step3-edit%20note.png)
![Step 3 - Looping](docs/screenshots/Step3-Looping.png)
![Step 3 - Sing Along](docs/screenshots/Step3-sing%20along%20inside%20editor.png)

### Step 4 — Export Files
![Step 4 - Export](docs/screenshots/Step4-Export%20Files.png)

## Features

### AI Pipeline
- **Vocal separation** (Demucs v4) — isolates vocals from full mix
- **Pitch detection** (PYIN) — robust pitch tracking via librosa
- **Forced alignment** (WhisperX) — syllable-level timing with ~50ms median accuracy, energy-based fallback
- **BPM detection** — automatic tempo analysis with beat-phase alignment
- **Onset snapping** — refines syllable boundaries using spectral onsets
- **One-click generation** — audio → Ultrastar format in minutes

### Piano Roll Editor
- **Full note editing** — move, resize, split, merge, delete notes
- **Golden/Rap note types** — visual indicators (★ gold, orange rap)
- **Grid alignment** (Ctrl+B) — snap the entire beat grid to match the audio
- **GAP adjustment** (Ctrl+G) — click any grid line to set the GAP position
- **BPM calibration tool** — manually place beat markers on the waveform; linear regression over all markers calculates the exact BPM; persistent grey reference markers survive across calibration sessions
- **Text editor** — edit raw Ultrastar content with live preview
- **Session notes** — jot down reminders while editing; saved automatically per session and restored next time you open the editor
- **Flag markers** — place green marker lines anywhere on the canvas (right-click → Add Flag); drag, nudge ±1 beat, or delete via right-click; shown as green ticks on the scrollbar; persisted per session
- **Custom scrollbar** — fully custom div-based slider; the handle tracks the canvas center beat so zooming in/out never moves it; playhead and flag ticks align perfectly with no browser-offset math
- **Select all** (Ctrl+A) — select all notes for bulk move
- **Undo/Redo** — full snapshot history (notes, BPM, GAP, downbeat offset, headers)
- **Waveform display** — smooth high-resolution waveform (750 peaks/sec) showing full-mix or vocal track alongside notes
- **Downbeat alignment** — independent measure grid offset stored as `#DOWNBEATOFFSET` header
- **Metronome** — accent clicks aligned to the downbeat for timing reference
- **Extra headers** — YOUTUBE, COVER, GENRE and other Ultrastar tags
- **Context menus** — right-click on notes or empty space for quick actions

### Playback & Audio
- **Sing-along mode** — use your microphone to sing along with the song in real time, see your pitch trail overlaid on the notes for realistic editing
- **Vocal trace** — automatically runs the separated vocal audio through the same pitch detector as the mic; draws a pink trail behind the notes so you can see exactly where the vocals land and align notes by eye. Right-click a pink frame to insert a note at the exact position and pitch (snapped to grid). Toggle with **V**.
- **Mic device selection** — choose from available microphones with volume gain control
- **Active mode badge** — pulsing red MIC / pink VOCAL indicator on the canvas when recording
- **MIDI pitch playback** — hear synthesized pitches during playback (triangle wave)
- **Vocal mute toggle** — isolate MIDI pitches or hear both
- **Audio scrub** — drag the playhead to hear frozen audio grains at any position
- **Drag pitch preview** — hear the pitch while moving notes

### Loop & Navigation
- **Loop regions** — Shift+drag on the time ruler to set a loop, with draggable handles
- **Playhead scrub** — drag the playhead handle with audio + MIDI preview
- **Smart cursors** — move/resize indicators when hovering over notes
- **Keyboard shortcuts** — Space (play/pause), L (loop), Escape (clear loop/deselect)
  - **←/→** — seek −5s/+5s (no selection), or move selected note(s) ±1 beat
  - **Shift+←/→** — seek −1s/+1s (no selection), or move selected note(s) ±4 beats
  - **↑/↓** — shift selected note(s) pitch ±1 semitone
  - **Shift+↑/↓** — shift selected note(s) pitch ±1 octave

### Project Management
- **Project launcher** — create, open, rename, and delete song projects
- **Session persistence** — projects survive server restarts

### Export
- **Song Assets** — attach a cover image (480×480), background image (1920×1080), and video filename to the song; both images go through an interactive **crop tool** (pan + zoom) before upload
- **Asset headers** — `#COVER`, `#BACKGROUND`, `#VIDEO`, `#VIDEOGAP` are written into the Ultrastar `.txt` automatically whenever an asset is saved
- **One-click ZIP** — downloads all files in a ready-to-drop Ultrastar folder: `.txt` with all headers, images renamed to `Artist - Title [CO].jpg` / `[BG].jpg`, MIDI, audio, and processing summary
- **Ultrastar .txt** — standard format, compatible with all Ultrastar players
- **MIDI export** — pitch data as MIDI file
- **Processing summary** — detailed report of the AI pipeline

## Architecture

- **Frontend**: Svelte + Vite (port 5173) — 4-step wizard UI with project launcher
- **Backend**: Python FastAPI (port 8001) — service-based with isolated AI workers

## AI Models

| Model | Purpose | Status |
|-------|---------|--------|
| PYIN (librosa) | Pitch detection | Built-in |
| WhisperX | Forced alignment (syllable timing) | Optional (falls back to vanilla Whisper, then user lyrics) |
| openai-whisper | Transcription fallback | Optional (if WhisperX unavailable) |
| Demucs v4 | Vocal separation | Optional (can upload vocals directly) |

> **Torch dependency:** WhisperX, openai-whisper, and Demucs all require PyTorch. If `torch` doesn't support your platform (e.g. older Intel Macs), the app still works — you just skip AI-powered transcription and vocal separation. Upload vocals directly and provide lyrics manually instead.

## Quick Start

### Prerequisites

- **Python 3.10–3.12** with `pip` (3.13+ may have compatibility issues with some AI libraries)
- **Node.js 18+** with `npm`
- **FFmpeg** — required by audio processing libraries

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### 1. Clone & Setup Backend

```bash
git clone https://github.com/retotito/UltrastarCreatorTool.git
cd UltrastarCreatorTool

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install core Python dependencies
pip install -r backend/requirements.txt

# Install AI dependencies (optional — requires PyTorch ~2GB, Python 3.10-3.12)
# Skip these if torch doesn't support your platform
pip install demucs==4.0.1        # vocal separation
pip install whisperx openai-whisper  # transcription + forced alignment

# Optional: Pre-download AI models (~3GB, avoids delay on first use)
python backend/download_models.py

# Start backend server (port 8001)
cd backend && python main.py
```

> **Note:** The first time you run "Generate", WhisperX and Demucs will download their AI models automatically (~1–3GB). This can take several minutes depending on your internet connection. You can avoid this wait by running `python backend/download_models.py` after install.

### 2. Setup Frontend (new terminal)

```bash
cd UltrastarCreatorTool/frontend

# Install Node dependencies
npm install

# Start dev server (port 5173)
npm run dev
```

### 3. Open the App

Open **http://localhost:5173** in your browser. The Vite proxy automatically forwards `/api/*` requests to the backend on port 8001.

## Changelog

### v2.0.4
- **Custom app icon** — new branded 1024×1024 icon (with padding) used across macOS, Windows, Android, and iOS builds
- **Negative beats / early GAP** — removed the beat-0 lower-bound constraint; GAP can now be set before the first note, allowing songs that start before beat 0
- **Metronome divisor** — three click intervals: quarter note (♩), half note (𝅗𝅥), and full bar (𝄺); buttons appear when metronome is active
- **Dynamic BEATS_PER_QUARTER** — `Math.round(bpm / 30)` so the grid and downbeat modulo work correctly with fractional BPM values
- **CRLF import fix** — Windows `.txt` files with `\r\n` line endings now parse correctly (notes no longer missing after import)
- **m4a / AAC support** — audio is pre-converted to WAV before Demucs so m4a uploads no longer fail vocal separation
- **Vocal download extension** — downloaded vocals always use `.mp3` instead of inheriting the wrong uploaded-file extension
- **Audio ended event** — playback animation frame is now cancelled when the audio track ends naturally, preventing a stale playhead
- **Word-space red dot** — the indicator dot is drawn on the note *missing* the trailing space (not on the following note)
- **Auto-fix word spaces across breaks** — `autoFixWordSpaces()` correctly moves leading spaces to the trailing position on the previous note even across line breaks

### v2.0.3 and earlier
- Bohning UltraStar format compliance (BPM×4, `#LANGUAGE`, no blank line after headers, `#MP3`, GAP/beat-0, YASS linebreaks, trailing word spaces)
- Trailing word-space feature with visual red-dot indicator and one-click auto-fix

## VS Code Tasks

Use the pre-configured tasks to start servers:
- **Start Frontend Dev Server** — `cd frontend && npm run dev`
- **Start Backend Server** — `cd backend && python main.py`

## Project Structure

```
frontend/           Svelte app
  src/
    components/     Step1Upload, Step2Lyrics, Step3Generate, Step4Editor, Step5Export, StepNavigation, ProjectLauncher
    stores/         Shared state (appStore.js)
    services/       API client (api.js)
backend/            FastAPI server
  services/         AI service modules (pitch, alignment, BPM, vocals, ultrastar, midi)
  workers/          Subprocess isolation for AI tasks
  utils/            Logging, error handling
frontendTest/       Test audio + lyrics files
docs/               Architecture docs, plan
```
