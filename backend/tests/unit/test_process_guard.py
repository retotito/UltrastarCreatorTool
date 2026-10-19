"""The packaged backend's guards against a vanished app (orphaned process, dead log pipe)."""

import io
import threading

from utils.process_guard import PipeSafeStream, watch_parent


class DeadPipe(io.StringIO):
    def write(self, data):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")


def test_writing_to_a_dead_pipe_does_not_raise():
    stream = PipeSafeStream(DeadPipe())
    assert stream.write("log line\n") == 0
    stream.flush()


def test_writes_pass_through_while_the_pipe_is_alive():
    target = io.StringIO()
    PipeSafeStream(target).write("hello")
    assert target.getvalue() == "hello"


def test_watchdog_fires_when_the_parent_changes():
    parents = iter([100, 100, 1])
    fired = threading.Event()
    thread = watch_parent(on_orphaned=fired.set, interval=0.01, get_parent=lambda: next(parents, 1))
    thread.join(timeout=2)
    assert fired.is_set()


def test_watchdog_stays_quiet_while_the_parent_lives():
    fired = threading.Event()
    watch_parent(on_orphaned=fired.set, interval=0.01, get_parent=lambda: 100)
    assert not fired.wait(0.1)
