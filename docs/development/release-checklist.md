# Test Checklist v2.0.4

> **Status:** Current · **Last updated:** 2026-05-16

Legend: ⏳ not tested · ✅ pass · ❌ fail

---

## Bohning's requested fixes (next update)

- [✅] Suport for m4a files
- [✅] BPM should be multiplied until above 200 (e.g. 100 BPM → 400, not 200)
- [✅] `#LANGUAGE` should use full English name (e.g. `English`, not `en`)
- [✅] Empty line between header and notes in .txt (when no video file)
- [✅] `#MP3` filename reference in .txt is wrong
- [✅] First note should start on beat 0 (GAP = time to first vocal note)
- [✅] Linebreak end-times not needed anymore — calculate "YASS-style"
- [❌] Pitches could be normalized (mod 12) — octave is irrelevant for singing (leave as it is for now)
- [✅] Inter-word spaces should be after the word, not before

---

## New fixes to test


**Audio seek in Editor (use a large full mix file > 10 MB)**
- [ ] ⏳ Play → stop at 20s → click to seek to 15s → play — audio matches position — ARM
- [ ] ⏳ Play → stop at 20s → click to seek to 15s → play — audio matches position — Intel
- [ ] ⏳ Same but using arrow keys to seek — ARM
- [ ] ⏳ Same but using arrow keys to seek — Intel

**Demucs on Intel Mac**
- [ ] ⏳ Vocal separation runs without crash — Intel (needs fresh build from main)

**Downloads (Export page)**
- [ ] ⏳ .txt / audio / .zip save to disk (not open in browser tab) — ARM
- [ ] ⏳ .txt / audio / .zip save to disk (not open in browser tab) — Intel

---

## Core flow regression (before every release)

- [ ] ⏳ Upload full mix via file picker
- [ ] ⏳ Vocal separation (Demucs)
- [ ] ⏳ Lyrics transcription (WhisperX)
- [ ] ⏳ Generate Ultrastar files
- [ ] ⏳ Piano roll editor opens with notes
- [ ] ⏳ Audio plays in sync with notes
- [ ] ⏳ Export .zip downloads correctly
- [ ] ⏳ Resume last session works

## Releasing with automatic updates

1. Write `RELEASE_NOTES.md`: the app's "What's new" window and the GitHub release's text.
2. Set the version in `frontend/src-tauri/tauri.conf.json` and `frontend/package.json`, with numeric pre-releases only
   (`5.0.0-2`; the Windows .msi refuses "beta"). Installed apps offer an update only when this is higher than their own.
3. Tag and push (`v5.0.0`). The workflow signs the updates and adds `latest.json` to a draft release.
4. Check the draft, then publish it as the **latest** release. Installed apps read
   `releases/latest/download/latest.json`: drafts and pre-releases are never offered.

Updates are signed with the key in `~/.tauri/ultrastar-updater.key`, also stored as the `TAURI_SIGNING_PRIVATE_KEY` repository
secret; its public part is in `tauri.conf.json`. **Back the key up: without it, installed apps can't be updated anymore**, since
they only accept updates signed with it. Never commit it.
