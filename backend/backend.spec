# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Ultrastar Creator backend.

Build command (from project root):
    pyinstaller backend/backend.spec

The output binary is placed in dist/backend (or dist/backend.app on macOS).
The GitHub Actions workflow renames it to backend-{target_triple} and copies it
to frontend/src-tauri/binaries/ before running `npm run tauri build`.
"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files, copy_metadata

block_cipher = None

# ── Collect packages that use dynamic/lazy imports ───────────────────────────
datas = []
binaries = []
hiddenimports = []

# ── Package metadata required by importlib.metadata.version() at runtime ─────
# transformers/audio_utils.py calls importlib.metadata.version("torchcodec")
# at import time; without the dist-info directory this raises PackageNotFoundError.
for _meta_pkg in (
    'torchcodec', 'transformers', 'tokenizers', 'huggingface_hub',
    'whisperx', 'faster_whisper', 'pyannote.audio', 'pyannote.core',
    'speechbrain', 'torch', 'torchaudio', 'torchvision', 'Pillow',
):
    try:
        datas += copy_metadata(_meta_pkg)
    except Exception:
        pass

# fastapi + starlette (lots of lazy loading)
_d, _b, _h = collect_all('fastapi')
datas += _d; binaries += _b; hiddenimports += _h

_d, _b, _h = collect_all('starlette')
datas += _d; binaries += _b; hiddenimports += _h

# uvicorn
_d, _b, _h = collect_all('uvicorn')
datas += _d; binaries += _b; hiddenimports += _h

# librosa — heavily uses importlib/lazy imports
_d, _b, _h = collect_all('librosa')
datas += _d; binaries += _b; hiddenimports += _h

# numba + llvmlite (used by librosa)
_d, _b, _h = collect_all('numba')
datas += _d; binaries += _b; hiddenimports += _h

_d, _b, _h = collect_all('llvmlite')
datas += _d; binaries += _b; hiddenimports += _h

# scipy + numpy
_d, _b, _h = collect_all('scipy')
datas += _d; binaries += _b; hiddenimports += _h

# soundfile, audioread, soxr — librosa audio backends
for pkg in ('soundfile', 'audioread', 'soxr', 'cffi'):
    _d, _b, _h = collect_all(pkg)
    datas += _d; binaries += _b; hiddenimports += _h

# pyphen — loads data files at runtime
_d, _b, _h = collect_all('pyphen')
datas += _d; binaries += _b; hiddenimports += _h

# mido
_d, _b, _h = collect_all('mido')
datas += _d; binaries += _b; hiddenimports += _h

# pydantic
_d, _b, _h = collect_all('pydantic')
datas += _d; binaries += _b; hiddenimports += _h

# ── essentia (BPM detection) + its bundled SDL/ffmpeg dylibs ─────────────────
# essentia ships its own .dylibs folder (SDL 1.2, SDL2, libavcodec, …).
# PyInstaller only auto-discovers load-time dependencies, so libSDL2-2.0.0.dylib
# (loaded at runtime by SDL 1.2's dllinit constructor) is not bundled unless we
# explicitly add it.  We place all essentia dylibs in _MEIPASS root so the
# DYLD_LIBRARY_PATH that PyInstaller's bootloader sets to _MEIPASS makes them
# findable by dlopen() calls inside the native libraries.
try:
    import importlib.util as _ilu
    _essentia_spec = _ilu.find_spec('essentia')
    if _essentia_spec and _essentia_spec.origin:
        _essentia_dylib_dir = os.path.join(os.path.dirname(_essentia_spec.origin), '.dylibs')
        if os.path.isdir(_essentia_dylib_dir):
            import glob as _glob
            for _lib in _glob.glob(os.path.join(_essentia_dylib_dir, '*.dylib')):
                binaries += [(_lib, '.')]
    _d, _b, _h = collect_all('essentia')
    datas += _d; binaries += _b; hiddenimports += _h
except Exception as _e:
    print(f"[spec] essentia collection skipped: {_e}")

# ── Optional AI packages (only if installed) ──────────────────────────────────
for optional_pkg in ('torch', 'torchaudio', 'demucs', 'whisperx', 'whisper', 'pyannote', 'pyannote.audio', 'pyannote.core', 'pyannote.database', 'pyannote.metrics', 'pyannote.pipeline', 'asteroid_filterbanks', 'speechbrain', 'faster_whisper', 'PIL', 'torchvision', 'transformers', 'Pillow'):
    try:
        _d, _b, _h = collect_all(optional_pkg)
        datas += _d; binaries += _b; hiddenimports += _h
    except Exception:
        pass

# ── Explicitly add PIL .so extensions (collect_all misses them for Pillow) ───
import glob as _glob
import importlib.util as _ilu
_pil_spec = _ilu.find_spec('PIL')
if _pil_spec and _pil_spec.submodule_search_locations:
    _pil_dir = list(_pil_spec.submodule_search_locations)[0]
    for _so in _glob.glob(os.path.join(_pil_dir, '*.so')) + _glob.glob(os.path.join(_pil_dir, '*.dylib')):
        binaries += [(_so, 'PIL')]

# ── Explicit hidden imports that PyInstaller misses ───────────────────────────
hiddenimports += [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.loops.uvloop',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.protocols.websockets.wsproto_impl',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'multipart',
    'python_multipart',
    'email.mime.multipart',
    'email.mime.text',
    'librosa.core',
    'librosa.feature',
    'librosa.effects',
    'librosa.beat',
    'librosa.onset',
    'librosa.util',
    'librosa.filters',
    'scipy.signal',
    'scipy.interpolate',
    'scipy.ndimage',
    'sklearn',
    'sklearn.utils',
    'sklearn.neighbors',
    # PIL C extensions
    'PIL._imaging',
    'PIL._imagingcms',
    'PIL._imagingft',
    'PIL._imagingmath',
    'PIL._imagingmorph',
    'PIL._webp',
]

# ── Include the full backend source tree ──────────────────────────────────────
backend_dir = os.path.abspath('backend')

datas += [
    (os.path.join(backend_dir, 'services'), 'services'),
    (os.path.join(backend_dir, 'utils'), 'utils'),
    (os.path.join(backend_dir, 'workers'), 'workers'),
]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [os.path.join(backend_dir, 'main.py')],
    pathex=[backend_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PIL', 'IPython', 'jupyter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,   # Keep console so backend logs are visible
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='backend',
)
