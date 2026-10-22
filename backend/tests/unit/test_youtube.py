"""YouTube links: parsing, song details, errors, and the yt-dlp calls (with fakes, no network)."""

import hashlib
import io
import json
import os
import subprocess
import zipfile

import pytest

from services import download_tools, youtube
from services.download_tools import ToolError, Tools
from services.youtube import YouTube, YouTubeError


class TestVideoId:
    @pytest.mark.parametrize("link", [
        "https://www.youtube.com/watch?v=_KztNIg4cvE",
        "youtube.com/watch?v=_KztNIg4cvE&list=PL123&t=30",
        "https://youtu.be/_KztNIg4cvE?si=abc",
        "https://music.youtube.com/watch?v=_KztNIg4cvE",
        "https://www.youtube.com/shorts/_KztNIg4cvE",
        "https://www.youtube-nocookie.com/embed/_KztNIg4cvE",
        "_KztNIg4cvE",
    ])
    def test_links(self, link):
        assert youtube.video_id(link) == "_KztNIg4cvE"

    @pytest.mark.parametrize("link", [
        "", "https://vimeo.com/12345", "https://evil.com/watch?v=_KztNIg4cvE",
        "https://www.youtube.com/watch?v=short", "--exec rm -rf /", "https://www.youtube.com/channel/UC123",
    ])
    def test_not_videos(self, link):
        assert youtube.video_id(link) is None


class TestSongDetails:
    def test_youtube_music_fields_win(self):
        info = {"artist": "Freak Power", "track": "Turn On, Tune In, Cop Out", "title": "whatever (Official Video)"}
        assert youtube.song_details(info) == {"artist": "Freak Power", "title": "Turn On, Tune In, Cop Out"}

    @pytest.mark.parametrize("title, expected", [
        ("Crystal Waters - Gypsy Woman (She's Homeless) (Official Music Video)",
         ("Crystal Waters", "Gypsy Woman (She's Homeless)")),
        ("The Police – Roxanne [Official Video] HD", ("The Police", "Roxanne")),
        ("U2 - Beautiful Day (Lyrics)", ("U2", "Beautiful Day")),
        ("Alicia Keys - Fallin' | Official Audio", ("Alicia Keys", "Fallin'")),
    ])
    def test_artist_and_title_from_the_video_title(self, title, expected):
        details = youtube.song_details({"title": title, "channel": "SomeChannelVEVO"})
        assert (details["artist"], details["title"]) == expected

    def test_channel_as_artist_when_the_title_has_no_dash(self):
        details = youtube.song_details({"title": "Lovefool (Official Video)", "channel": "The Cardigans - Topic"})
        assert details == {"artist": "The Cardigans", "title": "Lovefool"}

    def test_language_from_uploader_or_original_captions(self):
        assert youtube.video_language({"language": "de-DE"}) == "de"
        assert youtube.video_language({"automatic_captions": {"en": [], "en-orig": [], "fr": []}}) == "en"
        assert youtube.video_language({"automatic_captions": {"en": []}}) is None

    def test_summary_lists_uploader_subtitles_and_a_jpeg_thumbnail(self):
        info = {"id": "_KztNIg4cvE", "title": "A - B", "duration": 230, "subtitles": {"en": [], "de": []},
                "thumbnails": [{"url": "https://i.ytimg.com/vi/x/max.webp", "width": 1920},
                               {"url": "https://i.ytimg.com/vi/x/hq.jpg", "width": 480},
                               {"url": "https://i.ytimg.com/vi/x/sd.jpg", "width": 640}]}
        found = youtube.summary(info)
        assert found["thumbnail"].endswith("sd.jpg")
        assert found["subtitle_languages"] == ["de", "en"]
        assert found["url"] == "https://www.youtube.com/watch?v=_KztNIg4cvE"


