# Documentation

Developer documentation for Ultrastar Creator Tool. For what the app does and how to install it, see the
[project README](../README.md). For setup, tests and conventions, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Where things live

| Folder | Contents |
|---|---|
| [architecture/](architecture/) | How the system is built: components, the AI pipeline, UltraStar domain rules |
| [features/](features/) | Design specs of individual app features |
| [development/](development/) | Running, testing, building and releasing |
| [decisions/](decisions/) | Architecture Decision Records (ADRs): why things are the way they are |
| [plans/](plans/) | Active work plans |
| [archive/](archive/) | Outdated documents, kept for history. Don't rely on them |
| [known-issues.md](known-issues.md) | Known limitations and test cases |

## Index

**Architecture**
- [Overview](architecture/overview.md): components, processes, data storage
- [AI pipeline](architecture/pipeline.md): from audio to UltraStar `.txt`, as currently implemented
- [UltraStar grid, beats & GAP](architecture/ultrastar-grid-gap.md)
- [BPM / GAP change recalculation rules](architecture/recalculation.md)

**Features**
- [YouTube import](features/youtube-import.md)
- [Backup](features/backup.md)
- [Cleanup sections](features/cleanup-sections.md)
- [Segment-local regenerate](features/segment-regenerate.md)
- [Vocal trace vs mic lines](features/vocal-trace-vs-mic.md)
- [Vocal tracing strategy (Analyze 5s)](features/vocal-tracing-strategy.md)
- [Keyboard shortcuts](features/shortcuts.md)

**Development**
- [Commands](development/commands.md): start servers, common tasks
- [Testing](development/testing.md): automated tests and the evaluation harness
- [Release checklist](development/release-checklist.md): manual checks before a release
- Building: [macOS](development/building/macos.md) · [Windows](development/building/windows.md) · [Linux](development/building/linux.md)

**Decisions**
- [0001: Keep the Python sidecar](decisions/0001-keep-python-sidecar.md)
- [0002: Forced alignment of user lyrics](decisions/0002-forced-alignment-of-user-lyrics.md)
- [0003: GAME decides syllable pitches](decisions/0003-game-note-model.md)

**Plans**
- [Forced alignment of user lyrics](plans/forced-alignment.md)

## Conventions

- File names are lowercase-kebab-case (`segment-regenerate.md`).
- Every document starts with its title and a status line:
  `> **Status:** Current | Draft | Archived · **Last updated:** YYYY-MM-DD`
- Documents describe the **current** state. History goes in [CHANGELOG.md](../CHANGELOG.md) and git; the reasons
  for important choices go in `decisions/`.
- When a document becomes outdated, update it or move it to `archive/` with a note on what replaced it.
  Move files with `git mv` so their history is kept.
- New decision records: copy [decisions/template.md](decisions/template.md) and use the next number.
