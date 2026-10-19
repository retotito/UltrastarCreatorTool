# Windows Build & Debug

> **Status:** Current · **Last updated:** 2026-06-06

## Prerequisites

1. **Rust** — [rustup.rs](https://rustup.rs) (includes `cargo`)
2. **Visual Studio Build Tools** — "Desktop development with C++" workload
3. **Node.js + npm** — [nodejs.org](https://nodejs.org)
4. **Python 3.10+** — [python.org](https://python.org)
5. **WebView2** — pre-installed on Windows 10/11

---

## First-Time Setup

```powershell
cd C:\Users\retok\Projects\UltrastarCreatorTool

# Create venv and install backend dependencies
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
pip install pyinstaller

# Install AI packages (bundled into the sidecar at build time — not downloaded by the user)
# The Python CODE must be in the sidecar; model WEIGHTS (~2 GB) are downloaded on first app launch.
# CPU-only PyTorch (smaller); swap 'cpu' for 'cu121' etc. if you have a CUDA GPU.
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install whisperx demucs

# Install frontend dependencies
cd frontend
npm install
```

---

## Build

Run from project root:

```powershell
cd C:\Users\retok\Projects\UltrastarCreatorTool

# 1. Build Python sidecar
.venv\Scripts\pyinstaller.exe backend/backend.spec --distpath dist-backend --noconfirm --clean

# 2. Copy sidecar to Tauri resources
Remove-Item -Recurse -Force frontend\src-tauri\resources\backend -ErrorAction SilentlyContinue
Copy-Item -Recurse dist-backend\backend frontend\src-tauri\resources\backend

# 3. Set Tauri build target to MSI only
# The NSIS (.exe) installer cannot handle the large sidecar binary.
# Before building, ensure tauri.conf.json has: "targets": ["msi"]
# (The default "all" is for Mac; change it back after building on Windows.)

# 4. Build Tauri app
cd frontend
npm run tauri build
```

> **Important:** `tauri.conf.json` must have `"targets": ["msi"]` when building on Windows.
> The NSIS `.exe` installer fails with the Python sidecar due to file size limits.
> On Mac, use `"targets": "all"` (the default in the repo) to produce `.app` + `.dmg`.

Output: `frontend\src-tauri\target\release\bundle\msi\UltrastarCreatorTool_x.x.x_x64_en-US.msi`

---

## Install

Before installing a new build, kill any running instance first (otherwise the installer
cannot overwrite locked DLLs):

```powershell
Stop-Process -Name "backend" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "ultrastar-creator" -Force -ErrorAction SilentlyContinue
```

Then run the `.exe` installer.

---

## Debug / Logs

The backend writes logs to:
```
%LOCALAPPDATA%\com.ultrastar.creator\logs\backend.log
```

**Open in Notepad** (quick read):
```powershell
notepad "$env:LOCALAPPDATA\com.ultrastar.creator\logs\backend.log"
```

**Clear the log** (start fresh before a new test run):
```powershell
Clear-Content "$env:LOCALAPPDATA\com.ultrastar.creator\logs\backend.log"
```

**Simple tail** (fails if the file doesn't exist yet):
```powershell
Get-Content "$env:LOCALAPPDATA\com.ultrastar.creator\logs\backend.log" -Wait -Tail 50
```

**Safe tail** (waits for the file to appear first — use this one):
```powershell
while (-not (Test-Path "$env:LOCALAPPDATA\com.ultrastar.creator\logs\backend.log")) {
    Write-Host "Waiting for backend to start..."; Start-Sleep 1
}
Get-Content "$env:LOCALAPPDATA\com.ultrastar.creator\logs\backend.log" -Wait -Tail 50
```

---

## Clean App Data

To fully reset (remove sessions, uploads, logs):
```powershell
Remove-Item -Recurse -Force "$env:APPDATA\com.ultrastar.creator" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\com.ultrastar.creator" -ErrorAction SilentlyContinue
```

---

## Full Reset Before a New Build

Run these 4 steps in order before installing a fresh build:

**1. Kill running processes** (so the installer can overwrite locked files):
```powershell
Stop-Process -Name "backend" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "ultrastar-creator" -Force -ErrorAction SilentlyContinue
```

**2. Uninstall the app** via Windows Settings → Apps → UltrastarCreatorTool → Uninstall.

**3. Clean app data** (sessions, logs):
```powershell
Remove-Item -Recurse -Force "$env:APPDATA\com.ultrastar.creator" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\com.ultrastar.creator" -ErrorAction SilentlyContinue
```

**4. Delete AI model cache** (optional — only needed to force a full re-download of the ~2 GB models):
```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\huggingface" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\torch" -ErrorAction SilentlyContinue
```

> Step 4 is not required for normal builds — the new version will find the cached models automatically.

---

## Windows-Specific Differences from macOS

| Topic | macOS | Windows |
|---|---|---|
| Backend binary | `backend` | `backend.exe` |
| Tauri WebView origin | `tauri://localhost` | `http://tauri.localhost` |
| App data dir | `~/Library/Application Support/com.ultrastar.creator` | `%APPDATA%\com.ultrastar.creator` |
| Log dir | `~/Library/Logs/com.ultrastar.creator` | `%LOCALAPPDATA%\com.ultrastar.creator\logs` |
| Build script | `./build_local.sh` | Manual steps above |


## Tauri dev
**backend:
```
cd C:\Users\retok\Projects\UltrastarCreatorTool
.venv\Scripts\activate
cd backend
python main.py
```

**frontend:
```
cd C:\Users\retok\Projects\UltrastarCreatorTool\frontend
npm run tauri dev
```