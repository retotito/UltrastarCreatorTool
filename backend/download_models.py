"""Pre-download AI models so the first "Generate" run doesn't have a long wait.

Usage:
    python backend/download_models.py

Downloads:
    - WhisperX "medium" model (~1.5GB)
    - WhisperX wav2vec2 alignment model (~300MB)
    - Demucs htdemucs model (~80MB) — optional, for vocal separation
"""

import sys
import os

def main():
    print("=" * 60)
    print("  Ultrastar Creator Tool — Model Downloader")
    print("=" * 60)
    print()

    # ── WhisperX ──
    print("[1/3] Downloading WhisperX transcription model (medium)...")
    try:
        import whisperx
        import torch

        device = "cpu"
        compute_type = "int8"
        model = whisperx.load_model("medium", device, compute_type=compute_type)
        del model
        print("  ✓ WhisperX model downloaded successfully")
    except ImportError:
        print("  ✗ WhisperX not installed. Install with: pip install whisperx")
        print("    Skipping...")
    except Exception as e:
        print(f"  ✗ Failed to download WhisperX model: {e}")

    print()

    # ── WhisperX alignment model (wav2vec2) ──
    print("[2/3] Downloading WhisperX alignment model (wav2vec2, English)...")
    try:
        import whisperx

        device = "cpu"
        align_model, align_metadata = whisperx.load_align_model(
            language_code="en", device=device
        )
        del align_model, align_metadata
        print("  ✓ Alignment model downloaded successfully")
    except ImportError:
        print("  ✗ WhisperX not installed. Skipping...")
    except Exception as e:
        print(f"  ✗ Failed to download alignment model: {e}")

    print()

    # ── Demucs ──
    print("[3/3] Downloading Demucs vocal separation model (htdemucs)...")
    try:
        import demucs
        from demucs.pretrained import get_model
        model = get_model("htdemucs")
        del model
        print("  ✓ Demucs model downloaded successfully")
    except ImportError:
        print("  ⓘ Demucs not installed (optional). Install with: pip install demucs")
        print("    Skipping — you can still use the tool by uploading vocals directly.")
    except Exception as e:
        print(f"  ✗ Failed to download Demucs model: {e}")

    print()
    print("=" * 60)
    print("  Done! You can now run the backend: cd backend && python main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
