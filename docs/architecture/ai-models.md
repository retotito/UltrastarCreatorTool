# AI models

> **Status:** Current · **Last updated:** 2026-11-06

The models the app uses, and their licences.

| Model | Purpose | Status |
|-------|---------|--------|
| [FCPE](https://github.com/CNChTu/FCPE) by CN_ChiTu ([ONNX export](https://huggingface.co/tuneperfect/fcpe-onnx)) | Pitch detection (neural, for singing) | Downloaded in setup (~48 MB) from [our unchanged copy](https://huggingface.co/Retotito/ultrastar-models), MIT licence |
| PYIN (librosa) | Pitch detection fallback | Built-in |
| [Tune Studio aligner](https://huggingface.co/tuneperfect/tunestudio-aligner) by [Tune Studio](https://github.com/ZerNico/tunestudio): Meta's [MMS forced aligner](https://huggingface.co/MahmoudAshraf/mms-300m-1130-forced-aligner) fine-tuned on singing | Syllable timing: aligns your lyrics to the vocals | Downloaded in setup from [our unchanged copy](https://huggingface.co/Retotito/ultrastar-models). Weights licensed **CC-BY-NC-4.0** (non-commercial) |
| [uroman](https://github.com/isi-nlp/uroman) by Ulf Hermjakob, USC ISI | Romanizes lyrics in any script for the aligner | Bundled. This project uses the universal romanizer software 'uroman' written by Ulf Hermjakob, USC Information Sciences Institute (2015-2020) |
| WhisperX | Lyric suggestions from the vocals; fallback timing | Optional (falls back to vanilla Whisper, then user lyrics) |
| openai-whisper | Transcription fallback | Optional (if WhisperX unavailable) |
| Demucs v4 | Vocal separation | Optional (can upload vocals directly) |
| [GAME](https://github.com/openvpi/GAME) by openvpi | Finds the sung notes | Downloaded in setup, non-commercial licence |
| Mel-Band RoFormer vocals model by Kimberley Jensen ([ONNX export by audiojs](https://huggingface.co/audiojs/mel-roformer)) | Better vocal separation | Optional, downloaded on first use |

> **Torch dependency:** WhisperX, openai-whisper, and Demucs all require PyTorch. If `torch` doesn't support your platform (e.g. older Intel Macs), the app still works — you just skip AI-powered transcription and vocal separation. Upload vocals directly and provide lyrics manually instead.
