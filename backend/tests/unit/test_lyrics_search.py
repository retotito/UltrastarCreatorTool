"""LRCLIB lyrics: picking the right entry and cleaning its text (no network)."""

import pytest

import services.lyrics_search as lyrics


def entry(title="Turn On, Tune In, Cop Out", artist="Freak Power", duration=265.0, synced=None, plain=None,
          instrumental=False, id=1):
    return {"id": id, "trackName": title, "artistName": artist, "duration": duration, "instrumental": instrumental,
            "syncedLyrics": synced, "plainLyrics": plain}


SYNCED = "[00:07.30] Turn on\n[00:14.50] I'm on the fast lane\n[00:20.00] \n[00:30.00][01:30.00] Turn on, tune in, cop out"


class TestParsing:
    def test_lrc_lines_repeat_per_timestamp_and_sort_by_time(self):
        lines = lyrics.parse_lrc(SYNCED)
        assert [(line["start"], line["text"]) for line in lines] == [
            (7.3, "Turn on"), (14.5, "I'm on the fast lane"), (30.0, "Turn on, tune in, cop out"),
            (90.0, "Turn on, tune in, cop out"),
        ]

    def test_section_labels_and_empty_lines_are_dropped_but_rap_markers_kept(self):
        assert lyrics.clean_lines(["[Chorus]", "", "  la   la ", "(Verse 2)", "[RAP]", "yo", "[/RAP]"]) == [
            "la la", "[RAP]", "yo", "[/RAP]",
        ]

    def test_synced_lyrics_give_every_sung_line_in_order(self):
        found = lyrics.entry_lyrics(entry(synced=SYNCED, plain="Turn on\nI'm on the fast lane\nTurn on, tune in, cop out"))
        assert found["text"].split("\n") == [
            "Turn on", "I'm on the fast lane", "Turn on, tune in, cop out", "Turn on, tune in, cop out",
        ]
        assert found["synced"] is True
        assert found["line_starts"] == [7.3, 14.5, 30.0, 90.0]

    def test_plain_lyrics_when_not_synced(self):
        found = lyrics.entry_lyrics(entry(plain="[Intro]\nLa la\n\nDa da"))
        assert (found["text"], found["synced"], found["line_starts"]) == ("La la\nDa da", False, [])


class TestPick:
    def test_same_title_ignoring_punctuation_and_version_labels(self):
        best = lyrics.pick([entry(title="Something Else", id=1), entry(title="Turn On Tune In Cop Out (Remastered)", id=2,
                                                                         plain="x")],
                           "Turn On, Tune In, Cop Out", "Freak Power")
        assert best["id"] == 2

    def test_synced_beats_plain_and_closest_length_wins(self):
        entries = [entry(id=1, plain="x", duration=265), entry(id=2, synced=SYNCED, duration=300),
                   entry(id=3, synced=SYNCED, duration=262)]
        assert lyrics.pick(entries, "Turn On, Tune In, Cop Out", "Freak Power", duration=264)["id"] == 3

    def test_instrumentals_and_empty_entries_are_skipped(self):
        assert lyrics.pick([entry(instrumental=True, plain="x"), entry()], "Turn On, Tune In, Cop Out", "Freak Power") is None

    def test_same_title_by_another_artist_is_not_picked_automatically(self):
        assert lyrics.pick([entry(title="Turn On Tune In", artist="Threshold", plain="x")],
                           "Turn on tune in", "Freek Power") is None

    def test_a_slightly_misspelled_artist_still_matches(self):
        assert lyrics.pick([entry(artist="Freakpower", plain="x")], "Turn On, Tune In, Cop Out", "Freak Power")

    def test_a_different_song_is_not_returned(self):
        assert lyrics.pick([entry(title="Rush", plain="x")], "Turn On, Tune In, Cop Out", "Freak Power") is None


def test_search_retries_without_version_label(monkeypatch):
    calls = []

    def fake_fetch(params):
        calls.append(params)
        return [] if len(calls) == 1 else [entry(synced=SYNCED)]

    monkeypatch.setattr(lyrics, "fetch", fake_fetch)
    found = lyrics.search("Freak Power", "Turn On, Tune In, Cop Out (Remastered 2011)")
    assert found["best"]["synced"] is True
    assert calls[1]["track_name"] == "turn on tune in cop out"


