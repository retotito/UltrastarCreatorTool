# Changelog

All notable changes to Ultrastar Creator Tool. Newest first.

## Unreleased

### ▶ YouTube link in Step 1
- Paste a YouTube link instead of uploading a file: the app shows the video, downloads its audio as the full mix and
  fills in artist, title and (when YouTube knows it) the language for Step 2; the link is written as `#YOUTUBE`
- The download tools (yt-dlp, QuickJS) are downloaded on first use and updated automatically when YouTube changes
- One step: paste the link and press **⬇ Download**. Uploads and downloads both show a blocking window with a
  spinner and **Cancel**, then "Which song is this?"; the card shows the file as "Artist - Title"

### 🎯 Lyrics timing without hallucinated notes
- **Forced alignment of your lyrics**: syllable timing now comes from aligning the lyrics you confirmed directly to
  the vocals, instead of matching Whisper's transcript. Words Whisper didn't hear no longer get guessed positions.
  On six test songs, misplaced syllables (> 0.5 s off) dropped from 57 % to 7 %.
- Uses [Tune Studio](https://github.com/ZerNico/tunestudio)'s singing-tuned aligner (new ~1.2 GB download in setup,
  non-commercial licence)
- Generating works without running "Generate Lyrics from Vocals" first; segment re-generation no longer runs Whisper
- Previous behaviour available with `ULTRASTAR_ALIGNMENT_ENGINE=legacy`
- Works for lyrics in every script (Cyrillic, Greek, Arabic, Chinese, Japanese, …) via uroman

### 🎵 "Which song is this?"
- After an upload (full mix or vocals) or a YouTube download, a window proposes artist and title to check, correct
  or swap. The proposal is checked online in the background, so "Title - Artist" file names and wrong tags are
  recognised. Confirming names the audio file "Artist - Title". Step 2 searches the lyrics only with confirmed
  names (they can be changed later in Step 2)
- The window also asks for the song's language and, for songs sung in two languages, an optional second one.
  Both are written as English names (`#LANGUAGE:English, German`), as the UltraStar format wants; Step 2 has the
  same two fields, and imported charts with two languages keep both
- Step 4's "Edit song info" has dropdowns for language and an optional second language (it used to save the
  typed name instead of the code). In the editor's text view, changing `#ARTIST`, `#TITLE` or `#LANGUAGE` and
  pressing "Apply Changes" now saves them like everywhere else (before, they were ignored)
- With two languages, Whisper (Vocals tab) transcribes every passage in its own language instead of translating
  the second language into the first; this takes about twice as long

### 📝 New Step 2
- Artist, title and language at the top; for file uploads taken from the file's tags or name
- Two sides with tabs for the lyrics sources: **LRCLIB** (published lyrics, searched automatically), **Vocals**
  (Whisper) and **Cleaned vocals** (Whisper on your Step 4 cleanup) — compare any two side by side
- Each side has its own "Generate UltraStar file"; the timing audio follows the tab (Vocals or Cleaned vocals;
  LRCLIB uses the cleaned vocals when there is a cleanup)
- Hyphenation happens automatically when generating; words you split yourself are kept
- Asks before replacing an existing UltraStar file; lyrics are saved with the project, not only in the browser

### 🎶 Held notes keep their length
- The last long note before a pause is no longer cut short (Ben Harper's final "sun": 0.2 s → 5.5 s, then split
  into "~" notes); it lasts as long as the voice keeps singing. `ULTRASTAR_HOLD_NOTES=0` turns it off

