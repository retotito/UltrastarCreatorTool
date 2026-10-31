"""The Hugging Face cache without symlinks on Windows.

huggingface_hub keeps each file once in `blobs/` and links to it from `snapshots/<revision>/`. Windows allows the
links only with Developer Mode or as admin, and newer Windows 11 versions refuse to follow them for many programs
("[WinError 448] ... untrusted mount point"); the file then can't be opened and looks 0 bytes. So on Windows the
app has huggingface_hub store plain files, and replaces existing snapshot links with hard links to their blob
(same file, no extra space, not a link Windows refuses).
"""

import os
import shutil
import sys

from utils.logger import log_step


def store_plain_files(platform: str = sys.platform) -> bool:
    """On Windows: new downloads go into snapshots/ as plain files instead of symlinks. True if switched."""
    if platform != "win32":
        return False
    try:
        from huggingface_hub import file_download
    except ImportError:
        return False
    file_download.are_symlinks_supported = lambda *args, **kwargs: False
    return True


def _replace_link(link: str) -> bool:
    target = os.path.normpath(os.path.join(os.path.dirname(link), os.readlink(link)))
    if not os.path.isfile(target):
        return False   # a dangling link: leave it, huggingface_hub downloads the file again
    tmp = link + ".plain"
    try:
        os.link(target, tmp)
    except OSError:
        shutil.copyfile(target, tmp)   # no hard links on this drive: a copy
    os.unlink(link)
    os.replace(tmp, link)
    return True


def replace_snapshot_links(cache_dir: str) -> int:
    """Replace the symlinks in every repository's snapshots/ with plain files of their blob. Returns how many."""
    replaced = 0
    if not os.path.isdir(cache_dir):
        return 0
    for repo in os.listdir(cache_dir):
        snapshots = os.path.join(cache_dir, repo, "snapshots")
        if not os.path.isdir(snapshots):
            continue
        for root, _dirs, files in os.walk(snapshots):
            for name in files:
                path = os.path.join(root, name)
                if not os.path.islink(path):
                    continue
                try:
                    replaced += _replace_link(path)
                except OSError as e:
                    log_step("HF_CACHE", f"Couldn't replace the link {path}: {e}")
    return replaced


def fix_windows_cache(platform: str = sys.platform) -> None:
    """At startup on Windows: no new symlinks, and the existing ones replaced."""
    if not store_plain_files(platform):
        return
    from huggingface_hub.constants import HF_HUB_CACHE
    replaced = replace_snapshot_links(HF_HUB_CACHE)
    if replaced:
        log_step("HF_CACHE", f"Replaced {replaced} symlinks in {HF_HUB_CACHE} with plain files")