class TestErrors:
    @pytest.mark.parametrize("stderr, text, retryable", [
        ("ERROR: [youtube] abcdefghijk: Private video. Sign in", "private", False),
        ("ERROR: [youtube] abcdefghijk: Sign in to confirm your age", "adults", False),
        ("ERROR: [youtube] abcdefghijk: Video unavailable", "isn't available on YouTube", False),
        ("ERROR: Sign in to confirm you're not a bot", "bot", False),
        ("ERROR: [youtube] abcdefghijk: nsig extraction failed", "Couldn't get the song", True),
    ])
    def test_messages(self, stderr, text, retryable):
        error = youtube.explain(stderr)
        assert text in str(error) and error.retryable is retryable

    def test_progress_lines(self):
        assert youtube.parse_progress("@progress 1024 4096 NA") == (1024, 4096)
        assert youtube.parse_progress("@progress 1024 NA 8000.5") == (1024, 8000)
        assert youtube.parse_progress("@progress NA NA NA") == (0, None)


# ── tools ────────────────────────────────────────────────────
def zip_with(path_in_zip, content=b"#!/bin/sh\necho ok\n", mode=0o755):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        info = zipfile.ZipInfo(path_in_zip)
        info.external_attr = (mode | 0o100000) << 16
        zf.writestr(info, content)
        zf.writestr("_internal/lib.txt", b"x")
    return buffer.getvalue()


def fake_github(files, tag="2026.10.21"):
    """get_json and download fakes serving `files` {asset name: bytes} with correct digests."""
    calls = {"json": 0, "download": 0}

    def get_json(url):
        calls["json"] += 1
        return {"tag_name": tag, "assets": [
            {"name": name, "browser_download_url": f"https://example/{name}",
             "digest": "sha256:" + hashlib.sha256(data).hexdigest()} for name, data in files.items()]}

    def download(url, target, on_progress=None):
        calls["download"] += 1
        with open(target, "wb") as f:
            f.write(files[url.rsplit("/", 1)[1]])
    return get_json, download, calls


class TestTools:
    def test_installs_verifies_and_keeps_the_executable_bit(self, tmp_path):
        get_json, download, calls = fake_github({"yt-dlp_macos.zip": zip_with("yt-dlp_macos")})
        tools = Tools(str(tmp_path), get_json, download, ("darwin", "arm64"))
        path = tools.ensure("yt-dlp")
        assert path.endswith(os.path.join("yt-dlp", "2026.10.21", "yt-dlp_macos"))
        assert os.access(path, os.X_OK)
        assert os.path.isfile(os.path.join(os.path.dirname(path), "_internal", "lib.txt"))
        assert tools.ensure("yt-dlp") == path and calls["download"] == 1   # installed: no new download

    def test_single_file_tools(self, tmp_path):
        get_json, download, _ = fake_github({"qjs-darwin-arm64": b"binary"}, tag="v0.17.0")
        path = Tools(str(tmp_path), get_json, download, ("darwin", "arm64")).ensure("quickjs")
        assert os.path.basename(path) == "qjs-darwin-arm64" and os.access(path, os.X_OK)

    def test_a_damaged_download_is_rejected(self, tmp_path):
        get_json, _, _ = fake_github({"qjs-darwin-arm64": b"binary"})

        def bad_download(url, target, on_progress=None):
            with open(target, "wb") as f:
                f.write(b"tampered")
        with pytest.raises(ToolError, match="checksum"):
            Tools(str(tmp_path), get_json, bad_download, ("darwin", "arm64")).ensure("quickjs")

    def test_update_replaces_an_older_version(self, tmp_path):
        files = {"qjs-darwin-arm64": b"v1"}
        get_json, download, _ = fake_github(files, tag="v1")
        tools = Tools(str(tmp_path), get_json, download, ("darwin", "arm64"))
        old = tools.ensure("quickjs")
        get_json2, download2, _ = fake_github({"qjs-darwin-arm64": b"v2"}, tag="v2")
        tools._get_json, tools._download = get_json2, download2
        new = tools.ensure("quickjs", update=True)
        assert "v2" in new and not os.path.exists(old)

    def test_offline_keeps_the_installed_version(self, tmp_path):
        get_json, download, _ = fake_github({"qjs-darwin-arm64": b"v1"}, tag="v1")
        tools = Tools(str(tmp_path), get_json, download, ("darwin", "arm64"))
        path = tools.ensure("quickjs")

        def offline(url):
            raise OSError("no network")
        tools._get_json = offline
        assert tools.ensure("quickjs", update=True) == path

    def test_unsafe_zip_paths_are_refused(self, tmp_path):
        get_json, download, _ = fake_github({"yt-dlp_macos.zip": zip_with("../evil")})
        with pytest.raises(ToolError):
            Tools(str(tmp_path), get_json, download, ("darwin", "arm64")).ensure("yt-dlp")

    def test_unsupported_platform(self, tmp_path):
        with pytest.raises(ToolError, match="isn't available"):
            Tools(str(tmp_path), *fake_github({})[:2], ("sunos", "sparc")).ensure("yt-dlp")

    def test_odd_versions_are_refused(self):
        assert download_tools.safe_version("2026.10.21") and download_tools.safe_version("v0.17.0")
        assert not download_tools.safe_version("../x") and not download_tools.safe_version(".hidden")


