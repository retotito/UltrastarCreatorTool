# Future stack: a desktop app that improves its own models

> **Status:** Draft · **Last updated:** 2026-11-01

A vision for a possible new version (a rewrite, not the 5.x line), written down so the reasons are not lost. The
current app continues as it is: Svelte in Tauri, Python sidecar ([0001](../decisions/0001-keep-python-sidecar.md)).

## Goal

An installable app for Windows, macOS and Linux (no web service: running the models on a server is too expensive
to offer for free) that

- runs today's models locally and can take up new ones quickly (models appear first in PyTorch, later in ONNX or
  GGUF);
- gets better with use: the corrections people make in the editor become training data for our own models, above
  all word alignment and syllable start/end, until the charts need no corrections;
- plays audio reliably on every system (playback, speed, MIDI, microphone).

All code is written by an AI agent, so the criteria are the product and how well agents work with the stack, not
which languages the maintainer knows.

## What the 5.0 release taught us

- **Audio in the UI is the weak spot.** The editor plays through the web view's `<audio>` and WebAudio. On Linux
  (WebKitGTK, which plays through GStreamer) the players stayed silent, then stalled, and Space arrived twice. MIDI
  notes start and stop from the drawing loop, so a late frame makes them longer.
- **The system's web view differs per OS** (WKWebView, WebView2, WebKitGTK). Drawing, modals and the editor worked
  everywhere; audio, timing and keys did not.
- **Python at runtime makes installers heavy and fragile**: 500–800 MB, slow start, wheels per macOS version (Intel
  needed torch 2.2.2, onnxruntime 1.19.2, numpy < 2), PyInstaller workarounds, a Hugging Face cache that Windows
  refused to open (symlinks).
- **Web UI itself was not the problem**, and it is what agents build best.

## Recommended stack

A native app: no browser engine and no system web view. The UI is drawn by the app itself, so the web view problems
above can't come back, and the app needs less memory and disk.

```
UI          Qt 6 / QML (declarative, GPU-accelerated), custom-drawn piano roll and waveform
Core        C++: audio engine, AI inference, file formats, UltraStar logic
  audio     native output/input (Qt Multimedia or a dedicated library such as miniaudio or RtAudio),
            time-stretching (e.g. Rubber Band), MIDI tones mixed into the output stream, sample-accurate
  models    ONNX Runtime (CoreML on macOS, DirectML on Windows, CUDA), whisper.cpp,
            llama.cpp / GGUF for large audio and language models
AI engine   Python, optional and downloaded separately: new PyTorch models before they exist as ONNX, local fine-tuning
Training    Python + PyTorch → ONNX (preprocessing inside the model) → model registry
```

Why:

- **Native on all three systems.** OBS Studio (audio and video), MuseScore 4 (a complex editor with playback),
  DaVinci Resolve and KDE are built this way and run on Windows, macOS and Linux.
- **The on-device AI ecosystem is C/C++** (ONNX Runtime, whisper.cpp, llama.cpp, ggml): used directly, no bindings.
- **Audio owns the clock**: one native engine, so the playhead, MIDI and the microphone agree on every system and on
  slow computers.
- **Mature and well documented** (30 years), which helps an AI agent as much as a person. Qt is LGPL.
- One native program: no Python in the default install, fast start.

Costs: C++ has no memory safety of its own (tests, sanitizers and code review matter more), and CMake builds take
more care than `cargo` or `dotnet`.

### Runner-up: Rust with Slint

Safer and more modern: Rust's memory safety and tooling, Slint as a native declarative UI (made by former Qt
developers), the AI libraries through mature crates (`ort`, `whisper-rs`, llama.cpp bindings, candle). The UI
ecosystem is younger than Qt's, which is the risk for an editor of this size. egui is the other Rust UI: very good
for tool UIs and custom drawing, plainer looking.

### Considered and ranked lower

| Stack | Why not first |
|---|---|
| Rust core + web UI in a bundled Chromium (Electron, CEF) | Same engine everywhere and what agents build best, but a browser layer the app doesn't need (~150 MB, more memory) |
| C# + Avalonia | Good, but reaches the AI libraries through bindings and has fewer audio libraries |
| C++ + JUCE | The best audio (DAWs, plugins), laborious for everything else; for a plugin version |
| Python + PySide6 | Qt with the newest models in-process, but the packaging problems stay |
| System web views (Tauri today, WebKitGTK) | The 5.0 lessons above |
| Flutter | Weak at audio and AI integration |

## The building blocks that matter more than the language

### 1. Corrections as training data

Every correction in the editor is a labelled example: the model's output against the right answer, at a known place
in the audio. Store them structured, not only as the finished `.txt`:

- per note: model output (start, end, pitch, syllable) and the user's final value;
- the model and pipeline version that produced it;
- the song's identity (artist/title, USDB id when known) and the audio's checksum, not the audio itself.

This can start in the current app: the editor already keeps the model's timings (`rawTimings`).

### 2. Training: where, and the copyright question

| Where | Pros | Cons |
|---|---|---|
| Central (our machine or a rented GPU) | Everyone's corrections help everyone; strong GPUs | The users' songs can't simply be uploaded |
| On the user's computer (small adapter, e.g. LoRA) | Audio never leaves the computer | Slow on laptops; Intel Macs practically can't |
| Federated (train locally, send only the model change) | No audio leaves the computer, everyone benefits | The most complex |

Without the audio, timings alone don't train a model. A pragmatic start: train centrally on songs we own, and use
the shared corrections (timings only, opt-in) to find where the models fail and which songs to add.

### 3. A replaceable model layer and a registry

- Models are files with a version, a size and a SHA-256, from our Hugging Face repository (as
  `services/model_mirror.py` does today).
- Each model declares its inputs and outputs; the app picks the runtime (ONNX, GGUF, the Python engine).
- Preprocessing (mel spectrograms, normalisation) goes into the exported model, so the app and the training can't
  compute features differently.

### 4. Evaluation before every model release

The reference charts (see [testing](../development/testing.md)) become an automatic suite: every new model or
pipeline version gets a score (onset/offset error per syllable, pitch accuracy, line breaks) and is released only
if it is better. The same suite checks a port against the Python pipeline.

## Path

1. Release 5.x as it is.
2. In the current app: store corrections (block 1) and automate the evaluation (block 4). Useful whatever comes
   next.
3. Move the remaining models to ONNX in Python, checked by the evaluation: smaller installers already in 5.x.
4. Start the new app: the audio engine and the editor UI first, then the pipeline stage by stage, each compared
   with the Python version on the reference songs.
5. Release it as a new major version once it matches 5.x on the evaluation.

## Open questions

- C++ + Qt, or Rust + Slint: decide with a prototype of the piano roll with playback and MIDI in both.
- Training data: opt-in sharing of timings, local fine-tuning, or both. Needs a licence and privacy check.
