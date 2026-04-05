"""Ultrastar Song Generator — FastAPI Backend Server.

Thin route layer. All processing logic lives in services/.
"""

import os
import sys
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
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(ServiceError, service_exception_handler)

# Directories
DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "downloads")
CORRECTIONS_DIR = os.path.join(os.path.dirname(__file__), "corrections")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
REFERENCE_DIR = os.path.join(os.path.dirname(__file__), "reference_songs")
SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")

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
    from services.pitch_detection import CREPE_AVAILABLE
    from services.alignment import _check_mfa
    from services.vocal_separation import DEMUCS_AVAILABLE
    
    return {
        "status": "ok",
        "version": "2.0.0",
        "models": {
            "crepe": CREPE_AVAILABLE,
            "mfa": _check_mfa(),
            "demucs": DEMUCS_AVAILABLE,
        }
    }


# ────────────────────────────────────────────────────────────
# Step 1: Upload & Vocal Extraction
# ────────────────────────────────────────────────────────────
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


@app.post("/api/extract-vocals/{session_id}")
async def extract_vocals(session_id: str):
    """Run Demucs vocal separation on uploaded audio."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    from services.vocal_separation import separate_vocals, DEMUCS_AVAILABLE
    
    if not DEMUCS_AVAILABLE:
        raise ServiceError("Demucs not installed", "Install with: pip install demucs", 503)
    
    try:
        session["status"] = "extracting_vocals"
        output_dir = os.path.join(UPLOAD_DIR, session_id)
        vocal_path = separate_vocals(session["original_audio"], output_dir)
        
        session["vocal_audio"] = vocal_path
        session["status"] = "vocals_extracted"
        save_session(session_id)
        
        return {
            "status": "ok",
            "session_id": session_id,
            "vocal_url": f"/api/preview-audio/{session_id}/vocals",
        }
    except Exception as e:
        session["status"] = "extraction_failed"
        save_session(session_id)
        raise ServiceError("Vocal extraction failed", str(e))


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
    return FileResponse(path, headers={'Accept-Ranges': 'bytes'})


# ────────────────────────────────────────────────────────────
# Step 2a: Whisper ASR Transcription
# ────────────────────────────────────────────────────────────
@app.post("/api/transcribe/{session_id}")
async def transcribe_audio(session_id: str, language: str = Form("en")):
    """Transcribe vocal audio using Whisper ASR.
    
    Returns the transcribed text with line breaks at phrase boundaries.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Find the vocal audio file
    audio_path = session.get("vocal_audio") or session.get("original_audio")
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="No audio file found. Upload audio first.")
    
    log_step("WHISPER", f"Transcribing {os.path.basename(audio_path)} (lang={language})...")
    
    try:
        import whisper
        
        # Map short language codes to Whisper language names
        WHISPER_LANG_MAP = {
            "en": "English", "de": "German", "fr": "French",
            "es": "Spanish", "it": "Italian", "pt": "Portuguese",
            "nl": "Dutch", "ja": "Japanese", "ko": "Korean",
            "zh": "Chinese",
        }
        
        # Load model (cached after first load)
        model_name = "medium"
        log_step("WHISPER", f"Loading Whisper model '{model_name}'...")
        model = whisper.load_model(model_name)
        
        # Transcribe with word-level timestamps
        log_step("WHISPER", "Running transcription...")
        result = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
        )
        
        # Build text with line breaks at segment boundaries
        lines = []
        all_words = []  # word-level timestamps for alignment anchoring
        for segment in result.get("segments", []):
            text = segment.get("text", "").strip()
            if text:
                lines.append(text)
            # Extract word-level timestamps
            for w in segment.get("words", []):
                all_words.append({
                    "word": w.get("word", "").strip(),
                    "start": round(w.get("start", 0), 4),
                    "end": round(w.get("end", 0), 4),
                })
        
        transcribed_text = "\n".join(lines)
        
        # Save word timestamps to session for use during alignment
        session["whisper_words"] = all_words
        save_session(session_id)
        
        # Also save to debug file
        debug_dir = os.path.join(os.path.dirname(__file__), 'downloads')
        try:
            debug_path = os.path.join(debug_dir, 'whisper_words.txt')
            with open(debug_path, 'w') as f:
                f.write(f"WHISPER WORD TIMESTAMPS ({len(all_words)} words)\n{'='*60}\n\n")
                for w in all_words:
                    dur = w['end'] - w['start']
                    f.write(f"  {w['start']:8.3f} - {w['end']:8.3f}  ({dur:5.3f}s)  {w['word']}\n")
            log_step("WHISPER", f"Word timestamps saved: {len(all_words)} words -> {debug_path}")
        except Exception:
            pass
        
        # Count words
        word_count = sum(len(line.split()) for line in lines)
        
        log_step("WHISPER", f"Transcription complete: {len(lines)} lines, {word_count} words")
        if lines:
            log_step("WHISPER", f"  First line: '{lines[0][:80]}'")
            log_step("WHISPER", f"  Last line:  '{lines[-1][:80]}'")
        
        return JSONResponse({
            "text": transcribed_text,
            "lines": len(lines),
            "words": word_count,
            "language": language,
            "language_name": WHISPER_LANG_MAP.get(language, language),
            "model": model_name,
        })
        
    except ImportError:
        raise HTTPException(status_code=500, detail="Whisper not installed. Run: pip install openai-whisper")
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
@app.post("/api/generate/{session_id}")
async def generate_ultrastar_files(session_id: str):
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
    generation_start = time.time()
    
    try:
        # Step 3a: BPM Detection
        log_step("GENERATE", "Step 1/4: BPM detection")
        from services.bpm_detection import detect_bpm, get_audio_duration, refine_bpm
        
        original_path = session.get("original_audio")
        bpm = detect_bpm(vocal_path, original_audio_path=original_path)
        audio_duration = get_audio_duration(vocal_path)
        
        # Step 3b: Pitch Detection
        log_step("GENERATE", "Step 2/4: Pitch detection")
        from services.pitch_detection import detect_pitches_crepe
        
        pitch_data = detect_pitches_crepe(vocal_path)
        
        # Step 3c: Alignment
        log_step("GENERATE", "Step 3/4: Syllable alignment")
        whisper_words = session.get("whisper_words", [])
        
        # Primary: Whisper-based alignment (no chunk drift, ~150ms accuracy)
        # Fallback: MFA chunked alignment (if no Whisper words available)
        syllable_timings = None
        if whisper_words:
            log_step("GENERATE", f"Using Whisper alignment ({len(whisper_words)} words)")
            try:
                from services.alignment_whisper import align_whisper
                syllable_timings = align_whisper(lyrics, whisper_words, language)
                if syllable_timings:
                    log_step("GENERATE", f"Whisper alignment: {len(syllable_timings)} syllables")
                else:
                    log_step("GENERATE", "Whisper alignment returned empty, falling back to MFA")
            except Exception as e:
                log_step("GENERATE", f"Whisper alignment failed: {e}, falling back to MFA")
                import traceback
                traceback.print_exc()
        
        if not syllable_timings:
            log_step("GENERATE", "Using MFA alignment (fallback)")
            from services.alignment import align_lyrics_to_audio
            syllable_timings = align_lyrics_to_audio(vocal_path, lyrics, language, whisper_words=whisper_words)
        
        # Calculate GAP from first syllable
        gap_ms = 0
        if syllable_timings:
            gap_ms = int(syllable_timings[0]["start"] * 1000)
            log_step("GENERATE", f"GAP: {gap_ms}ms (first syllable at {syllable_timings[0]['start']:.3f}s)")
        
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
        
        # Determine pitch/alignment methods (from actual results, not just availability)
        from services.pitch_detection import CREPE_AVAILABLE
        from services.alignment import _check_mfa as check_mfa_avail
        pitch_method = "CREPE" if CREPE_AVAILABLE else "PYIN (fallback)"
        
        # Check what method was actually used by looking at syllable_timings
        if syllable_timings:
            methods_used = set(t.get("method", "unknown") for t in syllable_timings)
            if "whisper" in methods_used:
                whisper_count = sum(1 for t in syllable_timings if t.get("method") == "whisper")
                align_method = f"Whisper ({whisper_count}/{len(syllable_timings)} syllables)"
            elif "mfa" in methods_used:
                mfa_count = sum(1 for t in syllable_timings if t.get("method") == "mfa")
                align_method = f"MFA (chunked, {mfa_count}/{len(syllable_timings)} syllables)"
            elif "fallback_energy" in methods_used:
                align_method = "Energy-based fallback (MFA failed)"
            elif "fallback_even" in methods_used:
                align_method = "Even distribution fallback"
            else:
                align_method = f"Mixed ({', '.join(methods_used)})"
        else:
            align_method = "MFA" if check_mfa_avail() else "Even distribution (fallback)"
        
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
    exclude_keys = {"syllable_timings", "ultrastar_content"}
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
    
    return {
        "status": "ok",
        "session_id": session_id,
        "bpm": result["bpm"],
        "gap_ms": result["gap_ms"],
        "audio_duration": result["audio_duration"],
        "syllable_timings": result["syllable_timings"],
        "ultrastar_content": result["ultrastar_content"],
        "vocal_url": f"/api/preview-audio/{session_id}/vocals",
    }


