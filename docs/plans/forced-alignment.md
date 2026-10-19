# Plan: Forced Alignment of User Lyrics

| | |
|---|---|
| **Status** | Accepted, in progress (docs restructure and test foundation done) |
| **Owner** | Reto Küpfer |
| **Created** | 2026-10-19 |
| **Goal** | Remove invented note placements by timing the user's corrected lyrics directly against the audio |

## 1. Problem

Generated UltraStar files contain notes at wrong positions ("hallucinations") wherever Whisper did not
recognise the sung words correctly. See [Known Issues](../known-issues.md), case "Gypsy Woman".

### Root cause

Timing currently comes from **Whisper's transcript**, not from the lyrics the user corrected:

```
vocal.wav ─► WhisperX ASR ─► Whisper's words ─► wav2vec2 align ─► timed Whisper words
                                                                         │
user-corrected lyrics ──────────────────────► _match_words() ◄───────────┘
                                                    │
                                   unmatched words ─► _fill_gaps_hybrid()
                                                      (interpolation, "silent region"
                                                       remapping, energy guessing)
```

When Whisper misses, mishears or invents words, the user's words have no timestamp to match. The gap-fill step
then **guesses** positions ([alignment_whisper.py](../../backend/services/alignment_whisper.py) `_fill_gaps_hybrid`,
`_energy_align_range`). Those guesses are the hallucinations. Better heuristics cannot fix this: the information
is missing.

### Contributing factors

| Factor | Current | Effect |
|---|---|---|
| Alignment model | `WAV2VEC2_ASR_BASE_960H` (read speech, base size) | Weak on sung vowels, melisma, vocalise |
| Default ASR model | `medium` ("balanced" preset) | More misrecognitions than `large-v3-turbo` |
| Voice activity detection | pyannote (speech-trained) | Band bleed and reverb tails reach Whisper |
| Segment filtering | none | Low-confidence / made-up segments become lyrics suggestions |

## 2. Solution

Run CTC **forced alignment of the user's final lyrics** over the whole song. Whisper is used only to *suggest*
text in Step 2; it is no longer a timing source.

```
vocal.wav ─► aligner (MMS, once per audio) ─► per-frame letter probabilities ("emissions")
                                                          │
user-corrected lyrics ─► normalise + romanise ─► Viterbi ─┘─► every word + letter timed, in order
                                                                    │
                                     syllable split (existing char logic) ─► cleanups ─► syllable_timings
```

Properties:

- **Every lyric word gets a position**, in order, where the audio fits it best. No matching step, no gaps.
- **Failure is visible.** If the text cannot fit the audio, alignment fails with an error, or the affected
  words get a low score that the editor can show. It never makes up positions.
- **Language coverage** grows from the WhisperX alignment models to the ~1,100 MMS languages (via romanisation).
- **Output format stays the same** as `align_whisper()`, so pitch, BPM, GAP and the UltraStar writer don't change.

Implementation basis: model `MahmoudAshraf/mms-300m-1130-forced-aligner` (pinned) through `transformers`, with our
own Viterbi search; no forced-alignment package (see [ADR 0002](../decisions/0002-forced-alignment-of-user-lyrics.md)
for why). Tune Studio uses the same approach with a singing fine-tune of this model.

## 3. Decisions

| # | Question | Decision (2026-10-19) |
|---|---|---|
| D1 | The MMS model weights are **CC-BY-NC-4.0** (non-commercial). Acceptable? | **Accepted.** The app is free; credit the model in the README and setup screen; engine stays swappable. See [ADR 0002](../decisions/0002-forced-alignment-of-user-lyrics.md) |
| D2 | Evaluation songs | Community charts from `~/Music/UltraStar Deluxe/` (local only, not in git): Alicia Keys – Fallin', Chrystal Waters – Gypsy Woman, Lenny Kravitz – I'll Be Waiting, The Cardigans – Lovefool, The Police – Roxanne, U2 – Beautiful Day. Charts made by this tool are excluded. **Gap:** no German song yet |
| D3 | Old docs | **Archived** in `docs/archive/` |

## 4. Phases

Each phase ends in a working, releasable state.

### Phase 0: Spike (go / no-go)

Goal: prove the gain on real songs before changing the app.

- `backend/scripts/spike_ctc_align.py`: runs `ctc-forced-aligner` on a vocal file + lyrics and prints word
  timings. Throwaway code, not wired into the app.
- Run it and the current pipeline on the D2 songs, compare both against the references with the existing
  `compare_timing_ms()` ([reference_comparison.py](../../backend/services/reference_comparison.py)).
- Check that the package works under Python 3.12 / torch 2.8 (the current `.venv`), its CPU runtime on a 4-minute
  song, and peak memory.

**Exit:** CTC alignment has clearly fewer gross errors (> 500 ms) than the current pipeline on the problem songs.
Otherwise stop and reconsider.

