# Tauri App — Build & Debug

## Build

Run from project root:

```bash
./build_local.sh
```

This will:
1. Build the Python backend sidecar with PyInstaller
2. Copy the binary to `frontend/src-tauri/binaries/`
3. Build the Tauri `.app` and `.dmg` via `npm run tauri build`

Output `.dmg` → `frontend/src-tauri/target/release/bundle/dmg/`

---

## Install

Open the DMG folder in Finder:
```bash
open "/Users/retokupfer/projects/SongCreatorGrok/frontend/src-tauri/target/release/bundle/dmg/"
```

Or mount and install directly:
```bash
open "/Users/retokupfer/projects/SongCreatorGrok/frontend/src-tauri/target/release/bundle/dmg/Ultrastar Creator_2.0.0_aarch64.dmg"
```

---

## Log Files

The backend sidecar writes all stdout/stderr to a log file on each launch:

```
~/Library/Logs/com.ultrastar.creator/backend.log
```

**Tail live:**
```bash
tail -f ~/Library/Logs/com.ultrastar.creator/backend.log
```

**Open in Console.app:**
```bash
open -a Console ~/Library/Logs/com.ultrastar.creator/backend.log
```

---

## Run from Terminal (see live output)

Launching from Terminal shows `[backend]` lines directly:

```bash
"/Applications/Ultrastar Creator.app/Contents/MacOS/Ultrastar Creator"
```

---

## Debugging Checklist

1. **Is the sidecar binary present?**
   ```bash
   ls -la "/Applications/Ultrastar Creator.app/Contents/MacOS/backend"
   ```

2. **Is port 8001 bound after launch?**
   ```bash
   lsof -i :8001
   ```

3. **Is the sidecar process running?**
   ```bash
   ps aux | grep backend | grep -v grep
   ```

4. **Check the log for startup errors:**
   ```bash
   tail -50 ~/Library/Logs/com.ultrastar.creator/backend.log
   ```

5. **System crash logs** — open Console.app and filter by `Ultrastar Creator`

---

## Architecture

| Component | In dev | In release |
|-----------|--------|------------|
| Frontend | Vite dev server (port 5173) | Bundled static files in `.app` |
| Backend | Manually started `python backend/main.py` | PyInstaller sidecar auto-started by Tauri |
| API base | `http://localhost:8001` | `http://localhost:8001` (same) |

The sidecar is only spawned in `--release` builds (`#[cfg(not(debug_assertions))]`).
