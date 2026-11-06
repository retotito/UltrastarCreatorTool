"""Writing an exported song to where the user chose: a song folder, or a single file.

The backend runs on the same computer, so it writes directly: nothing large passes through the web view's memory. Both
write beside the target first and then rename, so a failed export leaves what was there.
"""

import os
import shutil
import uuid
from typing import List, Tuple, Union


class ExportTargetError(ValueError):
    """The chosen location can't be used. Something to tell the user."""


class FolderExists(ExportTargetError):
    """The song folder is already there and may only be replaced when the user said so."""


def _write(source: Union[bytes, str], target: str) -> None:
    """`source` is the content, or the path of a file to copy."""
    if isinstance(source, bytes):
        with open(target, "wb") as f:
            f.write(source)
    else:
        shutil.copyfile(source, target)


def _absolute_folder(path: str) -> str:
    if not path or not os.path.isabs(path):
        raise ExportTargetError("Choose a complete folder path.")
    if not os.path.isdir(path):
        raise ExportTargetError(f"The folder doesn't exist: {path}")
    return path


def export_folder(parent: str, folder_name: str, files: List[Tuple[str, Union[bytes, str]]],
                  replace: bool = False) -> str:
    """Write `files` (name, content or path) as `parent`/`folder_name`/ and return its path. Names are ours, from
    `safe_filename`. An existing folder raises FolderExists unless `replace`; it is only removed once the new one is
    complete."""
    _absolute_folder(parent)
    target = os.path.join(parent, folder_name)
    exists = os.path.lexists(target)
    if exists and not replace:
        raise FolderExists(f"{folder_name} already exists.")
    marker = uuid.uuid4().hex[:8]
    staging = os.path.join(parent, f".{folder_name}.export-{marker}")
    previous = os.path.join(parent, f".{folder_name}.previous-{marker}")
    try:
        os.makedirs(staging)
        for name, source in files:
            _write(source, os.path.join(staging, name))
        if exists:
            os.rename(target, previous)
        try:
            os.rename(staging, target)
        except OSError:
            if exists:
                os.rename(previous, target)
            raise
    except OSError as e:
        raise ExportTargetError(f"Couldn't write the song folder: {e}") from e
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if exists:
        shutil.rmtree(previous, ignore_errors=True)
    return target


def export_file(path: str, source: Union[bytes, str]) -> str:
    """Write one file to `path`, the location the save dialog returned (it has asked about overwriting)."""
    if not path or not os.path.isabs(path):
        raise ExportTargetError("Choose a complete file path.")
    _absolute_folder(os.path.dirname(path))
    partial = f"{path}.{uuid.uuid4().hex[:8]}.part"
    try:
        _write(source, partial)
        os.replace(partial, path)
    except OSError as e:
        raise ExportTargetError(f"Couldn't save the file: {e}") from e
    finally:
        if os.path.exists(partial):
            os.remove(partial)
    return path
