"""The audio files of an exported song, as MP3 (the default, every game plays it) or Ogg Vorbis (what UltraStar Play and
Melody Mania recommend).

The app keeps its audio as WAV, so an export encodes once, whichever format is chosen.
"""

import os
import subprocess
import tempfile
from typing import List, Optional, Tuple

from services.song_export import ExportTargetError

# Encoder settings, tried in order. MP3: LAME VBR ~190 kbit/s. Ogg: libvorbis quality 6 (~192 kbit/s); FFmpeg's own
# Vorbis encoder is the fallback for an FFmpeg without libvorbis (Homebrew's): it works but sounds worse.
_ENCODERS = {
    "mp3": [["-codec:a", "libmp3lame", "-q:a", "2"]],
    "ogg": [["-codec:a", "libvorbis", "-q:a", "6"],
            ["-codec:a", "vorbis", "-strict", "experimental", "-q:a", "6"]],
}
AUDIO_FORMATS = tuple(_ENCODERS)


class AudioEncodeError(ExportTargetError):
    """The audio couldn't be made in the chosen format. Something to tell the user."""


def audio_format(value) -> str:
    """The export's audio format from a request value: "mp3" or "ogg", MP3 for anything else."""
    value = str(value or "").strip().lower().lstrip(".")
    return value if value in _ENCODERS else "mp3"


def audio_ext(fmt: str) -> str:
    return "." + audio_format(fmt)


def encode_commands(ffmpeg: str, source: str, target: str, fmt: str) -> List[List[str]]:
    """The FFmpeg commands that make `target` from `source` in `fmt`, to try in order: 44.1 kHz stereo, no video."""
    return [[ffmpeg, "-y", "-i", source, "-vn", "-ar", "44100", "-ac", "2", *codec, target]
            for codec in _ENCODERS[audio_format(fmt)]]


def audio_for_export(path: str, fmt: str, ffmpeg: Optional[str] = None) -> Tuple[str, bool]:
    """`path` in `fmt`: (path to use, whether it is a temporary file the caller removes). A file already in that format is
    used as it is. MP3 falls back to the original file if it can't be encoded, as before; Ogg raises AudioEncodeError,
    since a file named .ogg that isn't one doesn't play."""
    fmt = audio_format(fmt)
    ext = audio_ext(fmt)
    if path.lower().endswith(ext):
        return path, False
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        target = tmp.name
    for command in encode_commands(ffmpeg or "ffmpeg", path, target, fmt):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and os.path.getsize(target) > 0:
            return target, True
    os.unlink(target)
    if fmt == "mp3":
        return path, False
    raise AudioEncodeError(f"Couldn't make the .{fmt} file of {os.path.basename(path)}. Try MP3 instead.")
