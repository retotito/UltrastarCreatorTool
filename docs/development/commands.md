# Server Commands

> **Status:** Current · **Last updated:** 2026-07-17

## Prerequisites

Make sure you're in the project root:

```bash
cd /Users/retokupfer/projects/SongCreatorGrok
```

---

## Backend Server (FastAPI — port 8001)

```bash
source .venv/bin/activate
cd backend
python main.py
```

Or in one line from the project root:

```bash
.venv/bin/python backend/main.py
```

The API will be available at **http://localhost:8001**. Health check: `http://localhost:8001/api/health`

---

## Frontend Dev Server (Vite — port 5173)

```bash
cd frontend
npm run dev
```

The app will be available at **http://localhost:5173**. The Vite proxy automatically forwards `/api/*` requests to the backend on port 8001.

---

## Both Servers (quick start)

Open two terminal tabs and run:

**Tab 1 — Backend:**
```bash
cd /Users/retokupfer/projects/SongCreatorGrok && .venv/bin/python backend/main.py
```

To run in the background without it getting suspended (output goes to `/tmp/songcreator.log`):
```bash
cd /Users/retokupfer/projects/SongCreatorGrok && .venv/bin/python3 backend/main.py >> /tmp/songcreator.log 2>&1 &
tail -f /tmp/songcreator.log
```

**Tab 2 — Frontend:**
```bash
cd /Users/retokupfer/projects/SongCreatorGrok/frontend && npm run dev
```

---

## Debugging the Tauri App

**Run the built .app from Terminal** (shows all stdout/stderr live):
```bash
"/Applications/UltrastarCreatorTool.app/Contents/MacOS/UltrastarCreatorTool"
```

**Tail the backend sidecar log** (written by the app on each launch):
```bash
tail -f ~/Library/Logs/com.ultrastar.creator/backend.log
```

**Check if the backend sidecar is running:**
```bash
ps aux | grep backend | grep -v grep
lsof -i :8001
```

**Check if port 8001 is bound after launch:**
```bash
lsof -i :8001
```

**Verify the sidecar binary is present and executable:**
```bash
ls -la "/Applications/UltrastarCreatorTool.app/Contents/MacOS/backend"
```

**Open macOS Console.app** and filter by process name `UltrastarCreatorTool` for system-level crash logs.

---

## Kill Servers

**Kill backend** (if port 8001 is already in use):
```bash
pkill -f "python.*main.py"
```

Or by port:
```bash
lsof -ti :8001 | xargs kill -9
```

**Kill frontend** (port 5173):
```bash
lsof -ti :5173 | xargs kill -9
```

**Kill both:**
```bash
pkill -f "python.*main.py"; lsof -ti :5173 | xargs kill -9
```

---

## VS Code Tasks

You can also start the servers using the VS Code task runner (`Cmd+Shift+P` → "Tasks: Run Task"):

- **Start Backend Server** — runs `cd backend && python main.py`
- **Start Frontend Dev Server** — runs `npm run dev`

---

## Build Frontend for Production

```bash
cd frontend
npx vite build
```

Output goes to `frontend/dist/`.

---

## Full App Build (Tauri + Sidecar)

```bash
cd /Users/retokupfer/projects/SongCreatorGrok && ./build_local.sh
```

Output: `frontend/src-tauri/target/release/bundle/` — produces `.app` + `.dmg` on Mac.

> **Platform note for `tauri.conf.json` `targets`:**
> - **Mac**: keep `"targets": "all"` (produces `.app` + `.dmg`; requires `brew install create-dmg`)
> - **Windows**: change to `"targets": ["msi"]` — the NSIS `.exe` installer cannot handle the large Python sidecar binary due to file size limits. See [building/windows.md](building/windows.md) for details.

---

## Install Dependencies

**Python (backend):**
```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
```

**Node (frontend):**
```bash
cd frontend
npm install
```

**Node config file:**
```bash
"files.maxMemoryForLargeFilesMB": 4096
```