# ────────────────────────────────────────────────────────────
# Step 4: Save corrections
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
# Step 4b: Apply BPM / GAP (re-quantize from raw ms timings)
# ────────────────────────────────────────────────────────────
@app.post("/api/apply-bpm/{session_id}")
async def apply_bpm(session_id: str, bpm: float = Form(...), gap_ms: int = Form(...)):
    """Regenerate Ultrastar content with user-specified BPM and GAP.
    
    Uses the stored raw syllable_timings (in seconds) and pitch_data to
    re-quantize notes to the new beat grid.  This lets the user adjust BPM
    in the piano-roll editor and then export a clean Ultrastar file.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = session.get("result")
    if not result:
        raise ServiceError("No generation result", "Run generation first")

    syllable_timings = result.get("syllable_timings")
    pitch_data = result.get("pitch_data")
    if not syllable_timings:
        raise ServiceError("No syllable timings available")

    # Regenerate Ultrastar content with new BPM / GAP
    from services.ultrastar import generate_ultrastar, generate_processing_summary
    ultrastar_content = generate_ultrastar(
        syllable_timings=syllable_timings,
        pitch_data=pitch_data,
        bpm=bpm,
        gap_ms=gap_ms,
        artist=session.get("artist", "Unknown Artist"),
        title=session.get("title", "Unknown Song"),
        language=session.get("language", "English"),
    )

    # Save the new txt file
    timestamp = int(time.time())
    txt_filename = f"song_{timestamp}.txt"
    txt_path = os.path.join(DOWNLOADS_DIR, txt_filename)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(ultrastar_content)

    # Update session result
    result["bpm"] = bpm
    result["gap_ms"] = gap_ms
    result["ultrastar_content"] = ultrastar_content
    result["txt_file"] = txt_filename

    log_step("APPLY-BPM", f"Session {session_id}: BPM={bpm:.2f}, GAP={gap_ms}ms → {txt_filename}")
    save_session(session_id)

    return {
        "status": "ok",
        "bpm": bpm,
        "gap_ms": gap_ms,
        "ultrastar_content": ultrastar_content,
    }


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
    
    return FileResponse(path, filename=filename)


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
if __name__ == "__main__":
    import uvicorn
    
    log_step("SERVER", "Starting Ultrastar Song Generator v2.0")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
