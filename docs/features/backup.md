# Backup Feature — Design Spec

> **Status:** Current · **Last updated:** 2026-06-23

## What is a backup?

A backup is a snapshot of the UltraStar `.txt` file at a point in time —
the same content that `save_editor_state` reconstructs from notes + BPM + GAP.
It does **not** back up audio files; only the song/note data.

---

## File Storage

```
backend/sessions/backups/<session_id>/backup_<unix_timestamp_ms>.txt
```

- One subfolder per session under `SESSIONS_DIR/backups/`
- Each backup is a plain `.txt` file named by Unix timestamp in milliseconds
- Max backups per session: **20** (oldest auto-deleted when limit is exceeded)
- Folder is created on first backup, deleted when session is deleted

---

## Backend

### New file: `backend/services/backup_service.py`

Pure functions — no FastAPI, no global state:

```python
get_backup_dir(session_id) -> str
list_backups(session_id) -> list[dict]   # [{ts, filename, size_bytes}] newest first
create_backup(session_id, txt_content) -> dict   # returns the new entry
delete_backup(session_id, ts) -> bool
restore_backup(session_id, ts) -> str    # returns txt_content
prune_backups(session_id, max_keep=20)   # called after every create
```

### New routes in `main.py` (tagged `backup`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/sessions/{id}/backup` | Create backup now — reads current `.txt` from session result |
| `GET` | `/api/sessions/{id}/backups` | List all backups (newest first) |
| `DELETE` | `/api/sessions/{id}/backup/{ts}` | Delete one backup by timestamp |
| `POST` | `/api/sessions/{id}/backup/{ts}/restore` | Restore: overwrite session state from backup |

### Session delete cleanup (`delete_session_endpoint`)

Add after `shutil.rmtree(upload_dir)`:

```python
backup_dir = os.path.join(SESSIONS_DIR, "backups", session_id)
if os.path.isdir(backup_dir):
    shutil.rmtree(backup_dir, ignore_errors=True)
```

### Storage manager (`get_storage_info`)

Add a `backups` list and `backups_size` to each session row:

```python
backup_dir = os.path.join(SESSIONS_DIR, "backups", sid)
backup_files = []
if os.path.isdir(backup_dir):
    for fname in sorted(os.listdir(backup_dir), reverse=True):
        fpath = os.path.join(backup_dir, fname)
        backup_files.append({"label": "backup", "path": fpath, "size": _file_size(fpath)})
backups_size = sum(f["size"] for f in backup_files)
# backups_size is included in total_size
# backup_files is returned as "backup_files" on the session row
```

Frontend (StorageManager): render backup files as a nested `<details>` at the bottom of `sm-file-list`, **closed by default**:

```html
<!-- only rendered when backup_files.length > 0 -->
<details class="sm-file-details sm-backup-details">
  <summary>{backup_files.length} backup files · {formatSize(backups_size)}</summary>
  <div class="sm-file-list sm-backup-list">
    {#each backup_files as f}
      <div class="sm-file-row">
        <span class="sm-file-label">backup</span>
        <span class="sm-file-name sm-mono">{basename(f.path)}</span>
        <span class="sm-file-size">{formatSize(f.size)}</span>
      </div>
    {/each}
  </div>
</details>
```

The summary shows count + total size so impact is visible without expanding.

---

## Frontend

### New file: `frontend/src/lib/autoBackup.js`

Auto-backup timer logic — no Svelte deps, pure JS:

```js
createAutoBackup({ getIntervalMs, onBackup, isEnabled })
  // Returns: { markChanged(), destroy() }
  // - Timer fires every getIntervalMs()
  // - If changedSinceLastBackup === false → skip (no API call)
  // - markChanged() sets changedSinceLastBackup = true
  // - onBackup() is the async callback that calls the API
  // - destroy() clears the timer
```

Settings stored in `localStorage`:
- Key: `backup_interval_min` — values: 5 / 10 / 30 / 60, default: **10**
- Key: `backup_auto_enabled` — boolean, default: **true**

### New file: `frontend/src/components/BackupModal.svelte`

Props:
```
sessionId: string
onRestore: (txtContent: string) => void   // called after restore; editor applies it
```

Internal state (all local to component):
```
open: boolean
backups: Array<{ts, label, size_bytes}>
loading: boolean
saving: boolean
autoEnabled: boolean        ← synced to localStorage
intervalMin: number         ← synced to localStorage
```

UI layout:
```
┌─ Song Backups ─────────────────────────────────────────┐
│  Auto-backup  [toggle]  every [5 · 10 · 30 · 60 min]  │
│  [↓ Backup Now]                              [✕ close] │
│  ──────────────────────────────────────────────────    │
│  Today 14:32  2.1 KB   [↩ restore]  [🗑 delete]       │
│  Today 14:01  2.0 KB   [↩ restore]  [🗑 delete]       │
│  Yesterday 23:45  1.9 KB  [↩ restore]  [🗑 delete]    │
│  (empty state: "No backups yet")                       │
└────────────────────────────────────────────────────────┘
```

- Restore shows a confirm dialog: "Restore this backup? Current unsaved changes will be lost."
- Delete shows a confirm dialog: "Delete this backup?"
- After restore: modal closes, `onRestore(txtContent)` is called

### Wire-up in `Step4Editor.svelte`

1. Import `BackupModal` and `createAutoBackup`
2. Add backup button next to the Notes button:
   ```svelte
   <button class="tool-btn" on:click={() => backupModalOpen = true} title="Backups">
     🕐 Backups
   </button>
   ```
3. In `onMount`: start auto-backup timer via `createAutoBackup`
4. In `onDestroy`: call `autoBackup.destroy()`
5. Call `autoBackup.markChanged()` inside `markUnsaved()` (already called on every edit)
6. `onRestore` callback: call existing `applyRestoredEditorState(txtContent)` or equivalent

---

## Auto-backup behaviour

- Timer always runs while editor is mounted
- On each tick: skip if `changedSinceLastBackup === false`
- `changedSinceLastBackup` resets to `false` after a successful backup
- `markChanged()` sets it to `true` — called by `markUnsaved()` in Step4Editor
- If auto-backup is **disabled** in the modal, timer still runs but always skips
- No pause/resume on idle — simpler, and skipping is equivalent

---

## Restore flow

1. User clicks restore on a backup entry
2. Frontend calls `POST /api/sessions/{id}/backup/{ts}/restore`
3. Backend reads the `.txt`, parses it, overwrites `session["result"]` and re-saves session JSON
4. Backend returns `{ txt_content, notes, bpm, gap_ms }` (same shape as `save_editor_state` response)
5. Frontend calls `onRestore(data)` → Step4Editor applies notes/BPM/GAP exactly like it does on initial load

---

## Constraints

- Max 20 backups per session (prune oldest on create)
- Backup files are plain UTF-8 `.txt` — no compression needed (typically 2–5 KB each)
- No backup-of-backup: restoring does not auto-create a backup first (user can click "Backup Now" before restoring)
- Backup button is disabled while `uiModalGuardActive` (same guard as Notes button)
