# Plan: Step 2 with lyric sources as tabs

| | |
|---|---|
| **Status** | Built (2026-10-22), being tested |
| **Created** | 2026-10-22 |
| **Goal** | One clear Step 2: compare lyrics from LRCLIB, the vocals and the cleaned vocals side by side, generate from either side |

## Layout

```
Artist [          ]  Title [          ]  Language [ ▾ ]

┌ LEFT ─────────────────────────────┐ ┌ RIGHT ────────────────────────────┐
│ [LRCLIB] [Vocals] [Cleaned vocals]│ │ [LRCLIB] [Vocals] [Cleaned vocals]│
│ tab tools (search / listen)       │ │ tab tools                         │
│ ┌ text ─────────────────────────┐ │ │ ┌ text ─────────────────────────┐ │
│ └───────────────────────────────┘ │ │ └───────────────────────────────┘ │
│ [🚀 Generate UltraStar file]       │ │ [🚀 Generate UltraStar file]       │
└───────────────────────────────────┘ └───────────────────────────────────┘
                [📄 Generate empty UltraStar file]
```

## Decisions (2026-10-22)

1. **Tabs are lyric sources, each side has its own texts** (changed 2026-10-25; before, both sides showed one
   shared text per source): LRCLIB, YouTube (the video's subtitles, for songs imported from YouTube), Vocals
   (Whisper), Cleaned vocals (Whisper on the Step 4 cleanup, tab only when one exists). Loading LRCLIB or Whisper fills only the side it was started from; editing one side never changes
   the other. Stored as `lyrics_sources.sides.{left,right}`; older sessions' shared texts go to both sides.
2. **Generate per side** replaces "Lyrics for generation: left / right" and the separate "Generate from Cleaned
   Vocals" button. The timing audio follows the tab: Vocals → vocals, Cleaned vocals → cleaned vocals, LRCLIB
   (no audio of its own) → cleaned vocals when a cleanup exists, else vocals. No checkbox.
3. **Hyphenation is automatic and invisible**: the text is hyphenated right before generating; the tab's text
   isn't changed. Hyphens the user wrote are kept **per word** (before: a whole line was skipped if it contained
   one `-`). Wrong splits are fixed in the editor.
4. **Little happens on its own** (changed 2026-10-25; before, LRCLIB searched whenever its text was empty and the
   sides swapped when it found nothing): the first time Step 2 opens a song, LRCLIB is searched once and a clear
   match fills the **left** side's LRCLIB text (remembered per song in the browser, so it doesn't search again).
   Everything else is by hand: "Search LRCLIB…" on a side (searches with the song's names right away), Whisper.
5. **Defaults**: left LRCLIB, right Vocals.
6. **Artist and title for file uploads** from the file's tags, else from the file name ("Artist - Title.mp3").
7. **Texts are saved in the session** (not only the browser), so they survive another computer or cleared data.
8. **Re-generating** asks before replacing an existing chart.

## Steps

1. ✅ Backend: per-word hyphenation; lyric sources in the session (GET/PUT); artist/title from tags or file name on
   upload.
2. ✅ Frontend: new Step 2 layout (`LyricsPanel.svelte` per side), generate per side, cleaned-vocals checkbox,
   warning before replacing a chart. Old sessions: the left "Generated Lyrics" text becomes the Vocals tab, the
   right (browser-only) text the LRCLIB tab.
3. Test together.
