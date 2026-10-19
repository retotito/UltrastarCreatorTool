# Architecture Overview

> **Status:** Current · **Last updated:** 2026-10-19

## Components

```
┌──────────────────────── Tauri app (Rust) ────────────────────────┐
│  starts / stops the backend sidecar, hosts the web view          │
│                                                                  │
│  ┌──────────── Svelte UI ────────────┐      HTTP (localhost:8001)│
│  │ Project launcher                  │ ───────────────────────┐  │
│  │ Step 1 Upload    Step 2 Lyrics    │                        │  │
│  │ Step 3 Generate  Step 4 Editor    │                        ▼  │
│  │ Step 5 Export                     │        ┌──── Python sidecar ────┐
│  └───────────────────────────────────┘        │ FastAPI  (main.py)     │
│                                               │ services/  AI pipeline │
└───────────────────────────────────────────────│ sessions/  JSON state  │
                                                └────────────────────────┘
```

| Component | Tech | Location | Role |
|---|---|---|---|
| Desktop shell | Tauri 2 (Rust) | `frontend/src-tauri/` | Launches the PyInstaller-built backend from the app resources, kills it on exit, writes its log |
| UI | Svelte + Vite | `frontend/src/` | Wizard steps, piano-roll editor, playback, mic sing-along |
| API client | JavaScript | `frontend/src/services/api.js` | All backend calls; `http://localhost:8001/api` in Tauri, `/api` (Vite proxy) in the browser |
| Backend | Python 3.12, FastAPI | `backend/main.py` | HTTP endpoints, session management, orchestration of the pipeline |
| Pipeline services | onnxruntime, librosa, WhisperX, Demucs, pyphen, uroman, mido | `backend/services/` | One module per stage, see [pipeline.md](pipeline.md) |

The UI only talks to the backend over HTTP. It doesn't know the backend is written in Python.
See [ADR 0001](../decisions/0001-keep-python-sidecar.md) for why the backend stays a Python sidecar.

## Backend modules

| Module | Responsibility |
|---|---|
| `services/vocal_separation.py` | Demucs v4 (`htdemucs`, two stems): vocals + instrumental |
| `services/hyphenation.py` | Syllable splitting of lyrics with pyphen |
| `services/bpm_detection.py` | BPM (essentia if available, else librosa), beat phase, BPM refinement from syllable times |
| `services/pitch_detection.py` | Pitch track (FCPE, PYIN fallback) and the pitch of each syllable |
| `services/forced_alignment.py` | Forced alignment of the lyrics (Tune Studio aligner, uroman) |
| `services/syllable_alignment.py` | Chooses the alignment engine, with fallbacks |
| `services/lyrics_search.py` | Lyrics from LRCLIB |
| `services/melisma.py` | Splits long syllables into `~` notes where the pitch moves |
| `services/alignment_whisper.py` | Syllable timing from WhisperX word/char timestamps (current primary aligner) |
| `services/alignment.py` | Energy-based fallback aligner |
| `services/onset_snapping.py` | Moves syllable starts to nearby spectral onsets |
| `services/ultrastar.py` | Writes the UltraStar `.txt` and the processing summary |
| `services/midi_export.py` | MIDI export of the notes |
| `services/reference_comparison.py` | Compares output with a verified reference `.txt` (timing metrics) |
| `services/audio_cleanup.py` | Mutes cleanup sections in the vocal track |
| `services/backup_service.py` | Session backups |
| `utils/` | Logging, error types and handlers |

## Data storage

| What | Dev mode | Installed app (macOS) |
|---|---|---|
| Sessions, uploads, downloads, references | `backend/` (next to the source) | `~/Library/Application Support/com.ultrastar.creator/` |
| Backend log | console | `~/Library/Logs/com.ultrastar.creator/backend.log` |
| Whisper / alignment models | `~/.cache/huggingface/hub`, `~/.cache/torch/hub/checkpoints` | same |

On Windows the app data lives in `%APPDATA%\com.ultrastar.creator`.

## Session lifecycle

1. **Upload** (Step 1): audio is normalised and stored; optionally Demucs separates the vocals.
2. **Lyrics** (Step 2): WhisperX transcribes the vocals as a suggestion; the user corrects and hyphenates. Whisper
   word/char timestamps are stored in the session (`whisper_words`, `whisper_chars`).
3. **Generate** (Step 3): BPM → pitch → alignment → `.txt` / MIDI / summary, stored in `session["result"]`.
4. **Edit** (Step 4): the editor changes notes; segment tools re-run parts of the pipeline on a time range.
5. **Export** (Step 5): ZIP with `.txt`, audio, images, MIDI.

Sessions are JSON files in `sessions/` and are loaded at backend start.
