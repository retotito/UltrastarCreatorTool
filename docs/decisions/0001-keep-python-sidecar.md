# 0001: Keep the Python sidecar

> **Status:** Accepted · **Date:** 2026-10-19

## Context

The backend is a Python FastAPI process bundled with PyInstaller and started by the Tauri app. Packaging it is the
most fragile part of the release build: torch, WhisperX, pyannote, Demucs, librosa and numba all need PyInstaller
workarounds (`backend/backend.spec`), each architecture needs its own runner, and the artifact is several GB.

A comparable project ([Tune Studio](https://github.com/ZerNico/tunestudio)) has no Python at runtime: it runs ONNX
and GGML models from a Rust addon. The same is possible in our Tauri Rust backend (`ort`, `whisper-rs`).

## Decision

Keep the Python sidecar for now. Fix the alignment quality first
([0002](0002-forced-alignment-of-user-lyrics.md)), in Python, where experimenting is fastest.

## Alternatives considered

- **Port the backend to Rust (Tauri commands, ONNX / whisper.cpp).** Removes PyInstaller and makes CI simpler and
  cross-platform. But it means rewriting about 9,500 lines and 69 endpoints, including the librosa signal processing.
  Postponed, not rejected. The UI only uses HTTP, so a step-by-step migration stays possible.

## Consequences

- Release builds stay heavy. Mitigations: fail the build when a required package doesn't install, and add a smoke
  test of the frozen backend.
- New models can be tried directly from Python packages.
- If the backend is ported later, the evaluation harness (see [testing](../development/testing.md)) makes it
  possible to check the port against the Python results.
