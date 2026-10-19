# Segment Local Regenerate Workflow (Design)

> **Status:** Current · **Last updated:** 2026-06-12

## Goal

Regenerate lyrics and notes for a selected area directly in Step 4, with better local accuracy and lower hallucination risk by processing an isolated audio clip.

## Selection Sources

Use the same processing engine for both entry points:

1. Cleanup segment
2. Active loop range

Both are converted to a unified range object:

- start_ms
- end_ms
- source_type: cleanup | loop

## Two-Way Workflow

### Path A: Lyrics-First (safe path, recommended default)

1. User opens modal for selected range.
2. Backend exports a temporary audio clip for start_ms to end_ms.
3. Backend runs local transcription and alignment preview on clip only.
4. UI shows recognized lyrics under waveform and confidence score.
5. User chooses:
   - Retry recording
   - Re-run recognition
   - Continue to note generation
6. If user continues, backend runs pitch + note synthesis using accepted lyrics.
7. Existing notes inside range are replaced with newly generated notes.
8. UI shows diff summary and offers undo/revert.

### Path B: One-Go Regenerate (fast path)

1. User starts full regenerate from selected range.
2. Existing notes inside range are removed first (with pre-snapshot for undo).
3. Backend runs transcription + pitch + note generation in one pipeline call.
4. New notes are inserted in range.
5. UI shows result summary and confidence warnings.

## Note Replacement Rules

1. Notes fully inside range are deleted.
2. Notes crossing the left or right boundary are split at boundary before deletion/replace.
3. One undo snapshot is always created before modifications.
4. Keep modifications constrained to range to avoid collateral edits.

## Draggable Modal UX

Single movable modal for both paths, anchored near selected range by default.

### Modal Sections

1. Header:
   - title
   - selected time range
   - drag handle
2. Mode:
   - Lyrics-first (recommended)
   - One-go regenerate
3. Recognition controls:
   - language
   - model preset (fast | accurate)
   - confidence threshold
4. Preview panel:
   - recognized text lines
   - per-line confidence
   - low-confidence highlights
5. Actions:
   - Re-recognize
   - Re-record area
   - Continue to notes
   - Apply
   - Cancel

### Progress States

1. Extracting clip
2. Recognizing lyrics
3. Aligning timing
4. Detecting pitch
5. Creating notes
6. Applying changes
7. Cleaning temporary files

## Backend API Shape (proposed)

### 1) Preview transcription for selected range

POST /api/segment-preview/:session_id

Request:
- start_ms
- end_ms
- language
- source_type
- model_preset

Response:
- preview_id
- lyrics_lines
- words_with_timing
- confidence_summary
- low_confidence_spans

### 2) Generate notes from preview or one-go

POST /api/segment-regenerate/:session_id

Request:
- start_ms
- end_ms
- mode: preview_confirmed | one_go
- preview_id (optional for preview_confirmed)
- replace_existing: true
- language
- model_preset

Response:
- created_notes
- deleted_note_ids
- split_note_changes
- confidence_summary
- warnings

### 3) Explicit cleanup endpoint (optional)

POST /api/segment-cleanup-temp/:session_id

Request:
- preview_id or job_id

Response:
- deleted_files_count

## Temp File Lifecycle and Disk Safety

1. Write temporary clips into a dedicated session temp folder:
   - backend/sessions/<session_id>/temp/
2. Name clips deterministically with timestamp + range hash.
3. Delete clip immediately after pipeline success or failure.
4. Also run periodic sweep for stale temp files (for crashed jobs).
5. Never store temp clip names in long-lived generated_files list.
6. Keep max temp retention short (for example 30-60 minutes).

## Hallucination Mitigation Strategy

1. Process only isolated range clips.
2. Add small configurable padding around range (for breathing context), then trim back to exact range in output.
3. Use confidence threshold to block low-quality apply.
4. In Lyrics-first path, require explicit user confirmation before note synthesis.
5. Prefer accepted preview lyrics as constrained text input in final generation step when available.

## Rollout Plan

1. Phase 1:
   - Path A only
   - preview lyrics and confidence
   - manual continue to note generation
2. Phase 2:
   - Path B one-go
   - warnings and confidence gates
3. Phase 3:
   - support both triggers (cleanup segment and loop)
   - polish modal UX and keyboard shortcuts

## Open Decisions

1. Default trigger location:
   - cleanup context menu only, or also loop toolbar action
2. How strict confidence gate should be before apply
3. Whether to allow manual lyric edits in preview before generation
4. Which model presets should be exposed in UI
