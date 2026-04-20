# Test Checklist v2.0.4

Legend: ⏳ not tested · ✅ pass · ❌ fail

---

## Bohning's requested fixes (next update)

- [✅] BPM should be multiplied until above 200 (e.g. 100 BPM → 400, not 200)
- [✅] `#LANGUAGE` should use full English name (e.g. `English`, not `en`)
- [✅] Empty line between header and notes in .txt (when no video file)
- [✅] `#MP3` filename reference in .txt is wrong
- [✅] First note should start on beat 0 (GAP = time to first vocal note)
- [ ] Linebreak end-times not needed anymore — calculate "YASS-style"
- [❌] Pitches could be normalized (mod 12) — octave is irrelevant for singing (leave as it is for now)
- [ ] Inter-word spaces should be after the word, not before

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
