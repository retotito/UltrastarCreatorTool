"""Models downloaded from our own Hugging Face repository, unchanged copies of the originals.

The aligner and FCPE were published in small one-person repositories (tuneperfect/…). The app downloads them only
from MODEL_REPO (huggingface.co/Retotito/ultrastar-models, pinned to MODEL_REVISION), so it doesn't depend on those
staying online. A downloaded file must have the original's size and SHA-256. A copy of the original that is already
in the Hugging Face cache (installs from before the switch) is used as it is, so nobody downloads it twice.
"""

import hashlib
import os
from typing import Optional

MODEL_REPO = "Retotito/ultrastar-models"
MODEL_REVISION = "75854108a364f01f8ee0a3df0db9ce8eb902beca"   # the upload of 2026-10-25 (aligner, boundary, FCPE)


class ModelUnavailable(RuntimeError):
    pass


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def cached_path(model: dict) -> Optional[str]:
    """The model's file if it is in the Hugging Face cache (ours, or the original from an older install), else None.
    No network access."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None
    for repo, filename, revision in ((MODEL_REPO, model["path"], MODEL_REVISION),
                                     (model["original_repo"], model["original_file"], model["original_revision"])):
        try:
            path = try_to_load_from_cache(repo, filename, revision=revision)
        except Exception:
            continue
        # Size check: on Windows a failed hardlink can leave an empty snapshot file.
        if isinstance(path, str) and os.path.isfile(path) and os.path.getsize(path) == model["bytes"]:
            return path
    return None


def fetch(model: dict) -> str:
    """The model's file: from the cache, else downloaded from MODEL_REPO and checked against the original's size
    and SHA-256. Raises ModelUnavailable if the download isn't the expected file."""
    found = cached_path(model)
    if found:
        return found
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(MODEL_REPO, model["path"], revision=MODEL_REVISION)
    if os.path.getsize(path) != model["bytes"] or _sha256(path) != model["sha256"]:
        raise ModelUnavailable(f"The downloaded {model['path']} isn't the expected file.")
    return path
