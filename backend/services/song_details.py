"""Artist and title of an uploaded song: from the file's tags, else from its name ("Artist - Title.mp3").

Read before the upload is converted to WAV, which drops the tags.
"""

import json
import os
import re
import subprocess
from typing import Optional

from services.youtube import clean_title

TAG_TIMEOUT_SEC = 20


def details_from_filename(filename: str) -> dict:
    """{"artist", "title"} from a file name like "01 - Artist - Title (Official Video).mp3"."""
    stem = os.path.splitext(os.path.basename(filename or ""))[0]
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"^\s*\d{1,3}\s*[-.]\s*", "", stem)          # leading track number
    stem = re.sub(r"\s*\[(vocals?|instrumental|karaoke|voc|instr)\]\s*$", "", stem, flags=re.I)
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", clean_title(stem), maxsplit=1)]
    if len(parts) == 2 and all(parts):
        return {"artist": parts[0], "title": parts[1]}
    return {"artist": "", "title": parts[0] if parts and parts[0] else ""}


def details_from_tags(path: str, ffprobe: Optional[str]) -> dict:
    """{"artist", "title"} from the file's metadata tags (ID3, MP4, Vorbis …); empty strings if none."""
    if not ffprobe:
        return {"artist": "", "title": ""}
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_entries", "format_tags", "--", path],
            capture_output=True, text=True, timeout=TAG_TIMEOUT_SEC)
        tags = {k.lower(): v for k, v in (json.loads(result.stdout or "{}").get("format", {}).get("tags") or {}).items()}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"artist": "", "title": ""}
    artist = tags.get("artist") or tags.get("album_artist") or ""
    return {"artist": artist.strip(), "title": (tags.get("title") or "").strip()}


def song_details(path: str, filename: str, ffprobe: Optional[str]) -> dict:
    """Tags first (each field on its own), the file name for what the tags don't have. Also returns the raw
    names (`filename`, `tags_name`) for checking the song online (services/song_identify.py)."""
    tagged = details_from_tags(path, ffprobe)
    named = details_from_filename(filename)
    tags_name = " - ".join(part for part in (tagged["artist"], tagged["title"]) if part)
    return {"artist": tagged["artist"] or named["artist"], "title": tagged["title"] or named["title"],
            "filename": os.path.splitext(os.path.basename(filename or ""))[0], "tags_name": tags_name}


def mark_new_song(session: dict, sources: dict, found: dict) -> None:
    """A new full mix (upload or YouTube), or vocals without one: its names become the proposal and the song is
    unconfirmed until the user checks names and languages in Step 1's song window. Step 2 waits with its LRCLIB
    search until then. Names the new file doesn't have stay as they were."""
    session["song_name_sources"] = sources
    session["song_confirmed"] = False
    for key in ("artist", "title"):
        if found.get(key):
            session[key] = found[key]
