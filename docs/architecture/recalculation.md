# BPM / GAP Change — Recalculation Rules

> **Status:** Current · **Last updated:** 2026-06-19

---

## Test Checklist

- [x] **BPM change** — notes/breaks proportional scale (verified with 218-note song)
- [x] **BPM change** — flags recalc from `timeMs`
- [x] **BPM change** — GAP stays fixed
- [x] **GAP change** — notes/breaks reposition via `requantizeFromMs` (ms values preserved)
- [x] **GAP change** — flags recalc from `timeMs`
- [x] **Scroll** — view stays centered on same audio position after GAP change
- [x] **BPM change** — note `duration` scales correctly (min 1 floor) — verified by code inspection; only runs in no-rawTimings path
- [x] **BPM change** — downbeat anchor recalcs from `downbeatOffsetMs` (diamond-drag source only; pick/tapper uses metroAnchor path)
- [x] **BPM change** — metronome anchor scales proportionally — verified with ms-based formula (`-28 × 600/480 = -35`, equivalent to `(anchorMs - gap) × newBpm/15000`)
- [x] **GAP change** — downbeat and metronome anchor recalc correctly with new GAP (metroAnchor audio position preserved: `anchorMs = oldGap + oldBeat×15000/oldBpm`, verified)
- [x] **GAP/BPM change without rawTimings** — now handled correctly: note audio positions are preserved via ms conversion (`startMs = oldGap + oldBeat×15000/oldBpm`, `newBeat = (startMs - newGap)×newBpm/15000`). Previously the old proportional-only formula was a no-op for GAP-only changes (bpm unchanged → newBeat = oldBeat). Fixed in `resyncAllToGrid`.
- [x] **Diamond drag** — GAP snaps to nearest grid beat (≤ ½ beat), flags recalc from timeMs, downbeat anchor recalcs with new gapMs, metronome grid uses corrected anchor (`gap-snap` db1 ≠ drag db1)
- [x] **Diamond drag GAP snap** — implemented and verified: GAP snaps ≤ ½ beat, flags/anchor recalc with new gapMs

---

## Core formula

```
time_ms = GAP + beat × 15000 / BPM
```

**Beat 0 is at GAP ms.** GAP defines the origin of the beat grid.  
The inverse (ms → beat) is:

```
beat = round((time_ms - GAP) × BPM / 15000)
```

When BPM changes, beat positions scale proportionally:

```
newBeat = round(oldBeat × newBpm / oldBpm)
```

The beat value stored in the `.txt` file is the **source of truth** for notes and breaks.  
We scale beats directly — no conversion to ms and back.

---

## Per item type

### Notes (regular)
- Source of truth: `startBeat` and `duration` (from `.txt`)
- On BPM change:
  ```
  newStart    = snapToGrid(round(oldStart    × newBpm / oldBpm))
  newDuration = round(oldDuration × newBpm / oldBpm)   (min 1)
  ```

### Breaks
- Source of truth: `startBeat` and `endBeat` (from `.txt`)
- On BPM change: identical formula to notes — both use `snapToGrid(round(...))`.

### Flags
- Source of truth: `timeMs` in localStorage
  (flags are waveform markers — they have no beat in the `.txt`)
- On BPM change:
  ```
  newBeat = round((flag.timeMs - gapMs) × newBpm / 15000)
  ```
  (`normalizeFlag` does this via `msToBeat`)

### GAP
- Source of truth: `gapMs` (ms value — audio position, beat 0 origin)
- On BPM change: **unchanged** — GAP stays at its audio position.
  The grid snaps to GAP, not the other way around.

  GAP only changes when the user explicitly edits the GAP field.

### Metronome anchor (`#METRONOMEANCHOR`)
- Source of truth: **audio time** (derived from beat + old GAP + old BPM at the moment of change)
- On BPM or GAP change:
  ```
  anchorTimeMs = oldGapMs + oldBeat × 15000 / oldBpm
  newBeat = (anchorTimeMs - newGapMs) × newBpm / 15000
  ```
  When only BPM changes this simplifies to `oldBeat × newBpm / oldBpm`.  
  When only GAP changes it recalculates from the audio position (preserving alignment with the song).

### Downbeat offset (`#DOWNBEATOFFSET`)
- Source of truth: `downbeatOffsetMs` (ms — audio position set by diamond drag)
- On BPM change: recalc beat from ms: `(downbeatOffsetMs - gapMs) × newBpm / 15000`
- **Only applies when the anchor was set via diamond drag** (`metronomeDownbeat1Beat === null`).
  When set via pick/tapper tool, `metronomeDownbeat1Beat` is the source of truth and step 6 handles it.

---

## What does NOT change on BPM change

- `downbeatOffsetMs` (`#DOWNBEATOFFSET`) — stays in ms (absolute audio position of beat 1).
- `flag.timeMs` — stays in ms (source of truth for flags).
- `gapMs` (`#GAP`) — stays fixed (it is the grid origin, beat 0).

---

## Implementation: `resyncAllToGrid(previousTimingRef)`

Called after every BPM or GAP change.
`previousTimingRef = { bpm: oldBpm, gapMs: oldGapMs }`

```
1. GAP                 → unchanged (it is beat 0, the grid origin)
2. Scale notes         → snapToGrid(round(oldBeat × newBpm / oldBpm))
3. Scale breaks        → same formula as notes
4. Recalc flags        → msToBeat(flag.timeMs) via normalizeFlag()
5. Recalc downbeat     → (downbeatOffsetMs - gapMs) × newBpm / 15000
6. Scale metro anchor  → oldBeat × newBpm / oldBpm
```

Steps 2 and 3 only run when `rawTimings` is absent (txt-loaded songs).
When `rawTimings` is present, `requantizeFromMs` handles notes/breaks instead.

---

## Grid Offset Change (diamond drag)

When the user drags the diamond to set `downbeatOffsetMs`, the beat grid phase shifts.
After the drag commits:

```
1. Snap GAP  → newGapMs = downbeatOffsetMs + round((gapMs - downbeatOffsetMs) / beatDur) × beatDur
               (max shift = ½ beat — keeps GAP on the new grid)
2. Notes     → unchanged (beat values stay; distance to GAP preserved)
3. Breaks    → unchanged
4. Flags     → recalc beat from timeMs via normalizeFlag() (< ½ beat drift, acceptable)
5. Downbeat  → (downbeatOffsetMs - newGapMs) × bpm / 15000
6. Metro     → unchanged
```

The slight audio misalignment of notes is intentional — offset calibration is done
before fine-tuning note positions.