# ── yt-dlp calls ─────────────────────────────────────────────
class FakeTools:
    folder = "/tmp/tools"

    def __init__(self):
        self.version = 1

    def ensure(self, tool, update=False, on_progress=None):
        if update:
            self.version += 1
        return f"/tools/{tool}/v{self.version}"


def completed(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout, stderr)


def test_inspect_passes_only_the_id_after_double_dash():
    seen = []

    def run(args, **kwargs):
        seen.append(args)
        return completed(json.dumps({"id": "_KztNIg4cvE", "title": "A - B"}))
    info = YouTube(FakeTools(), "/usr/bin/ffmpeg", run=run).inspect("_KztNIg4cvE")
    assert info["id"] == "_KztNIg4cvE"
    args = seen[0]
    assert args[-2:] == ["--", "https://www.youtube.com/watch?v=_KztNIg4cvE"]
    assert "--ignore-config" in args and "quickjs:/tools/quickjs/v1" in args


def test_a_tool_failure_updates_yt_dlp_and_retries_once():
    answers = [completed(stderr="ERROR: nsig extraction failed", code=1), completed(json.dumps({"id": "x" * 11}))]
    used = []

    def run(args, **kwargs):
        used.append(args[0])
        return answers.pop(0)
    YouTube(FakeTools(), None, run=run).inspect("_KztNIg4cvE")
    assert used == ["/tools/yt-dlp/v1", "/tools/yt-dlp/v2"]


def test_an_unavailable_video_is_not_retried():
    calls = []

    def run(args, **kwargs):
        calls.append(1)
        return completed(stderr="ERROR: [youtube] _KztNIg4cvE: Private video", code=1)
    with pytest.raises(YouTubeError, match="private"):
        YouTube(FakeTools(), None, run=run).inspect("_KztNIg4cvE")
    assert calls == [1]


def test_download_reports_progress_and_returns_the_file(tmp_path):
    class Process:
        def __init__(self, args, **kwargs):
            out = [a for a in args if a.endswith("%(ext)s")][0].replace("%(ext)s", "m4a")
            open(out, "wb").write(b"audio")
            self.stdout = io.StringIO("@progress 10 100 NA\n@progress 100 100 NA\n")
            self.stderr = io.StringIO("")

        def wait(self, timeout=None):
            return 0
    progress = []
    path = YouTube(FakeTools(), None, popen=Process).download_audio(
        "_KztNIg4cvE", str(tmp_path), on_progress=lambda done, total: progress.append((done, total)))
    assert path.endswith("youtube_audio.m4a") and progress == [(10, 100), (100, 100)]


def test_ids_are_checked_before_yt_dlp_runs():
    with pytest.raises(YouTubeError):
        YouTube(FakeTools(), None, run=lambda *a, **k: completed()).inspect("--exec=x")
