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
from difflib import SequenceMatcher
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


# An automatic match needs the artist to be about right ("Freak Power" vs "Freakpower" passes,
# "Threshold" doesn't); otherwise the user picks from the suggestions.
MIN_ARTIST_SIMILARITY = 0.75


def artist_similarity(entry: dict, artist: str) -> float:
    return SequenceMatcher(None, normalize(entry.get("artistName", "")), normalize(artist)).ratio()


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
    if wanted_artist and artist_similarity(best, artist) < MIN_ARTIST_SIMILARITY:
        return None  # same title by someone else: let the user choose from the suggestions
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


MAX_CANDIDATES = 10
LENGTH_MATCH_SEC = 5.0


def similarity(entry: dict, title: str, artist: str) -> float:
    """0..1: how close an entry's title and artist are to what the user typed (title counts double)."""
    title_score = SequenceMatcher(None, base_title(entry.get("trackName", "")), base_title(title)).ratio()
    artist_score = SequenceMatcher(None, normalize(entry.get("artistName", "")), normalize(artist)).ratio()
    return (2 * title_score + artist_score) / 3


def candidates(entries: List[dict], title: str, artist: str, duration: Optional[float] = None) -> List[dict]:
    """Entries to choose from, most similar first: lyrics plus `score` and `length_match`.

    Instrumentals and entries without lyrics are left out; duplicates (same title, artist, length
    and text) appear once, the synced one if there is one.
    """
    usable = [e for e in entries if not e.get("instrumental") and (e.get("syncedLyrics") or e.get("plainLyrics"))]

    def length_off(entry):
        return abs(entry["duration"] - duration) if duration and entry.get("duration") else None

    def order(entry):
        off = length_off(entry)
        length_ok = off is not None and off <= LENGTH_MATCH_SEC
        return (-round(similarity(entry, title, artist), 2), not length_ok, not entry.get("syncedLyrics"),
                off if off is not None else 999.0)

    out, seen = [], set()
    for entry in sorted(usable, key=order):
        found = entry_lyrics(entry)
        key = (normalize(found["track"]), normalize(found["artist"]), round(found["duration"] or 0), found["text"])
        if key in seen or not found["text"]:
            continue
        seen.add(key)
        off = length_off(entry)
        found["score"] = round(similarity(entry, title, artist), 3)
        found["length_match"] = None if off is None else off <= LENGTH_MATCH_SEC
        out.append(found)
        if len(out) == MAX_CANDIDATES:
            break
    return out


def search(artist: str, title: str, duration: Optional[float] = None) -> dict:
    """What LRCLIB has for this song: `best` (lyrics of the clear match, or None) and `candidates`
    (similar entries to choose from). Raises OSError when LRCLIB can't be reached.

    Asks by artist and title first, then without version labels, then as free text, so typos and
    missing words still give suggestions.
    """
    entries: dict = {}

    def ask(params):
        for entry in fetch(params):
            entries.setdefault(entry.get("id"), entry)

    ask({"track_name": title, "artist_name": artist})
    if len(entries) < 3 and base_title(title) != normalize(title):
        ask({"track_name": base_title(title), "artist_name": artist})
    ask({"q": f"{artist} {title}"})
    if len(entries) < 3:
        ask({"q": base_title(title) or title})
    found = list(entries.values())
    best = pick(found, title, artist, duration)
    log_step("LYRICS", f"LRCLIB: {len(found)} results for '{artist} - {title}', "
                       f"{'picked ' + str(best.get('id')) if best else 'no clear match'}")
    return {
        "best": entry_lyrics(best) if best else None,
        "candidates": candidates(found, title, artist, duration),
    }
