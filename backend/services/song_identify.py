"""Which song is this? Artist and title from a file name, its tags or a YouTube title, checked online.

"She's Only Happy In The Sun - Ben Harper" can be "Artist - Title" or "Title - Artist"; the text alone
can't tell. LRCLIB's free-text search can: its entries have the artist and title separately. Entries
are ranked by how many words they share with the name (in any order) and by matching the song's length.
"""

import re
from typing import Callable, Dict, List, Optional

from services.lyrics_search import base_title, normalize
from services.youtube import clean_title

MAX_MATCHES = 6
LENGTH_MATCH_SEC = 5.0
# A match this good is proposed instead of the split of the name.
CONFIDENT_SCORE = 0.75


def words(text: str) -> set:
    return set(normalize(text).split())


def name_score(raw: str, artist: str, title: str) -> float:
    """0..1: how well "artist title" and the raw name cover each other's words (order doesn't matter)."""
    mine, theirs = words(raw), words(f"{artist} {title}")
    if not mine or not theirs:
        return 0.0
    common = len(mine & theirs)
    precision, recall = common / len(theirs), common / len(mine)
    return 2 * precision * recall / (precision + recall) if common else 0.0


def raw_names(session: dict) -> List[str]:
    """What the song was called where it came from, most telling first."""
    found = session.get("song_name_sources") or {}
    names = [found.get("youtube_title"), found.get("tags_name"), found.get("filename")]
    out: List[str] = []
    for name in names:
        name = clean_title(re.sub(r"[_]+", " ", name or "")).strip()
        if name and re.search(r"[^\W\d_]{2,}", name) and name.lower() not in (n.lower() for n in out):
            out.append(name)
    return out


def matches(raw: List[str], duration: Optional[float], fetch: Callable[[dict], list]) -> List[Dict]:
    """Songs on LRCLIB that fit the names: {artist, title, album, duration, length_match, score}."""
    seen: Dict[tuple, Dict] = {}
    for name in raw:
        for entry in fetch({"q": name}):
            artist, title = (entry.get("artistName") or "").strip(), (entry.get("trackName") or "").strip()
            if not artist or not title:
                continue
            score = max(name_score(n, artist, base_title(title) or title) for n in raw)
            length = entry.get("duration")
            length_match = None if not (duration and length) else abs(length - duration) <= LENGTH_MATCH_SEC
            key = (normalize(artist), base_title(title))
            candidate = {"artist": artist, "title": title, "album": entry.get("albumName") or "",
                         "duration": length, "length_match": length_match, "score": round(score, 3)}
            best = seen.get(key)
            # Keep one entry per song: the one with the matching length, else the first.
            if best is None or (length_match and not best["length_match"]):
                seen[key] = candidate
    ranked = sorted(seen.values(), key=lambda c: (-round(c["score"], 1), not c["length_match"], -c["score"]))
    return [c for c in ranked if c["score"] > 0][:MAX_MATCHES]


def identify(raw: List[str], guess: Dict[str, str], duration: Optional[float],
             fetch: Callable[[dict], list]) -> Dict:
    """{"proposal": {artist, title}, "matches": [...], "names": raw}. The proposal is the best match when it
    is a clear one, else `guess` (the split of the name or the tags)."""
    found = matches(raw, duration, fetch) if raw else []
    proposal = dict(guess)
    if found and found[0]["score"] >= CONFIDENT_SCORE:
        proposal = {"artist": found[0]["artist"], "title": base_title_display(found[0]["title"])}
    return {"proposal": proposal, "matches": found, "names": raw}


def base_title_display(title: str) -> str:
    """The title without "(Remastered 2011)", "- Live" and the like, keeping its own spelling."""
    return clean_title(re.sub(r"\s+-\s+(remaster(ed)?|live|radio edit|single version).*$", "", title, flags=re.I)).strip() or title
