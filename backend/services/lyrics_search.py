"""Lyrics from LRCLIB (lrclib.net), an open database of (often line-synced) song lyrics.

Used by Step 2's "Find lyrics online": the published lyrics are usually complete, where Whisper
misses or mishears words in sung audio. Tune Studio uses the same source.
"""

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional

from utils.logger import log_step

API = "https://lrclib.net/api/search"
# LRCLIB asks clients to identify themselves.
USER_AGENT = "UltrastarCreatorTool (https://github.com/retotito/UltrastarCreatorTool)"
TIMEOUT_SEC = 10
# LRCLIB answers 503 "ServerOverloaded" (with Retry-After) or 429 when busy: wait and try again.
RETRY_STATUSES = {429, 502, 503, 504}
RETRY_DELAYS_SEC = (1, 2, 4)


class LyricsServiceBusy(OSError):
    """LRCLIB stayed busy (overloaded) after retrying."""

TIMESTAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
# Whole-line section labels like "[Chorus]" or "(Verse 2)"; [RAP] / [/RAP] are the app's own markers.
SECTION_LABEL = re.compile(r"^\s*[\[(][^\])]*[\])]\s*$")
APP_MARKERS = {"[rap]", "[/rap]"}
# Title noise that versions add: "(Remastered 2011)", "- Live", "[Official Video]".
TITLE_NOISE = re.compile(r"[(\[].*?[)\]]|\s+-\s+.*$")


def normalize(text: str) -> str:
    """Lowercase, accents and punctuation removed, single spaces: for comparing titles and artists."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def base_title(title: str) -> str:
    return normalize(TITLE_NOISE.sub(" ", title or ""))


def parse_lrc(text: str) -> List[dict]:
    """Lines of LRC text, sorted by time. A line with several timestamps appears once per timestamp."""
    lines = []
    for raw in (text or "").splitlines():
        starts = [int(m.group(1)) * 60 + float(m.group(2)) for m in TIMESTAMP.finditer(raw)]
        lyric = TIMESTAMP.sub("", raw).strip()
        if lyric:
            lines.extend({"start": start, "text": lyric} for start in starts)
    return sorted(lines, key=lambda line: line["start"])


def clean_lines(lines: List[str]) -> List[str]:
    """Lyrics lines ready for the app: no section labels, no empty lines, single spaces."""
    out = []
    for line in lines:
        line = " ".join(line.split())
        if not line:
            continue
        if SECTION_LABEL.match(line) and line.lower() not in APP_MARKERS:
            continue
        out.append(line)
    return out


def pick(entries: List[dict], title: str, artist: str, duration: Optional[float] = None) -> Optional[dict]:
    """The best entry: same title (ignoring version labels), then same artist, synced lyrics, closest length."""
    wanted_title, wanted_artist = base_title(title), normalize(artist)

    def usable(entry):
        return not entry.get("instrumental") and (entry.get("syncedLyrics") or entry.get("plainLyrics"))

    def rank(entry):
        title_match = base_title(entry.get("trackName", "")) == wanted_title
        artist_match = wanted_artist and wanted_artist in normalize(entry.get("artistName", ""))
        length_off = abs((entry.get("duration") or 0) - duration) if duration and entry.get("duration") else 30.0
        return (not title_match, not artist_match, not entry.get("syncedLyrics"), length_off)

    candidates = [e for e in entries if usable(e)]
    if not candidates:
        return None
    best = min(candidates, key=rank)
    if base_title(best.get("trackName", "")) != wanted_title and wanted_title not in base_title(best.get("trackName", "")):
        return None  # a different song: better nothing than wrong lyrics
    return best


def entry_lyrics(entry: dict) -> dict:
    """Lyrics of an LRCLIB entry: text (one line per sung line, in order) and line start times if synced."""
    synced = parse_lrc(entry.get("syncedLyrics") or "")
    if synced:
        lines = clean_lines([line["text"] for line in synced])
        timed = [line for line in synced if line["text"] in set(lines)]
    else:
        lines = clean_lines((entry.get("plainLyrics") or "").splitlines())
        timed = []
    return {
        "text": "\n".join(lines),
        "lines": len(lines),
        "synced": bool(synced),
        "line_starts": [round(line["start"], 2) for line in timed],
        "track": entry.get("trackName", ""),
        "artist": entry.get("artistName", ""),
        "album": entry.get("albumName") or "",
        "duration": entry.get("duration"),
        "id": entry.get("id"),
    }


def fetch(params: dict, sleep=time.sleep) -> List[dict]:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(len(RETRY_DELAYS_SEC) + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUSES:
                raise
            if attempt == len(RETRY_DELAYS_SEC):
                raise LyricsServiceBusy(f"LRCLIB is busy (HTTP {error.code})") from error
            try:
                wait = max(float(error.headers.get("Retry-After") or 0), RETRY_DELAYS_SEC[attempt])
            except ValueError:
                wait = RETRY_DELAYS_SEC[attempt]
            log_step("LYRICS", f"LRCLIB busy (HTTP {error.code}), retrying in {wait:.0f}s")
            sleep(min(wait, 10))


def search(artist: str, title: str, duration: Optional[float] = None) -> Optional[dict]:
    """The lyrics LRCLIB has for this song, or None. Raises OSError when LRCLIB can't be reached."""
    entries = fetch({"track_name": title, "artist_name": artist})
    if not entries and base_title(title) != normalize(title):
        entries = fetch({"track_name": base_title(title), "artist_name": artist})
    if not entries:
        entries = fetch({"q": f"{artist} {title}"})
    best = pick(entries, title, artist, duration)
    log_step("LYRICS", f"LRCLIB: {len(entries)} results for '{artist} - {title}', "
                       f"{'picked ' + str(best.get('id')) if best else 'none matches'}")
    return entry_lyrics(best) if best else None
