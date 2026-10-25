"""Models from Hugging Face with a fallback to our mirror, in case an original repository goes away.

The aligner and FCPE come from small one-person repositories (tuneperfect/…). Unchanged copies are kept in
MIRROR_REPO (huggingface.co/Retotito/ultrastar-models, pinned to MIRROR_REVISION). The original is always tried
first; the mirror only when the original is gone (deleted, made private or gated, the file or version missing),
not when the network is down. A file from the mirror must have the original's size and SHA-256.
"""

import hashlib
import os
from typing import Optional

from utils.logger import log_step

MIRROR_REPO = "Retotito/ultrastar-models"
MIRROR_REVISION = "75854108a364f01f8ee0a3df0db9ce8eb902beca"   # the upload of 2026-10-25 (aligner, boundary, FCPE)


class ModelUnavailable(RuntimeError):
    pass


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def cached_path(model: dict) -> Optional[str]:
    """The model's file if it is in the Hugging Face cache (the original's or the mirror's), else None.
    No network access."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None
    for repo, filename, revision in ((model["repo"], model["file"], model["revision"]),
                                     (MIRROR_REPO, model["mirror_file"], model.get("mirror_revision", MIRROR_REVISION))):
        try:
            path = try_to_load_from_cache(repo, filename, revision=revision)
        except Exception:
            continue
        # Size check: on Windows a failed hardlink can leave an empty snapshot file.
        if isinstance(path, str) and os.path.isfile(path) and os.path.getsize(path) == model["bytes"]:
            return path
    return None


def _gone(error: Exception) -> bool:
    """Whether a download error means the original isn't there any more (rather than no network)."""
    from huggingface_hub import errors
    gone = tuple(cls for cls in (getattr(errors, n, None) for n in (
        "RepositoryNotFoundError", "RevisionNotFoundError", "EntryNotFoundError", "GatedRepoError",
        "DisabledRepoError", "RemoteEntryNotFoundError")) if cls)
    if isinstance(error, gone):
        return True
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None) in (401, 403, 404, 410, 451)


def fetch(model: dict) -> str:
    """The model's file: from the cache, else downloaded from the original, else (if the original is gone) from
    the mirror, checked against the original's size and SHA-256. Raises ModelUnavailable."""
    found = cached_path(model)
    if found:
        return found
    from huggingface_hub import hf_hub_download
    try:
        return hf_hub_download(model["repo"], model["file"], revision=model["revision"])
    except Exception as error:
        if not _gone(error):
            raise
        log_step("MODELS", f"{model['repo']} is not available ({type(error).__name__}); using the mirror {MIRROR_REPO}")
    path = hf_hub_download(MIRROR_REPO, model["mirror_file"], revision=model.get("mirror_revision", MIRROR_REVISION))
    if os.path.getsize(path) != model["bytes"] or _sha256(path) != model["sha256"]:
        raise ModelUnavailable(f"The mirror's copy of {model['file']} isn't the expected file.")
    return path
