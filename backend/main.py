"""Ultrastar Song Generator — FastAPI Backend Server.

Thin route layer. All processing logic lives in services/.
"""

import multiprocessing
# Must be called before any other code when frozen with PyInstaller on macOS.
# Prevents child processes (e.g. Demucs workers) from re-executing the full app.
multiprocessing.freeze_support()

import os
import sys


def _fix_frozen_path():
    """When running as a PyInstaller frozen binary the macOS GUI launch environment
    strips most of PATH (no /opt/homebrew/bin etc.).  WhisperX calls ffmpeg as a
    subprocess by name, so we need to make sure it's findable."""
    if not getattr(sys, 'frozen', False):
        return
    # 1. bundled ffmpeg extracted alongside our binary by PyInstaller
    if hasattr(sys, '_MEIPASS'):
        mei = sys._MEIPASS
        if os.path.isfile(os.path.join(mei, 'ffmpeg')):
            os.environ['PATH'] = mei + os.pathsep + os.environ.get('PATH', '')
            return
    # 2. common macOS install locations (Homebrew arm64, Homebrew x86, MacPorts)
    for d in ('/opt/homebrew/bin', '/usr/local/bin', '/opt/local/bin'):
        if os.path.isfile(os.path.join(d, 'ffmpeg')):
            os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')
            return


_fix_frozen_path()
import time
import json
import uuid
import shutil
import tempfile
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from utils.logger import log, log_step
from utils.error_handler import (
    global_exception_handler,
    service_exception_handler,
    ServiceError,
)