### Phase 1: Test and evaluation foundation

Goal: measure every later change, and stop regressions.

1. **pytest setup** ✅ done 2026-10-19
   - `backend/requirements-dev.txt` (pytest, pytest-cov); `backend/pyproject.toml` with pytest config.
   - `backend/tests/` with `conftest.py`, `unit/`, `integration/`, `fixtures/`.
   - Markers: `slow` (loads models), `eval` (needs local songs). The default run uses neither and needs no torch.
2. **Characterization tests** ✅ done 2026-10-19 (download formatting moved to `services/ultrastar.py` `format_for_download` so it can be tested):
   - `parse_lyrics` (hyphens, `[RAP]`, empty lines, apostrophes)
   - syllable split by character timestamps (`_distribute_by_chars`, `_distribute_proportional`)
   - UltraStar writer ([ultrastar.py](../../backend/services/ultrastar.py)): headers, GAP, line breaks, trailing `-`,
     apostrophe normalisation (recent fixes `05a9a60`, `8f72c72`)
   - hyphenation (the old `test_hyphenation.py` script turned into assertions)
   - `parse_ultrastar_file` / `compare_timing_ms`
3. **Evaluation harness** `backend/eval/`
   - `songs.example.yaml`: manifest format (vocal path, lyrics, reference `.txt`, language). The real
     `songs.yaml` and the audio stay local and are gitignored.
   - `run_eval.py --engine legacy|ctc`: runs alignment on every song and writes a Markdown report.
   - Metrics per song and overall: median onset error, % syllables within 50 / 100 ms, **gross errors > 500 ms**
     (the hallucination metric), runtime.
4. **CI** ✅ done 2026-10-19: `.github/workflows/tests.yml` on push and PR: unit tests only (no torch, < 1 min). Kept separate from the
   release build.
5. ✅ Old script-style tests: `test_alignment.py` moved to `backend/scripts/manual_energy_alignment.py`, `test_hyphenation.py` replaced by real tests.

### Phase 2: Forced alignment engine

New module `backend/services/forced_alignment.py`, public API:

```python
def align_lyrics(audio_path: str, lyrics_text: str, language: str,
                 pitch_data: dict | None = None) -> list[dict]:
    """Same output format as align_whisper(): syllable, start, end, confidence, is_rap, line_index, method."""
```

Internal steps (each a small, tested function):

| Step | What | Test approach |
|---|---|---|
| 1. Lyrics → words | Reuse `parse_lyrics`; join syllables into words; keep the syllable map | Unit |
| 2. Normalise | Strip `~`, punctuation; split `oh-oh-oh` vocalise into parts; drop bracketed backing vocals from the alignment text (configurable) | Unit |
| 3. Language | ISO 639-1 (app) → ISO 639-3 (MMS) table for all languages in `frontend/src/lib/languages.ts` | Unit: every UI language maps |
| 4. Emissions | Model over the whole vocal track (30 s windows, 2 s context); **cached per audio file hash** so segment-regenerate and re-generate are fast | Slow test on a short clip |
| 5. Viterbi | `get_alignments` / `get_spans` over the full text; fails clearly if the text doesn't fit | Unit with **synthetic emissions** (no model needed) |
| 6. Word + letter times | `postprocess_results`, plus letter spans for syllable splitting | Unit, synthetic |
| 7. Syllable split | Existing char-based split, fed with MMS letter times | Reuses Phase 1 tests |
| 8. Cleanups | *Pull in edges*: a line's first/last word more than 0.8 s away from its neighbour gets moved back. *Snap to voice*: word start moves to the first voiced, loud frame (uses existing `pitch_data`) | Unit with hand-made arrays |
| 9. Confidence | Mean log-prob per word → `confidence` 0–1; lines below a threshold flagged `low_confidence` | Unit |

Optional, behind a setting: when the lyrics include line times (e.g. from a future LRCLIB import), re-align only
the lines that land far from their expected time, inside a padded window.

### Phase 3: Integration

- Setting `alignment_engine`: `ctc` (default once Phase 0/eval agree) or `legacy` (current code).
- Wire into the generate step ([main.py](../../backend/main.py) "Step 3c: Alignment") and `segment_generate`.
  Segment regenerate aligns the user's text in the segment window using the cached emissions.
- Fallback order: `ctc` → (model missing or failure) `legacy` → energy fallback, each logged with the reason.
- Onset snapping ([onset_snapping.py](../../backend/services/onset_snapping.py)) re-evaluated with the eval harness:
  keep only if it still improves results.
- Setup screen: download the aligner model (~1.2 GB) like the existing models; storage manager lists it.
- Packaging: add `ctc_forced_aligner` (and its romanisation data) to `requirements.txt` and `backend.spec`.
  Remove the `|| echo "continuing"` fallback in `build.yml` for required packages, so a broken install fails the build.
