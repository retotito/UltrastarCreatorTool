# Vocal Trace (Pink) vs Mic Lines (Green) — Design Reference

> **Status:** Current · **Last updated:** 2026-06-22

_Last updated: 2026-06-22. Pink line is fully implemented and working. Green line should be updated to mirror the pink architecture — differences noted in the Green section below._

---

## Pink Line (Vocal Trace) — Implemented ✅

### What it is
Colored overlay blocks drawn on the piano roll showing how well the pre-recorded vocal audio matches each note. Pink = hit, orange = miss.

### Record pipeline (`sampleVocalTrace`, ~line 8846)

Called on a fixed 25ms grid (`VOCAL_TRACE_STEP_SEC = 0.025`) during playback. Only fires inside note windows.

1. Copy `channelData[sample window]` into `vocalTraceSampleBuf`
2. Pitch detect → frequency → MIDI float
3. If unvoiced (low clarity or out-of-range Hz): skip frame entirely
4. Rolling median over 5 samples (smoothing)
5. **Octave-correct toward `note.pitch`** (shift ±12 until `|pitch - note.pitch| <= 6`) — baked into `sungPitch`
6. Clamp to MIDI 36–84
7. Store `{ beat, sungPitch }` — no `isHit`, no note reference
8. Upsert by beat (replace any existing frame within ±half-step tolerance — prevents duplicates on re-pass)

### Draw pipeline (canvas draw loop, ~line 2839)

```
frameW = max(2px, beatToX(vtBeatGap) - beatToX(0))   // pixel width of one 25ms frame
frameH = noteHeight
HARD_TOL = 1  // ±1 semitone, fixed — not user-controlled

for each frame in vocalTraceFrames:
    skip if outside visible beat range

    x = beatToX(frame.beat)           // FIXED — never changes after recording
    missY = pitchToY(frame.sungPitch) // FIXED — never changes after recording

    // Draw-time hit evaluation: look up which note (if any) covers this beat
    isHit = false
    drawY = missY
    for each note:
        if note covers frame.beat:
            isHit = |frame.sungPitch - note.pitch| <= HARD_TOL
            if isHit: drawY = pitchToY(note.pitch)  // snap to note row (Ultrastar style)
            break

    color = pink/gold/rap-orange (hit) or orange (miss/no note)
    fillRect(x, drawY - frameH/2, frameW, frameH)
```

### Key principles

**X is fixed at record time.** `x = beatToX(frame.beat)` — the beat was computed when the frame was recorded and never changes. Moving, resizing, or deleting a note has no effect on any frame's X position.

**Y for misses is fixed at record time.** `missY = pitchToY(frame.sungPitch)` — the octave-corrected sung pitch is stored once and used for miss rendering. Moving a note up/down does not move miss blocks.

**Y for hits snaps to the current note row.** `drawY = pitchToY(note.pitch)` — hit blocks sit exactly on the note rectangle (Ultrastar style). If the note moves vertically, hit blocks follow.

**Color is the only draw-time evaluation.** At each draw, we look up whether the current note at `frame.beat` is a hit or miss. This means:
- Moving a note horizontally → frames no longer covered by it → turn orange immediately
- Moving a note vertically → hit/miss threshold re-evaluated on every redraw
- Deleting a note → frames render orange (no note found)

**Frame width is fixed (`frameW`), not capped at note boundaries.** The last frame of a note may extend a few pixels past the note's right edge into the inter-note gap. This is acceptable and avoids any note-position dependency.

### Constants
- `HARD_TOL = 1` semitone (fixed, not tied to `pitchTolerance` UI)
- `vtBeatGap = VOCAL_TRACE_STEP_SEC * bpm / 15` — beat-space width of one frame
- Frame height = `noteHeight`
- Hit colors: `rgba(255, 80, 180, 0.45)` pink / `rgba(255, 215, 0, 0.45)` gold / `rgba(255, 152, 0, 0.45)` rap
- Miss color: `rgba(255, 140, 50, 0.45)` orange

---

## Green Line (Mic / Sing-Along) — Target Architecture

The green draw loop should mirror the pink draw loop above. The record pipeline is different (live mic, rAF timing), but the draw principles are identical.

### How green differs from pink

| | Pink | Green |
|---|---|---|
| Audio source | Pre-recorded vocal file | Live mic (`micAnalyser`) |
| Sample rate | Fixed 25ms grid | rAF ~16ms (variable) |
| Stored per frame | `{ beat, sungPitch }` | `{ beat, sungPitch, isHit }` |
| `isHit` | Draw-time only (not stored) | Currently baked at record time → **should move to draw time** |
| `HARD_TOL` | Fixed = 1 | Should use `pitchTolerance` UI setting (1/2/3) |
| Frame rendering | Frame-by-frame (25ms → ~50px, no overlap) | Group consecutive same-state frames into one rect (16ms rAF → dense frames, grouping avoids tiny fragmented blocks) |
| First-frame snap | None — X purely from `frame.beat` | None — gap ≤ 1 rAF frame (~8px), acceptable |
| Miss color | Orange | Orange (same) |

### Target draw pipeline (green)

```
HARD_TOL = pitchTolerance  // 1=hard, 2=medium, 3=easy — user-controlled

Group consecutive frames by draw-time isHit:
    for each group of consecutive same-state frames:
        x_start = beatToX(group[0].beat)
        x_end   = beatToX(group[-1].beat) + frameW

        note = note covering group[0].beat (if any)
        isHit = note exists AND |group[0].sungPitch - note.pitch| <= HARD_TOL
        drawY = isHit ? pitchToY(note.pitch) : pitchToY(group[0].sungPitch)
        color = green/gold/rap-orange (hit) or orange (miss)
        fillRect(x_start, drawY - frameH/2, x_end - x_start, frameH)
```

**What changes from current green:**
1. Re-evaluate `isHit` at draw time using `pitchTolerance` instead of stored value
2. Miss color: red → orange `rgba(255, 140, 50, 0.45)`
3. Keep grouping (don't switch to frame-by-frame)

**What stays the same:**
- Record pipeline (rAF mic sampling, rolling median, octave correction)
- `micNoteHits` data structure
- Grouping logic for consecutive frames

---

## Resolved Bugs

### ✅ PL/green timing offset — dots appeared ~23ms early
Stored beat used `startSample / sampleRate` (FFT window start). Fixed to `(startSample + fftSize/2) / sampleRate` (center of the 46ms window). Applied in `_detectPitchFrames`.

### ✅ PL/green Y snapping — dots on integer semitone rows
Stored `pitch = Math.round(midiFloat)` caused staircase. Fixed: `_detectPitchFrames` now also stores `pitchRaw` (float MIDI). Draw loops use `pitchToY(frame.pitchRaw ?? frame.pitch)` for smooth curves.

### ✅ Pink frames moved when notes were moved
First-frame snap (`x = beatToX(n.startBeat)`) and noteEndX capping (`cappedW = min(frameW, noteEndX - x)`) both depended on current note position. Fixed: both removed. X is now purely `beatToX(frame.beat)`, width is always `frameW`.