# ────────────────────────────────────────────────────────────
# App setup
# ────────────────────────────────────────────────────────────
app = FastAPI(title="Ultrastar Song Generator", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "tauri://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(ServiceError, service_exception_handler)

# Directories — use persistent user data dir when running as frozen sidecar,
# so sessions/uploads survive backend restarts between app launches.
def _user_data_dir() -> str:
    """Return a persistent data directory that survives PyInstaller temp extraction."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller sidecar — store data in ~/Library/Application Support/com.ultrastar.creator
        base = os.path.expanduser("~/Library/Application Support/com.ultrastar.creator")
    else:
        # Dev mode — store alongside source files as before
        base = os.path.dirname(__file__)
    return base

_DATA_DIR = _user_data_dir()
DOWNLOADS_DIR = os.path.join(_DATA_DIR, "downloads")
CORRECTIONS_DIR = os.path.join(_DATA_DIR, "corrections")
UPLOAD_DIR = os.path.join(_DATA_DIR, "uploads")
REFERENCE_DIR = os.path.join(os.path.dirname(__file__), "reference_songs")
SESSIONS_DIR = os.path.join(_DATA_DIR, "sessions")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(CORRECTIONS_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REFERENCE_DIR, exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)

# In-memory session store
sessions: dict = {}


def save_session(session_id: str):
    """Persist a session to disk as JSON."""
    session = sessions.get(session_id)
    if not session:
        return
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session, f, default=str)
    except Exception as e:
        log_step("PERSIST", f"Failed to save session {session_id}: {e}")


def safe_json(data):
    """Round-trip through JSON with default=str to sanitize numpy types etc."""
    return json.loads(json.dumps(data, default=str))


def load_sessions():
    """Load all sessions from disk on startup."""
    count = 0
    for fname in os.listdir(SESSIONS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                session = json.load(f)
            sid = session.get("id", fname.replace(".json", ""))
            sessions[sid] = session
            count += 1
        except Exception as e:
            log_step("PERSIST", f"Failed to load {fname}: {e}")
    if count:
        log_step("PERSIST", f"Restored {count} sessions from disk")


# Load saved sessions on import
load_sessions()


# ────────────────────────────────────────────────────────────
# Health check
# ────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    from services.vocal_separation import DEMUCS_AVAILABLE
    
    return {
        "status": "ok",
        "version": "2.0.0",
        "models": {
            "pitch": "PYIN",
            "alignment": "WhisperX",
            "demucs": DEMUCS_AVAILABLE,
        }
    }


# ────────────────────────────────────────────────────────────
# First-run setup: model download status + SSE download stream
# ────────────────────────────────────────────────────────────

def _check_model_status() -> dict:
    """Return which AI models are already downloaded."""
    import shutil

    # ffmpeg
    ffmpeg_ok = shutil.which('ffmpeg') is not None

    # WhisperX / faster-whisper medium model
    whisperx_ok = False
    hf_cache = os.path.expanduser("~/.cache/huggingface/hub")
    faster_whisper_dir = os.path.join(hf_cache, "models--Systran--faster-whisper-medium")
    if os.path.isdir(faster_whisper_dir):
        # Check that there's at least one snapshot with the required model files
        snapshots = os.path.join(faster_whisper_dir, "snapshots")
        if os.path.isdir(snapshots):
            for snap in os.listdir(snapshots):
                snap_path = os.path.join(snapshots, snap)
                if os.path.isdir(snap_path):
                    # Require both config.json and model.bin to be present and non-empty
                    config_ok = os.path.isfile(os.path.join(snap_path, "config.json"))
                    model_ok = os.path.isfile(os.path.join(snap_path, "model.bin")) and \
                               os.path.getsize(os.path.join(snap_path, "model.bin")) > 100_000_000
                    if config_ok and model_ok:
                        whisperx_ok = True
                        break
    # Fallback: vanilla whisper medium
    if not whisperx_ok:
        vanilla_path = os.path.expanduser("~/.cache/whisper/medium.pt")
        whisperx_ok = os.path.isfile(vanilla_path) and os.path.getsize(vanilla_path) > 100_000_000

    # Demucs htdemucs
    demucs_ok = False
    torch_hub = os.path.expanduser("~/.cache/torch/hub/checkpoints")
    if os.path.isdir(torch_hub):
        for f in os.listdir(torch_hub):
            # htdemucs checkpoint has a known name prefix — only match actual .th files
            if f.endswith(".th") and (f.startswith("955717e8") or "htdemucs" in f.lower()):
                demucs_ok = True
                break

    return {
        "ffmpeg": ffmpeg_ok,
        "whisperx": whisperx_ok,
        "demucs": demucs_ok,
        "ready": ffmpeg_ok and whisperx_ok and demucs_ok,
    }


@app.get("/api/setup/status")
async def setup_status():
    """Check which AI models are already downloaded."""
    return _check_model_status()


@app.get("/api/setup/download")
async def setup_download():
    """SSE stream: download any missing AI models and report progress."""
    import asyncio

    async def event_stream():
        def send(type: str, step: str = "", message: str = "", done: bool = False, error: bool = False, percent: int = None):
            import json
            data = {"type": type, "step": step, "message": message}
            if percent is not None:
                data["percent"] = percent
            return f"data: {json.dumps(data)}\n\n"

        status = _check_model_status()

        # ── ffmpeg ──
        if not status["ffmpeg"]:
            yield send("progress", "ffmpeg", "ffmpeg not found — please install via Homebrew: brew install ffmpeg", error=True)
        else:
            yield send("done", "ffmpeg", "ffmpeg found")

        await asyncio.sleep(0.05)

        # ── WhisperX ──
        if not status["whisperx"]:
            yield send("progress", "whisperx", "Downloading WhisperX medium model (~1.5 GB)…", percent=0)
            await asyncio.sleep(0.05)
            try:
                from huggingface_hub import snapshot_download

                WHISPERX_TOTAL_BYTES = 1_528_000_000  # ~1.5 GB
                hf_dir = os.path.expanduser(
                    "~/.cache/huggingface/hub/models--Systran--faster-whisper-medium"
                )

                def _get_downloaded_bytes():
                    total = 0
                    for root, _, files in os.walk(hf_dir):
                        for f in files:
                            try:
                                total += os.path.getsize(os.path.join(root, f))
                            except OSError:
                                pass
                    return total

                loop = asyncio.get_event_loop()
                fut = loop.run_in_executor(
                    None,
                    lambda: snapshot_download("Systran/faster-whisper-medium")
                )
                while not fut.done():
                    await asyncio.sleep(0.5)
                    downloaded = _get_downloaded_bytes()
                    pct = min(99, int(downloaded * 100 / WHISPERX_TOTAL_BYTES))
                    mb_done = downloaded / 1_000_000
                    mb_total = WHISPERX_TOTAL_BYTES / 1_000_000
                    yield send("progress", "whisperx",
                               f"Downloading… {mb_done:.0f} / {mb_total:.0f} MB",
                               percent=pct)
                await fut  # re-raise any exception

                yield send("done", "whisperx", "WhisperX medium model ready")
            except ImportError as e:
                yield send("done", "whisperx", f"WhisperX not installed — {e}", error=True)
            except Exception as e:
                yield send("error", "whisperx", f"Download failed: {e}")
        else:
            yield send("done", "whisperx", "WhisperX medium model already downloaded")

        await asyncio.sleep(0.05)

        # ── Demucs ──
        if not status["demucs"]:
            yield send("progress", "demucs", "Downloading Demucs vocal separation model (~80 MB)…", percent=0)
            await asyncio.sleep(0.05)
            try:
                import torch

                DEMUCS_TOTAL_BYTES = 85_000_000  # ~80 MB
                torch_hub_dir = os.path.expanduser("~/.cache/torch/hub/checkpoints")

                def _get_demucs_bytes():
                    total = 0
                    if not os.path.isdir(torch_hub_dir):
                        return 0
                    for f in os.listdir(torch_hub_dir):
                        if f.endswith(".th") or f.endswith(".th.tmp"):
                            try:
                                total += os.path.getsize(os.path.join(torch_hub_dir, f))
                            except OSError:
                                pass
                    return total

                def _download_demucs():
                    from demucs.pretrained import get_model
                    get_model("htdemucs")

                loop = asyncio.get_event_loop()
                fut = loop.run_in_executor(None, _download_demucs)
                while not fut.done():
                    await asyncio.sleep(0.5)
                    downloaded = _get_demucs_bytes()
                    pct = min(99, int(downloaded * 100 / DEMUCS_TOTAL_BYTES))
                    mb_done = downloaded / 1_000_000
                    mb_total = DEMUCS_TOTAL_BYTES / 1_000_000
                    yield send("progress", "demucs",
                               f"Downloading… {mb_done:.0f} / {mb_total:.0f} MB",
                               percent=pct)
                await fut

                yield send("done", "demucs", "Demucs model ready")
            except ImportError:
                yield send("done", "demucs", "Demucs not installed — vocals must be provided manually", error=True)
            except Exception as e:
                yield send("error", "demucs", f"Download failed: {e}")
        else:
            yield send("done", "demucs", "Demucs model already downloaded")

        await asyncio.sleep(0.05)
        import json
        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ────────────────────────────────────────────────────────────
# Session management
# ────────────────────────────────────────────────────────────
@app.get("/api/sessions")
async def list_all_sessions():
    """List all sessions (for the launcher page)."""
    result = []
    for sid, s in sessions.items():
        has_result = s.get("result") is not None
        result.append({
            "id": sid,
            "artist": s.get("artist", "Unknown"),
            "title": s.get("title", "Untitled"),
            # If a result exists, always surface as generated regardless of raw status
            "status": "generated" if has_result else s.get("status", "unknown"),
            "created_at": s.get("created_at", 0),
            "has_result": has_result,
        })
    # Sort newest first
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return {"status": "ok", "sessions": result}


@app.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: str):
    """Delete a session and its files."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Remove session file
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(session_file):
        os.remove(session_file)

    # Remove upload directory if it exists
    upload_dir = os.path.join(UPLOAD_DIR, session_id)
    if os.path.isdir(upload_dir):
        shutil.rmtree(upload_dir, ignore_errors=True)

    # Remove generated files
    result = session.get("result", {})
    for key in ("txt_file", "midi_file", "summary_file", "corrected_txt_file"):
        fname = result.get(key) if isinstance(result, dict) else None
        if fname:
            fpath = os.path.join(DOWNLOADS_DIR, fname)
            if os.path.exists(fpath):
                os.remove(fpath)

    del sessions[session_id]
    log_step("SESSION", f"Deleted session {session_id}")
    return {"status": "ok"}


@app.post("/api/resume/{session_id}")
async def resume_specific_session(session_id: str):
    """Resume an existing session by ID (opens it without cloning)."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    vocal = session.get("vocal_audio")
    original = session.get("original_audio")
    any_audio = vocal or original
    if not any_audio or not os.path.exists(any_audio):
        raise HTTPException(status_code=404, detail="Audio files no longer exist")

    has_vocals = vocal is not None and os.path.exists(vocal)
    has_original = original is not None and os.path.exists(original)

    lyrics = session.get("lyrics", "")
    syllable_count = 0
    line_count = 0
    if session.get("parsed_lyrics"):
        syllable_count = sum(len(line) for line in session["parsed_lyrics"])
        line_count = len(session["parsed_lyrics"])

    # Use best available filename for display
    display_file = vocal if has_vocals else original
    display_filename = os.path.basename(display_file)

    return JSONResponse(safe_json({
        "status": "ok",
        "session_id": session_id,
        "filename": display_filename,
        "has_vocals": has_vocals,
        "has_original": has_original,
        "has_lyrics": bool(lyrics),
        "lyrics": lyrics,
        "artist": session.get("artist", "Unknown Artist"),
        "title": session.get("title", "Unknown Song"),
        "language": session.get("language", "en"),
        "syllable_count": syllable_count,
        "line_count": line_count,
        "has_result": session.get("result") is not None,
        "result": session.get("result"),
    }))


@app.post("/api/import")
async def import_ultrastar(
    txt_file: UploadFile = File(...),
    audio_file: UploadFile = File(None),
    vocal_file: UploadFile = File(None),
):
    """Import an existing Ultrastar song (.txt + optional audio files) into a new session.

    Accepts:
        txt_file: Required — Ultrastar .txt with notes
        audio_file: Optional — full mix audio
        vocal_file: Optional — isolated vocals audio
    At least one audio file must be provided.

    Parses the Ultrastar .txt to extract notes, BPM, GAP, and metadata.
    Creates a session with a pre-populated result so the editor opens directly.
    """
    from services.reference_comparison import parse_ultrastar_file
    import librosa

    if not audio_file and not vocal_file:
        raise HTTPException(status_code=400, detail="At least one audio file is required (mix or vocals)")

    # Read .txt content
    txt_content = (await txt_file.read()).decode("utf-8", errors="replace")
    parsed = parse_ultrastar_file(txt_content)

    if not parsed["notes"]:
        # Give a specific error depending on what's missing
        has_headers = bool(parsed["headers"])
        has_bpm = parsed["bpm"] > 0
        if not has_headers:
            raise HTTPException(status_code=400, detail="Not a valid Ultrastar file — no #TITLE, #BPM or other headers found")
        elif not has_bpm:
            raise HTTPException(status_code=400, detail="Ultrastar file has no #BPM header — cannot parse notes")
        else:
            raise HTTPException(status_code=400, detail="No notes found in Ultrastar file (expected lines starting with : or * or F:)")

    bpm = parsed["bpm"]
    gap_ms = int(parsed["gap"])
    headers = parsed["headers"]

    artist = headers.get("ARTIST", "Unknown Artist")
    title = headers.get("TITLE", "Unknown Song")
    language = headers.get("LANGUAGE", "en")

    # Save audio files
    session_id = str(uuid.uuid4())[:8]
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    original_path = None
    vocal_path = None
    duration_path = None  # whichever audio we use to measure duration

    if audio_file:
        original_path = os.path.join(session_dir, audio_file.filename)
        audio_bytes = await audio_file.read()
        with open(original_path, "wb") as f:
            f.write(audio_bytes)
        duration_path = original_path

    if vocal_file:
        vocal_path = os.path.join(session_dir, vocal_file.filename)
        vocal_bytes = await vocal_file.read()
        with open(vocal_path, "wb") as f:
            f.write(vocal_bytes)
        if not duration_path:
            duration_path = vocal_path

    # Get audio duration
    try:
        audio_duration = librosa.get_duration(filename=duration_path)
    except Exception:
        audio_duration = 0.0

    # Build syllable_timings from parsed notes (convert beats to seconds)
    syllable_timings = []
    for note in parsed["notes"]:
        start_sec = gap_ms / 1000.0 + note["start_beat"] * 15.0 / bpm
        end_sec = gap_ms / 1000.0 + (note["start_beat"] + note["duration"]) * 15.0 / bpm
        syllable_timings.append({
            "syllable": note["syllable"],
            "start": round(start_sec, 4),
            "end": round(end_sec, 4),
            "midi_note": note["pitch"],
            "confidence": 1.0,
            "method": "imported",
            "is_rap": note.get("is_rap", False),
        })

    # Save the .txt to downloads
    timestamp = int(time.time())
    txt_filename = f"song_{timestamp}.txt"
    txt_path = os.path.join(DOWNLOADS_DIR, txt_filename)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_content)

    # Create session with result — store None for missing files, not aliases
    session = {
        "id": session_id,
        "original_audio": original_path,
        "vocal_audio": vocal_path,
        "lyrics": "",
        "artist": artist,
        "title": title,
        "language": language,
        "status": "generated",
        "created_at": time.time(),
        "imported": True,
        "result": {
            "txt_file": txt_filename,
            "midi_file": None,
            "summary_file": None,
            "bpm": bpm,
            "gap_ms": gap_ms,
            "syllable_count": len(syllable_timings),
            "audio_duration": audio_duration,
            "pitch_method": "imported",
            "alignment_method": "imported",
            "elapsed_seconds": 0,
            "syllable_timings": syllable_timings,
            "ultrastar_content": txt_content,
        },
    }
    sessions[session_id] = session
    save_session(session_id)

    has_vocals = vocal_path is not None
    has_original = original_path is not None
    # Use the first available filename for display
    display_filename = (audio_file.filename if audio_file else vocal_file.filename)

    log_step("IMPORT", f"Imported '{artist} - {title}' as session {session_id} "
             f"({len(syllable_timings)} notes, BPM={bpm}, GAP={gap_ms}ms, "
             f"vocals={'yes' if has_vocals else 'no'}, mix={'yes' if has_original else 'no'})")

    return {
        "status": "ok",
        "session_id": session_id,
        "filename": display_filename,
        "artist": artist,
        "title": title,
        "language": language,
        "syllable_count": len(syllable_timings),
        "line_count": len(parsed["breaks"]) + 1,
        "bpm": bpm,
        "gap_ms": gap_ms,
        "has_lyrics": True,
        "lyrics": "",
        "has_result": True,
        "has_vocals": has_vocals,
        "has_original": has_original,
        "result": session["result"],
    }


# ────────────────────────────────────────────────────────────
# Step 1: Upload & Vocal Extraction
# ────────────────────────────────────────────────────────────
@app.post("/api/new-session")
async def new_session():
    """Create a blank session (no audio). Used when uploading vocals without a mix."""
    session_id = str(uuid.uuid4())[:8]
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    sessions[session_id] = {
        "id": session_id,
        "original_audio": None,
        "vocal_audio": None,
        "lyrics": None,
        "status": "new",
        "created_at": time.time(),
    }
    save_session(session_id)
    log_step("UPLOAD", f"Session {session_id}: created blank session")
    return {"status": "ok", "session_id": session_id}


@app.post("/api/upload")
async def upload_audio(audio: UploadFile = File(...)):
    """Upload an audio file (MP3/WAV). Returns a session ID."""
    session_id = str(uuid.uuid4())[:8]
    
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    
    file_path = os.path.join(session_dir, audio.filename)
    with open(file_path, "wb") as f:
        content = await audio.read()
        f.write(content)
    
    sessions[session_id] = {
        "id": session_id,
        "original_audio": file_path,
        "vocal_audio": None,
        "lyrics": None,
        "status": "uploaded",
        "created_at": time.time(),
    }
    
    log_step("UPLOAD", f"Session {session_id}: uploaded {audio.filename} ({len(content)} bytes)")
    save_session(session_id)
    
    return {
        "status": "ok",
        "session_id": session_id,
        "filename": audio.filename,
        "size": len(content),
    }


@app.post("/api/cancel-extract/{session_id}")
async def cancel_extract(session_id: str):
    """Signal the vocal extraction to abort (HTTP-level; Demucs runs to completion internally)."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["extract_cancelled"] = True
    return {"status": "ok", "message": "Extraction cancellation requested"}


@app.post("/api/extract-vocals/{session_id}")
async def extract_vocals(session_id: str):
    """Run Demucs vocal separation on uploaded audio."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    from services.vocal_separation import separate_vocals, DEMUCS_AVAILABLE
    
    if not DEMUCS_AVAILABLE:
        raise ServiceError("Demucs not installed", "Install with: pip install demucs", 503)
    
    session["extract_cancelled"] = False
    try:
        session["status"] = "extracting_vocals"
        output_dir = os.path.join(UPLOAD_DIR, session_id)
        audio_path = session["original_audio"]

        # Run Demucs in a thread so the event loop (and other requests) stay responsive
        import asyncio
        loop = asyncio.get_event_loop()
        vocal_path = await loop.run_in_executor(None, separate_vocals, audio_path, output_dir)

        if session.get("extract_cancelled"):
            raise HTTPException(status_code=499, detail="Extraction cancelled")

        session["vocal_audio"] = vocal_path
        session["status"] = "vocals_extracted"
        save_session(session_id)
        
        return {
            "status": "ok",
            "session_id": session_id,
            "vocal_url": f"/api/preview-audio/{session_id}/vocals",
        }
    except HTTPException:
        raise
    except Exception as e:
        session["status"] = "extraction_failed"
        save_session(session_id)
        raise ServiceError("Vocal extraction failed", str(e))


@app.get("/api/extract-vocals-stream/{session_id}")
async def extract_vocals_stream(session_id: str):
    """SSE stream for vocal extraction — emits phase messages and elapsed-time heartbeats."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from services.vocal_separation import separate_vocals, DEMUCS_AVAILABLE
    import asyncio

    def _send(phase: str, message: str = "", **kwargs) -> str:
        data = {"phase": phase, "message": message, **kwargs}
        return f"data: {json.dumps(data)}\n\n"

    async def event_generator():
        if not DEMUCS_AVAILABLE:
            yield _send("error", "Demucs not installed. Install with: pip install demucs")
            return

        if not session.get("original_audio"):
            yield _send("error", "No audio file uploaded")
            return

        yield _send("loading", "Loading Demucs model…")
        await asyncio.sleep(0.1)

        session["extract_cancelled"] = False
        session["status"] = "extracting_vocals"

        loop = asyncio.get_event_loop()
        output_dir = os.path.join(UPLOAD_DIR, session_id)
        audio_path = session["original_audio"]

        # Launch demucs in a thread pool so the event loop stays responsive
        executor_future = loop.run_in_executor(None, separate_vocals, audio_path, output_dir)

        yield _send("separating", "Separating vocals — may take 1–5 minutes depending on song length…")

        # Send heartbeats while waiting
        start = loop.time()
        while not executor_future.done():
            if session.get("extract_cancelled"):
                executor_future.cancel()
                yield _send("cancelled", "Extraction cancelled")
                return
            elapsed = int(loop.time() - start)
            yield _send("heartbeat", "", elapsed=elapsed)
            try:
                await asyncio.wait_for(asyncio.shield(executor_future), timeout=3.0)
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

        if session.get("extract_cancelled") or executor_future.cancelled():
            yield _send("cancelled", "Extraction cancelled")
            return

        exc = executor_future.exception() if not executor_future.cancelled() else RuntimeError("cancelled")
        if exc:
            session["status"] = "extraction_failed"
            save_session(session_id)
            yield _send("error", str(exc))
            return

        vocal_path = executor_future.result()
        session["vocal_audio"] = vocal_path
        session["status"] = "vocals_extracted"
        save_session(session_id)
        log_step("SEPARATE", f"Session {session_id}: vocals extracted via SSE stream")
        yield _send("done", "Vocals extracted successfully!", vocal_url=f"/api/preview-audio/{session_id}/vocals")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/upload-vocals/{session_id}")
async def upload_corrected_vocals(session_id: str, vocals: UploadFile = File(...)):
    """Upload manually corrected vocals (skip or replace Demucs output)."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    vocal_path = os.path.join(session_dir, f"vocals_{vocals.filename}")
    
    with open(vocal_path, "wb") as f:
        content = await vocals.read()
        f.write(content)
    
    session["vocal_audio"] = vocal_path
    session["status"] = "vocals_extracted"
    
    log_step("UPLOAD", f"Session {session_id}: uploaded corrected vocals ({len(content)} bytes)")
    save_session(session_id)
    
    return {"status": "ok", "session_id": session_id}


@app.post("/api/upload-mix/{session_id}")
async def upload_mix_audio(session_id: str, audio: UploadFile = File(...)):
    """Upload or replace the full mix audio for an existing session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    file_path = os.path.join(session_dir, audio.filename)

    with open(file_path, "wb") as f:
        content = await audio.read()
        f.write(content)

    session["original_audio"] = file_path
    session["filename"] = audio.filename

    log_step("UPLOAD", f"Session {session_id}: replaced mix audio with {audio.filename} ({len(content)} bytes)")
    save_session(session_id)

    return {"status": "ok", "session_id": session_id, "filename": audio.filename}


@app.delete("/api/delete-audio/{session_id}/{audio_type}")
async def delete_audio(session_id: str, audio_type: str):
    """Delete an audio file (original or vocals) from a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if audio_type == "original":
        path = session.get("original_audio")
        if path and os.path.exists(path):
            os.remove(path)
        session["original_audio"] = None
        log_step("DELETE", f"Session {session_id}: deleted original audio")
    elif audio_type == "vocals":
        path = session.get("vocal_audio")
        if path and os.path.exists(path):
            os.remove(path)
        session["vocal_audio"] = None
        session["status"] = "uploaded" if session.get("original_audio") else "created"
        log_step("DELETE", f"Session {session_id}: deleted vocals")
    else:
        raise HTTPException(status_code=400, detail="Invalid audio type. Use 'original' or 'vocals'.")

    save_session(session_id)
    return {
        "status": "ok",
        "has_original": session.get("original_audio") is not None,
        "has_vocals": session.get("vocal_audio") is not None,
    }


@app.get("/api/preview-audio/{session_id}/{audio_type}")
async def preview_audio(session_id: str, audio_type: str, request: Request):
    """Stream audio for preview with range request support for seeking."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if audio_type == "original":
        path = session.get("original_audio")
    elif audio_type == "vocals":
        path = session.get("vocal_audio")
    else:
        raise HTTPException(status_code=400, detail="Invalid audio type")
    
    if not path or not os.path.exists(path):
        # Try to find the file with different extension (e.g. .wav vs .mp3)
        if path:
            base = os.path.splitext(path)[0]
            for ext in ['.mp3', '.wav', '.flac', '.ogg']:
                alt = base + ext
                if os.path.exists(alt):
                    path = alt
                    # Update session so future requests use the correct path
                    if audio_type == "vocals":
                        session["vocal_audio"] = path
                    elif audio_type == "original":
                        session["original_audio"] = path
                    log_step("PREVIEW", f"Found {audio_type} at alternate path: {path}")
                    break
            else:
                raise HTTPException(status_code=404, detail=f"Audio file not found: {os.path.basename(path)}")
        else:
            raise HTTPException(status_code=404, detail="Audio file not found")
    
    file_size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    content_type = {
        '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
        '.flac': 'audio/flac', '.ogg': 'audio/ogg',
    }.get(ext, 'application/octet-stream')
    
    # Handle range requests for seeking support
    range_header = request.headers.get('range')
    if range_header:
        # Parse "bytes=start-end"
        range_str = range_header.replace('bytes=', '')
        parts = range_str.split('-')
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1
        
        def iter_range():
            with open(path, 'rb') as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        
        return StreamingResponse(
            iter_range(),
            status_code=206,
            headers={
                'Content-Range': f'bytes {start}-{end}/{file_size}',
                'Accept-Ranges': 'bytes',
                'Content-Length': str(length),
                'Content-Type': content_type,
            }
        )
    
    # No range — return full file with accept-ranges header
    # Build a user-friendly download name from artist/title
    artist = session.get("artist", "").strip()
    title_name = session.get("title", "").strip()
    if artist and title_name:
        base = f"{artist} - {title_name}"
    elif title_name:
        base = title_name
    elif artist:
        base = artist
    else:
        base = "Untitled Song"
    suffix = " [Vocals]" if audio_type == "vocals" else ""
    download_name = base + suffix + ext
    
    return FileResponse(path, filename=download_name, headers={'Accept-Ranges': 'bytes'})


# ────────────────────────────────────────────────────────────
# Step 2a: WhisperX ASR Transcription + Forced Alignment
# ────────────────────────────────────────────────────────────
@app.post("/api/cancel-transcribe/{session_id}")
async def cancel_transcribe(session_id: str):
    """Signal the transcription to abort."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["transcribe_cancelled"] = True
    return {"status": "ok", "message": "Transcription cancellation requested"}


@app.post("/api/transcribe/{session_id}")
def transcribe_audio(session_id: str, language: str = Form("en")):
    """Transcribe vocal audio using WhisperX with phoneme-level forced alignment.
    
    WhisperX provides ~50ms word boundaries (vs ~200ms for vanilla Whisper)
    by running wav2vec2-based forced alignment after initial transcription.
    Falls back to vanilla Whisper if WhisperX is unavailable.
    
    Returns the transcribed text with line breaks at phrase boundaries.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Find the vocal audio file
    audio_path = session.get("vocal_audio") or session.get("original_audio")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="No audio file found. Upload audio first.")
    
    # Map short language codes to Whisper language names
    WHISPER_LANG_MAP = {
        "en": "English", "de": "German", "fr": "French",
        "es": "Spanish", "it": "Italian", "pt": "Portuguese",
        "nl": "Dutch", "ja": "Japanese", "ko": "Korean",
        "zh": "Chinese",
    }
    
    log_step("WHISPER", f"Transcribing {os.path.basename(audio_path)} (lang={language})...")
    
    # --- Try WhisperX first (phoneme-level forced alignment) ---
    try:
        import whisperx
        import torch
        
        device = "cpu"  # MPS has limited WhisperX support
        compute_type = "int8"  # Efficient for CPU
        model_name = "medium"
        
        log_step("WHISPERX", f"Loading WhisperX model '{model_name}' (device={device})...")
        model = whisperx.load_model(model_name, device, compute_type=compute_type)
        
        # Load audio at WhisperX's expected sample rate
        log_step("WHISPERX", "Loading audio...")
        audio = whisperx.load_audio(audio_path)
        
        # Step 1: Initial transcription (same quality as vanilla Whisper)
        log_step("WHISPERX", "Running transcription...")
        result = model.transcribe(audio, batch_size=4, language=language)
        
        # Step 2: Forced alignment with wav2vec2 for precise word boundaries
        log_step("WHISPERX", "Running forced alignment (wav2vec2)...")
        align_model, align_metadata = whisperx.load_align_model(
            language_code=language, device=device
        )
        result = whisperx.align(
            result["segments"],
            align_model,
            align_metadata,
            audio,
            device,
            return_char_alignments=True,  # character-level for syllable distribution
        )
        
        # Free alignment model to save memory
        del align_model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Extract word-level and char-level timestamps
        lines = []
        all_words = []
        all_chars = []
        
        for segment in result.get("segments", []):
            text = segment.get("text", "").strip()
            if text:
                lines.append(text)
            
            # Word-level timestamps (phoneme-aligned, ~50ms accuracy)
            for w in segment.get("words", []):
                word_text = w.get("word", "").strip()
                if not word_text:
                    continue
                start = w.get("start")
                end = w.get("end")
                if start is None or end is None:
                    continue
                all_words.append({
                    "word": word_text,
                    "start": round(start, 4),
                    "end": round(end, 4),
                    "score": round(w.get("score", 0.0), 4),
                })
            
            # Character-level timestamps (for precise syllable splitting)
            for c in segment.get("chars", []):
                char_text = c.get("char", "")
                start = c.get("start")
                end = c.get("end")
                if start is None or end is None:
                    continue
                all_chars.append({
                    "char": char_text,
                    "start": round(start, 4),
                    "end": round(end, 4),
                    "score": round(c.get("score", 0.0), 4),
                })
        
        transcribed_text = "\n".join(lines)
        
        # Save to session
        session["whisper_words"] = all_words
        session["whisper_chars"] = all_chars
        session["whisper_method"] = "whisperx"
        save_session(session_id)
        
        # Debug output
        debug_dir = os.path.join(os.path.dirname(__file__), 'downloads')
        try:
            debug_path = os.path.join(debug_dir, 'whisper_words.txt')
            with open(debug_path, 'w') as f:
                f.write(f"WHISPERX WORD TIMESTAMPS ({len(all_words)} words, {len(all_chars)} chars)\n{'='*60}\n\n")
                f.write("WORDS:\n")
                for w in all_words:
                    dur = w['end'] - w['start']
                    f.write(f"  {w['start']:8.3f} - {w['end']:8.3f}  ({dur:5.3f}s)  score={w['score']:.2f}  {w['word']}\n")
                f.write(f"\nCHARACTERS ({len(all_chars)}):\n")
                for c in all_chars[:200]:  # First 200 chars
                    dur = c['end'] - c['start']
                    f.write(f"  {c['start']:8.3f} - {c['end']:8.3f}  ({dur:5.3f}s)  '{c['char']}'\n")
                if len(all_chars) > 200:
                    f.write(f"  ... and {len(all_chars) - 200} more chars\n")
            log_step("WHISPERX", f"Timestamps saved: {len(all_words)} words, {len(all_chars)} chars")
        except Exception:
            pass
        
        word_count = sum(len(line.split()) for line in lines)
        
        log_step("WHISPERX", f"Transcription complete: {len(lines)} lines, {word_count} words")
        log_step("WHISPERX", f"  Alignment: {len(all_words)} words, {len(all_chars)} char timestamps")
        if all_words:
            avg_score = sum(w['score'] for w in all_words) / len(all_words)
            log_step("WHISPERX", f"  Avg alignment score: {avg_score:.3f}")
        if lines:
            log_step("WHISPERX", f"  First line: '{lines[0][:80]}'")
            log_step("WHISPERX", f"  Last line:  '{lines[-1][:80]}'")
        
        return JSONResponse({
            "text": transcribed_text,
            "lines": len(lines),
            "words": word_count,
            "language": language,
            "language_name": WHISPER_LANG_MAP.get(language, language),
            "model": f"whisperx-{model_name}",
            "alignment": "wav2vec2",
            "char_timestamps": len(all_chars),
        })
    
    except ImportError:
        log_step("WHISPER", "WhisperX not available, falling back to vanilla Whisper...")
    except Exception as e:
        import traceback
        log_step("WHISPERX", f"WhisperX failed: {e}, falling back to vanilla Whisper")
        log_step("WHISPERX", traceback.format_exc())
    
    # --- Fallback: vanilla Whisper ---
    try:
        import whisper
        
        model_name = "medium"
        log_step("WHISPER", f"Loading Whisper model '{model_name}'...")
        model = whisper.load_model(model_name)
        
        log_step("WHISPER", "Running transcription...")
        result = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
        )
        
        lines = []
        all_words = []
        for segment in result.get("segments", []):
            text = segment.get("text", "").strip()
            if text:
                lines.append(text)
            for w in segment.get("words", []):
                all_words.append({
                    "word": w.get("word", "").strip(),
                    "start": round(w.get("start", 0), 4),
                    "end": round(w.get("end", 0), 4),
                })
        
        transcribed_text = "\n".join(lines)
        session["whisper_words"] = all_words
        session["whisper_chars"] = []  # No char-level from vanilla Whisper
        session["whisper_method"] = "whisper"
        save_session(session_id)
        
        # Debug output
        debug_dir = os.path.join(os.path.dirname(__file__), 'downloads')
        try:
            debug_path = os.path.join(debug_dir, 'whisper_words.txt')
            with open(debug_path, 'w') as f:
                f.write(f"WHISPER (fallback) WORD TIMESTAMPS ({len(all_words)} words)\n{'='*60}\n\n")
                for w in all_words:
                    dur = w['end'] - w['start']
                    f.write(f"  {w['start']:8.3f} - {w['end']:8.3f}  ({dur:5.3f}s)  {w['word']}\n")
            log_step("WHISPER", f"Word timestamps saved: {len(all_words)} words")
        except Exception:
            pass
        
        word_count = sum(len(line.split()) for line in lines)
        log_step("WHISPER", f"Fallback transcription complete: {len(lines)} lines, {word_count} words")
        
        return JSONResponse({
            "text": transcribed_text,
            "lines": len(lines),
            "words": word_count,
            "language": language,
            "language_name": WHISPER_LANG_MAP.get(language, language),
            "model": f"whisper-{model_name}",
            "alignment": "whisper-native",
            "char_timestamps": 0,
        })
        
    except ImportError:
        raise HTTPException(status_code=500, detail="Neither WhisperX nor Whisper installed. Run: pip install whisperx")
    except Exception as e:
        import traceback
        log_step("WHISPER", f"Transcription failed: {e}")
        log_step("WHISPER", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


# ────────────────────────────────────────────────────────────
# Step 2b: Lyrics Input
# ────────────────────────────────────────────────────────────
@app.post("/api/lyrics/{session_id}")
async def submit_lyrics(
    session_id: str,
    lyrics: str = Form(...),
    artist: str = Form("Unknown Artist"),
    title: str = Form("Unknown Song"),
    language: str = Form("en"),
):
    """Submit lyrics and metadata for processing."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    from services.alignment_whisper import parse_lyrics
    
    parsed = parse_lyrics(lyrics)
    flat_count = sum(len(line) for line in parsed)
    
    session["lyrics"] = lyrics
    session["artist"] = artist
    session["title"] = title
    session["language"] = language
    session["parsed_lyrics"] = parsed
    session["status"] = "lyrics_submitted"
    save_session(session_id)
    
    log_step("LYRICS", f"Session {session_id}: {flat_count} syllables, {len(parsed)} lines")
    
    return {
        "status": "ok",
        "session_id": session_id,
        "syllable_count": flat_count,
        "line_count": len(parsed),
        "preview": [
            {"line": i + 1, "syllables": [s["text"] for s in line]}
            for i, line in enumerate(parsed)
        ],
    }


@app.post("/api/hyphenate")
async def hyphenate_lyrics(
    lyrics: str = Form(...),
    language: str = Form("en"),
):
    """Auto-hyphenate plain lyrics using pyphen."""
    from services.hyphenation import hyphenate_lyrics as do_hyphenate, PYPHEN_AVAILABLE
    
    result = do_hyphenate(lyrics, language)
    return {
        "status": "ok",
        "pyphen_available": PYPHEN_AVAILABLE,
        **result,
    }


# ────────────────────────────────────────────────────────────
# Test data endpoints (development mode)
# ────────────────────────────────────────────────────────────
@app.get("/api/test-lyrics")
async def get_test_lyrics():
    """Load test lyrics from frontendTest/lyrics.txt."""
    project_root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(project_root, "frontendTest", "lyrics.txt")
    
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Test lyrics not found")
    
    with open(path, "r") as f:
        return {"lyrics": f.read()}


@app.get("/api/test-vocal")
async def get_test_vocal():
    """Serve test vocal audio from frontendTest/test_vocal.wav."""
    project_root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(project_root, "frontendTest", "test_vocal.wav")
    
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Test vocal not found")
    
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/resume-last")
async def resume_last_session():
    """Create a new session cloned from the most recent one.
    
    Reuses audio files, whisper word timestamps, lyrics, and metadata
    so you can skip upload + transcription when re-generating.
    """
    if not sessions:
        raise HTTPException(status_code=404, detail="No previous sessions found")
    
    # Find the most recent session
    last = max(sessions.values(), key=lambda s: s.get("created_at", 0))
    
    # Verify audio still exists
    vocal = last.get("vocal_audio")
    original = last.get("original_audio")
    if not vocal or not os.path.exists(vocal):
        raise HTTPException(status_code=404, detail="Last session's audio files no longer exist")
    
    # Create new session reusing the same files
    session_id = str(uuid.uuid4())[:8]
    new_session = {
        "id": session_id,
        "original_audio": original,
        "vocal_audio": vocal,
        "lyrics": last.get("lyrics"),
        "artist": last.get("artist", "Unknown Artist"),
        "title": last.get("title", "Unknown Song"),
        "language": last.get("language", "en"),
        "whisper_words": last.get("whisper_words", []),
        "whisper_chars": last.get("whisper_chars", []),
        "whisper_method": last.get("whisper_method", "whisper"),
        "parsed_lyrics": last.get("parsed_lyrics"),
        "reference_content": last.get("reference_content"),
        "reference_filename": last.get("reference_filename"),
        "result": last.get("result"),  # carry over generation result
        "status": "generated" if last.get("result") else ("lyrics_submitted" if last.get("lyrics") else "vocals_extracted"),
        "created_at": time.time(),
    }
    sessions[session_id] = new_session
    save_session(session_id)

    lyrics = last.get("lyrics", "")
    syllable_count = 0
    line_count = 0
    if new_session.get("parsed_lyrics"):
        syllable_count = sum(len(line) for line in new_session["parsed_lyrics"])
        line_count = len(new_session["parsed_lyrics"])
    
    log_step("RESUME", f"New session {session_id} from {last['id']} "
             f"(vocals={os.path.basename(vocal)}, "
             f"{len(new_session.get('whisper_words', []))} whisper words, "
             f"{syllable_count} syllables)")
    
    # Build reference info if available
    reference_info = None
    ref_content = new_session.get("reference_content")
    ref_filename = new_session.get("reference_filename")
    if ref_content:
        try:
            from services.reference_comparison import parse_ultrastar_file
            parsed_ref = parse_ultrastar_file(ref_content)
            reference_info = {
                "filename": ref_filename,
                "notes_count": len(parsed_ref["notes"]),
                "bpm": parsed_ref["bpm"],
                "gap": parsed_ref["gap"],
            }
        except Exception:
            reference_info = {"filename": ref_filename, "notes_count": 0, "bpm": 0, "gap": 0}

    return {
        "status": "ok",
        "session_id": session_id,
        "from_session": last["id"],
        "filename": os.path.basename(vocal),
        "has_lyrics": bool(lyrics),
        "lyrics": lyrics,
        "artist": new_session["artist"],
        "title": new_session["title"],
        "language": new_session["language"],
        "syllable_count": syllable_count,
        "line_count": line_count,
        "whisper_words": len(new_session.get("whisper_words", [])),
        "reference": reference_info,
        "has_result": last.get("result") is not None,
        "has_vocals": vocal is not None and os.path.exists(vocal),
        "has_original": original is not None and os.path.exists(original),
    }


@app.post("/api/load-test-session")
async def load_test_session():
    """Create a session pre-loaded with test files (dev convenience)."""
    session_id = f"test-{str(uuid.uuid4())[:4]}"
    project_root = os.path.dirname(os.path.dirname(__file__))
    
    vocal_path = os.path.join(project_root, "frontendTest", "test_vocal.wav")
    lyrics_path = os.path.join(project_root, "frontendTest", "lyrics.txt")
    
    if not os.path.exists(vocal_path) or not os.path.exists(lyrics_path):
        raise HTTPException(status_code=404, detail="Test files not found")
    
    with open(lyrics_path, "r") as f:
        lyrics = f.read()
    
    from services.alignment_whisper import parse_lyrics
    parsed = parse_lyrics(lyrics)
    
    sessions[session_id] = {
        "id": session_id,
        "original_audio": vocal_path,
        "vocal_audio": vocal_path,
        "lyrics": lyrics,
        "artist": "U2",
        "title": "Beautiful Day",
        "language": "en",
        "parsed_lyrics": parsed,
        "status": "lyrics_submitted",
        "created_at": time.time(),
    }
    
    flat_count = sum(len(line) for line in parsed)
    log_step("TEST", f"Test session {session_id}: {flat_count} syllables loaded")
    
    return {
        "status": "ok",
        "session_id": session_id,
        "artist": "U2",
        "title": "Beautiful Day",
        "syllable_count": flat_count,
        "line_count": len(parsed),
    }


# ────────────────────────────────────────────────────────────
# Step 3: Generate Ultrastar Files
# ────────────────────────────────────────────────────────────
@app.post("/api/cancel/{session_id}")
async def cancel_generation(session_id: str):
    """Signal the generation pipeline to abort."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["cancelled"] = True
    return {"status": "ok", "message": "Cancellation requested"}


@app.post("/api/generate/{session_id}")
def generate_ultrastar_files(session_id: str):
    """Run the full processing pipeline: BPM → Pitch → Alignment → Ultrastar."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not session.get("vocal_audio"):
        raise ServiceError("No vocal audio", "Upload or extract vocals first")
    if not session.get("lyrics"):
        raise ServiceError("No lyrics", "Submit lyrics first")
    
    vocal_path = session["vocal_audio"]
    lyrics = session["lyrics"]
    artist = session.get("artist", "Unknown Artist")
    title = session.get("title", "Unknown Song")
    language = session.get("language", "en")
    
    session["status"] = "generating"
    session["cancelled"] = False
    generation_start = time.time()

    def check_cancelled():
        if session.get("cancelled"):
            session["status"] = "cancelled"
            raise ServiceError("Generation cancelled", "Cancelled by user")

    try:
        # Step 3a: BPM Detection
        log_step("GENERATE", "Step 1/4: BPM detection")
        from services.bpm_detection import detect_bpm, get_audio_duration, refine_bpm, detect_beat_phase
        
        original_path = session.get("original_audio")
        bpm = detect_bpm(vocal_path, original_audio_path=original_path)
        audio_duration = get_audio_duration(vocal_path)
        
        # Detect beat phase (where musical beats actually fall in the audio)
        beat_phase_sec = detect_beat_phase(original_path or vocal_path, bpm)
        
        # Step 3b: Pitch Detection
        log_step("GENERATE", "Step 2/4: Pitch detection")
        check_cancelled()
        from services.pitch_detection import detect_pitches
        
        pitch_data = detect_pitches(vocal_path)
        
        # Step 3c: Alignment
        log_step("GENERATE", "Step 3/4: Syllable alignment")
        check_cancelled()
        whisper_words = session.get("whisper_words", [])
        whisper_chars = session.get("whisper_chars", [])
        whisper_method = session.get("whisper_method", "whisper")
        
        # Primary: WhisperX-based alignment (phoneme-aligned ~50ms accuracy)
        # Fallback: energy-based alignment
        syllable_timings = None
        if whisper_words:
            log_step("GENERATE", f"Using {whisper_method} alignment ({len(whisper_words)} words, {len(whisper_chars)} chars)")
            try:
                from services.alignment_whisper import align_whisper
                syllable_timings = align_whisper(
                    lyrics, whisper_words, language,
                    char_timestamps=whisper_chars,
                    audio_path=vocal_path,
                )
                if syllable_timings:
                    log_step("GENERATE", f"Alignment: {len(syllable_timings)} syllables")
                else:
                    log_step("GENERATE", "Alignment returned empty, falling back to energy-based")
            except Exception as e:
                log_step("GENERATE", f"Alignment failed: {e}, falling back to energy-based")
                import traceback
                traceback.print_exc()
        
        # Onset snapping: refine syllable boundaries using spectral onsets
        if syllable_timings:
            try:
                from services.onset_snapping import snap_to_onsets
                syllable_timings = snap_to_onsets(vocal_path, syllable_timings)
                log_step("GENERATE", "Onset snapping applied")
            except Exception as e:
                log_step("GENERATE", f"Onset snapping skipped: {e}")
        
        if not syllable_timings:
            log_step("GENERATE", "Using energy-based alignment (fallback)")
            from services.alignment import align_lyrics_to_audio
            syllable_timings = align_lyrics_to_audio(vocal_path, lyrics, language)
        
        # Calculate GAP aligned to the musical beat grid.
        # GAP = the beat phase offset, i.e. where the song's actual rhythm starts.
        # The beat grid follows the real music (kick drum, instruments),
        # NOT the first syllable. The first note will land on whatever beat
        # it naturally falls on (e.g. beat 32, 64, etc.).
        gap_ms = 0
        if syllable_timings:
            first_start_ms = syllable_timings[0]["start"] * 1000
            musical_bpm = bpm / 2.0
            beat_period_ms = 60000.0 / musical_bpm
            phase_ms = beat_phase_sec * 1000.0
            
            # GAP = beat phase (where the actual first musical beat falls)
            gap_ms = max(0, int(round(phase_ms)))
            
            first_note_offset_ms = first_start_ms - gap_ms
            first_note_beat = first_note_offset_ms * bpm / 15000
            log_step("GENERATE", f"GAP: {gap_ms}ms (phase={phase_ms:.0f}ms, "
                     f"first syllable={first_start_ms:.0f}ms, "
                     f"first note at beat {first_note_beat:.1f}, "
                     f"period={beat_period_ms:.0f}ms)")
        
        # Refine BPM using syllable timestamps (can recover exact BPM)
        bpm = refine_bpm(syllable_timings, gap_ms, bpm)
        
        # Add line_index to timings if not present
        from services.alignment_whisper import parse_lyrics as parse_lyrics_fast
        parsed = parse_lyrics_fast(lyrics)
        syllable_idx = 0
        for line_idx, line in enumerate(parsed):
            for _ in line:
                if syllable_idx < len(syllable_timings):
                    syllable_timings[syllable_idx]["line_index"] = line_idx
                syllable_idx += 1
        
        # Step 3d: Generate files
        log_step("GENERATE", "Step 4/4: Generating output files")
        check_cancelled()
        from services.ultrastar import generate_ultrastar, generate_processing_summary
        from services.midi_export import generate_midi
        
        # Generate Ultrastar .txt
        txt_content = generate_ultrastar(
            syllable_timings=syllable_timings,
            pitch_data=pitch_data,
            bpm=bpm,
            gap_ms=gap_ms,
            artist=artist,
            title=title,
            language=language,
        )
        
        # Determine pitch/alignment methods (from actual results)
        pitch_method = "PYIN"
        
        # Check what method was actually used by looking at syllable_timings
        if syllable_timings:
            methods_used = set(t.get("method", "unknown") for t in syllable_timings)
            if "whisperx" in methods_used:
                wx_count = sum(1 for t in syllable_timings if t.get("method") == "whisperx")
                char_count = sum(1 for t in syllable_timings if t.get("split_method") == "char")
                align_method = f"WhisperX ({wx_count}/{len(syllable_timings)} syllables, {char_count} char-split)"
            elif "whisper" in methods_used:
                whisper_count = sum(1 for t in syllable_timings if t.get("method") == "whisper")
                align_method = f"Whisper ({whisper_count}/{len(syllable_timings)} syllables)"
            elif "fallback_energy" in methods_used:
                align_method = "Energy-based fallback"
            elif "fallback_even" in methods_used:
                align_method = "Even distribution fallback"
            else:
                align_method = f"Mixed ({', '.join(methods_used)})"
        else:
            align_method = "Energy-based fallback"
        
        # Generate summary
        summary_content = generate_processing_summary(
            syllable_timings=syllable_timings,
            bpm=bpm,
            gap_ms=gap_ms,
            audio_duration=audio_duration,
            pitch_method=pitch_method,
            alignment_method=align_method,
        )
        
        # Save files
        timestamp = int(time.time())
        txt_filename = f"song_{timestamp}.txt"
        midi_filename = f"pitches_{timestamp}.mid"
        summary_filename = f"summary_{timestamp}.txt"
        
        txt_path = os.path.join(DOWNLOADS_DIR, txt_filename)
        midi_path = os.path.join(DOWNLOADS_DIR, midi_filename)
        summary_path = os.path.join(DOWNLOADS_DIR, summary_filename)
        
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt_content)
        
        generate_midi(syllable_timings, pitch_data, bpm, midi_path)
        
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_content)
        
        elapsed = time.time() - generation_start
        log_step("GENERATE", f"Done in {elapsed:.1f}s: {txt_filename}")
        
        # Store result in session
        session["status"] = "generated"
        session["result"] = {
            "txt_file": txt_filename,
            "midi_file": midi_filename,
            "summary_file": summary_filename,
            "bpm": bpm,
            "gap_ms": gap_ms,
            "beat_phase_sec": beat_phase_sec,
            "syllable_count": len(syllable_timings),
            "audio_duration": audio_duration,
            "pitch_method": pitch_method,
            "alignment_method": align_method,
            "elapsed_seconds": elapsed,
            "syllable_timings": syllable_timings,
            "ultrastar_content": txt_content,
            "pitch_data": pitch_data,
        }
        save_session(session_id)
        
        # ── Auto-compare with reference (ms-based, BPM-independent) ──
        ms_comparison = None
        ref_content = session.get("reference_content")
        if ref_content and syllable_timings:
            try:
                from services.reference_comparison import compare_timing_ms
                ms_comparison = compare_timing_ms(syllable_timings, ref_content)
                session["result"]["ms_comparison"] = ms_comparison
                save_session(session_id)
                log_step("GENERATE", f"MS comparison: {ms_comparison['matched']} matched, "
                         f"median {ms_comparison.get('median_error_sec', '?')}s, "
                         f"{ms_comparison.get('pct_within_200ms', '?')}% ≤200ms")
            except Exception as cmp_err:
                log.warning(f"MS comparison failed: {cmp_err}")
        
        return {
            "status": "ok",
            "session_id": session_id,
            "bpm": bpm,
            "gap_ms": gap_ms,
            "syllable_count": len(syllable_timings),
            "audio_duration": round(audio_duration, 1),
            "pitch_method": pitch_method,
            "alignment_method": align_method,
            "elapsed_seconds": round(elapsed, 1),
            "files": {
                "txt": f"/api/download/{session_id}/txt",
                "midi": f"/api/download/{session_id}/midi",
                "summary": f"/api/download/{session_id}/summary",
                "vocals": f"/api/preview-audio/{session_id}/vocals",
            },
            "ultrastar_preview": txt_content[:2000],
            "ms_comparison": ms_comparison,
        }
    except Exception as e:
        session["status"] = "generation_failed"
        log.error(f"Generation failed for session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        raise ServiceError("Generation failed", str(e))


@app.get("/api/generate/result/{session_id}")
async def get_generation_result(session_id: str):
    """Get the result of a previous generation."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session["status"] != "generated":
        return {"status": "pending", "current_status": session["status"]}
    
    result = session.get("result", {})
    # Build response safely — exclude large fields
    exclude_keys = {"syllable_timings", "ultrastar_content", "pitch_data"}
    response = {"status": "ok", "session_id": session_id}
    for k, v in result.items():
        if k not in exclude_keys:
            response[k] = v
    response["ultrastar_preview"] = result.get("ultrastar_content", "")[:2000]
    return response


# ────────────────────────────────────────────────────────────
# Step 4: Editor data
# ────────────────────────────────────────────────────────────
@app.get("/api/editor-data/{session_id}")
async def get_editor_data(session_id: str):
    """Get note data for the piano roll editor."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    result = session.get("result")
    if not result:
        raise ServiceError("No generation result", "Run generation first")
    
    vocal = session.get("vocal_audio")
    original = session.get("original_audio")
    has_vocals = vocal is not None and os.path.exists(vocal)
    has_original = original is not None and os.path.exists(original)

    # Determine vocal_url — prefer vocals, fall back to original
    if has_vocals:
        vocal_url = f"/api/preview-audio/{session_id}/vocals"
    elif has_original:
        vocal_url = f"/api/preview-audio/{session_id}/original"
    else:
        vocal_url = None

    return {
        "status": "ok",
        "session_id": session_id,
        "bpm": result["bpm"],
        "gap_ms": result["gap_ms"],
        "beat_phase_ms": result.get("beat_phase_sec", 0.0) * 1000,
        "audio_duration": result["audio_duration"],
        "syllable_timings": result["syllable_timings"],
        "ultrastar_content": result["ultrastar_content"],
        "vocal_url": vocal_url,
        "has_vocals": has_vocals,
        "has_original": has_original,
        "has_edits": result.get("has_edits", False),
        "edit_count": result.get("edit_count", 0),
        "last_saved": result.get("last_saved"),
    }


# ────────────────────────────────────────────────────────────
# Step 4: Save editor state
# ────────────────────────────────────────────────────────────
@app.post("/api/save-editor/{session_id}")
async def save_editor_state(session_id: str, request: Request):
    """Save the current piano-roll editor state (notes, BPM, GAP) back to the session.

    Accepts JSON body with:
        notes: list of note objects {startBeat, duration, pitch, syllable, isRap, type}
        bpm: float
        gap_ms: int
    
    Reconstructs Ultrastar content from the notes and persists everything.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = session.get("result")
    if not result:
        raise ServiceError("No generation result", "Run generation first")

    body = await request.json()
    editor_notes = body.get("notes", [])
    editor_bpm = body.get("bpm")
    editor_gap = body.get("gap_ms")
    extra_headers = body.get("extra_headers", [])

    if not editor_notes:
        raise ServiceError("No notes provided")
    if editor_bpm is None or editor_gap is None:
        raise ServiceError("BPM and gap_ms are required")

    # Reconstruct Ultrastar .txt content from the editor notes
    lines = []
    lines.append(f"#TITLE:{session.get('title', 'Unknown Song')}")
    lines.append(f"#ARTIST:{session.get('artist', 'Unknown Artist')}")
    lines.append(f"#BPM:{editor_bpm:.2f}")
    lines.append(f"#GAP:{int(editor_gap)}")
    lang = session.get("language", "en")
    lang_name = {"en": "English", "de": "German", "fr": "French", "es": "Spanish",
                 "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "ja": "Japanese",
                 "ko": "Korean", "zh": "Chinese"}.get(lang, lang.title())
    lines.append(f"#LANGUAGE:{lang_name}")
    _mp3_path = session.get('original_audio') or session.get('vocal_audio') or 'song.mp3'
    lines.append(f"#MP3:{os.path.basename(_mp3_path)}")

    # Extra headers from the editor (e.g. YOUTUBE, COVER, etc.)
    standard_keys = {'TITLE', 'ARTIST', 'BPM', 'GAP', 'LANGUAGE', 'MP3'}
    for header in extra_headers:
        key = header.get('key', '')
        value = header.get('value', '')
        if key.upper() not in standard_keys:
            lines.append(f"#{key}:{value}")

    for note in editor_notes:
        note_type = note.get("type", "")
        if note_type == "break":
            end_beat = note.get("endBeat")
            if end_beat is not None:
                lines.append(f"- {note['startBeat']} {end_beat}")
            else:
                lines.append(f"- {note['startBeat']}")
        else:
            if note.get("isGolden"):
                prefix = "*"
            elif note.get("isRap"):
                prefix = "F:"
            else:
                prefix = ":"
            lines.append(f"{prefix} {note['startBeat']} {note['duration']} {note['pitch']} {note['syllable']}")

    lines.append("E")
    ultrastar_content = "\n".join(lines)

    # Update session result
    result["bpm"] = editor_bpm
    result["gap_ms"] = int(editor_gap)
    result["ultrastar_content"] = ultrastar_content
    result["has_edits"] = True
    result["edit_count"] = result.get("edit_count", 0) + 1
    result["last_saved"] = time.time()

    # Also write the file to downloads
    timestamp = int(time.time())
    txt_filename = f"song_{timestamp}.txt"
    txt_path = os.path.join(DOWNLOADS_DIR, txt_filename)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(ultrastar_content)
    result["txt_file"] = txt_filename

    # Inject asset headers (COVER, BACKGROUND, VIDEO, VIDEOGAP) from session
    _update_txt_asset_headers(session)

    save_session(session_id)

    note_count = sum(1 for n in editor_notes if n.get("type") != "break")
    log_step("SAVE-EDITOR", f"Session {session_id}: {note_count} notes, BPM={editor_bpm:.1f}, GAP={editor_gap}ms, {len(extra_headers)} extra headers (save #{result['edit_count']})")

    return {
        "status": "ok",
        "session_id": session_id,
        "note_count": note_count,
        "edit_count": result["edit_count"],
        "last_saved": result["last_saved"],
        "txt_file": txt_filename,
    }


# ────────────────────────────────────────────────────────────
# Step 4: Save corrections (legacy)
# ────────────────────────────────────────────────────────────
@app.post("/api/corrections/{session_id}")
async def save_corrections(session_id: str, corrections: dict = None):
    """Save user corrections from the piano roll editor."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not corrections:
        raise ServiceError("No corrections provided")
    
    # Save correction pair: AI output vs user correction
    correction_file = os.path.join(
        CORRECTIONS_DIR,
        f"{session_id}_{int(time.time())}.json"
    )
    
    correction_data = {
        "session_id": session_id,
        "timestamp": time.time(),
        "artist": session.get("artist", ""),
        "title": session.get("title", ""),
        "original_timings": session.get("result", {}).get("syllable_timings", []),
        "user_corrections": corrections,
    }
    
    with open(correction_file, "w") as f:
        json.dump(correction_data, f, indent=2)
    
    log_step("CORRECTIONS", f"Saved corrections: {correction_file}")
    
    return {"status": "ok", "saved": correction_file}



# ────────────────────────────────────────────────────────────
# Step 5: Export & Download
# ────────────────────────────────────────────────────────────
@app.post("/api/export/{session_id}")
async def export_with_corrections(
    session_id: str,
    corrected_content: str = Form(None),
):
    """Export final files, optionally with corrected Ultrastar content."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    result = session.get("result")
    if not result:
        raise ServiceError("No generation result", "Run generation first")
    
    if corrected_content:
        # Save corrected version
        timestamp = int(time.time())
        corrected_filename = f"song_corrected_{timestamp}.txt"
        corrected_path = os.path.join(DOWNLOADS_DIR, corrected_filename)
        
        with open(corrected_path, "w", encoding="utf-8") as f:
            f.write(corrected_content)
        
        result["corrected_txt_file"] = corrected_filename
        log_step("EXPORT", f"Saved corrected file: {corrected_filename}")
    
    return {
        "status": "ok",
        "files": {
            "txt": f"/api/download/{session_id}/txt",
            "midi": f"/api/download/{session_id}/midi",
            "summary": f"/api/download/{session_id}/summary",
            "vocals": f"/api/preview-audio/{session_id}/vocals",
        }
    }


@app.patch("/api/session/{session_id}/metadata")
async def update_metadata(session_id: str, artist: str = Form(...), title: str = Form(...)):
    """Update artist/title in session and rewrite the .txt file headers."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session["artist"] = artist
    session["title"] = title
    save_session(session_id)

    # Rewrite headers in the .txt file on disk
    result = session.get("result")
    if result:
        for key in ["corrected_txt_file", "txt_file"]:
            fname = result.get(key)
            if not fname:
                continue
            path = os.path.join(DOWNLOADS_DIR, fname)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                import re
                content = re.sub(r"^#TITLE:.*$", f"#TITLE:{title}", content, count=1, flags=re.MULTILINE)
                content = re.sub(r"^#ARTIST:.*$", f"#ARTIST:{artist}", content, count=1, flags=re.MULTILINE)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                log_step("METADATA", f"Updated headers in {fname}")
            except Exception as e:
                log_step("METADATA", f"Failed to update {fname}: {e}")

    log_step("METADATA", f"Session {session_id}: artist='{artist}', title='{title}'")
    return {"status": "ok", "artist": artist, "title": title}


@app.get("/api/download/{session_id}/{file_type}")
async def download_file(session_id: str, file_type: str):
    """Download a generated file."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    result = session.get("result")
    if not result:
        raise HTTPException(status_code=404, detail="No files generated yet")
    
    file_map = {
        "txt": result.get("corrected_txt_file", result.get("txt_file")),
        "midi": result.get("midi_file"),
        "summary": result.get("summary_file"),
    }
    
    filename = file_map.get(file_type)
    if not filename:
        raise HTTPException(status_code=404, detail=f"File type '{file_type}' not found")
    
    path = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    # Build a user-friendly download name from artist/title
    artist = session.get("artist", "").strip()
    title = session.get("title", "").strip()
    if artist and title:
        base = f"{artist} - {title}"
    elif title:
        base = title
    elif artist:
        base = artist
    else:
        base = "Untitled Song"
    
    ext_map = {"txt": ".txt", "midi": ".mid", "summary": "_summary.txt"}
    download_name = base + ext_map.get(file_type, ".txt")
    
    return FileResponse(path, filename=download_name)


# ────────────────────────────────────────────────────────────
# Song assets helpers
# ────────────────────────────────────────────────────────────

import re as _re

def _set_header(content: str, key: str, value: str) -> str:
    """Insert or replace a #KEY:value line in Ultrastar .txt content.

    Always removes any existing occurrences first to prevent duplicates,
    then inserts after the last header line in the file.
    """
    new_line = f"#{key}:{value}"
    # Remove all existing occurrences of this key
    content = _remove_header(content, key)
    # Find the last #... line in the entire file (not just consecutive from top)
    lines = content.split("\n")
    idx = 0
    for i, ln in enumerate(lines):
        if ln.startswith("#"):
            idx = i + 1
    lines.insert(idx, new_line)
    return "\n".join(lines)


def _remove_header(content: str, key: str) -> str:
    """Remove all #KEY:... lines from Ultrastar .txt content."""
    lines = [ln for ln in content.split("\n") if not _re.match(rf"^#{key}:[^\n]*$", ln)]
    return "\n".join(lines)


def _update_txt_asset_headers(session: dict) -> None:
    """Inject/update or remove COVER, BACKGROUND, VIDEO, VIDEOGAP, YOUTUBE in the session's .txt file."""
    result = session.get("result")
    if not result:
        return
    txt_file = result.get("txt_file")
    if not txt_file:
        return
    path = os.path.join(DOWNLOADS_DIR, txt_file)
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as f:
        content = f.read()

    artist = session.get("artist", "").strip()
    title = session.get("title", "").strip()
    if artist and title:
        base = f"{artist} - {title}"
    elif title:
        base = title
    elif artist:
        base = artist
    else:
        base = "Untitled Song"

    cover_file = session.get("cover_file")
    if cover_file and os.path.exists(cover_file):
        content = _set_header(content, "COVER", f"{base} [CO].jpg")
    else:
        content = _remove_header(content, "COVER")

    bg_file = session.get("bgimage_file")
    if bg_file and os.path.exists(bg_file):
        content = _set_header(content, "BACKGROUND", f"{base} [BG].jpg")
    else:
        content = _remove_header(content, "BACKGROUND")

    video_filename = session.get("video_filename")
    if video_filename:
        content = _set_header(content, "VIDEO", video_filename)
        video_gap = session.get("video_gap")
        if video_gap is not None:
            content = _set_header(content, "VIDEOGAP", str(video_gap))
        else:
            content = _remove_header(content, "VIDEOGAP")
    else:
        content = _remove_header(content, "VIDEO")
        content = _remove_header(content, "VIDEOGAP")

    youtube_url = session.get("youtube_url")
    if youtube_url:
        content = _set_header(content, "YOUTUBE", youtube_url)
    else:
        content = _remove_header(content, "YOUTUBE")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    result["ultrastar_content"] = content


# ────────────────────────────────────────────────────────────
# Song assets: cover image, background image, video filename
# ────────────────────────────────────────────────────────────

@app.post("/api/cover/{session_id}")
async def upload_cover(session_id: str, image: UploadFile = File(...)):
    """Save a pre-cropped cover image (480×480 JPEG) for the session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    cover_path = os.path.join(session_dir, "cover.jpg")
    data = await image.read()
    with open(cover_path, "wb") as f:
        f.write(data)
    session["cover_file"] = cover_path
    save_session(session_id)
    _update_txt_asset_headers(session)
    log_step("ASSETS", f"Cover saved for session {session_id} ({len(data)} bytes)")
    return {"status": "ok"}


@app.get("/api/cover/{session_id}")
async def get_cover(session_id: str):
    """Serve the cover image for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    cover_path = session.get("cover_file")
    if not cover_path or not os.path.exists(cover_path):
        raise HTTPException(status_code=404, detail="No cover image")
    return FileResponse(cover_path, media_type="image/jpeg")


@app.delete("/api/cover/{session_id}")
async def delete_cover(session_id: str):
    """Remove the cover image for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    cover_path = session.get("cover_file")
    if cover_path and os.path.exists(cover_path):
        os.remove(cover_path)
    session.pop("cover_file", None)
    save_session(session_id)
    _update_txt_asset_headers(session)
    return {"status": "ok"}


@app.post("/api/bgimage/{session_id}")
async def upload_bgimage(session_id: str, image: UploadFile = File(...)):
    """Save a background image for the session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    bg_path = os.path.join(session_dir, "background.jpg")
    data = await image.read()
    with open(bg_path, "wb") as f:
        f.write(data)
    session["bgimage_file"] = bg_path
    save_session(session_id)
    _update_txt_asset_headers(session)
    log_step("ASSETS", f"Background image saved for session {session_id} ({len(data)} bytes)")
    return {"status": "ok"}


@app.get("/api/bgimage/{session_id}")
async def get_bgimage(session_id: str):
    """Serve the background image for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    bg_path = session.get("bgimage_file")
    if not bg_path or not os.path.exists(bg_path):
        raise HTTPException(status_code=404, detail="No background image")
    return FileResponse(bg_path, media_type="image/jpeg")


@app.delete("/api/bgimage/{session_id}")
async def delete_bgimage(session_id: str):
    """Remove the background image for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    bg_path = session.get("bgimage_file")
    if bg_path and os.path.exists(bg_path):
        os.remove(bg_path)
    session.pop("bgimage_file", None)
    save_session(session_id)
    _update_txt_asset_headers(session)
    return {"status": "ok"}


@app.get("/api/assets/{session_id}")
async def get_assets_meta(session_id: str):
    """Return stored video filename, gap and youtube url for the session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "video_filename": session.get("video_filename", ""),
        "video_gap": session.get("video_gap", 0),
        "youtube_url": session.get("youtube_url", ""),
    }


@app.post("/api/assets/{session_id}")
async def save_assets_meta(session_id: str, request: Request):
    """Save video filename and optional video gap for the session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    body = await request.json()
    video_filename = (body.get("video_filename") or "").strip()
    video_gap = body.get("video_gap")
    youtube_url = (body.get("youtube_url") or "").strip()
    if video_filename:
        session["video_filename"] = video_filename
    else:
        session.pop("video_filename", None)
    if video_gap is not None:
        try:
            session["video_gap"] = float(video_gap)
        except (ValueError, TypeError):
            pass
    else:
        session.pop("video_gap", None)
    if youtube_url:
        session["youtube_url"] = youtube_url
    else:
        session.pop("youtube_url", None)
    save_session(session_id)
    _update_txt_asset_headers(session)
    log_step("ASSETS", f"Video meta saved for session {session_id}: video={video_filename!r} youtube={youtube_url!r}")
    return {"status": "ok"}


@app.get("/api/download-zip/{session_id}")
async def download_zip(session_id: str):
    """Bundle all generated files into a single ZIP download."""
    import zipfile
    import io
    from starlette.responses import Response

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = session.get("result")
    if not result:
        raise HTTPException(status_code=404, detail="No files generated yet")

    # Build base name from artist/title
    artist = session.get("artist", "").strip()
    title_name = session.get("title", "").strip()
    if artist and title_name:
        base = f"{artist} - {title_name}"
    elif title_name:
        base = title_name
    elif artist:
        base = artist
    else:
        base = "Untitled Song"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Ultrastar .txt — inject asset headers before writing
        txt_file = result.get("corrected_txt_file", result.get("txt_file"))
        if txt_file:
            path = os.path.join(DOWNLOADS_DIR, txt_file)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    txt_content = f.read()

                # Helper: insert/replace a header line
                def _set_header(content, key, value):
                    import re
                    tag = f"#{key}:"
                    new_line = f"#{key}:{value}"
                    if tag in content:
                        return re.sub(rf"#{key}:[^\n]*", new_line, content)
                    # Insert after last # header line
                    lines = content.split("\n")
                    idx = 0
                    for i, ln in enumerate(lines):
                        if ln.startswith("#"):
                            idx = i + 1
                        else:
                            break
                    lines.insert(idx, new_line)
                    return "\n".join(lines)

                cover_path = session.get("cover_file")
                if cover_path and os.path.exists(cover_path):
                    cover_archive = f"{base} [CO].jpg"
                    txt_content = _set_header(txt_content, "COVER", cover_archive)

                bg_path = session.get("bgimage_file")
                if bg_path and os.path.exists(bg_path):
                    bg_archive = f"{base} [BG].jpg"
                    txt_content = _set_header(txt_content, "BACKGROUND", bg_archive)

                video_filename = session.get("video_filename")
                if video_filename:
                    txt_content = _set_header(txt_content, "VIDEO", video_filename)
                    video_gap = session.get("video_gap")
                    if video_gap is not None:
                        txt_content = _set_header(txt_content, "VIDEOGAP", str(video_gap))

                zf.writestr(f"{base}.txt", txt_content)

        # MIDI
        midi_file = result.get("midi_file")
        if midi_file:
            path = os.path.join(DOWNLOADS_DIR, midi_file)
            if os.path.exists(path):
                zf.write(path, f"{base}.mid")

        # Summary
        summary_file = result.get("summary_file")
        if summary_file:
            path = os.path.join(DOWNLOADS_DIR, summary_file)
            if os.path.exists(path):
                zf.write(path, f"{base}_summary.txt")

        # Vocals audio
        vocal_path = session.get("vocal_audio")
        if vocal_path and os.path.exists(vocal_path):
            ext = os.path.splitext(vocal_path)[1]
            zf.write(vocal_path, f"{base} [Vocals]{ext}")

        # Original audio
        original_path = session.get("original_audio")
        if original_path and os.path.exists(original_path):
            ext = os.path.splitext(original_path)[1]
            zf.write(original_path, f"{base}{ext}")

        # Cover image
        cover_path = session.get("cover_file")
        if cover_path and os.path.exists(cover_path):
            zf.write(cover_path, f"{base} [CO].jpg")

        # Background image
        bg_path = session.get("bgimage_file")
        if bg_path and os.path.exists(bg_path):
            zf.write(bg_path, f"{base} [BG].jpg")

    buf.seek(0)
    zip_name = f"{base}.zip"
    log_step("EXPORT", f"ZIP download: {zip_name}")

    # Content-Disposition headers are latin-1 only; use RFC 5987 filename* for
    # song titles that contain non-ASCII characters (curly quotes, accents, …).
    from urllib.parse import quote as _urlquote
    ascii_name = zip_name.encode("ascii", errors="replace").decode("ascii")
    utf8_name = _urlquote(zip_name, safe="")
    content_disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition},
    )


