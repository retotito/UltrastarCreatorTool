"""Duets: two singers in one UltraStar chart (`P1`/`P2` tracks), see docs/plans/duets.md.

In a chart each singer has a track of notes and line breaks. The editor keeps one list: every note and break has
`singer` 1, 2 or "both" (sung together, written into both tracks). A solo chart has no `singer` at all.
"""

import re
from typing import Dict, List, Optional

BOTH = "both"
_TRACK = re.compile(r"^P\s*(\d)\s*$")


def track_marker(line: str) -> Optional[object]:
    """The singer a `P1`/`P2` line starts (1, 2), "both" for an old chart's `P3`, else None."""
    m = _TRACK.match(line.strip())
    if not m:
        return None
    return {"1": 1, "2": 2, "3": BOTH}.get(m.group(1))


def is_duet(content: str) -> bool:
    return any(track_marker(line) is not None for line in content.splitlines())


def singer_names(headers: Dict[str, str]) -> Dict[str, str]:
    """The singers' names: `#P1`/`#P2`, else the older `#DUETSINGERP1`/`P2`, else USDB's `p1=`/`p2=` in `#VIDEO`,
    else "Singer 1"/"Singer 2". `headers` has upper-case keys."""
    video = dict(part.split("=", 1) for part in (headers.get("VIDEO") or "").split(",") if "=" in part)
    names = {}
    for n in ("1", "2"):
        names[f"p{n}"] = ((headers.get(f"P{n}") or headers.get(f"DUETSINGERP{n}") or video.get(f"p{n}") or "").strip()
                          or f"Singer {n}")
    return names


def _key(note: dict) -> tuple:
    if note.get("type") == "break":
        return ("break", note.get("startBeat"))
    return (note.get("startBeat"), note.get("duration"), note.get("pitch"), note.get("syllable"),
            bool(note.get("isGolden")), bool(note.get("isRap")), bool(note.get("isFreestyle")))


def merge_shared(elements: List[dict]) -> List[dict]:
    """Notes and breaks that are in both tracks (the same beat, length, pitch, syllable and type) become one
    element sung by "both". Sorted by beat, a break before the notes starting at its beat. Returns copies."""
    elements = [dict(el) for el in elements]
    first = {}
    for el in elements:
        if el.get("singer") == 1:
            first.setdefault(_key(el), el)
    shared = set()
    out = []
    for el in elements:
        if el.get("singer") == 2:
            twin = first.get(_key(el))
            if twin is not None and id(twin) not in shared:
                shared.add(id(twin))
                twin["singer"] = BOTH
                continue
        out.append(el)
    return sorted(out, key=lambda el: (el.get("startBeat", 0), 0 if el.get("type") == "break" else 1))


def track(elements: List[dict], singer: int) -> List[dict]:
    """One singer's notes and line breaks, in order, without breaks that would leave an empty line. In a duet an
    element without a singer (made by a tool that doesn't know about duets) counts as sung by both, so it isn't lost."""
    mine = sorted((el for el in elements if el.get("singer") in (singer, BOTH, None)),
                  key=lambda el: (el.get("startBeat", 0), 0 if el.get("type") == "break" else 1))
    out = []
    for el in mine:
        if el.get("type") == "break":
            # Only between two notes: not first, not twice in a row (the last one is dropped below)
            if out and out[-1].get("type") != "break":
                out.append(el)
        else:
            out.append(el)
    while out and out[-1].get("type") == "break":
        out.pop()
    return out


def note_line(note: dict) -> str:
    if note.get("type") == "break":
        return f"- {note['startBeat']}"
    if note.get("isGolden") and note.get("isRap"):
        prefix = "G"   # golden rap
    elif note.get("isGolden") or note.get("type") == "golden":
        prefix = "*"
    elif note.get("isRap") or note.get("type") == "rap":
        prefix = "R"
    elif note.get("isFreestyle") or note.get("type") == "freestyle":
        prefix = "F"
    else:
        prefix = ":"
    return f"{prefix} {note['startBeat']} {note['duration']} {note['pitch']} {note['syllable']}"


def body_lines(elements: List[dict]) -> List[str]:
    """The chart's note lines (without headers and `E`): one list for a solo chart, `P1` and `P2` tracks for a
    duet (any element with a `singer`)."""
    if not any(el.get("singer") is not None for el in elements):
        return [note_line(el) for el in elements]
    lines = []
    for singer in (1, 2):
        lines.append(f"P{singer}")
        lines += [note_line(el) for el in track(elements, singer)]
    return lines


def header_lines(names: Dict[str, str]) -> List[str]:
    """`#P1`/`#P2` (format 1.0) and `#DUETSINGERP1`/`P2` (older games, YASS) with the singers' names."""
    return [f"#P1:{names['p1']}", f"#P2:{names['p2']}",
            f"#DUETSINGERP1:{names['p1']}", f"#DUETSINGERP2:{names['p2']}"]


DUET_HEADERS = {"P1", "P2", "P3", "DUETSINGERP1", "DUETSINGERP2", "DUETSINGERP3"}
