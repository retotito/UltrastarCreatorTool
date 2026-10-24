"""YouTube links in Step 1: the video's details and its audio, through yt-dlp.

Only an 11-character video id ever reaches yt-dlp (after "--"), so nothing a user types can become
a yt-dlp option. yt-dlp and QuickJS come from `download_tools`; FFmpeg is the app's own.
"""

import glob
import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional
from urllib.parse import parse_qs, urlparse

from services.download_tools import ToolError, Tools
from utils.logger import log_step

ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com",
         "www.youtube-nocookie.com", "youtu.be"}
INSPECT_TIMEOUT_SEC = 120
DOWNLOAD_TIMEOUT_SEC = 1800


class YouTubeError(Exception):
    """Something to tell the user. `retryable` is False when the video itself can't be had."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class YouTubeCancelled(YouTubeError):
    """The user cancelled the download."""

    def __init__(self):
        super().__init__("Cancelled.", retryable=False)


def video_id(link: str) -> Optional[str]:
    """The video id of a YouTube link (watch, youtu.be, music, shorts, embed, live), or None."""
    link = (link or "").strip()
    if ID.match(link):
        return link
    if "://" not in link:
        link = "https://" + link
    try:
        url = urlparse(link)
    except ValueError:
        return None
    host = (url.hostname or "").lower()
    if host not in HOSTS:
        return None
    if host == "youtu.be":
        candidate = url.path.strip("/").split("/")[0]
    elif url.path == "/watch":
        candidate = (parse_qs(url.query).get("v") or [""])[0]
    else:
        parts = url.path.strip("/").split("/")
        candidate = parts[1] if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v") else ""
    return candidate if ID.match(candidate) else None


def watch_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


# "(Official Music Video)", "[Lyrics]", "| Official Audio", "HD", ...
_TITLE_NOISE = re.compile(
    r"\s*[\(\[][^\)\]]*\b(official|video|audio|lyrics?|visuali[sz]er|hd|hq|4k|remaster(ed)?|mv|clip)\b[^\)\]]*[\)\]]"
    r"|\s*\|\s*official.*$|\s+(official\s+)?(music\s+)?video$|\s+(hd|hq|4k|1080p|720p)$",
    re.IGNORECASE,
)
_CHANNEL_NOISE = re.compile(r"\s*(-\s*topic|vevo|official)\s*$", re.IGNORECASE)


def clean_title(title: str) -> str:
    previous = None
    while previous != title:
        previous, title = title, _TITLE_NOISE.sub("", title).strip(" -|")
    return " ".join(title.split())


def song_details(info: dict) -> dict:
    """Artist and title for the song: YouTube Music's own fields, else "Artist - Title" in the video title,
    else the channel name."""
    artist = info.get("artist") or (info.get("artists") or [None])[0] or info.get("creator")
    title = info.get("track")
    raw_title = info.get("title") or ""
    if not (artist and title):
        cleaned = clean_title(raw_title)
        parts = re.split(r"\s+[-–—]\s+", cleaned, maxsplit=1)
        if len(parts) == 2 and all(parts):
            artist, title = artist or parts[0], title or parts[1]
        else:
            title = title or cleaned
            artist = artist or _CHANNEL_NOISE.sub("", info.get("channel") or info.get("uploader") or "").strip()
    return {"artist": (artist or "").strip(), "title": clean_title(title or "").strip()}


def video_language(info: dict) -> Optional[str]:
    """The language the video is in, as far as YouTube knows: the uploader's setting, else the one its
    automatic captions were heard in ("de-orig")."""
    language = info.get("language")
    if language:
        return language.split("-")[0].lower()
    heard = [key for key in (info.get("automatic_captions") or {}) if key.endswith("-orig")]
    return heard[0][:-len("-orig")].split("-")[0].lower() if len(heard) == 1 else None


def preview_thumbnail(info: dict) -> Optional[str]:
    """The largest JPEG thumbnail up to 1280 px wide (WebP may not decode everywhere)."""
    jpegs = [t for t in info.get("thumbnails") or [] if urlparse(t.get("url", "")).path.endswith(".jpg")]
    fitting = [t for t in jpegs if (t.get("width") or 0) <= 1280]
    best = max(fitting, key=lambda t: t.get("width") or 0, default=None)
    return best["url"] if best else info.get("thumbnail")


def summary(info: dict) -> dict:
    """What Step 1 shows before downloading."""
    details = song_details(info)
    return {
        "video_id": info.get("id"),
        "url": watch_url(info["id"]) if info.get("id") else None,
        "video_title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": info.get("duration"),
        "thumbnail": preview_thumbnail(info),
        "language": video_language(info),
        # Captions written by the uploader (not YouTube's speech recognition): maybe real lyrics.
        "subtitle_languages": sorted((info.get("subtitles") or {}).keys()),
        **details,
    }


LANGUAGE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def subtitle_tracks(info: dict, language: Optional[str] = None) -> List[dict]:
    """The video's subtitles that may hold the lyrics, best first: written by the uploader (in the song's
    language first), then YouTube's automatic captions in the language it heard ("en-orig"; speech recognition,
    weak on singing). [{"lang", "auto", "label"}]."""
    from services.ultrastar import language_name
    manual = [k for k in (info.get("subtitles") or {}) if k != "live_chat" and LANGUAGE_KEY.match(k)]
    manual.sort(key=lambda k: (track_language(k) != (language or "").lower(), k))
    heard = [k for k in (info.get("automatic_captions") or {}) if k.endswith("-orig") and LANGUAGE_KEY.match(k)]
    tracks = [{"lang": k, "auto": False, "language": track_language(k),
               "label": f"{language_name(track_language(k))} (by the uploader)"} for k in manual]
    tracks += [{"lang": k, "auto": True, "language": track_language(k),
                "label": f"{language_name(track_language(k))} (automatic captions)"} for k in heard]
    # The same language more than once (Despacito: three English tracks): "English", "English 2", "English 3".
    seen: dict = {}
    for t in tracks:
        seen[t["label"]] = seen.get(t["label"], 0) + 1
        if seen[t["label"]] > 1:
            t["label"] = t["label"].replace(" (", f" {seen[t['label']]} (", 1)
    return tracks


def track_language(key: str) -> str:
    """ "es-419" / "de-orig" → "es" / "de"."""
    return key.split("-")[0].lower()


def pick_track(tracks: List[dict], languages: List[str]) -> Optional[dict]:
    """The best track in one of the song's languages (the uploader's before automatic captions), None if the
    video has none in them (then its subtitles would be a translation)."""
    wanted = [code for code in languages if code]
    for auto in (False, True):
        for code in wanted:
            found = next((t for t in tracks if t["auto"] == auto and t["language"] == code), None)
            if found:
                return found
    return None


def subtitles_to_swap(loaded: dict, current_text: str, languages: List[str]):
    """After the song's languages are confirmed: what to do with subtitles loaded with the download.
    None: keep them (right language, nothing loaded, or the user changed the text); "remove": the video has no
    track in the song's languages (they'd be a translation); else the track to load instead."""
    wanted = [code for code in languages if code]
    track = loaded.get("track")
    if not wanted or (current_text or "") != (loaded.get("text") or ""):
        return None
    if not track:   # none loaded (or removed before): load one now if the video has it in these languages
        return pick_track(loaded.get("tracks") or [], wanted)
    if track["language"] in wanted:
        return None
    return pick_track(loaded.get("tracks") or [], wanted) or "remove"


MIN_DETECT_LINES = 8
MIN_DETECT_PROBABILITY = 0.9


def text_language(text: str) -> Optional[str]:
    """The language the lyrics are written in, if that is clear (8+ lines, ≥ 90 %); None otherwise (short or
    repetitive lyrics, "la la la", mixed languages)."""
    if len([line for line in (text or "").splitlines() if line.strip()]) < MIN_DETECT_LINES:
        return None
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0          # the same answer every time
        best = detect_langs(text)[0]
    except Exception:                     # langdetect missing, or no letters to judge
        return None
    return best.lang.split("-")[0] if best.prob >= MIN_DETECT_PROBABILITY else None


_TIMING = re.compile(r"-->")
_TAGS = re.compile(r"<[^>]*>")
_NOISE = re.compile(r"[♪♫♬♩]|\[[^\]]*\]|\((?:music|applause|laughter|instrumental)[^)]*\)", re.IGNORECASE)


def vtt_to_lyrics(vtt: str) -> str:
    """WebVTT subtitles as lyrics lines: no header, cue numbers, timings, tags or "♪"/"[Music]"; a line repeated
    by the next cue (rolling automatic captions) is kept once."""
    import html
    lines: List[str] = []
    in_block = False
    for raw in (vtt or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            in_block = False
            continue
        if line.startswith("WEBVTT") or line.startswith(("NOTE", "STYLE", "REGION")):
            in_block = not line.startswith("WEBVTT")
            continue
        if in_block or _TIMING.search(line) or line.isdigit() or re.match(r"^(Kind|Language):", line):
            continue
        text = html.unescape(_TAGS.sub("", line))
        text = re.sub(r"\s+", " ", _NOISE.sub("", text)).strip(" -")
        if not text or text in lines[-2:]:
            continue
        lines.append(text)
    return "\n".join(lines)


def explain(stderr: str) -> YouTubeError:
    """yt-dlp's error output as something to tell the user."""
    lines = [line for line in (stderr or "").splitlines() if line.strip()]
    error = next((line for line in reversed(lines) if line.startswith("ERROR:")), lines[-1] if lines else "")
    error = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?([\w-]{11}:\s*)?", "", error)
    final = lambda message: YouTubeError(message, retryable=False)  # noqa: E731
    if re.search(r"private video", error, re.I):
        return final("This video is private, so it can't be downloaded.")
    if re.search(r"confirm your age|age.restricted|inappropriate for some users", error, re.I):
        return final("YouTube only shows this video to signed-in adults, so it can't be downloaded.")
    if re.search(r"members.only|join this channel", error, re.I):
        return final("This video is only for channel members, so it can't be downloaded.")
    if re.search(r"not available in your country|geo.?restrict", error, re.I):
        return final("This video isn't available in your country.")
    if re.search(r"live event|is live|premieres in", error, re.I):
        return final("This video is live or hasn't premiered yet. Try again once it can be watched in full.")
    if re.search(r"video unavailable|has been removed|no longer available|does not exist|account .* terminated",
                 error, re.I):
        return final("This video isn't available on YouTube anymore.")
    if re.search(r"getaddrinfo|name resolution|resolve host|network is unreachable|timed out|connection (refused|reset)",
                 error, re.I):
        return final("Couldn't reach YouTube. Check your internet connection and try again.")
    if re.search(r"not a bot|sign in to confirm", error, re.I):
        return final("YouTube asked to confirm this isn't a bot. Wait a while, then try again.")
    return YouTubeError(f"Couldn't get the song from YouTube: {error or 'yt-dlp failed'}")