# ────────────────────────────────────────────────────────────
# Reference comparison (learning from verified Ultrastar files)
# ────────────────────────────────────────────────────────────
@app.post("/api/reference/upload/{session_id}")
async def upload_reference(session_id: str, reference: UploadFile = File(...)):
    """Upload a verified/original Ultrastar .txt file for comparison."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    content = (await reference.read()).decode("utf-8", errors="replace")
    session["reference_content"] = content
    session["reference_filename"] = reference.filename
    save_session(session_id)
    
    # Parse to validate
    from services.reference_comparison import parse_ultrastar_file, compare_lyrics
    parsed = parse_ultrastar_file(content)
    
    log_step("REFERENCE", f"Session {session_id}: uploaded reference {reference.filename} ({len(parsed['notes'])} notes)")
    
    # Compare lyrics if user has already entered them
    lyrics_comparison = None
    user_lyrics = session.get("lyrics")
    if user_lyrics:
        lyrics_comparison = compare_lyrics(user_lyrics, content)
    
    return {
        "status": "ok",
        "filename": reference.filename,
        "notes_count": len(parsed["notes"]),
        "bpm": parsed["bpm"],
        "gap": parsed["gap"],
        "headers": parsed["headers"],
        "lyrics_comparison": lyrics_comparison,
    }


@app.post("/api/reference/compare/{session_id}")
async def compare_reference(session_id: str):
    """Compare AI-generated output with uploaded reference file."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    ai_content = session.get("result", {}).get("ultrastar_content")
    ref_content = session.get("reference_content")
    
    if not ai_content:
        raise ServiceError("No AI output", "Run generation first")
    if not ref_content:
        raise ServiceError("No reference file", "Upload a reference Ultrastar file first")
    
    from services.reference_comparison import compare_with_reference, store_comparison, compare_lyrics
    
    comparison = compare_with_reference(ai_content, ref_content)
    
    # Also compare lyrics
    user_lyrics = session.get("lyrics")
    lyrics_comparison = None
    if user_lyrics:
        lyrics_comparison = compare_lyrics(user_lyrics, ref_content)
        comparison["lyrics_comparison"] = lyrics_comparison
    
    # Store for learning
    metadata = {
        "artist": session.get("artist", ""),
        "title": session.get("title", ""),
        "language": session.get("language", "en"),
    }
    store_comparison(session_id, comparison, metadata)
    
    session["reference_comparison"] = comparison
    
    return {
        "status": "ok",
        "comparison": comparison,
    }


