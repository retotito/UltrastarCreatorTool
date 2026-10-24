"""Step 2's lyric sources, kept in the session: each side (left, right) has its own text per source, shown in its
tabs, so the two sides can be compared and edited independently.

Sources: "lrclib" (lyrics found online), "youtube" (the video's subtitles, songs imported from YouTube),
"vocals" (Whisper on the vocals), "cleaned" (Whisper on the cleaned vocals). Each has `text`, and optionally `marks` (colour highlights), `dividers` (line numbers
with a divider) and `info` (what produced the text, for the tab's status line).

Stored as {"sides": {"left": {source: …}, "right": {…}}, "tabs": {"left": source, "right": source}}. Sessions
from before had one text per source for both sides ("sources"): `sides_of` gives it to each side.
"""

from typing import Any, Dict

SOURCES = ("lrclib", "youtube", "vocals", "cleaned")
SIDES = ("left", "right")
MAX_TEXT = 200_000
MAX_MARKS = 2_000


class InvalidSources(ValueError):
    pass


def _clean_source(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidSources("A source must be an object")
    out: Dict[str, Any] = {}
    if "text" in value:
        if not isinstance(value["text"], str) or len(value["text"]) > MAX_TEXT:
            raise InvalidSources("text must be a string of at most 200,000 characters")
        out["text"] = value["text"]
    if "marks" in value:
        marks = value["marks"]
        if not isinstance(marks, list) or len(marks) > MAX_MARKS or not all(isinstance(m, dict) for m in marks):
            raise InvalidSources("marks must be a list of objects")
        out["marks"] = marks
    if "dividers" in value:
        dividers = value["dividers"]
        if not isinstance(dividers, list) or not all(isinstance(d, int) and d >= 0 for d in dividers):
            raise InvalidSources("dividers must be a list of line numbers")
        out["dividers"] = sorted(set(dividers))
    if "info" in value:
        if not isinstance(value["info"], (dict, type(None))):
            raise InvalidSources("info must be an object")
        out["info"] = value["info"]
    return out


def sides_of(stored: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Each side's sources (copies); older sessions' shared "sources" go to both sides."""
    if stored.get("sides"):
        return {side: {k: dict(v) for k, v in (stored["sides"].get(side) or {}).items()} for side in SIDES}
    shared = stored.get("sources") or {}
    return {side: {k: dict(v) for k, v in shared.items()} for side in SIDES}


def merge(stored: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """`stored` ({"sides": …, "tabs": …}) with `update` applied: given fields replace stored ones,
    others stay. Raises InvalidSources for anything unexpected."""
    result = {"sides": sides_of(stored), "tabs": dict(stored.get("tabs") or {})}
    for side, sources in (update.get("sides") or {}).items():
        if side not in SIDES or not isinstance(sources, dict):
            raise InvalidSources(f"Unknown side {side!r}")
        for name, value in sources.items():
            if name not in SOURCES:
                raise InvalidSources(f"Unknown source {name!r}")
            result["sides"][side].setdefault(name, {}).update(_clean_source(value))
    if update.get("sources"):
        raise InvalidSources("Sources are per side now: send {\"sides\": {\"left\": …, \"right\": …}}")
    for side, tab in (update.get("tabs") or {}).items():
        if side not in SIDES or tab not in SOURCES:
            raise InvalidSources(f"Unknown tab {side!r}: {tab!r}")
        result["tabs"][side] = tab
    return result
