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

1. **Tabs are lyric sources, the two sides are views.** Each source has one text: LRCLIB, Vocals (Whisper),
   Cleaned vocals (Whisper on the Step 4 cleanup, tab only when one exists). Showing the same source on both sides
   shows the same text.
2. **Generate per side** replaces "Lyrics for generation: left / right" and the separate "Generate from Cleaned
   Vocals" button. The timing audio follows the tab: Vocals → vocals, Cleaned vocals → cleaned vocals, LRCLIB
   (no audio of its own) → cleaned vocals when a cleanup exists, else vocals. No checkbox.
3. **Hyphenation is automatic and invisible**: the text is hyphenated right before generating; the tab's text
   isn't changed. Hyphens the user wrote are kept **per word** (before: a whole line was skipped if it contained
   one `-`). Wrong splits are fixed in the editor.
4. **LRCLIB searches automatically** when artist and title are known and its text is empty.
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