@app.get("/api/reference/stats")
async def reference_stats():
    """Get learning stats and biases from stored reference comparisons."""
    from services.reference_comparison import get_reference_stats
    
    stats = get_reference_stats()
    return {"status": "ok", **stats}


@app.get("/api/reference/notes/{session_id}")
async def get_reference_notes(session_id: str):
    """Get parsed reference notes for overlay in the piano roll editor."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    ref_content = session.get("reference_content")
    if not ref_content:
        raise HTTPException(status_code=404, detail="No reference file uploaded")
    
    from services.reference_comparison import parse_ultrastar_file
    parsed = parse_ultrastar_file(ref_content)
    
    return {
        "status": "ok",
        "bpm": parsed["bpm"],
        "gap": parsed["gap"],
        "notes": parsed["notes"],
        "breaks": parsed["breaks"],
    }


# ────────────────────────────────────────────────────────────
# Startup
# ────────────────────────────────────────────────────────────


@app.post("/api/save-mic-trail/{session_id}")
async def save_mic_trail(session_id: str, trail: str = Form(...), audio: UploadFile = File(None)):
    """Save a mic pitch trail recording + optional voice audio to downloads folder.
    
    Accepts multipart form: 'trail' (JSON string) and optional 'audio' (webm file).
    Keeps only the last 5 recordings, auto-deleting the oldest.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    body = json.loads(trail)
    
    # Save to downloads folder with timestamp
    import glob as glob_mod
    timestamp = int(time.time())
    
    # Save trail JSON
    trail_filename = f"mic_trail_{session_id[:8]}_{timestamp}.json"
    trail_filepath = os.path.join(DOWNLOADS_DIR, trail_filename)
    with open(trail_filepath, "w") as f:
        json.dump(body, f, indent=2)
    
    # Save audio if provided
    audio_filename = None
    if audio and audio.filename:
        ext = audio.filename.rsplit('.', 1)[-1] if '.' in audio.filename else 'webm'
        audio_filename = f"mic_audio_{session_id[:8]}_{timestamp}.{ext}"
        audio_filepath = os.path.join(DOWNLOADS_DIR, audio_filename)
        audio_data = await audio.read()
        with open(audio_filepath, "wb") as f:
            f.write(audio_data)
        log_step("MIC", f"Saved mic audio: {audio_filename} ({len(audio_data) // 1024} KB)")
    
    # Keep only last 5 mic trail files for this session
    for prefix in ("mic_trail_", "mic_audio_"):
        pattern = os.path.join(DOWNLOADS_DIR, f"{prefix}{session_id[:8]}_*")
        existing = sorted(glob_mod.glob(pattern))
        while len(existing) > 5:
            oldest = existing.pop(0)
            os.remove(oldest)
            log_step("MIC", f"Removed old: {os.path.basename(oldest)}")
    
    sample_count = len(body.get('samples', []))
    log_step("MIC", f"Saved mic trail: {trail_filename} ({sample_count} samples)")
    
    result = {"status": "ok", "filename": trail_filename}
    if audio_filename:
        result["audioFile"] = audio_filename
    return result