### 🔁 "AI generate notes" on a loop = the same notes as Generate
- A loop in the editor now gets the same note steps as the whole song: GAME's notes, octave check, repeated lines,
  consonant trimming (it had FCPE's pitch only), and its timings match its notes one to one

### 🔤 English split into sung syllables
- Words pyphen left whole are split as they are sung: "sing-ing", "pie-ces", "ban-da-ges", "un-pre-dic-ta-ble"
  (silent "e", "-es"/"-ed" and "-ing" handled). Agreement with the syllables of 7 real charts: 95.4 → 98.3 %

### ✂️ Notes trimmed like by hand
- Notes start where the voice sings (not on "s", "sh", "f", "t"…: the aligner's letter times show where the first
  vowel or l/m/n/r/w begins), end where it fades and leave air before the
  next syllable, as in hand fine-tuned charts: note lengths much closer to them (Robert Post: +103 → +36 ms).
  `ULTRASTAR_TRIM_CONSONANTS=0` turns it off
- The chart BPM is brought near 600 (slow songs doubled: 356 → 712), so the beat grid is fine enough for it
  (Ben Harper against the fine-tuned chart: start error 49 → 35 ms, starts more than 150 ms off 20 → 7)

### 🛑 Files without sound are refused
- Uploading a file with no audio track (e.g. a video-only .mp4) now says so right away, instead of failing later
  in the vocal separation ("Demucs failed: index 0 is out of bounds")

### ✨ Better vocal separation (optional)
- Step 1 has a second button, "✨ Better separation (slow, ~10 min)": Mel-Band RoFormer instead of Demucs.
  Much cleaner where voices overlap (duets, backing vocals); downloads its model (464 MB) the first time

### ✍️ Numbers and signs in lyrics
- Numbers are timed as they are sung ("12" → "twelve", in Italian "dodici") and "&" as "and"; the chart keeps
  the text as written
- Signs on their own ("—", "…") no longer become notes of their own; they stay with the previous word

### 🎵 Notes from a note model (GAME)
- Each syllable's pitch now comes from GAME (openvpi), a model that transcribes sung notes, as Tune Studio does;
  much better where two voices overlap. Reference songs: right pitch class 56 → 64 %, octave errors 4.5 → 3.0 %
- First-run setup downloads it (~362 MB, non-commercial licence, see docs/decisions/0003)

### 🎼 Octave check keeps low voices
- Notes are moved at most one octave (was three). In duets the low male voice was pushed up towards the female
  voice; on "Amada Mia, Amore Mio" 35 of 97 low notes now match Tune Studio's chart, before 3
- Repeated lines (choruses) are compared: a note an octave off where the other repetitions clearly agree is
  moved back (reference songs: octave errors 4.85 → 4.5 %)

### 🌍 Hyphenation in more languages
- Uses pyphen's dictionary for every language that has one (Russian, Greek, Ukrainian, Catalan, …), one syllable
  per character for Chinese, Japanese and Korean, and a generic vowel rule otherwise. Before, all languages but 17
  were silently hyphenated with English rules

### 🎵 Pitch
- New neural pitch detection (FCPE, ~48 MB download in setup): more notes on the right pitch (within a semitone of
  the reference charts 77 % instead of 71 %), a pitch for every sung syllable, and about 10× faster than before
- The slide into a note no longer pulls its pitch down
- Octave check: notes the pitch detection put one to three octaves off are moved back next to their
  neighbours (no more jumps of more than an octave inside a line)
- **Melisma:** long syllables whose melody moves are split into `~` notes (e.g. "gas ~ ~"), also in segment
  regenerate; vibrato and slides into a note don't split. Off with `ULTRASTAR_MELISMA=off`
- Syllables without a detected pitch take the neighbouring note's pitch instead of C4 (no more octave jumps)

### 🐛 Bug Fixes
- Downloading a re-imported song no longer turns mid-word syllables into `Beau--`

## v4.1.0

### 🎵 Freestyle Note Support
- New **freestyle note type** (`F` prefix) — parsed, rendered in purple, available via context menu, and supported in the backend pipeline
- Standard `R` prefix used for rap notes (legacy `F:` prefix accepted as input for compatibility)

### 🐛 Bug Fixes
- **Selection panel** — deselect button now works correctly; close button made larger for easier clicking
- **L key** — works correctly with notes selected; toolbar buttons no longer accidentally deselect notes
- **Metronome grid** — uses nearest power-of-2 for `BEATS_PER_QUARTER` to fix grid alignment at unusual BPMs (e.g. 464)

## v4.0.0

### ⚙️ Storage Manager
- New **Storage Manager** modal (gear icon) — lists all sessions with size, lets you delete orphaned sessions and debug data, and remove downloaded AI models to free up disk space

### ✂️ Vocal Audio Cleanup Sections
- Draw, drag, resize, split, and join **cleanup segments** directly on the waveform
- Segments define regions to silencr or  replace witch voice recording
- Waveform context menu shortcut to add a cleanup section at the cursor

### 🎙️ Record Over Sections
- **Segment recording** — record a replacement vocal take over any cleanup section
- Review recorded take with loop playback; hand off directly to AI note generation
- Source switching (original / vocals / edited) inside the recording modal

### 🤖 AI Re-generation Over Section or Loop
- Generate new Ultrastar notes for any loop region or cleanup section using the AI pipeline
- Use edited-vocal or original-vocal as source

### 🎛️ Metronome & BPM Tools
- **Draggable diamond handle** in the canvas top strip — drag to set the downbeat anchor visually without opening a modal
- Metronome modal: time signature, speed factor, persist settings across sessions
- **BPM guard** — orange warning below 200 BPM, red/disabled below 100 with confirm dialog

### 🎵 Pitch Lines
- **Blue pitch line** — precomputed full-song vocal pitch displayed as continuous dots across the canvas
- **Green pitch line** — recorded/patched section pitch, independent of blue line

### 🎸 Vibrato Tool
- Auto generate Vibrato on a long notes

### 💾 .txt Backup
- **Auto backup** — configurable timer saves a snapshot of the session at regular intervals
- **Manual backup** — save a named snapshot at any time


### 📝 Lyrics Editor (Step 2)
- **CodeMirror** editor replaces the plain textarea — zebra stripes, line numbers, syntax highlighting, proper selection colors
- **Comparison field** — second text field side-by-side for comparing against an alternative lyrics source

### 🎹 Editor Keyboard & UX
- **Y key** — select the note at the current playhead position (also on double-click)
- **N key** — add a new note at the cursor position (beat + pitch from mouse)
- **S key** — splits at playhead position when playhead is inside the selected note; otherwise splits at midpoint
- Right-click split also prefers playhead position when inside the note
- **Fix Spaces modal** — explains old vs. new word-space convention with before/after example before applying
- **Help modal** (ℹ️ button) — keyboard shortcut reference accessible at any time
- Escape correctly deselects newly added notes
- Selection preserved through undo/redo
- Multi-select: clicking an already-selected note collapses to single selection
- Viewport auto-centers on selected note after arrow key moves (only when note not visible)
- Unified blue note borders; golden ★ and rap R indicators drawn above notes
- White syllable text; trailing-space syllables shown in grey with · marker
- Editor fills full viewport height dynamically
- Find widget (Cmd+F) — search syllables, jump to match, highlight
- `#END` marker — canvas line, toolbar controls, scrollbar tick, navigation support
- Tab/Shift+Tab plays the note's MIDI pitch while navigating
- Playhead position persisted across navigation and session reopen
- Loop region shown as a tinted band in the scrollbar track
- Tauri app opens maximized on launch

### 🐛 Bug Fixes
- BPM change corruption fixed — direct beat scaling prevents gaps between adjacent notes
- encode uploads to WAV — eliminates encoder delay and frame-quantized seeking
- Precount countdown timing corrected for non-1× playback speeds
- Vocal trace hit detection applies same octave-correction as mic mode
- Vocal trace fixed-X position, no note-tracking gaps, correct timing center
- Cleanup segment drag auto-scroll; keyboard nudge in viewport
- Backup restore: reset data guard before reload; custom confirm dialog (no browser `confirm()`)
- Canvas find widget, ShortcutBar, pitch utilities extracted to separate files (smaller editor bundle)

## v3.1.0

- **App renamed** — product name and window title changed from "Ultrastar Creator" to `UltrastarCreatorTool` for consistency with the GitHub repo name
- **Kill backend on close** — closing the Tauri window now cleanly kills the backend sidecar process (and releases port 8001) on both macOS and Windows
- **WhisperX fallback warning** — if WhisperX is unavailable and vanilla Whisper was used instead, a dismissable amber modal warns the user that timestamps are less precise
- **Windows model integrity fix** — `_file_size_accurate()` used for all model size checks to handle NTFS hardlink edge cases; 0-byte snapshot files from HuggingFace blobs are auto-repaired by copying from the blobs folder
- **Detailed model status logging** — `log_step()` calls added throughout model status checks and download flow for easier debugging
- **Version bump to 3.1.0**

## v3.0.2
- **Vocal trace determinism** — removed sticky pitch prediction from `sampleVocalTrace`; the vocal trace now produces identical results regardless of where playback starts
- **Unvoiced reset** — on an unvoiced frame the rolling median window is immediately cleared, preventing stale pitches from influencing the next voiced frame
- **Frame clearing on play** — all vocal trace frames ahead of the playhead are cleared when playback starts, so stale data from a previous run never bleeds into a new recording pass
- **Loop wrap re-warmup** — on loop wrap, frames are cleared and the rolling median is re-seeded via backward scan, keeping trace consistent across repeated loops
- **View-only frames visible during playback** — frames outside the current playback pass (view-only mode) are now drawn correctly while audio is playing
- **Between-note frame clicks** — right-clicking a vocal trace frame in the gap between notes no longer accidentally blocks a seek

## v3.0.1
- **BPM tapper** — new Tap button next to the BPM input opens a modal where you tap the beat by clicking or pressing Enter; shows live BPM and apply buttons for 1×–8× multipliers; play/pause and jump-to-GAP controls included; metronome is muted while the tapper is open
- **BPM change: no gaps** — fixed double-rounding that caused gaps to appear between adjacent notes when changing BPM; notes now scale using a single proportional multiply
- **BPM change: preserve edits** — syllable, pitch, and x-position/duration edits are now preserved when BPM is changed
- **BPM change: clear overlays** — pitch line, vocal trace, and mic trail are automatically cleared on BPM change (they would be misaligned at the new BPM)
- **GAP change: stable positions** — notes now stay at their absolute audio positions when only the GAP is adjusted
- **Vocal trace octave correction** — vocal trace hit detection now applies the same octave-correction logic as mic sing-along, so singing an octave higher or lower still counts as a hit

## v3.0.0
- **Pitch line overlay** — precomputes an offline full-song pitch analysis of the vocal audio and draws thin continuous dots across the entire canvas; toggle on/off with a dedicated button
- **Pitch tolerance selector** — choose Hard (±1 semitone), Medium (±2), or Easy (±3) hit tolerance for both mic sing-along and vocal trace modes; dropdown appears in the mic controls panel
- **Hit/miss overlap fix** — red (miss) blocks no longer extend into the start of adjacent green (hit) blocks; miss blocks now end exactly at their last detected sample beat
- **Mic startup latency fix** — disabled `echoCancellation` and `noiseSuppression` on mic input to eliminate the initial audio processing delay before pitch detection begins

## v2.0.5
- **Header editing** — `#GENRE`, `#CREATOR`, `#VOCALS`, `#INSTRUMENTAL`, `#YEAR`, `#EDITION`, and `#LANGUAGE` fields are now editable in the Edit Song modal; all are written into the exported `.txt` and ZIP
- **Song Assets UI overhaul** — Vocals and Full Mix shown as read-only display rows; Instrumental is editable; hints shown for missing audio; archive filename for vocals fixed
- **Audio normalisation on upload** — all uploaded audio (m4a, wav, flac, …) is converted to 44 100 Hz MP3 at upload time, ensuring playback compatibility with QuickTime and Apple Music
- **Session cleanup** — deleting a session now removes *all* generated files across multiple generation runs (tracked via `generated_files` list), plus session-prefixed mic trail, mic audio, and comparison files
- **ZIP export checkboxes in asset rows** — Vocals, Instrumental, Summary, and MIDI checkboxes are now inline with each asset row instead of a separate options panel
- **Instrumental download button** — a dedicated download button for the instrumental track is available in the export grid
- **"All Files Individual" respects checkboxes** — the bulk download button honours the Vocals / Instrumental / Summary / MIDI include flags
- **`subprocess` import fix** — fixed a `NameError` that silently prevented audio normalisation from running
- **ffprobe bundled** — ffprobe is now bundled alongside ffmpeg in the PyInstaller sidecar

## v2.0.4
- **Custom app icon** — new branded 1024×1024 icon (with padding) used across macOS, Windows, Android, and iOS builds
- **Negative beats / early GAP** — removed the beat-0 lower-bound constraint; GAP can now be set before the first note, allowing songs that start before beat 0
- **Metronome divisor** — three click intervals: quarter note (♩), half note (𝅗𝅥), and full bar (𝄺); buttons appear when metronome is active
- **Dynamic BEATS_PER_QUARTER** — `Math.round(bpm / 30)` so the grid and downbeat modulo work correctly with fractional BPM values
- **CRLF import fix** — Windows `.txt` files with `\r\n` line endings now parse correctly (notes no longer missing after import)
- **m4a / AAC support** — audio is pre-converted to WAV before Demucs so m4a uploads no longer fail vocal separation
- **Vocal download extension** — downloaded vocals always use `.mp3` instead of inheriting the wrong uploaded-file extension
- **Audio ended event** — playback animation frame is now cancelled when the audio track ends naturally, preventing a stale playhead
- **Word-space red dot** — the indicator dot is drawn on the note *missing* the trailing space (not on the following note)
- **Auto-fix word spaces across breaks** — `autoFixWordSpaces()` correctly moves leading spaces to the trailing position on the previous note even across line breaks

## v2.0.3 and earlier
- Bohning UltraStar format compliance (BPM×4, `#LANGUAGE`, no blank line after headers, `#MP3`, GAP/beat-0, YASS linebreaks, trailing word spaces)
- Trailing word-space feature with visual red-dot indicator and one-click auto-fix
