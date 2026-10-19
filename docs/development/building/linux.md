# Linux Build & Debug

> **Status:** Current · **Last updated:** 2026-05-21

## Prerequisites

1. **Rust** — [rustup.rs](https://rustup.rs) (includes `cargo`)
2. **Node.js 18+** — via NodeSource or [nodejs.org](https://nodejs.org)
3. **Python 3.10+** — available via `apt`
4. **ffmpeg** — via `apt`
5. **WebKit2GTK** — required by Tauri for rendering

---

## First-Time Setup

```bash
# System dependencies
sudo apt update
sudo apt install -y \
  python3 python3-pip python3-venv \
  ffmpeg \
  curl build-essential \
  libwebkit2gtk-4.1-dev libgtk-3-dev \
  libayatana-appindicator3-dev librsvg2-dev \
  patchelf file

# Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Clone repo
git clone https://github.com/retotito/UltrastarCreatorTool.git
cd UltrastarCreatorTool

# Python venv and backend dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install pyinstaller

# AI packages (code bundled into sidecar; model weights ~2 GB downloaded on first app launch)
# CPU-only PyTorch — swap 'cpu' for 'cu121' etc. if you have a CUDA GPU
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install whisperx demucs

# Frontend dependencies
cd frontend && npm install && cd ..
```

---

## Code Changes Required Before Building

### 1. Fix the data directory for Linux

In `backend/main.py`, find `_user_data_dir()` and replace the `else` branch so it handles Linux:

```python
def _user_data_dir() -> str:
    """Return a persistent data directory that survives PyInstaller temp extraction."""
    if getattr(sys, 'frozen', False):
        if sys.platform == 'win32':
            base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'com.ultrastar.creator')
        elif sys.platform == 'darwin':
            base = os.path.expanduser("~/Library/Application Support/com.ultrastar.creator")
        else:  # Linux
            base = os.path.expanduser("~/.local/share/com.ultrastar.creator")
    else:
        base = os.path.dirname(__file__)
    return base
```

### 2. Set Tauri build target to AppImage

In `frontend/src-tauri/tauri.conf.json`, change:
```json
"targets": "all"
```
to:
```json
"targets": ["appimage"]
```

> The default `"all"` is for Mac. On Linux `"all"` would also attempt `.deb` and `.rpm` — `.rpm` requires additional tooling. AppImage is the most portable format.

---

## Build

Run from project root:

```bash
# 1. Build Python sidecar
source .venv/bin/activate
.venv/bin/pyinstaller backend/backend.spec --distpath dist-backend --noconfirm --clean

# 2. Copy sidecar to Tauri resources
rm -rf frontend/src-tauri/resources/backend
cp -r dist-backend/backend frontend/src-tauri/resources/backend

# 3. Build Tauri AppImage
cd frontend
npm run tauri build
```

The `backend.spec` auto-detects ffmpeg/ffprobe via `which ffmpeg` — no manual path changes needed as long as ffmpeg is installed.

Output: `frontend/src-tauri/target/release/bundle/appimage/ultrastar-creator_2.0.5_amd64.AppImage`

---

## Install / Run

AppImage requires no installation — just make it executable and run:

```bash
chmod +x ultrastar-creator_2.0.5_amd64.AppImage
./ultrastar-creator_2.0.5_amd64.AppImage
```

---

## Debug / Logs

**Run from terminal** (shows all stdout/stderr live):
```bash
./ultrastar-creator_2.0.5_amd64.AppImage
```

**Tail the backend sidecar log:**
```bash
tail -f ~/.local/share/com.ultrastar.creator/logs/backend.log
```

**Check if the backend sidecar is running:**
```bash
ps aux | grep backend | grep -v grep
lsof -i :8001
```

---

## Clean App Data

To fully reset (remove sessions, uploads, logs):
```bash
rm -rf ~/.local/share/com.ultrastar.creator
```

**Delete AI model cache** (optional — only needed to force a full re-download of the ~2 GB models):
```bash
rm -rf ~/.cache/huggingface
rm -rf ~/.cache/torch
```

---

## Linux-Specific Differences from macOS

| Topic | macOS | Linux |
|---|---|---|
| Backend binary | `backend` | `backend` |
| Tauri WebView | WKWebView | WebKit2GTK |
| App data dir | `~/Library/Application Support/com.ultrastar.creator` | `~/.local/share/com.ultrastar.creator` |
| Log dir | `~/Library/Logs/com.ultrastar.creator` | `~/.local/share/com.ultrastar.creator/logs` |
| Build output | `.app` + `.dmg` | `.AppImage` |
| Tauri targets | `"all"` | `["appimage"]` |

---

## Dev Mode (without building)

**Backend:**
```bash
cd /path/to/UltrastarCreatorTool
source .venv/bin/activate
python backend/main.py
```

**Frontend:**
```bash
cd /path/to/UltrastarCreatorTool/frontend
npm run dev
```