def test_search_finds_nothing(monkeypatch):
    monkeypatch.setattr(lyrics, "fetch", lambda params: [])
    assert lyrics.search("Nobody", "Nothing") == {"best": None, "candidates": []}


def test_a_misspelled_title_gives_suggestions_but_no_automatic_match(monkeypatch):
    def fake_fetch(params):
        if "q" in params:
            return [entry(id=1, synced=SYNCED), entry(id=2, title="Rush", plain="la")]
        return []

    monkeypatch.setattr(lyrics, "fetch", fake_fetch)
    found = lyrics.search("Freak Power", "Tune In Cop Out")
    assert found["best"] is None or found["best"]["id"] == 1
    assert [c["id"] for c in found["candidates"]] == [1, 2]  # most similar first


class TestCandidates:
    def test_matching_length_and_timestamps_rank_first(self):
        entries = [entry(id=1, plain="a", duration=262), entry(id=2, synced="[00:01.00] b", duration=300),
                   entry(id=3, synced="[00:01.00] c", duration=263)]
        found = lyrics.candidates(entries, "Turn On, Tune In, Cop Out", "Freak Power", duration=264)
        assert [c["id"] for c in found] == [3, 1, 2]

    def test_duplicates_appear_once_and_synced_wins(self):
        entries = [entry(id=1, plain="Turn on"), entry(id=2, synced="[00:01.00] Turn on"), entry(id=3, plain="Other text")]
        found = lyrics.candidates(entries, "Turn On, Tune In, Cop Out", "Freak Power")
        assert [c["id"] for c in found] == [2, 3]

    def test_length_match_is_marked(self):
        entries = [entry(id=1, plain="a", duration=262), entry(id=2, plain="b", duration=300)]
        found = lyrics.candidates(entries, "Turn On, Tune In, Cop Out", "Freak Power", duration=264)
        assert [(c["id"], c["length_match"]) for c in found] == [(1, True), (2, False)]

    def test_without_song_length_nothing_is_marked(self):
        found = lyrics.candidates([entry(plain="a")], "Turn On, Tune In, Cop Out", "Freak Power")
        assert found[0]["length_match"] is None

    def test_instrumentals_are_left_out(self):
        assert lyrics.candidates([entry(instrumental=True, plain="a")], "x", "y") == []

    def test_at_most_ten(self):
        entries = [entry(id=i, plain=f"text {i}") for i in range(15)]
        assert len(lyrics.candidates(entries, "Turn On, Tune In, Cop Out", "Freak Power")) == 10


@pytest.mark.slow
def test_live_lrclib():
    """Real request (network): run with -m slow."""
    found = lyrics.search("Freak Power", "Turn On, Tune In, Cop Out")
    assert found["best"] and "fast lane" in found["best"]["text"]
    sloppy = lyrics.search("freak power", "tune in cop out")
    assert any("fast lane" in c["text"] for c in sloppy["candidates"])


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(code, retry_after="1"):
    import email.message
    import urllib.error
    headers = email.message.Message()
    headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://lrclib.net/api/search", code, "busy", headers, None)


def test_fetch_retries_while_lrclib_is_busy(monkeypatch):
    answers = [http_error(503), http_error(503), FakeResponse(b'[{"id": 7}]')]

    def fake_urlopen(request, timeout):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(lyrics.urllib.request, "urlopen", fake_urlopen)
    waits = []
    assert lyrics.fetch({"q": "x"}, sleep=waits.append) == [{"id": 7}]
    assert waits == [1, 2]


def test_fetch_gives_up_with_a_clear_error(monkeypatch):
    def always_busy(request, timeout):
        raise http_error(503)

    monkeypatch.setattr(lyrics.urllib.request, "urlopen", always_busy)
    with pytest.raises(lyrics.LyricsServiceBusy):
        lyrics.fetch({"q": "x"}, sleep=lambda s: None)


def test_fetch_does_not_retry_other_errors(monkeypatch):
    calls = []

    def not_found(request, timeout):
        calls.append(1)
        raise http_error(404)

    monkeypatch.setattr(lyrics.urllib.request, "urlopen", not_found)
    import urllib.error
    with pytest.raises(urllib.error.HTTPError):
        lyrics.fetch({"q": "x"}, sleep=lambda s: None)
    assert calls == [1]
