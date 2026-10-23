"""Naming the song's audio after artist and title."""

from services.song_files import rename_audio_to_song, safe_filename


def make(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"audio")
    return str(path)


def test_the_full_mix_gets_artist_and_title(tmp_path):
    session = {"artist": "Ben Harper", "title": "She's Only Happy In The Sun",
               "original_audio": make(tmp_path, "She's Only Happy In The Sun - Ben Harper.wav")}
    rename_audio_to_song(session)
    assert session["original_audio"].endswith("Ben Harper - She's Only Happy In The Sun.wav")
    assert session["filename"] == "Ben Harper - She's Only Happy In The Sun.wav"
    assert (tmp_path / "Ben Harper - She's Only Happy In The Sun.wav").exists()


def test_uploaded_vocals_only_get_a_vocals_name(tmp_path):
    session = {"artist": "U2", "title": "Beautiful Day", "original_audio": None,
               "vocal_audio": make(tmp_path, "vocals_track01.wav")}
    rename_audio_to_song(session)
    assert session["vocal_audio"].endswith("U2 - Beautiful Day [Vocals].wav")


def test_vocals_made_from_a_mix_keep_their_name(tmp_path):
    vocals = make(tmp_path, "mix_vocals.wav")
    session = {"artist": "U2", "title": "Beautiful Day", "original_audio": make(tmp_path, "mix.wav"), "vocal_audio": vocals}
    rename_audio_to_song(session)
    assert session["vocal_audio"] == vocals


def test_a_taken_name_or_missing_names_change_nothing(tmp_path):
    make(tmp_path, "U2 - Beautiful Day.wav")
    original = make(tmp_path, "upload.wav")
    session = {"artist": "U2", "title": "Beautiful Day", "original_audio": original}
    assert rename_audio_to_song(session) == [] and session["original_audio"] == original
    assert rename_audio_to_song({"artist": "", "title": "x", "original_audio": original}) == []


def test_forbidden_characters_are_removed():
    assert safe_filename('AC/DC - Who: Made "Who"?') == "ACDC - Who Made Who"
    assert safe_filename(" ... ") == "Untitled song"
