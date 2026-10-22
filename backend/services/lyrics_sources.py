"""Step 2's lyric sources, kept in the session: one text per source, shown in the tabs of either side.

Sources: "lrclib" (lyrics found online), "vocals" (Whisper on the vocals), "cleaned" (Whisper on the
cleaned vocals). Each has `text`, and optionally `marks` (colour highlights), `dividers` (line numbers
with a divider) and `info` (what produced the text, for the tab's status line).
"""

from typing import Any, Dict

SOURCES = ("lrclib", "vocals", "cleaned")
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


def merge(stored: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """`stored` ({"sources": …, "tabs": …}) with `update` applied: given fields replace stored ones,
    others stay. Raises InvalidSources for anything unexpected."""
    result = {"sources": {k: dict(v) for k, v in (stored.get("sources") or {}).items()},
              "tabs": dict(stored.get("tabs") or {})}
    for name, value in (update.get("sources") or {}).items():
        if name not in SOURCES:
            raise InvalidSources(f"Unknown source {name!r}")
        result["sources"].setdefault(name, {}).update(_clean_source(value))
    for side, tab in (update.get("tabs") or {}).items():
        if side not in SIDES or tab not in SOURCES:
            raise InvalidSources(f"Unknown tab {side!r}: {tab!r}")
        result["tabs"][side] = tab
    return result
