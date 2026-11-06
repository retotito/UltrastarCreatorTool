# Ultrastar Grid, Beats & GAP — Domain Knowledge

> **Status:** Current · **Last updated:** 2026-10-27

## Ultrastar Beat System

- One Ultrastar beat lasts `15 / BPM` seconds (the format's BPM counts quarter beats).
- Detection gives 4× the musical tempo (`detect_bpm`: 89 musical → 356). The chart BPM is that, doubled or
  halved to lie nearest **600** (`chart_bpm`, 424–848): 356 → 712, 494 stays. A beat is then about 25 ms, fine
  enough for notes that start and end where they are sung (consonant trimming); doubling keeps every musical
  beat on the grid. `refine_bpm` runs before, on the 4× grid.
- The editor derives beats per musical quarter from the BPM: `BEATS_PER_QUARTER = 2^round(log2(BPM / 30))`
  (356 → 16, 712 → 32), so metronome and grid lines follow a doubled BPM.
- A musical measure (4/4 time) = `BEATS_PER_QUARTER * 4` Ultrastar beats

## Note Pitches

The UltraStar format's pitch is relative: **0 = C4** ("The number 0 corresponds to the note C4 and Midi Note 60"). This
app stores and edits **MIDI numbers: 60 = C4** (its pitch line, MIDI tones and pitch tools work in MIDI). On import, a
chart whose median pitch is below 30 is moved up 5 octaves (+60, `services/ultrastar.py` `to_midi_pitches`), so it
matches the vocals at once; the downloaded file goes back to 0 = C4 (`to_relative_pitches`). Tools that play the notes
(Tune Studio, USDB Syncer) read a MIDI number as 5 octaves too high; the games mostly score the pitch class.

## Key Formulas

```
beatToTime(beat) = gapSec + (beat * 15) / bpm
timeToBeat(timeSec) = ((timeSec - gapSec) * bpm) / 15
```

Where `gapSec = gapMs / 1000`, `bpm` is the Ultrastar BPM value.

## What GAP Is

- GAP (in milliseconds) defines the audio timestamp where **Ultrastar beat 0** occurs
- It's the origin point of the Ultrastar coordinate system
- All note startBeats are relative to this point
- Beat 0 can be anywhere in the audio — it doesn't have to be the first note or the first beat

## Playback Headers

Measured from the start of the audio file, independent of each other, as UltraStar Deluxe reads them. None of them
moves the notes, so changing BPM or GAP leaves them where they are in the song. Note the units.

| Header | Unit | Meaning |
|---|---|---|
| `#GAP` | ms | Where beat 0 is |
| `#START` | seconds | Where the game starts playing, to skip an intro. Notes before it become freestyle (no points), so the editor refuses a position after the first note and shows a warning if notes later end up before it. If the first note is less than 3 s after it, the game starts 3 s before that note |
| `#END` | ms, whole number | Where the song counts as finished |
| `#VIDEOGAP` | seconds | Video position = audio position + VIDEOGAP. 0 if the audio comes from the same video; only needed for audio from elsewhere. It belongs to a video: written with a video file, or if not 0 with a YouTube link |
| `#PREVIEWSTART` | seconds | Where the preview starts in the song list; not set by the app |

Importing a chart keeps its video: `#VIDEO` as a file name, or USDB's `v=<id>,...` tags as the YouTube link; `#YOUTUBE`
and `#VIDEOGAP`. The editor's "Set GAP / Set Start" below is about beat 0, not `#START`.

## The Exported File

`format_for_download` makes the `.txt` of the ZIP and the single download (one function, so they are the same file):
UTF-8 without BOM, CRLF (USDB reads a file with only LF as one long line), no blank lines, pitches relative to C4, USDB's
header order, values trimmed, only known headers. Inside the app charts are read with LF; an imported file's line endings are
normalised, since writing CRLF text as CRLF again gives `\r\r\n`, which is read as blank lines.

Note texts: "If the text is not followed by a space, the next text will be directly attached" (USDB Syncer's format
page). So a mid-word syllable has no ending (`wel` + `come `) and a `-` is shown as written: only 0.3 % of USDB's
syllables end in one, mostly the lyrics' own ("three-" + "wheeler "). The format forbids no characters; `clean_syllable`
(and `cleanSyllable` in the editor) makes odd spaces plain and removes invisible and control characters. Older versions
of the app added a `-` to mid-word syllables: `strip_added_hyphens` removes them on import and download, recognised
by a chart where mid-word syllables without one are at most half as many as those with one (38 of USDB's 28,868 charts).

**The USDB `.txt`** (`format_for_usdb`) differs only where USDB's tools need it. `#VIDEO` can't serve both: a game needs
the video's file name there, while USDB Syncer and Tune Studio find the video by the tag `v=<YouTube id>` and ignore a
file name and `#YOUTUBE`. So the upload file has `#VIDEO:v=<id>`, no `#YOUTUBE`, no vocals or instrumental files, and a
duet has its singers as `p1=`/`p2=` in the tags and [DUET] in the title. It isn't put in the ZIP: in a song folder a game
would probably list the song twice.

## What the Grid Is

- The grid is a visual representation of musical beat subdivisions
- Grid lines are drawn at regular beat intervals starting from beat 0 (which is at the GAP position)
- The grid's position in time is entirely determined by the GAP value
- **Moving the grid = changing the GAP** — they are inseparable

## Two Separate Operations

### 1. Grid Align (Ctrl+G) — "Slide the grid to match the music"
- **Purpose**: Align the beat grid with actual audio beats (phase alignment)
- **What happens**: The entire grid slides left/right. Since the grid position IS the GAP, this changes the GAP value.
- **The yellow GAP line moves WITH the grid** (it's always at beat 0)
- **Notes re-quantize** from their raw audio timestamps using `requantizeFromMs()`
- **Use case**: The auto-detected GAP is slightly off, so beats don't line up with the kick drum. Slide the grid until they do.

### 2. Set GAP / Set Start (Ctrl+S) — "Pick which grid line becomes beat 0"
- **Purpose**: Choose a different grid line as the Ultrastar origin (beat 0)
- **What happens**: The grid does NOT move visually. Only which line is labeled "beat 0" changes. The yellow GAP marker jumps to the clicked line.
- **Internally**: GAP changes to the audio time of the clicked grid line. Notes re-quantize.
- **Use case**: The grid aligns perfectly with the music, but beat 0 is at the wrong place (e.g., you want it at the start of verse 1 instead of the intro).

### Key difference
- **Ctrl+G**: Grid moves, GAP marker stays at beat 0 (which moves with the grid)
- **Ctrl+S**: Grid stays put, GAP marker jumps to a different grid line

## Beat Phase Detection (Backend)

- `detect_beat_phase(audio_path, ultrastar_bpm)` in `bpm_detection.py`
- Uses `librosa.beat.beat_track()` (NOT `librosa.beat_track` — lazy alias is broken in v0.10.2)
- Computes circular mean of beat positions to find phase offset
- Returns phase offset in seconds
- Backend sets `gap_ms = max(0, round(beat_phase_sec * 1000))`
- This gives the GAP as where actual musical beats start, not where the first syllable is

## Metronome

- Clicks on every **quarter beat** (every `BEATS_PER_QUARTER` ultrastar beats) the playhead passes
- Works for negative beats too (before GAP), using `((quarterBeat % 4) + 4) % 4` for proper modulo
- Downbeat (beat 1 of measure) = higher pitch (1200 Hz), other beats = lower (800 Hz)
- Not tied to canvas visibility — it's purely based on the playhead position in beat-space
- The first click happens when the playhead crosses the next quarter-beat boundary from wherever playback started

## Raw Timings & Requantization

- Notes store raw audio timestamps (`rawTimings`) alongside beat positions
- `requantizeFromMs()` rebuilds all note startBeats and durations from raw audio timestamps using the current bpm/gapMs
- This is what makes grid alignment and GAP changes work — notes snap to the new grid based on their actual audio positions

## Grid Visibility

- Measure lines (every 32 beats): `#4a4a7e`, 1.5px (brightest)
- Quarter note lines (every 8 beats): `#3a3a6e`, 1px
- Eighth note lines (every 4 beats): `#2a2a50`, 0.5px
- 16th note lines (every beat): `#1e1e38`, 0.3px (only when zoomed in, zoom > 4)

## GAP Line

- Persistent yellow dashed line at beat 0 (always visible when on screen)
- Color: `#ffd70066` stroke, `#ffd70088` label
- Label: "GAP" shown at the top
