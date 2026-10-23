"""Naming a song's audio files after it: "Artist - Title.wav", "Artist - Title [Vocals].wav"."""

import os

from utils.logger import log_step

_FORBIDDEN = set('\\/:*?"<>|\0')


def safe_filename(name: str) -> str:
    """`name` without characters file systems forbid, at most 120 characters, never empty."""
    cleaned = "".join(c for c in name if c not in _FORBIDDEN).strip(" .")
    return cleaned[:120] or "Untitled song"


def rename_audio_to_song(session: dict) -> list:
    """Rename the session's full mix to "Artist - Title<ext>" (and an uploaded vocals-only file to
    "Artist - Title [Vocals]<ext>"), updating the session's paths. Vocals Demucs made from a mix keep their
    name. A file whose target name is taken is left as it is. Returns the (old, new) names renamed."""
    artist, title = (session.get("artist") or "").strip(), (session.get("title") or "").strip()
    if not (artist and title):
        return []
    base = safe_filename(f"{artist} - {title}")
    renames = [("original_audio", "")]
    vocal = session.get("vocal_audio") or ""
    if not session.get("original_audio") and os.path.basename(vocal).startswith("vocals_"):
        renames.append(("vocal_audio", " [Vocals]"))
    done = []
    for key, suffix in renames:
        path = session.get(key)
        if not path or not os.path.isfile(path):
            continue
        target = os.path.join(os.path.dirname(path), base + suffix + os.path.splitext(path)[1])
        if os.path.abspath(target) == os.path.abspath(path) or os.path.exists(target):
            continue
        try:
            os.replace(path, target)
        except OSError as e:
            log_step("METADATA", f"Couldn't rename {os.path.basename(path)}: {e}")
            continue
        session[key] = target
        if key == "original_audio":
            session["filename"] = os.path.basename(target)
        done.append((os.path.basename(path), os.path.basename(target)))
        log_step("METADATA", f"Renamed {os.path.basename(path)} → {os.path.basename(target)}")
    return done
