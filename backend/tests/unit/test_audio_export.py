"""The export's audio as MP3 or Ogg Vorbis, see services/audio_export.py."""

import os
import shutil
import subprocess

import pytest

from services.audio_export import AudioEncodeError, audio_ext, audio_for_export, audio_format, encode_commands

FFMPEG = shutil.which("ffmpeg")


@pytest.mark.parametrize("value, expected", [
    ("ogg", "ogg"), ("OGG", "ogg"), (".ogg", "ogg"), ("mp3", "mp3"), (None, "mp3"), ("", "mp3"), ("flac", "mp3"),
])
def test_unknown_formats_are_mp3(value, expected):
    assert audio_format(value) == expected
    assert audio_ext(value) == "." + expected


def test_ogg_tries_libvorbis_first_then_ffmpegs_own_encoder():
    commands = encode_commands("ffmpeg", "in.wav", "out.ogg", "ogg")
    assert [c[c.index("-codec:a") + 1] for c in commands] == ["libvorbis", "vorbis"]
    assert all(c[-1] == "out.ogg" and ["-ar", "44100"] == c[c.index("-ar"):c.index("-ar") + 2] for c in commands)
    assert "experimental" in commands[1]


def test_mp3_uses_lame():
    (command,) = encode_commands("ffmpeg", "in.wav", "out.mp3", "mp3")
    assert command[command.index("-codec:a") + 1] == "libmp3lame"


def test_a_file_already_in_the_format_is_used_as_it_is(tmp_path):
    song = tmp_path / "song.OGG"
    song.write_bytes(b"x")
    assert audio_for_export(str(song), "ogg") == (str(song), False)


def test_mp3_falls_back_to_the_original_and_ogg_says_why(tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not audio")
    missing_ffmpeg = str(tmp_path / "no-ffmpeg")
    assert audio_for_export(str(broken), "mp3", missing_ffmpeg) == (str(broken), False)
    with pytest.raises(AudioEncodeError, match=r"\.ogg"):
        audio_for_export(str(broken), "ogg", missing_ffmpeg)


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg")
def test_a_wav_becomes_a_real_ogg_vorbis_file(tmp_path):
    wav = tmp_path / "song.wav"
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(wav)],
                   capture_output=True, check=True)
    path, is_temp = audio_for_export(str(wav), "ogg", FFMPEG)
    try:
        assert is_temp and path.endswith(".ogg")
        with open(path, "rb") as f:
            head = f.read(64)
        assert head.startswith(b"OggS") and b"vorbis" in head
    finally:
        os.unlink(path)
