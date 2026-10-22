# Plan: Step 2 with lyric sources as tabs

| | |
|---|---|
| **Status** | In progress |
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
☑ Use cleaned vocals for timing        (only when a cleanup exists)
                [📄 Generate empty UltraStar file]
```

## Decisions (2026-10-22)

1. **Tabs are lyric sources, the two sides are views.** Each source has one text: LRCLIB, Vocals (Whisper),
   Cleaned vocals (Whisper on the Step 4 cleanup, tab only when one exists). Showing the same source on both sides
   shows the same text.
2. **Generate per side** replaces "Lyrics for generation: left / right" and the separate "Generate from Cleaned
   Vocals" button. Timing uses the cleaned vocals when a cleanup exists, with a checkbox to use the original.
3. **Hyphenation is automatic and invisible**: the text is hyphenated right before generating; the tab's text
   isn't changed. Hyphens the user wrote are kept **per word** (before: a whole line was skipped if it contained
   one `-`). Wrong splits are fixed in the editor.
4. **LRCLIB searches automatically** when artist and title are known and its text is empty.
5. **Defaults**: left LRCLIB, right Vocals.
6. **Artist and title for file uploads** from the file's tags, else from the file name ("Artist - Title.mp3").
7. **Texts are saved in the session** (not only the browser), so they survive another computer or cleared data.
8. **Re-generating** asks before replacing an existing chart.

## Steps

1. Backend: per-word hyphenation; lyric sources in the session (GET/PUT); artist/title from tags or file name on
   upload.
2. Frontend: new Step 2 layout (side component with tabs), generate per side, cleaned-vocals checkbox, warning.
3. Test together; docs and changelog.