- `whisper_words` stay in the session: they still feed segment preview and live words.

### Phase 4: Better lyric suggestions (Whisper hardening)

Improves the text the user starts from. Lower priority because alignment no longer depends on it.

- **Voiced-range gating** before Whisper: loudness gate tuned for separated vocals (−30 dB below the loud
  parts, breaths < 0.5 s joined, sounds < 0.25 s and stretches < 1 s dropped, chunks ≤ 28 s).
- **Drop made-up segments**: confidence < 0.3; or fewer than 2 characters/second with confidence < 0.7; or known
  filler ("Thanks for watching", "Subtitles by …", punctuation only). Check first whether WhisperX's batched mode
  keeps a per-segment log-prob; if not, call faster-whisper directly for this step.
- Default preset → `large-v3-turbo`.

### Phase 5: Editor feedback (optional)

- Step 4 marks `low_confidence` lines (e.g. orange line marker), so the user knows where to check.
- Problem list "lines to check" with jump-to.

## 5. Acceptance criteria

1. On the D2 evaluation set, gross errors (> 500 ms) drop clearly compared to `legacy`, with no song getting worse.
   Final targets are set from the Phase 0 numbers.
2. Every syllable of the user's lyrics appears in the output in order. No positions are invented.
3. Unit tests run in CI on every push in under a minute; the eval report is attached to the PR that switches the default.
4. Release build still produces a working app on both macOS architectures.
5. Docs updated: pipeline doc, known issues, model credits/licence.

## 6. Documentation restructure (runs alongside)

The current `docs/` is a flat list mixing current specs, outdated plans (MFA, V2) and build notes. Proposed
structure:

```
README.md                     Users: what it is, download, how to use (shortened; changelog moved out)
CHANGELOG.md                  Release notes (moved from README)
CONTRIBUTING.md               Dev setup, running app + tests, conventions, PR checklist
docs/
├── README.md                 Index: what lives where
├── architecture/
│   ├── overview.md           Components (Svelte, Tauri, Python sidecar), data flow, sessions
│   ├── pipeline.md           The AI pipeline as it IS (replaces PIPELINE.md + PIPELINE_V2.md)
│   └── ultrastar-format.md   ULTRASTAR_GRID_GAP.md + RECALCULATION.md
├── features/                 BACKUP_FEATURE, CLEANUP_SECTIONS, SEGMENT_LOCAL_REGENERATE_WORKFLOW,
│                             VOCAL_TRACE_VS_MIC_LINES, SHORTCUTS
├── development/
│   ├── commands.md           COMMANDS.md
│   ├── testing.md            pytest, markers, eval harness, TEST_CHECKLIST (manual release checks)
│   └── building/             macos.md (TAURI.md), windows.md, linux.md
├── decisions/                Short ADRs: context, decision, consequences
│   ├── 0001-keep-python-sidecar.md
│   └── 0002-forced-alignment-of-user-lyrics.md
├── plans/                    Active plans (this file)
├── known-issues.md
└── archive/                  PLAN_V2, REFACTORING_SUMMARY, CHECKLIST, superseded designs
```

Conventions:

- File names lowercase-kebab-case.
- Each doc starts with a small header: **Status** (current / draft / archived) and **Last reviewed** (date).
- Docs describe the current state; history goes in `CHANGELOG.md` and git, decisions in `decisions/`.
- Replace the stale template in `.github/copilot-instructions.md` with a real agent/contributor guide
  (`AGENTS.md`), linked from `CONTRIBUTING.md`.
- Moves done with `git mv` so history is kept; links in README updated.

## 7. Suggested order of work

| Step | Work | Size |
|---|---|---|
| 1 | Docs restructure (moves, index, headers, CONTRIBUTING) | S |
| 2 | Phase 1.1–1.2, 1.4: pytest + characterization tests + CI | M |
| 3 | Phase 0 spike + Phase 1.3 eval harness (needs D2 songs) | M |
| 4 | Phase 2 engine | L |
| 5 | Phase 3 integration + packaging | M |
| 6 | Phase 4 Whisper hardening | M |
| 7 | Phase 5 editor feedback | S–M |

## 8. Risks

| Risk | Mitigation |
|---|---|
| MMS (speech-trained) still weak on some singing styles | Eval set measures it; engine is swappable for a singing fine-tune later |
| CPU runtime / memory of a 300M model on long songs | Windowed emissions, cached per audio; measured in Phase 0 |
| PyInstaller misses package data (romanisation tables) | Smoke test of the frozen backend in the release workflow |
| Licence (D1) | Decision before Phase 2; credit in README and setup screen |
| User lyrics contain words that aren't sung (e.g. backing vocals) | Bracketed text excluded from alignment; low-confidence flags |
