"""Step 2 backend: lyric sources in the session, artist/title of uploaded files."""

import pytest

from services import lyrics_sources
from services.lyrics_sources import InvalidSources, merge
from services.song_details import details_from_filename, mark_new_song, song_details


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
        found = song_details("x.mp3", "Name Artist - Name Title.mp3", "ffprobe")
        assert (found["artist"], found["title"]) == ("Tagged Artist", "Name Title")
        assert (found["filename"], found["tags_name"]) == ("Name Artist - Name Title", "Tagged Artist")

    def test_a_new_song_replaces_the_names_and_needs_confirming(self):
        session = {"artist": "Old", "title": "Song", "song_confirmed": True, "language": "en"}
        mark_new_song(session, {"youtube_title": "Ben Harper - Diamonds"}, {"artist": "", "title": "Diamonds"})
        assert session == {"artist": "Old", "title": "Diamonds", "song_confirmed": False, "language": "en",
                           "song_name_sources": {"youtube_title": "Ben Harper - Diamonds"}}

    def test_a_video_without_sound_is_recognised(self, tmp_path):
        import shutil
        import subprocess
        from services.song_details import has_audio
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if not (ffmpeg and ffprobe):
            pytest.skip("ffmpeg not installed")
        video, song = tmp_path / "video only.mp4", tmp_path / "song.m4a"
        subprocess.run([ffmpeg, "-v", "quiet", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5", "-t", "1", str(video)], check=True)
        subprocess.run([ffmpeg, "-v", "quiet", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", str(song)], check=True)
        assert has_audio(str(video), ffprobe) is False and has_audio(str(song), ffprobe) is True
        (tmp_path / "noise.mp3").write_bytes(b"not audio")
        assert has_audio(str(tmp_path / "noise.mp3"), ffprobe) is False
        assert has_audio(str(video), None) is True   # can't check without ffprobe: don't block

    def test_real_tags_with_ffprobe(self, tmp_path):
        import shutil
        import subprocess
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if not (ffmpeg and ffprobe):
            pytest.skip("ffmpeg not installed")
        path = tmp_path / "tagged.mp3"
        subprocess.run([ffmpeg, "-v", "quiet", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "0.5",
                        "-metadata", "artist=The Police", "-metadata", "title=Roxanne", str(path)], check=True)
        found = song_details(str(path), "whatever.mp3", ffprobe)
        assert (found["artist"], found["title"], found["tags_name"]) == ("The Police", "Roxanne", "The Police - Roxanne")


class TestSongIdentify:
    ENTRIES = [
        {"artistName": "Ben Harper", "trackName": "She's Only Happy In The Sun", "albumName": "Diamonds", "duration": 236.0},
        {"artistName": "Ben Harper", "trackName": "She's Only Happy in the Sun", "albumName": "Live", "duration": 290.0},
        {"artistName": "Twinkle Twinkle Little Rock Star", "trackName": "She's Only Happy In The Sun", "duration": 203.0},
        {"artistName": "Sierra C", "trackName": "Something Else", "duration": 200.0},
    ]

    def fetch(self, params):
        return self.ENTRIES

    def test_title_artist_order_is_recognised(self):
        from services.song_identify import identify
        found = identify(["She's Only Happy In The Sun - Ben Harper"], {"artist": "Sierra C", "title": "x"}, 236.0, self.fetch)
        assert found["proposal"] == {"artist": "Ben Harper", "title": "She's Only Happy In The Sun"}
        assert found["matches"][0]["length_match"] is True
        assert len([m for m in found["matches"] if m["artist"] == "Ben Harper"]) == 1   # one entry per song

    def test_no_clear_match_keeps_the_guess(self):
        from services.song_identify import identify
        found = identify(["lskajdfl3ww4rlkjsdfoadjlkjl"], {"artist": "", "title": "lskajdfl3ww4"}, None, lambda p: [])
        assert found == {"proposal": {"artist": "", "title": "lskajdfl3ww4"}, "matches": [], "names": ["lskajdfl3ww4rlkjsdfoadjlkjl"]}

    def test_word_overlap_score_ignores_order(self):
        from services.song_identify import name_score
        assert name_score("Sun Happy Ben Harper", "Ben Harper", "Happy Sun") == 1.0
        assert name_score("abc", "Ben Harper", "Sun") == 0.0

    def test_raw_names_prefer_youtube_then_tags_then_file_name(self):
        from services.song_identify import raw_names
        session = {"song_name_sources": {"filename": "Track_01", "tags_name": "Sierra C - She's Only Happy",
                                         "youtube_title": "Ben Harper - She's Only Happy In The Sun (Official Video)"}}
        assert raw_names(session) == ["Ben Harper - She's Only Happy In The Sun", "Sierra C - She's Only Happy", "Track 01"]
        assert raw_names({"song_name_sources": {"filename": "123456"}}) == []   # nothing to search with
