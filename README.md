# Ultrastar Creator Tool

<p align="center">
  <img src="frontend/src-tauri/icons/icon.png" alt="Ultrastar Creator Icon" width="128" />
</p>

> **Latest release: v4.1.0** — Freestyle note support, editor bug fixes, and [97 supported languages](#supported-languages) for lyrics & Ultrastar song generation. See [Changelog](#changelog) below.

A tool to create **Ultrastar karaoke songs** with the help of AI. It guides you through 4 steps — from uploading audio to exporting a ready-to-play Ultrastar .txt file — using automatic vocal separation, pitch detection, and lyrics alignment to do the heavy lifting, while you fine-tune the result in a built-in piano roll editor.

**Goal**: Make it easy for anyone to create Ultrastar songs, so more people sing together. 🎤

## Download

> **Early access — not yet code-signed.** See instructions below to open it on macOS.

| Platform | Status | Link |
|----------|--------|------|
| macOS (Apple Silicon / ARM) | ✅ Available | [Google Drive](https://drive.google.com/drive/folders/1sFrLy6YNSMU56L0XAZ8I3tmb6WcEh1Oc?usp=sharing) |
| macOS (Intel x86) | ✅ Available | [Google Drive](https://drive.google.com/drive/folders/1sFrLy6YNSMU56L0XAZ8I3tmb6WcEh1Oc?usp=sharing) |
| Windows | ✅ Available | [Google Drive](https://drive.google.com/drive/u/0/folders/1ZYr0LAnmvewVIIbvbDlu5pK6F9XCBxjr) |
| Linux | 🔜 Coming soon | Same folder above |

### Opening on macOS (Gatekeeper bypass)

Because the app is not yet code-signed, macOS will block it on first launch. To open it:

1. Double-click the `.dmg` and drag **UltrastarCreatorTool** to your Applications folder.
2. Try to open it — macOS will show a *"cannot be opened because the developer cannot be verified"* message. Click **Cancel**.
3. Go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to the UltrastarCreatorTool entry.
4. Confirm by clicking **Open** in the dialog that appears.

You only need to do this once.

### Upgrading from v3.1.0 or earlier to v4.0.0

> ⚠️ **If you are upgrading from v3.1.0 or an older version**, follow these steps before installing:

1. **Close the app.** Since v3.1.0 the backend is killed automatically when the window closes. If you are on an older version (v3.0.x or below), the backend may still be running — kill it manually:
   - **macOS:** `pkill -f backend`
   - **Windows:** `taskkill /IM backend.exe /F`
2. **Uninstall the old app first** before installing the new version.
   - macOS: drag **UltrastarCreatorTool** out of Applications to Trash, then empty Trash.
   - Windows: uninstall via Settings → Apps before running the new installer.
3. **Sessions from v3.0.x or earlier** may have compatibility issues. Export your songs as ZIP before upgrading if you want to be safe.

Sessions created in **v3.1.0** should be compatible with v4.0.0

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

## Video Tutorials

| Overview — Getting Started | Pitch Line, Vocal Tracing & Sing Along |
|:--------------------------:|:--------------------------------------:|
| [![Overview](https://img.youtube.com/vi/zKw03mhrYX8/hqdefault.jpg)](https://www.youtube.com/watch?v=zKw03mhrYX8&t=5s) | [![Pitch Line & Vocal Trace](https://img.youtube.com/vi/p4ihQaDhwfg/hqdefault.jpg)](https://www.youtube.com/watch?v=p4ihQaDhwfg) |

| Looping & Scrubbing | BPM & Metronome |
|:-------------------:|:---------------:|
| [![Looping & Scrubbing](https://img.youtube.com/vi/WwAZQlhqSwE/hqdefault.jpg)](https://www.youtube.com/watch?v=WwAZQlhqSwE&t=2s) | [![BPM & Metronome](https://img.youtube.com/vi/L8jnov5M-XY/hqdefault.jpg)](https://www.youtube.com/watch?v=L8jnov5M-XY) |

| V4 - AI Limits and Workarounds |
|:-------------------------------:|
| [![V4 - AI Limits and Workarounds](https://img.youtube.com/vi/WOKcdjpthh0/hqdefault.jpg)](https://www.youtube.com/watch?v=WOKcdjpthh0) |

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
![Step 3 - BPM Tapper](docs/screenshots/Step3-BPM%20Tapper.png)

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
- **BPM tapper** — tap the beat in a modal (click or press Enter) to measure BPM; shows live BPM with apply buttons for 1×–8× multipliers; play/pause and jump-to-GAP controls included; metronome muted while tapper is open
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
- **Pitch tolerance / difficulty** — select Hard (±1), Medium (±2), or Easy (±3) semitone tolerance for hit detection in both mic and vocal trace modes
- **Pitch line** — precomputes an offline full-song pitch analysis of the vocal audio and draws it as thin continuous dots across the entire canvas (behind all other overlays); toggled on/off with a dedicated button; useful for a quick global pitch overview without running the vocal trace in real time
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

- **Desktop shell**: Tauri (Rust) — starts the bundled backend and hosts the UI
- **Frontend**: Svelte + Vite (port 5173 in dev) — step-by-step wizard UI with project launcher
- **Backend**: Python FastAPI sidecar (port 8001) — runs the AI pipeline and stores sessions

See [docs/architecture/overview.md](docs/architecture/overview.md) and [docs/architecture/pipeline.md](docs/architecture/pipeline.md).

## AI Models

| Model | Purpose | Status |
|-------|---------|--------|
| PYIN (librosa) | Pitch detection | Built-in |
| [Tune Studio aligner](https://huggingface.co/tuneperfect/tunestudio-aligner) by [Tune Studio](https://github.com/ZerNico/tunestudio): Meta's [MMS forced aligner](https://huggingface.co/MahmoudAshraf/mms-300m-1130-forced-aligner) fine-tuned on singing | Syllable timing: aligns your lyrics to the vocals | Downloaded in setup. Weights licensed **CC-BY-NC-4.0** (non-commercial) |
| WhisperX | Lyric suggestions from the vocals; fallback timing | Optional (falls back to vanilla Whisper, then user lyrics) |
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

## Supported Languages

The app supports lyrics transcription and Ultrastar song generation in **97 languages** via Whisper:

<details open>
<summary><strong>🌍 Show all 97 supported languages</strong></summary>

| Code | Language | Code | Language | Code | Language |
|------|----------|------|----------|------|----------|
| `af` | Afrikaans | `sq` | Albanian | `am` | Amharic |
| `ar` | Arabic | `hy` | Armenian | `az` | Azerbaijani |
| `ba` | Bashkir | `eu` | Basque | `be` | Belarusian |
| `bn` | Bengali | `bs` | Bosnian | `br` | Breton |
| `bg` | Bulgarian | `ca` | Catalan | `zh` | Chinese |
| `hr` | Croatian | `cs` | Czech | `da` | Danish |
| `nl` | Dutch | `en` | English | `et` | Estonian |
| `fo` | Faroese | `fi` | Finnish | `fr` | French |
| `gl` | Galician | `ka` | Georgian | `de` | German |
| `el` | Greek | `gu` | Gujarati | `ht` | Haitian Creole |
| `ha` | Hausa | `haw` | Hawaiian | `he` | Hebrew |
| `hi` | Hindi | `hu` | Hungarian | `is` | Icelandic |
| `id` | Indonesian | `it` | Italian | `ja` | Japanese |
| `jw` | Javanese | `kn` | Kannada | `kk` | Kazakh |
| `km` | Khmer | `ko` | Korean | `lo` | Lao |
| `la` | Latin | `lv` | Latvian | `ln` | Lingala |
| `lt` | Lithuanian | `lb` | Luxembourgish | `mk` | Macedonian |
| `mg` | Malagasy | `ms` | Malay | `ml` | Malayalam |
| `mt` | Maltese | `mi` | Maori | `mr` | Marathi |
| `mn` | Mongolian | `my` | Myanmar | `ne` | Nepali |
| `no` | Norwegian | `nn` | Nynorsk | `oc` | Occitan |
| `ps` | Pashto | `fa` | Persian | `pl` | Polish |
| `pt` | Portuguese | `pa` | Punjabi | `ro` | Romanian |
| `ru` | Russian | `sa` | Sanskrit | `sr` | Serbian |
| `sn` | Shona | `sd` | Sindhi | `si` | Sinhala |
| `sk` | Slovak | `sl` | Slovenian | `so` | Somali |
| `es` | Spanish | `su` | Sundanese | `sw` | Swahili |
| `sv` | Swedish | `tl` | Tagalog | `tg` | Tajik |
| `ta` | Tamil | `tt` | Tatar | `te` | Telugu |
| `th` | Thai | `bo` | Tibetan | `tr` | Turkish |
| `tk` | Turkmen | `uk` | Ukrainian | `ur` | Urdu |
| `uz` | Uzbek | `vi` | Vietnamese | `cy` | Welsh |
| `yi` | Yiddish | `yo` | Yoruba | | |

</details>

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Contributing & Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, tests, conventions
- [docs/](docs/README.md) — architecture, features, build guides, decisions
