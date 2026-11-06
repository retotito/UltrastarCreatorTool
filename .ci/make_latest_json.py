"""The update manifest the app checks (latest.json): `make_latest_json.py <folder> <tag> <version> <notes file>`.

<folder> holds the release's files and their .sig files, signed in the build jobs. Writes <folder>/latest.json.
"""
import datetime
import json
import os
import sys
from urllib.parse import quote

REPO = "retotito/UltrastarCreatorTool"
# What ends a file's name → the platform the updater looks up
PLATFORMS = {"_aarch64.app.tar.gz": "darwin-aarch64", "_x64.app.tar.gz": "darwin-x86_64", ".msi": "windows-x86_64"}


def manifest(names, read_signature, tag, version, notes, now):
    platforms = {}
    for name in names:
        for ending, platform in PLATFORMS.items():
            if name.endswith(ending) and f"{name}.sig" in names:
                platforms[platform] = {
                    "signature": read_signature(f"{name}.sig").strip(),
                    "url": f"https://github.com/{REPO}/releases/download/{quote(tag)}/{quote(name)}",
                }
    return {"version": version, "notes": notes.strip(), "pub_date": now, "platforms": platforms}


def main(folder, tag, version, notes_file):
    def read_signature(name):
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            return f.read()
    with open(notes_file, encoding="utf-8") as f:
        notes = f.read()
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = manifest(set(os.listdir(folder)), read_signature, tag, version, notes, now)
    if not data["platforms"]:
        sys.exit("No signed installers found: is the TAURI_SIGNING_PRIVATE_KEY secret set?")
    with open(os.path.join(folder, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("latest.json:", version, sorted(data["platforms"]))


if __name__ == "__main__":
    main(*sys.argv[1:])
