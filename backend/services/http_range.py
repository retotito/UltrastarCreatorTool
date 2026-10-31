"""HTTP Range requests for the audio players (RFC 9110, section 14).

Safari and Edge always ask for a range; GStreamer (the Linux web view's audio) also asks without one and for the
last bytes of a file (`bytes=-128`, MP3 tags), so every form has to give the same file's bytes.
"""


class RangeNotSatisfiable(Exception):
    """The range lies outside the file: answer 416 with `Content-Range: bytes */size`."""


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """The first range of a `Range` header as (start, end), both inclusive; None for the whole file.

    `bytes=0-99`, `bytes=100-` (to the end) and `bytes=-500` (the last 500 bytes). An end past the file is cut to
    its last byte. A header that isn't a byte range is ignored (the whole file), as the RFC asks.
    """
    if not header:
        return None
    unit, _, spec = header.strip().partition('=')
    if unit.strip().lower() != 'bytes' or not spec:
        return None
    first, sep, last = spec.split(',')[0].strip().partition('-')
    if not sep:
        return None
    try:
        if not first:                              # suffix: the last N bytes
            n = int(last)
            if n <= 0 or size == 0:
                raise RangeNotSatisfiable(header)
            return max(0, size - n), size - 1
        start = int(first)
        end = int(last) if last else size - 1
    except ValueError:
        return None
    if start >= size:
        raise RangeNotSatisfiable(header)
    if end < start:
        return None
    return start, min(end, size - 1)
