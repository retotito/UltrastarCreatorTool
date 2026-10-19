# Cleanup Sections — Design & Implementation

> **Status:** Current · **Last updated:** 2026-06-18

---

## The Concept (Intended Design)

### Audio Files

There are two vocal audio files per session:

| Name | When created | Ever modified? |
|---|---|---|
| **Original Vocal** | When the song is processed (demucs) or uploaded | Never — this is the permanent reference |
| **Edited Vocal** | When the first cleanup section is created | Yes — all cleanup edits write to this file |

The **Edited Vocal** starts as an exact copy of the Original Vocal.
From that point on, all cleanup operations read/write the Edited Vocal.
The Original Vocal is only ever read — never written.

---

### What a Cleanup Section Is

A cleanup section is a time range (start ms → end ms) that the user draws on the timeline.
It has two independent properties:

- **Is muted?** — yes by default when created
- **Has a recording?** — optional, added by the user

---

### Operations and Their Effect on the Edited Vocal

All of these happen **immediately** when the user acts — not on save.

| Action | What happens to Edited Vocal |
|---|---|
| Add a section | If Edited Vocal doesn't exist yet: create it as a full copy of Original Vocal. Then zero out the section range (mute) |
| Remove a section | Copy that range from Original Vocal back into Edited Vocal (restore) |
| Move a section left/right | Restore old range from Original → copy new range from Original → zero out new range |
| Resize a section (left or right edge) | Restore uncovered part from Original → zero out newly covered part |
| Add a recording to a section | Splice the recording audio into Edited Vocal at that range |
| Remove a recording from a section | Zero out that range (mute) — section still exists, recording is gone |
| Delete all sections | Delete the Edited Vocal file entirely — no sections means no edits |

The result: **Edited Vocal always reflects the current state of all sections**, immediately.
No "regenerate" step needed to hear the edits.

---

### Player Buttons

| Button | Plays |
|---|---|
| **Full Mix** | The original uploaded song (never changes) |
| **Vocals 🎤** | The Original Vocal (demucs output or upload — never edited) |
| **Edited ✂️** | The Edited Vocal (reflects all current cleanup sections and recordings) |

These URLs are fixed and never change. The frontend doesn't need to track
whether a splice has happened or not.

---

### The Temporary Recording

When the user records inside a section:
- The audio is captured in the browser as a temporary blob (in memory only)
- Nothing is written to disk yet
- The user can listen back and re-record
- When "Use This Recording" is clicked → the blob is uploaded and spliced into Edited Vocal
- The temporary blob is then discarded

---

## Current Implementation (What's Actually Built — differs from above)

> ⚠️ The current backend was not built according to the design above.
> This is the root cause of several bugs and confusing state.

### How it differs

**Backend:**
- There is only one vocal file: `session["vocal_audio"]`
- Before the first recording splice, `vocal_audio` = the original (demucs output)
- On the first recording splice: backend makes a backup of `vocal_audio` into `original_demucs_vocal`, then replaces `vocal_audio` with the patched version
- Muting does NOT write to `vocal_audio` — instead it generates a separate "cleaned" file each time from scratch

**The result:** `/vocals` endpoint means *original* before the first recording splice and *edited* after — the meaning changes mid-session. This forces the frontend to track `has_original_demucs` everywhere and causes bugs.

**There is no `edited_vocal` concept** — instead there is a derived `/cleaned` file that is:
- Only generated on save (not immediately)
- Deleted whenever a recording is spliced (needs regeneration)
- Only covers muting, not recordings

### Specific bugs caused by this

1. **First recording splice:** `originalVocalUrl` gets set to `/vocals` which is already the spliced file at that point — should be `/demucs`
2. **`editedAudioLoading` stuck:** set to `true` on splice but cleared by `onloadedmetadata` which is unreliable
3. **Stale Step 2 preview:** visits to Step 2 immediately after splice may play wrong URL
4. **No immediate feedback:** mute edits only audible after save/regenerate cycle

---

## Refactor Plan

### Decisions

- **Incremental operations only** — the backend modifies only the range being changed. Never rebuilds edited_vocal from scratch (that would destroy spliced recordings).
- **Rename `vocal_audio` → `original_vocal`** — clean rename since no backward compat needed.
- **`has_edited_vocal` flag** replaces `has_original_demucs` and `has_vocal_splice` in session data returned to frontend.

### Backend changes

1. Rename session key `vocal_audio` → `original_vocal`. Endpoint `/vocals` always serves it.
2. Add session key `edited_vocal`. Add endpoint `/api/preview-audio/{id}/edited` serving it.
3. Add endpoint `POST /api/edit-vocal/{id}` that accepts an operation and modifies `edited_vocal` in-place:
   - `{ op: "mute", start_ms, end_ms }` — zero out that range
   - `{ op: "restore", start_ms, end_ms }` — copy that range from `original_vocal` into `edited_vocal`
   - `{ op: "splice", start_ms, end_ms, recording: <file> }` — splice recording into `edited_vocal` at that range
   - `{ op: "create" }` — create `edited_vocal` as a full copy of `original_vocal` (called on first section add)
   - `{ op: "delete" }` — delete `edited_vocal` file (called when all sections are deleted)
4. Remove `generate-cleaned-audio` endpoint and `/cleaned` file concept.
5. Remove `original_demucs_vocal` key, `has_original_demucs` flag, `has_vocal_splice` flag.
6. Return `has_edited_vocal: bool` in session data.
7. Update Ultrastar export ZIP to use `edited_vocal` when it exists, else `original_vocal`.
8. Update Step 2 to use `edited_vocal` endpoint when `has_edited_vocal` is true.

### Frontend changes

1. `originalVocalUrl` = `/vocals` always — set once at load, never changes.
2. `editedVocalUrl` = `/edited?v=...` — cache-busted after any edit operation.
3. Remove all `has_original_demucs` conditional logic.
4. Remove `cleanedAudioAvailable`, `segRecPatched`, `cleanedAudioCacheBust`, `vocalUrl` state.
5. On every cleanup section add/remove/move/resize → call `POST /api/edit-vocal/{id}` with the right operation immediately.
6. On "Use This Recording" → call `POST /api/edit-vocal/{id}` with `op: "splice"`.
7. `Edited ✂️` button always plays `/edited`. Enabled when `has_edited_vocal` is true.

### What we get

- No confusing first-recording-splice special case
- No "regenerate to hear your changes" step — edits are immediate
- Frontend state is simple: two fixed URLs, one boolean flag
- Easier to reason about and debug

---

## Status

- [ ] Design agreed
- [ ] Backend refactor implemented
- [ ] Frontend refactor implemented
- [ ] Existing sessions tested for backward compatibility