@dataclass
class _Programs:
    yt_dlp: str
    qjs: str


class YouTube:
    """yt-dlp with the app's tools. Tools are installed on first use."""

    def __init__(self, tools: Tools, ffmpeg: Optional[str],
                 run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen):
        self.tools = tools
        self.ffmpeg = ffmpeg
        self._run = run
        self._popen = popen

    def _programs(self, update: bool = False) -> _Programs:
        try:
            return _Programs(self.tools.ensure("yt-dlp", update=update), self.tools.ensure("quickjs", update=update))
        except ToolError as error:
            raise YouTubeError(str(error)) from error

    def _base_args(self, programs: _Programs) -> List[str]:
        args = [programs.yt_dlp, "--ignore-config", "--no-playlist", "--color", "never",
                # only the downloaded QuickJS, never a JavaScript runtime that happens to be installed
                "--no-js-runtimes", "--js-runtimes", f"quickjs:{programs.qjs}",
                "--cache-dir", os.path.join(self.tools.folder, "yt-dlp-cache")]
        if self.ffmpeg:
            args += ["--ffmpeg-location", os.path.dirname(self.ffmpeg)]
        return args

    def _with_update(self, attempt: Callable[[_Programs], object]):
        """Run; if it fails for a reason that isn't the video, update yt-dlp and run once more."""
        programs = self._programs()
        try:
            return attempt(programs)
        except YouTubeError as error:
            if not error.retryable:
                raise
            try:
                updated = self._programs(update=True)
            except YouTubeError:
                raise error
            if updated.yt_dlp == programs.yt_dlp:
                raise
            log_step("YOUTUBE", "Retrying with the updated yt-dlp")
            return attempt(updated)

    def inspect(self, vid: str) -> dict:
        """The video's details (no download). Raises YouTubeError."""
        if not ID.match(vid or ""):
            raise YouTubeError("That isn't a YouTube video.", retryable=False)

        def attempt(programs):
            result = self._run(self._base_args(programs) + ["--skip-download", "--dump-single-json", "--",
                                                            watch_url(vid)],
                               capture_output=True, text=True, timeout=INSPECT_TIMEOUT_SEC)
            if result.returncode != 0:
                raise explain(result.stderr)
            try:
                return json.loads(result.stdout)
            except ValueError:
                raise YouTubeError("yt-dlp's answer couldn't be read. Try again.")
        return self._with_update(attempt)

    def subtitles(self, vid: str, track: dict, folder: str) -> str:
        """One subtitle track (see subtitle_tracks) as WebVTT text, no video downloaded. Raises YouTubeError."""
        if not ID.match(vid or "") or not LANGUAGE_KEY.match(track.get("lang", "")):
            raise YouTubeError("That isn't a YouTube video.", retryable=False)
        os.makedirs(folder, exist_ok=True)

        def attempt(programs):
            for old in glob.glob(os.path.join(glob.escape(folder), "subs*")):
                os.remove(old)
            result = self._run(self._base_args(programs) + [
                "--skip-download", "--write-auto-subs" if track.get("auto") else "--write-subs",
                "--sub-langs", track["lang"], "--sub-format", "vtt",
                "-o", os.path.join(folder, "subs.%(ext)s"), "--", watch_url(vid),
            ], capture_output=True, text=True, timeout=INSPECT_TIMEOUT_SEC)
            if result.returncode != 0:
                raise explain(result.stderr)
            files = glob.glob(os.path.join(glob.escape(folder), "subs*.vtt"))
            if not files:
                raise YouTubeError("YouTube sent no subtitles for this language.", retryable=False)
            with open(files[0], encoding="utf-8", errors="replace") as f:
                return f.read()
        return self._with_update(attempt)

    def download_audio(self, vid: str, folder: str,
                       on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
                       cancelled: Optional[threading.Event] = None) -> str:
        """Download the best audio stream as is into `folder` (as youtube_audio.<ext>); returns its path.
        Setting `cancelled` stops yt-dlp, removes the partial download and raises YouTubeError("Cancelled.")."""
        if not ID.match(vid or ""):
            raise YouTubeError("That isn't a YouTube video.", retryable=False)
        os.makedirs(folder, exist_ok=True)

        def attempt(programs):
            for old in glob.glob(os.path.join(folder, "youtube_audio.*")):
                os.remove(old)
            args = self._base_args(programs) + [
                "-f", "bestaudio[ext=m4a]/bestaudio/best",
                "-o", os.path.join(folder, "youtube_audio.%(ext)s"),
                "--newline", "--quiet", "--progress", "--progress-template",
                "download:@progress %(progress.downloaded_bytes)s %(progress.total_bytes)s "
                "%(progress.total_bytes_estimate)s",
                "--", watch_url(vid),
            ]
            if cancelled is not None and cancelled.is_set():
                raise YouTubeCancelled()
            process = self._popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if cancelled is not None:
                threading.Thread(target=_kill_when_cancelled, args=(process, cancelled), daemon=True).start()
            for line in process.stdout:
                if on_progress and line.startswith("@progress "):
                    on_progress(*parse_progress(line))
            stderr = process.stderr.read()
            code = process.wait(timeout=DOWNLOAD_TIMEOUT_SEC)
            if cancelled is not None and cancelled.is_set():
                for partial in glob.glob(os.path.join(glob.escape(folder), "youtube_audio.*")):
                    os.remove(partial)
                raise YouTubeCancelled()
            if code != 0:
                raise explain(stderr)
            files = [f for f in glob.glob(os.path.join(folder, "youtube_audio.*")) if not f.endswith(".part")]
            if not files:
                raise YouTubeError("yt-dlp finished but no audio file was written. Try again.")
            return files[0]
        return self._with_update(attempt)


def _kill_when_cancelled(process, cancelled: threading.Event) -> None:
    while process.poll() is None:
        if cancelled.wait(0.3):
            process.kill()
            return


def parse_progress(line: str) -> tuple:
    """(downloaded bytes, total bytes or None) from one "@progress" line."""
    def number(text):
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return None
    parts = line.split()
    done = number(parts[1]) if len(parts) > 1 else 0
    total = (number(parts[2]) if len(parts) > 2 else None) or (number(parts[3]) if len(parts) > 3 else None)
    return done or 0, total
