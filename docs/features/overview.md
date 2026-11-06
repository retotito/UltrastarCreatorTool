# Features

> **Status:** Current · **Last updated:** 2026-11-06

What the app can do, in full. The short version is in the [README](../../README.md).

## AI Pipeline
- **Vocal separation** — Demucs v4, or optionally Mel-Band RoFormer, which is slower but much cleaner where voices overlap
- **Forced alignment** — aligns your lyrics directly to the vocals, in every script, with a model tuned for singing
- **Notes** — a note model (GAME) and neural pitch detection (FCPE) find each syllable's pitch; octave errors are checked against repeated lines
- **Sung like by hand** — notes start on the sung vowel, long notes keep their length, melodies within a syllable become `~` notes
- **Syllables** — split as they are sung, for each language and line by line in two-language songs
- **BPM detection** — automatic tempo analysis with beat-phase alignment
- **Lyrics from several sources** — published lyrics (LRCLIB), Whisper on the vocals, or a YouTube video's subtitles
- **One-click generation** — audio → Ultrastar format in minutes, with real progress

## Piano Roll Editor
- **Full note editing** — move, resize, split, merge, delete notes
- **Duets** — two singers, shown together, edited one at a time (D switches); notes can be moved or linked between them, and tools act on the singer you edit
- **Golden, rap, golden rap and freestyle notes** — each with its own look
- **Warnings** — notes overlapping within a singer, line breaks inside a note and notes without text are marked, with a button that goes through them
- **Set START and END** — where the game starts and stops playing
- **Find** (Ctrl/Cmd+F) — search for a syllable
- **Toolbar layout** — hide the tools you don't need on small screens
- **Grid alignment** (Ctrl+B) — snap the entire beat grid to match the audio
- **GAP adjustment** (Ctrl+G) — click any grid line to set the GAP position
- **BPM tapper** — tap the beat in a modal (click or press Enter) to measure BPM; shows live BPM with apply buttons for 1×–8× multipliers; play/pause and jump-to-GAP controls included; metronome muted while tapper is open
- **Text editor** — edit raw Ultrastar content with live preview
- **Session notes** — jot down reminders while editing; saved automatically per session and restored next time you open the editor
- **Flag markers** — place green marker lines anywhere on the canvas (right-click → Add Flag); drag, nudge ±1 beat, or delete via right-click; shown as green ticks on the scrollbar; persisted per session
- **Custom scrollbar** — fully custom div-based slider; the handle tracks the canvas center beat so zooming in/out never moves it; playhead and flag ticks align perfectly with no browser-offset math
- **Select all** (Ctrl+A) — select all notes for bulk move
- **Undo/Redo** — full snapshot history (notes, BPM, GAP, downbeat offset, headers)
- **Waveform display** — smooth high-resolution waveform (750 peaks/sec) showing full-mix or vocal track alongside notes
- **Downbeat alignment** — independent measure grid offset stored as `#DOWNBEATOFFSET` header
- **Metronome** — accent clicks aligned to the downbeat for timing reference
- **Extra headers** — YOUTUBE, COVER, GENRE and other Ultrastar tags
- **Context menus** — right-click on notes or empty space for quick actions

## Playback & Audio
- **Sing-along mode** — use your microphone to sing along with the song in real time, see your pitch trail overlaid on the notes for realistic editing
- **Pitch tolerance / difficulty** — select Hard (±1), Medium (±2), or Easy (±3) semitone tolerance for hit detection in both mic and vocal trace modes
- **Pitch line** — precomputes an offline full-song pitch analysis of the vocal audio and draws it as thin continuous dots across the entire canvas (behind all other overlays); toggled on/off with a dedicated button; useful for a quick global pitch overview without running the vocal trace in real time
- **Vocal trace** — automatically runs the separated vocal audio through the same pitch detector as the mic; draws a pink trail behind the notes so you can see exactly where the vocals land and align notes by eye. Right-click a pink frame to insert a note at the exact position and pitch (snapped to grid). Toggle with **V**.
- **Mic device selection** — choose from available microphones with volume gain control
- **Active mode badge** — pulsing red MIC / pink VOCAL indicator on the canvas when recording
- **MIDI pitch playback** — hear synthesized pitches during playback (triangle wave)
- **Vocal mute toggle** — isolate MIDI pitches or hear both
- **Audio scrub** — drag the playhead to hear frozen audio grains at any position
- **Drag pitch preview** — hear the pitch while moving notes

## Loop & Navigation
- **Loop regions** — Shift+drag on the time ruler to set a loop, with draggable handles
- **Playhead scrub** — drag the playhead handle with audio + MIDI preview
- **Smart cursors** — move/resize indicators when hovering over notes
- **Keyboard shortcuts** — Space (play/pause), L (loop), Escape (clear loop/deselect)
  - **←/→** — seek −5s/+5s (no selection), or move selected note(s) ±1 beat
  - **Shift+←/→** — seek −1s/+1s (no selection), or move selected note(s) ±4 beats
  - **↑/↓** — shift selected note(s) pitch ±1 semitone
  - **Shift+↑/↓** — shift selected note(s) pitch ±1 octave

## Project Management
- **Project launcher** — create, open, rename, and delete song projects
- **Session persistence** — projects survive server restarts
- **Import** — existing charts with their duets, video link and notes kept; USDB's pitches are converted automatically
- **YouTube link** — instead of uploading a file: audio, artist, title and language come from the video

## Export
- **Song Assets** — attach a cover image (480×480), background image (1920×1080), and video filename to the song; both images go through an interactive **crop tool** (pan + zoom) before upload
- **Asset headers** — `#COVER`, `#BACKGROUND`, `#VIDEO`, `#VIDEOGAP` are written into the Ultrastar `.txt` automatically whenever an asset is saved
- **Export to folder** — choose a location; the app writes `Artist - Title/` with the `.txt`, audio, images and the extras you ticked, ready for a game
- **USDB `.txt`** — for uploading to [USDB](https://usdb.animux.de): Windows line endings, `#VIDEO:v=<YouTube id>`, pitches relative to C4
- **Video** — download the song's YouTube video (up to 1080p), on its own or in the song folder
- **ZIP** — the same files as the folder, in one file to pass on
- **Ultrastar .txt** — the format's conventions, for the game
- **MIDI export** — pitch data as MIDI file
- **Processing summary** — detailed report of the AI pipeline

## Languages

Lyrics transcription and song generation work in the 97 languages Whisper supports.
