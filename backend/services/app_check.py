"""Which of the libraries the app needs are there. They are built into the packaged app (backend.spec) and can't be
downloaded afterwards, so a missing one means the installation is broken: the setup screen says so instead of
features quietly doing less (numbers not spelled, no translation warning, …)."""

import importlib.util
from typing import List

# import name → what needs it
REQUIRED = {
    "numpy": "everything", "librosa": "audio", "soundfile": "audio", "onnxruntime": "aligner, pitch, notes",
    "huggingface_hub": "model downloads", "pyphen": "hyphenation", "uroman": "aligning non-Latin scripts",
    "num2words": "numbers in lyrics", "langdetect": "subtitle and line languages", "mido": "MIDI export",
}


def missing_packages() -> List[str]:
    """The required libraries that can't be imported ("num2words (numbers in lyrics)")."""
    missing = []
    for name, used_for in REQUIRED.items():
        try:
            found = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(f"{name} ({used_for})")
    return missing
