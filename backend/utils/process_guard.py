"""Keep the packaged backend tied to the app that started it.

When the Tauri app ends without stopping the backend (Cmd+Q, crash, force quit, update), the backend
used to keep running: it blocked port 8001 for the next launch, and its log pipe had no reader any
more, so the next log line failed with "[Errno 32] Broken pipe".
"""

import os
import sys
import threading
import time
from typing import Callable


class PipeSafeStream:
    """A stdout/stderr wrapper that ignores errors from a pipe nobody reads any more."""

    def __init__(self, stream):
        self._s = stream

    def write(self, data):
        try:
            return self._s.write(data)
        except (OSError, ValueError):
            return 0

    def flush(self):
        try:
            self._s.flush()
        except (OSError, ValueError):
            pass

    def fileno(self):
        try:
            return self._s.fileno()
        except Exception:
            return -1

    def isatty(self):
        return False

    def readable(self):
        return False

    def writable(self):
        return True

    def __getattr__(self, name):
        return getattr(self._s, name)


def use_utf8(stream) -> None:
    """Write `stream` as UTF-8, characters it can't take as "?". On Windows a pipe gets the old code page (cp1252):
    a line with "→" failed to encode (and PipeSafeStream dropped it), one with "ñ" reached the app as a byte that isn't
    UTF-8, and the app's log reader stopped there. So the log had almost nothing on Windows."""
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass   # not a text stream that can change (None in a windowed build, or already wrapped)


def make_streams_pipe_safe() -> None:
    use_utf8(sys.stdout)
    use_utf8(sys.stderr)
    sys.stdout = PipeSafeStream(sys.stdout)
    sys.stderr = PipeSafeStream(sys.stderr)


def watch_parent(on_orphaned: Callable[[], None] = lambda: os._exit(0),
                 interval: float = 2.0, get_parent: Callable[[], int] = os.getppid) -> threading.Thread:
    """Call `on_orphaned` once the process that started us is gone (our parent id changes)."""
    parent = get_parent()

    def run():
        while True:
            time.sleep(interval)
            if get_parent() != parent:
                on_orphaned()
                return

    thread = threading.Thread(target=run, name="parent-watchdog", daemon=True)
    thread.start()
    return thread
