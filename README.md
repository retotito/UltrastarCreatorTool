<p align="center">
  <img src="website/img/editor.webp" alt="Ultrastar Creator Tool: the piano roll editor with notes and lyrics over the song's waveform" width="900">
</p>

<h1 align="center">Ultrastar Creator Tool</h1>

<p align="center"><b>Create UltraStar songs with the help of AI.</b><br>
Upload a song or add a link to a song on YouTube, and create an UltraStar song with a little help from AI.</p>

<p align="center">
  <a href="https://retotito.github.io/UltrastarCreatorTool/"><b>Website</b></a> ·
  <a href="https://retotito.github.io/UltrastarCreatorTool/#download"><b>Download</b></a> ·
  <a href="https://github.com/retotito/UltrastarCreatorTool/issues/new/choose">Report a problem or idea</a>
</p>

<p align="center">
  <a href="https://github.com/retotito/UltrastarCreatorTool/releases"><img alt="Latest version" src="https://img.shields.io/github/v/release/retotito/UltrastarCreatorTool?label=version"></a>
  <a href="https://github.com/retotito/UltrastarCreatorTool/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/retotito/UltrastarCreatorTool/actions/workflows/tests.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: GPL-3.0" src="https://img.shields.io/badge/license-GPL--3.0-blue"></a>
</p>

---

## Download

**[⬇ Download the latest version](https://github.com/retotito/UltrastarCreatorTool/releases/latest)**: choose your
file under "Assets".

| Computer | File | Needs |
|----------|------|-------|
| Mac with Apple Silicon | `..._aarch64.dmg` | macOS 14 or newer |
| Mac with Intel | `..._x86_64.dmg` | macOS 12 or newer |
| Windows | `....msi` | 64-bit Windows |

The first start downloads the AI models, about **3.5 GB**. After that, the app offers new versions by itself; your
songs and models stay.

The app isn't code-signed yet, so your system warns you the first time:

- **macOS:** drag the app to Applications and open it. When macOS blocks it, go to **System Settings → Privacy &
  Security** and click **Open Anyway**.
- **Windows:** when SmartScreen warns you, click **More info**, then **Run anyway**.

**Coming from a version before 5.0?** Export the songs you want to keep as a ZIP, close and uninstall the old app, then
install this one.

## What's new in 5.0

- **Duets:** duet songs stay intact, both singers are shown, and you edit one at a time
- **YouTube:** paste a link instead of uploading a file, use its subtitles as lyrics, and export the video
- **Export:** a song folder ready for the game, or a `.txt` in USDB's format
- **Better results:** on six test songs, misplaced syllables dropped from 57 % to 7 %; a new model finds the notes
- **Better vocal separation:** an optional slower model, much cleaner where voices overlap
- **Automatic updates:** the app offers new versions and shows what's new

See the [full feature list](docs/features/overview.md) and the [CHANGELOG](CHANGELOG.md).

## Video tutorials

These show earlier versions, so some screens look different.

- [Overview: getting started](https://www.youtube.com/watch?v=zKw03mhrYX8&t=5s)
- [Pitch line, vocal tracing and sing along](https://www.youtube.com/watch?v=p4ihQaDhwfg)
- [Looping and scrubbing](https://www.youtube.com/watch?v=WwAZQlhqSwE&t=2s)
- [BPM and metronome](https://www.youtube.com/watch?v=L8jnov5M-XY)
- [AI limits and workarounds](https://www.youtube.com/watch?v=WOKcdjpthh0)

## Something went wrong?

The backend log shows every processing step and error:

- **macOS:** `~/Library/Logs/com.ultrastar.creator/backend.log`
- **Windows:** `%LOCALAPPDATA%\com.ultrastar.creator\logs\backend.log`

Please [open an issue](https://github.com/retotito/UltrastarCreatorTool/issues) and attach it.

## Licence

The app is free and open source under the [GPL-3.0](LICENSE). Its BPM detection uses Essentia, which stays under the
AGPL-3.0. The licence doesn't cover the AI models: some, including the aligner and the note model, are **free for
non-commercial use only**. See [AI models](docs/architecture/ai-models.md) for all of them and their licences.

## Development

To run the app from the source code you need Python 3.12, Node.js 18 or newer, and FFmpeg
(macOS: `brew install ffmpeg`).

```bash
git clone https://github.com/retotito/UltrastarCreatorTool.git
cd UltrastarCreatorTool

# Backend
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

# AI packages (about 2 GB). Without them, upload the vocals and lyrics yourself.
pip install torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0
pip install -r backend/requirements-ai.txt onnxruntime==1.24.4 whisperx==3.8.5 faster-whisper==1.2.1

python backend/main.py           # runs on port 8001

# Frontend, in a second terminal
cd frontend
npm install
npm run dev                      # open http://localhost:5173
```

Intel Macs need older AI packages: see the versions in [the build workflow](.github/workflows/release.yml). To build the
desktop app, see the guides for [macOS](docs/development/building/macos.md) and
[Windows](docs/development/building/windows.md).

[CONTRIBUTING.md](CONTRIBUTING.md) covers tests and conventions, and [docs/](docs/README.md) covers the architecture.

## Thanks

A big thank you to [Zeni (ZerNico)](https://github.com/ZerNico) from [Tune Perfect](https://huggingface.co/tuneperfect)
for the [aligner model](https://huggingface.co/tuneperfect/tunestudio-aligner). Fine-tuned on singing for
[Tune Studio](https://github.com/ZerNico/tunestudio), it now places your lyrics on the vocals in this app, and it made
the biggest difference to the results in 5.0.
