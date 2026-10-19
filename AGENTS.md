# Agent Guide

Instructions for AI coding assistants (Claude Code, Copilot, Codex, ...) working in this repository. Humans: see
[CONTRIBUTING.md](CONTRIBUTING.md), which this file builds on.

## Project

Desktop app that turns songs into UltraStar karaoke charts. Svelte UI in a Tauri shell, Python FastAPI sidecar
(`backend/`) running the AI pipeline (Demucs, WhisperX, PYIN, pyphen). Read
[docs/architecture/overview.md](docs/architecture/overview.md) and [docs/architecture/pipeline.md](docs/architecture/pipeline.md)
before changing the pipeline.

## Commands

```bash
.venv/bin/python backend/main.py                 # backend on :8001
cd frontend && npm run dev                       # UI on :5173
cd backend && ../.venv/bin/python -m pytest      # unit tests (no torch needed)
```

## Rules

- Run the unit tests after every backend change; add tests for new or changed behaviour (see
  [docs/development/testing.md](docs/development/testing.md)).
- Put new pipeline logic in `backend/services/` as testable functions, not inline in `main.py` endpoints.
- Keep the alignment output format (`syllable`, `start`, `end`, `confidence`, `is_rap`, `line_index`, `method`)
  stable: pitch, BPM, GAP and the UltraStar writer depend on it.
- UltraStar format rules (beats, GAP, BPM ×4, line breaks) are in
  [docs/architecture/ultrastar-grid-gap.md](docs/architecture/ultrastar-grid-gap.md) and
  [docs/architecture/recalculation.md](docs/architecture/recalculation.md). Don't change them without updating these docs.
- Never commit audio, session data or evaluation songs.
- Update the docs you make outdated, following the conventions in [docs/README.md](docs/README.md).
- Active plans live in `docs/plans/`. Check them before starting larger work.
