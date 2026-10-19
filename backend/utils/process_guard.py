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


def make_streams_pipe_safe() -> None:
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
