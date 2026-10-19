# Testing

> **Status:** Current · **Last updated:** 2026-10-19

Three levels, from fast to slow:

| Level | What | Needs | Runs |
|---|---|---|---|
| **Unit** | Pure logic: lyrics parsing, syllable timing, UltraStar writer and download format, hyphenation, reference parsing | `requirements-dev.txt` (no torch) | Every push / PR in CI, locally in < 1 s |
| **Slow** (`-m slow`) | Code that loads AI models | Full AI install + downloaded models | Locally, on demand |
| **Eval** (`-m eval`) | Alignment quality on real songs against verified reference charts | Local songs (see below) | Locally, before changing the alignment |

Manual checks before a release are in the [release checklist](release-checklist.md).

## Running

```bash
cd backend
../.venv/bin/pip install -r requirements-dev.txt   # once

../.venv/bin/python -m pytest                       # unit tests
../.venv/bin/python -m pytest tests/unit/test_ultrastar_writer.py -k bpm   # one file / one test
../.venv/bin/python -m pytest --cov=services        # with coverage
../.venv/bin/python -m pytest -m slow               # model tests
```

## Layout

```
backend/
├── pyproject.toml          pytest config and markers
├── requirements-dev.txt    test dependencies
├── tests/
│   ├── conftest.py         shared fixtures (e.g. make_pitch_data), skips slow/eval by default
│   └── unit/               one file per service area
└── scripts/                manual scripts (not collected by pytest)
```

## Writing tests

- Test behaviour through the module's functions, with small hand-made inputs. Don't load audio in unit tests:
  build pitch tracks with the `make_pitch_data` fixture, word timings as plain dicts.
- Name tests as statements: `test_line_change_inserts_a_break_two_beats_after_the_last_note`.
- A test that needs models gets `@pytest.mark.slow`; one that needs local songs gets `@pytest.mark.eval`.
- **Known bugs** are written as `@pytest.mark.xfail(reason="Known gap: ...", strict=True)`. When someone fixes the
  bug the test passes, `strict` turns that into a failure, and the marker must be removed. Open gaps:
  - Golden rap notes (`G`) don't get the trailing `-` on download.
  - `parse_ultrastar_file` ignores standard `R`, `G` and `F` note lines, so reference comparisons skip rap and
    freestyle notes.
- Logic that sits inside an endpoint in `main.py` can't be unit-tested: move it into a function in `services/`
  first (as done for `format_for_download`).

## Evaluation songs

Evaluation uses community charts that are **not** made by this tool, with their audio. Audio is copyrighted and stays
local: `backend/eval/songs.yaml`, `backend/eval/cache/` and `backend/eval/reports/` are gitignored. The harness
itself is planned in [plans/forced-alignment.md](../plans/forced-alignment.md) (Phase 1.3).

Current set (from `~/Music/UltraStar Deluxe/`): Alicia Keys – Fallin', Chrystal Waters – Gypsy Woman,
Lenny Kravitz – I'll Be Waiting, The Cardigans – Lovefool, The Police – Roxanne, U2 – Beautiful Day.
A German song is still missing.
