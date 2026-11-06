"""Demucs's percentage, read from its tqdm bar in the installed app and in dev."""

import io
import sys

import pytest

from services.vocal_separation import _ProgressStream, _run_demucs_subprocess, tqdm_percent


@pytest.mark.parametrize("text, expected", [
    (" 45%|████▌     | 90.0/200.0 [00:10<00:12,  8.5seconds/s]", 45),
    ("\r 10%|█ | 1/10\r 20%|██ | 2/10", 20),
    ("100%|██████████| 200/200", 100),
    ("Selected model is a bag of 1 models.", None),
    ("5% of nothing", None),
])
def test_tqdm_percent(text, expected):
    assert tqdm_percent(text) == expected


def test_the_stream_passes_everything_on_and_reports():
    out, seen = io.StringIO(), []
    stream = _ProgressStream(out, seen.append)
    stream.write(" 30%|███ | 3/10")
    stream.write("a warning\n")
    assert out.getvalue() == " 30%|███ | 3/10a warning\n" and seen == [30]


def test_the_stream_works_without_a_stderr():
    seen = []
    _ProgressStream(None, seen.append).write(" 7%|")
    assert seen == [7]


def run_python(code):
    return [sys.executable, "-c", code]


def test_the_process_reports_its_bar():
    seen = []
    _run_demucs_subprocess(run_python("import sys; [sys.stderr.write(f'\\r {p}%|#| x') for p in (10, 60, 100)]"), seen.append)
    assert seen and seen[-1] == 100


def test_a_failing_process_says_why():
    with pytest.raises(RuntimeError, match="boom"):
        _run_demucs_subprocess(run_python("import sys; sys.stderr.write('boom'); sys.exit(3)"), None)
