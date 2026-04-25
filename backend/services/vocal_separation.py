"""Vocal separation using Demucs v4."""

import os
import sys
import subprocess
import tempfile
import shutil
from utils.logger import log_step

# Check if Demucs is available without importing torch (which is very slow).
# The actual import happens lazily inside the functions that use it.
try:
    import importlib.util
    DEMUCS_AVAILABLE = importlib.util.find_spec('demucs') is not None
    if DEMUCS_AVAILABLE:
        log_step("INIT", "Demucs vocal separation available")
    else:
        log_step("INIT", "Demucs not installed, vocal separation unavailable")
except Exception:
    DEMUCS_AVAILABLE = False
    log_step("INIT", "Demucs availability check failed")


def _run_demucs_in_process(audio_path: str, temp_dir: str) -> None:
    """Call demucs in-process (required for PyInstaller frozen builds where
    sys.executable is the sidecar binary, not a real Python interpreter)."""
    from demucs.separate import main as demucs_main
    args = [
        "--two-stems", "vocals",
        "-o", temp_dir,
        "--mp3",
        audio_path,
    ]
    try:
        demucs_main(args)
    except SystemExit as e:
        if e.code not in (0, None):
            raise RuntimeError(f"Demucs exited with code {e.code}")
    except Exception as e:
        import traceback
        log_step("SEPARATE", f"Demucs in-process exception: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise


def _ensure_wav(audio_path: str, temp_dir: str) -> str:
    """If the audio file is not a WAV, convert it to WAV using the bundled ffmpeg.
    Returns the path to use (original if already WAV, converted path otherwise).
    This avoids torchaudio's dependency on FFmpeg shared libs for formats like .m4a."""
    ext = os.path.splitext(audio_path)[1].lower()
    if ext == '.wav':
        return audio_path
    # Find bundled or system ffmpeg
    ffmpeg_bin = None
    if hasattr(sys, '_MEIPASS'):
        candidate = os.path.join(sys._MEIPASS, 'ffmpeg')
        if os.path.isfile(candidate):
            ffmpeg_bin = candidate
    if ffmpeg_bin is None:
        ffmpeg_bin = shutil.which('ffmpeg')
    if ffmpeg_bin is None:
        log_step("SEPARATE", "ffmpeg not found — skipping pre-conversion, Demucs will try natively")
        return audio_path
    wav_path = os.path.join(temp_dir, 'input_converted.wav')
    log_step("SEPARATE", f"Pre-converting {os.path.basename(audio_path)} → WAV via {ffmpeg_bin}")
    result = subprocess.run(
        [ffmpeg_bin, '-y', '-i', audio_path, '-ar', '44100', '-ac', '2', wav_path],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not os.path.isfile(wav_path):
        log_step("SEPARATE", f"Pre-conversion failed: {result.stderr[-500:]}")
        return audio_path  # fall back to original
    log_step("SEPARATE", f"Pre-conversion done: {os.path.getsize(wav_path):,} bytes")
    return wav_path


def separate_vocals(audio_path: str, output_dir: str) -> str:
    """Extract vocals from a full song using Demucs v4.
    
    Args:
        audio_path: Path to the input audio file (MP3/WAV)
        output_dir: Directory to save the extracted vocals
        
    Returns:
        Path to the extracted vocal audio file
    """
    if not DEMUCS_AVAILABLE:
        raise RuntimeError("Demucs is not installed. Install with: pip install demucs")
    
    log_step("SEPARATE", f"Starting vocal separation: {os.path.basename(audio_path)}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Pre-convert to WAV if needed — torchaudio can always read WAV without
        # needing FFmpeg shared libraries (which aren't bundled in the frozen app).
        demucs_input = _ensure_wav(audio_path, temp_dir)

        if getattr(sys, 'frozen', False):
            # In a PyInstaller frozen binary sys.executable is the sidecar itself.
            # Spawning it with "-m demucs" would try to restart the server and fail
            # with "address already in use".  Call demucs in-process instead.
            log_step("SEPARATE", "Running Demucs in-process (frozen build)...")
            _run_demucs_in_process(demucs_input, temp_dir)
        else:
            # Dev mode: run as subprocess so heavy torch work is isolated.
            cmd = [
                sys.executable, "-m", "demucs",
                "--two-stems", "vocals",
                "-o", temp_dir,
                "--mp3",
                demucs_input,
            ]
            log_step("SEPARATE", "Running Demucs (this may take a few minutes)...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise RuntimeError(f"Demucs failed: {result.stderr}")
        
        # Demucs names its output folder after the input file's stem
        song_name = os.path.splitext(os.path.basename(demucs_input))[0]
        
        vocal_path = None
        all_files = []
        for root, dirs, files in os.walk(temp_dir):
            for f in sorted(files):
                full_path = os.path.join(root, f)
                all_files.append(f)
                log_step("SEPARATE", f"Found Demucs output: {f} ({os.path.getsize(full_path):,} bytes)")
                # Match exactly 'vocals.mp3' or 'vocals.wav' — NOT 'no_vocals.mp3'
                if f.lower().startswith("vocals."):
                    vocal_path = full_path
        
        log_step("SEPARATE", f"All Demucs files: {all_files}")
        log_step("SEPARATE", f"Selected vocal file: {vocal_path}")
        
        if vocal_path is None:
            raise RuntimeError(f"Demucs did not produce a vocals file. Files found: {all_files}")
        
        # Copy to output directory, preserving the actual extension
        ext = os.path.splitext(vocal_path)[1] or ".wav"
        output_path = os.path.join(output_dir, f"{song_name}_vocals{ext}")
        shutil.copy2(vocal_path, output_path)
        
        log_step("SEPARATE", f"Vocals extracted: {output_path} (from {os.path.basename(vocal_path)})")
        return output_path
