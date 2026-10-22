"""Step 2 backend: lyric sources in the session, artist/title of uploaded files."""

import pytest

from services import lyrics_sources
from services.lyrics_sources import InvalidSources, merge
from services.song_details import details_from_filename, song_details


class TestSources:
    def test_update_replaces_only_the_given_fields(self):
        stored = {"sources": {"lrclib": {"text": "old", "marks": [{"a": 1}]}}, "tabs": {"left": "lrclib"}}
        result = merge(stored, {"sources": {"lrclib": {"text": "new"}, "vocals": {"text": "heard"}},
                                "tabs": {"right": "vocals"}})
        assert result["sources"]["lrclib"] == {"text": "new", "marks": [{"a": 1}]}
        assert result["sources"]["vocals"] == {"text": "heard"}
        assert result["tabs"] == {"left": "lrclib", "right": "vocals"}
        assert stored["sources"]["lrclib"]["text"] == "old"  # input unchanged

    @pytest.mark.parametrize("update", [
        {"sources": {"youtube": {"text": "x"}}},
        {"sources": {"lrclib": {"text": 5}}},
        {"sources": {"lrclib": {"text": "x" * (lyrics_sources.MAX_TEXT + 1)}}},
        {"sources": {"lrclib": {"dividers": [-1]}}},
        {"tabs": {"middle": "lrclib"}},
        {"tabs": {"left": "spotify"}},
    ])
    def test_unexpected_input_is_refused(self, update):
        with pytest.raises(InvalidSources):
            merge({}, update)

    def test_dividers_are_sorted_and_unique(self):
        assert merge({}, {"sources": {"vocals": {"dividers": [5, 2, 5]}}})["sources"]["vocals"]["dividers"] == [2, 5]


class TestSongDetails:
    @pytest.mark.parametrize("filename, expected", [
        ("Freak Power - Turn On, Tune In, Cop Out.mp3", ("Freak Power", "Turn On, Tune In, Cop Out")),
        ("03 - U2 - Beautiful Day.flac", ("U2", "Beautiful Day")),
        ("Crystal_Waters_-_Gypsy_Woman_(Official_Video).m4a", ("Crystal Waters", "Gypsy Woman")),
        ("Alicia Keys - Fallin' [Vocals].wav", ("Alicia Keys", "Fallin'")),
        ("my recording.wav", ("", "my recording")),
    ])
    def test_from_the_file_name(self, filename, expected):
        found = details_from_filename(filename)
        assert (found["artist"], found["title"]) == expected

    def test_tags_win_field_by_field(self, monkeypatch):
        import services.song_details as sd
        monkeypatch.setattr(sd, "details_from_tags", lambda path, ffprobe: {"artist": "Tagged Artist", "title": ""})
        assert song_details("x.mp3", "Name Artist - Name Title.mp3", "ffprobe") == {
            "artist": "Tagged Artist", "title": "Name Title"}

    def test_real_tags_with_ffprobe(self, tmp_path):
        import shutil
        import subprocess
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if not (ffmpeg and ffprobe):
            pytest.skip("ffmpeg not installed")
        path = tmp_path / "tagged.mp3"
        subprocess.run([ffmpeg, "-v", "quiet", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.5",
                        "-metadata", "artist=The Police", "-metadata", "title=Roxanne", str(path)], check=True)
        assert song_details(str(path), "whatever.mp3", ffprobe) == {"artist": "The Police", "title": "Roxanne"}