if __name__ == "__main__":
    import uvicorn

    # Pre-load essentia (and its bundled libSDL-1.2.0.dylib) on the main thread
    # BEFORE uvicorn spawns worker threads.
    #
    # SDL 1.2's dylib constructor (dllinit) checks [NSThread isMainThread] and
    # calls error_dialog → [NSAlert init] when loaded on a background thread.
    # On macOS 26+, creating AppKit objects off the main thread raises an ObjC
    # exception that propagates to the C++ runtime and calls abort() (SIGABRT).
    #
    # Python caches loaded modules in sys.modules, so once the dylib is loaded
    # here on the main thread, subsequent imports by uvicorn worker threads are
    # no-ops and dllinit is never called again.
    # Minimal SDL2 preload: just dlopen the dylib on the main thread to trigger
    # SDL's C-constructor (dllinit) before uvicorn spawns background threads.
    # Avoids importing all of essentia (~13s) — essentia imports lazily on first use.
    try:
        import ctypes as _ctypes, glob as _glob, os as _os, sys as _sys
        _sdl_candidates = []
        _meipass = getattr(_sys, '_MEIPASS', None)
        if _meipass:
            _sdl_candidates += _glob.glob(_os.path.join(_meipass, 'libSDL2*.dylib'))
        try:
            import importlib.util as _ilu
            _spec = _ilu.find_spec('essentia')
            if _spec and _spec.origin:
                _sdl_candidates += _glob.glob(
                    _os.path.join(_os.path.dirname(_spec.origin), '.dylibs', 'libSDL2*.dylib'))
        except Exception:
            pass
        if _sdl_candidates:
            _ctypes.CDLL(_sdl_candidates[0])
            log_step("PRELOAD", f"SDL2 dlopen on main thread: {_os.path.basename(_sdl_candidates[0])}")
        else:
            log_step("PRELOAD", "SDL2 dylib not found — skipping preload")
    except Exception as _preload_err:
        log_step("PRELOAD", f"SDL preload skipped: {_preload_err}")

    log_step("SERVER", "Starting Ultrastar Song Generator v2.0")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
