# Duets

> **Status:** Current · **Last updated:** 2026-10-27

Two singers in one chart (UltraStar `P1`/`P2`). Assigned **by hand** in the editor; the pipeline stays as it is
(one voice, one note list). Branch: `feat/duets`.

## The format

```
#P1:Whitney Houston
#P2:Mariah Carey
P1
: 0 4 11 Ma
- 28
...
P2
: 30 2 11 We
...
E
```

- `#P1`/`#P2` name the singers. The older `#DUETSINGERP1`/`#DUETSINGERP2` are read by UltraStar Deluxe only for
  files before `#VERSION:1.0.0`, and by YASS. There is no language per singer: `#LANGUAGE` is the song's.
- A `P1` / `P2` line starts that singer's notes. Same beat grid, BPM and GAP; each singer has their own line breaks.
- There are no "both" notes: notes sung together are written in both tracks. UltraStar Deluxe refuses `P3`; Tune
  Studio copies a `P3` part of a pre-1.0 chart into both singers.
- Medley is off for duets in UltraStar Deluxe.

**In USDB** (28,823 charts, 906 duets, almost all with "[DUET]" in the title): only `P1`/`P2`, no `P3`. In 738 duets
singer 2 has exact copies of singer 1's notes (median 41 % of singer 2's notes; a third of the copies with another
pitch: harmonies, octaves). In 693 duets the singers have different notes at the same time (median 12 % of
singer 2's notes). USDB keeps the names in `#VIDEO` (`p1=…,p2=…`); USDB Syncer writes them as headers.

## What we build

### 1. Reading and writing duet charts ✅

Done: `services/duet.py` and `frontend/src/lib/ultrastar.js` (tests: `test_duet.py`, `ultrastar.test.js`). Round trip
of all 906 USDB duets: each track unchanged in 899; the others only list some notes out of beat order (we sort),
once golden-rap `G` notes are left aside (now read too, since the golden rap type was added).

- Today `parseUltrastar` (frontend) and `parse_ultrastar_file` (backend) skip `P1`/`P2` lines: a duet is read as one
  singer with both singers' notes and line breaks mixed. Both learn the tracks.
- Every note and line break gets `singer`: `1`, `2` or `'both'`; a solo chart has none. Reading a duet, a note that
  is in both tracks (same beat, length, pitch and syllable) becomes one `'both'` note, and so does a line break at
  the same beat in both. `P3` (pre-1.0 charts) is read as `'both'`.
- Writing a duet: the `P1` track has the notes and breaks of singer 1 and `'both'`, the `P2` track those of singer 2
  and `'both'`. A break that would leave an empty line in a track is left out of it. Headers `#P1`/`#P2` plus
  `#DUETSINGERP1`/`#DUETSINGERP2`. No medley headers.
- The .txt is written in three places today (editor save in `main.py`, the editor's text popup in
  `buildUltrastarContent`, `generate_ultrastar`). Duets go through one writer in `services/ultrastar.py`, with
  tests; the text popup gets its text from it (or a JS twin with the same tests).
- The alignment output format doesn't change: the singer belongs to the chart and the editor's notes.

### 2. Import and the session list ✅

Done. On import the names are also written as `#P1`/`#P2` into the chart, since `#VIDEO` is rewritten with the
asset headers; every save keeps `session["duet"]` up to date (removed when the chart isn't a duet).


- Importing a .txt with `P1`/`P2` marks the session as a duet (`duet: {p1, p2}` in the session). The import screen
  shows "Duet · name & name"; names from `#P1`/`#P2`, else `#DUETSINGERP1`/`P2`, else USDB's `p1=`/`p2=` in
  `#VIDEO`, else "Singer 1"/"Singer 2".
- The recent sessions list shows a duet badge once a session is a duet (imported, or set in the editor).

### 3. The editor (in progress)

First part done: Duet button and modal (`DuetModal.svelte`), singer chips for the active singer, drawing (other
singer semi-transparent and dashed, linked notes with an outer border), clicks reach the active singer first, the
right-click actions; logic in `frontend/src/lib/duet.js` (tests: `duet.test.js`). New notes go to the active singer.
Singer 2 is green (orange is taken by rap notes). Only the active singer's notes (and the linked ones) can be
clicked, box-selected, selected with Cmd+A or Tab, found and edited; the other singer's are only shown. **D**
switches the singer; switching drops the other singer's notes from the selection. Moving notes keeps the active
singer. Still open: two lyric rows, MIDI per singer, the tools (they act on the selection, so already on the
active singer).

**Line breaks**: each singer's lyrics line switches at their own breaks (in USDB only 12 of 906 duets have the
same breaks for both; 16 % of singer 2's own breaks fall inside a note of singer 1). Breaks are shared (`'both'`)
unless a singer needs their own: a new break inside the other singer's note becomes the active singer's (with a
message); the break's right-click menu has *For both singers* / *Only for [singer]* (refused where it would cut a
note of that singer). Shared breaks are red, a singer's own in their colour.


- **Duet button** in the second toolbar opens a modal:
  - *Set as duet*: names for singer 1 and 2. All existing notes and breaks become `'both'`.
  - Rename the singers.
  - *Unset duet*: "Which singer do you keep?" The other singer's notes are deleted (this is said in the modal);
    the kept singer's and the `'both'` notes stay. No overlapping leftovers.
- **Active singer**: chosen in the toolbar (the singers' names) or with a key. New notes, pastes and line breaks go
  to the active singer; where notes overlap, clicks reach the active singer's note first.
- **Always both singers shown**:
  - the active singer's notes solid in their colour (e.g. P1 blue, P2 orange);
  - the other singer's semi-transparent with a dashed outline;
  - `'both'` notes solid with both colours (an edge or stripe);
  - the pitch range of the grid is worked out from both singers' notes, so it doesn't jump when switching;
  - lyrics under the grid in two rows.
- **Assigning**: select notes, then right-click → *Singer 1 / Singer 2 / Both*, or keys (proposal: `1`, `2`, `3`;
  free today, `9`/`0` are MIDI/metronome).
- **Unlink** (right-click on `'both'` notes): two independent notes, one per singer, so their pitches can differ.
- MIDI playback: both singers, or only the active one.
- A red outline where notes of the same singer overlap (between the two singers overlapping is normal).
- The undo history covers all of this.

### 4. Generating and exporting

- Generating again replaces the notes, so a duet's assignment is lost: Step 2's "Generate again?" says so for a
  duet (it checks the saved chart), and the new chart's session is no longer marked as a duet. ✅
- Lyrics under the notes in two rows: not wanted.
- Export writes what the editor has (see Decisions).

### Tools on the active singer ✅

- **AI regenerate** (loop, cleanup section, after segment recording) and **Analyze 5s** replace only the active
  singer's notes in the range (`keptOnReplace`): the other singer's stay, linked ones there become the other
  singer's, the new notes are the active singer's. The audio is the shared vocal track (both voices): what comes out
  goes to the active singer and is corrected by hand, as when splitting a new song into singers. No hints.
- **Join** (J / Shift+J) only with a note of the same singer. **Vibrato** keeps the note's singer.
- **MIDI**: a toggle next to the MIDI button, *Both* or only the singer you edit.
- **Mic sing-along** and **vocal trace** compare with the singer you edit.
- Everything else works on the selection, so on the active singer already.

## Decisions

- **Manual only**: no automatic singer detection. Tune Studio has none either; separating two voices is a later
  topic.
- **Two singers at most**: UltraStar Deluxe refuses `P3`; all USDB duets use only P1/P2.
- **Linked notes**: a note sung by both is one `'both'` note; editing it changes it for both. Right-click:
  *Move to [other singer]*, *Link with [other singer]* (on one singer's notes); *Unlink* (two independent notes),
  *Only [singer 1] / Only [singer 2]* (on linked notes); *Select all notes of [singer]*. (No "swap singers": renaming does
  it.) Move and Link are refused where the other singer already has a note (no overlaps within a singer).
- **How linked notes look**: the active singer's colour plus a second outer border in the other singer's colour.
  Active singer's notes solid, the other singer's semi-transparent and dashed.
- **Export** what the editor has: a duet as a duet, a solo chart as solo. No extra solo version.
- **Open:** keys `1`/`2`/`3` and the colours (proposal: singer 1 blue, singer 2 orange).

## Order

1. Read/write with tests (synthetic charts in the tests, no USDB songs committed).
2. Import + session badge.
3. Editor: modal, singer field, drawing, active singer, assigning, unlink.
4. Export, regenerate warning, docs (`ultrastar-grid-gap.md` gets a duet section; `features/duets.md` when built).
