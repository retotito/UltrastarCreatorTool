"""External tools the app downloads on first use: yt-dlp (YouTube downloads) and QuickJS (the
JavaScript runtime yt-dlp needs to answer YouTube's checks).

They are not bundled: YouTube changes often and an older yt-dlp then stops working, so the app
fetches the latest GitHub release, verifies it against GitHub's SHA-256 digest, and can update
when a download fails (`ensure(..., update=True)`). Tune Studio does the same.

Layout: <folder>/<tool>/<version>/..., and <folder>/tools.json naming the installed versions.
"""

import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from utils.logger import log_step

USER_AGENT = "UltrastarCreatorTool (https://github.com/retotito/UltrastarCreatorTool)"
TIMEOUT_SEC = 30


class ToolError(Exception):
    """A tool can't be installed (no build for this computer, no network, bad download)."""


@dataclass(frozen=True)
class ToolSpec:
    repo: str
    asset: str          # release asset name for this computer
    executable: str     # path of the program inside the asset (the asset itself if not a zip)
    zipped: bool


def current_platform() -> tuple:
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64", "i386": "x86", "i686": "x86",
            "x86": "x86"}.get(machine, machine)
    return sys.platform, arch


def spec_for(tool: str, os_name: str, arch: str) -> Optional[ToolSpec]:
    """Which release file to use for a tool on a platform, or None if there is none."""
    if tool == "yt-dlp":
        # The "onedir" zips start in a fraction of a second; the single-file builds unpack themselves on
        # every run (6-13 s). The macOS build runs on Intel and Apple Silicon.
        found = {
            ("darwin", "arm64"): ("yt-dlp_macos.zip", "yt-dlp_macos"),
            ("darwin", "x64"): ("yt-dlp_macos.zip", "yt-dlp_macos"),
            ("win32", "x64"): ("yt-dlp_win.zip", "yt-dlp.exe"),
            ("win32", "x86"): ("yt-dlp_win_x86.zip", "yt-dlp_x86.exe"),
            ("win32", "arm64"): ("yt-dlp_win_arm64.zip", "yt-dlp_arm64.exe"),
            ("linux", "x64"): ("yt-dlp_linux.zip", "yt-dlp_linux"),
            ("linux", "arm64"): ("yt-dlp_linux_aarch64.zip", "yt-dlp_linux_aarch64"),
        }.get((os_name, arch))
        return ToolSpec("yt-dlp/yt-dlp", found[0], found[1], True) if found else None
    if tool == "quickjs":
        asset = {
            ("darwin", "arm64"): "qjs-darwin-arm64",
            ("darwin", "x64"): "qjs-darwin-x86_64",
            ("win32", "x64"): "qjs-windows-x86_64.exe",
            ("win32", "arm64"): "qjs-windows-x86_64.exe",   # Windows on ARM runs the x64 build
            ("win32", "x86"): "qjs-windows-x86.exe",
            ("linux", "x64"): "qjs-linux-x86_64",
            ("linux", "arm64"): "qjs-linux-aarch64",
        }.get((os_name, arch))
        return ToolSpec("quickjs-ng/quickjs", asset, asset, False) if asset else None
    raise ValueError(f"Unknown tool {tool}")


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, target: str, on_progress: Optional[Callable[[int, int], None]] = None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response, open(target, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done, total)


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_version(version: str) -> bool:
    """A release tag that can name a folder (no path separators, no '..', no leading dot)."""
    return bool(version) and version[0].isalnum() and len(version) <= 100 and ".." not in version and all(
        c.isalnum() or c in "._+-" for c in version)


def extract_zip(archive: str, target: str) -> None:
    """Unzip, keeping each file's Unix permissions (zipfile drops them) and refusing paths outside target."""
    root = os.path.realpath(target)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            destination = os.path.realpath(os.path.join(target, info.filename))
            if destination != root and not destination.startswith(root + os.sep):
                raise ToolError(f"Unsafe path in archive: {info.filename}")
            zf.extract(info, target)
            mode = (info.external_attr >> 16) & 0o777
            if mode and not info.is_dir():
                os.chmod(destination, mode)


