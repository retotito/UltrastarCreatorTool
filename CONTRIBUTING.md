# Contributing

Thanks for helping make Ultrastar Creator Tool better. This page covers how to set up the project, run it, test it
and get a change merged.

## Setup

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

### Test tools

```bash
.venv/bin/pip install -r backend/requirements-dev.txt
```

## Running the app

| What | Command |
|---|---|
| Backend (port 8001) | `.venv/bin/python backend/main.py` |
| Frontend in the browser (port 5173) | `cd frontend && npm run dev` |
| Desktop app (dev) | see [docs/development/building/macos.md](docs/development/building/macos.md) |

VS Code: the tasks *Start Backend Server* and *Start Frontend Dev Server* do the same. More commands are in
[docs/development/commands.md](docs/development/commands.md).

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest
```

Unit tests run in CI on every push and pull request. See [docs/development/testing.md](docs/development/testing.md)
for markers, fixtures, the evaluation songs and how to write tests.

## Project layout

```
backend/            FastAPI sidecar: main.py (endpoints), services/ (pipeline), tests/, scripts/
frontend/           Svelte UI (src/), Tauri shell (src-tauri/)
docs/               Developer documentation, start at docs/README.md
```

The architecture is described in [docs/architecture/overview.md](docs/architecture/overview.md) and the AI pipeline in
[docs/architecture/pipeline.md](docs/architecture/pipeline.md).

## Making a change

1. Branch from `main`.
2. Keep pipeline logic in `backend/services/` as functions that can be tested; endpoints in `main.py` should only
   read the request, call services and build the response.
3. Add or update tests for what you changed. A bug fix starts with a test that reproduces it.
4. Update the docs that describe what you changed, and their **Last updated** date. Record significant choices as a
   decision record in `docs/decisions/`.
5. Add a line to [CHANGELOG.md](CHANGELOG.md) for anything a user would notice.
6. Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `fix: ...`, `feat: ...`,
   `docs: ...`, `test: ...`, `refactor: ...`, `chore: ...`.

### Pull request checklist

- [ ] `pytest` passes
- [ ] Docs and changelog updated where needed
- [ ] For pipeline changes: before/after numbers from the evaluation songs
- [ ] For UI changes: tested in the desktop app, screenshot if the look changed

## Releases

Release builds are made by `.github/workflows/build.yml` when a `v*` tag is pushed. Run the
[release checklist](docs/development/release-checklist.md) before tagging.