class Tools:
    """Installs and finds the downloaded tools in `folder`."""

    def __init__(self, folder: str, get_json: Callable[[str], dict] = _get_json,
                 download: Callable[..., None] = _download, platform_key: Optional[tuple] = None):
        self.folder = folder
        self._get_json = get_json
        self._download = download
        self._platform = platform_key or current_platform()
        os.makedirs(folder, exist_ok=True)

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.folder, "tools.json")

    def _manifest(self) -> Dict[str, dict]:
        try:
            with open(self.manifest_path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_manifest(self, manifest: Dict[str, dict]) -> None:
        tmp = self.manifest_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(manifest, f, indent=2)
        os.replace(tmp, self.manifest_path)

    def installed(self, tool: str) -> Optional[str]:
        """Path of the installed tool's program, if it is there."""
        entry = self._manifest().get(tool)
        if entry and os.path.isfile(entry.get("path", "")):
            return entry["path"]
        return None

    def ensure(self, tool: str, update: bool = False,
               on_progress: Optional[Callable[[int, int], None]] = None) -> str:
        """The tool's program, downloading the latest release if it isn't installed (or, with `update`,
        if a newer one exists). Raises ToolError."""
        current = self.installed(tool)
        if current and not update:
            return current
        spec = spec_for(tool, *self._platform)
        if spec is None:
            raise ToolError(f"{tool} isn't available for this computer ({'/'.join(self._platform)}).")
        try:
            release = self._get_json(f"https://api.github.com/repos/{spec.repo}/releases/latest")
        except OSError as error:
            if current:
                return current  # offline: keep what works
            raise ToolError(f"Couldn't check for {tool}: {error}. Check your internet connection.") from error
        version = str(release.get("tag_name", ""))
        if not safe_version(version):
            raise ToolError(f"The latest {tool} release has an unexpected version: {version!r}")
        entry = self._manifest().get(tool)
        if current and entry and entry.get("version") == version:
            return current
        asset = next((a for a in release.get("assets", []) if a.get("name") == spec.asset), None)
        digest = (asset or {}).get("digest") or ""
        if not asset or not digest.startswith("sha256:"):
            raise ToolError(f"{tool} {version} has no verified download for this computer yet. Try again later.")

        log_step("TOOLS", f"Installing {tool} {version} ({spec.asset})")
        target = os.path.join(self.folder, tool, version)
        work = tempfile.mkdtemp(prefix=f".{tool}-", dir=self.folder)
        try:
            downloaded = os.path.join(work, spec.asset)
            self._download(asset["browser_download_url"], downloaded, on_progress)
            if sha256_of(downloaded) != digest.split(":", 1)[1].lower():
                raise ToolError(f"The {tool} download is damaged (checksum mismatch). Try again.")
            unpacked = os.path.join(work, "unpacked")
            os.makedirs(unpacked)
            if spec.zipped:
                extract_zip(downloaded, unpacked)
            else:
                shutil.move(downloaded, os.path.join(unpacked, spec.executable))
            program = os.path.join(unpacked, spec.executable)
            if not os.path.isfile(program):
                raise ToolError(f"The {tool} download doesn't contain {spec.executable}.")
            os.chmod(program, os.stat(program).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            shutil.rmtree(target, ignore_errors=True)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(unpacked, target)
        except OSError as error:
            raise ToolError(f"Couldn't install {tool}: {error}") from error
        finally:
            shutil.rmtree(work, ignore_errors=True)

        manifest = self._manifest()
        old = manifest.get(tool, {}).get("version")
        manifest[tool] = {"version": version, "path": os.path.join(target, spec.executable)}
        self._save_manifest(manifest)
        if old and old != version:
            shutil.rmtree(os.path.join(self.folder, tool, old), ignore_errors=True)
        return manifest[tool]["path"]
