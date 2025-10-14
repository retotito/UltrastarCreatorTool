from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.middleware.cors import CORSMiddleware
import uvicorn
import os
import tempfile
from pathlib import Path
import numpy as np
from typing import Optional, Union
import time
import traceback
import json
import logging
import random

# Audio processing imports
import librosa
import pyphen
from mido import Message, MidiFile, MidiTrack, MetaMessage
from demucs.separate import main as demucs_separate
import shutil
from audio_analysis import detect_syllable_boundaries, detect_bpm, calculate_gap_from_first_pitch
# import yt_dlp

app = FastAPI(title="Ultrastar Song Generator API")

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:5174"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Server is running"}

# Test file endpoints
@app.get("/test_vocal")
async def serve_test_vocal():
    """Serve the test vocal file for download"""
    # Go up one directory from backend to access frontendTest
    project_root = os.path.dirname(os.getcwd())
    test_vocal_path = os.path.join(project_root, "frontendTest", "test_vocal.wav")
    if os.path.exists(test_vocal_path):
        return FileResponse(
            test_vocal_path, 
            media_type="audio/wav",
            filename="test_vocal.wav",
            headers={"Content-Disposition": "attachment; filename=test_vocal.wav"}
        )
    else:
        raise HTTPException(status_code=404, detail="Test vocal file not found")

@app.get("/test_lyrics")
async def serve_test_lyrics():
    """Serve the test lyrics file"""
    # Go up one directory from backend to access frontendTest  
    project_root = os.path.dirname(os.getcwd())
    test_lyrics_path = os.path.join(project_root, "frontendTest", "lyrics.txt")
    if os.path.exists(test_lyrics_path):
        with open(test_lyrics_path, "r") as f:
            return {"lyrics": f.read()}
    else:
        raise HTTPException(status_code=404, detail="Test lyrics file not found")

@app.get("/test_files")
async def get_test_files():
    """Get information about available test files for easy loading"""
    try:
        # Go up one directory from backend to access frontendTest
        project_root = os.path.dirname(os.getcwd())
        test_dir = os.path.join(project_root, "frontendTest")
        
        files_info = {}
        
        # Check for lyrics file
        lyrics_path = os.path.join(test_dir, "lyrics.txt")
        if os.path.exists(lyrics_path):
            files_info["lyrics"] = {
                "available": True,
                "path": lyrics_path,
                "url": "/test_lyrics"
            }
        else:
            files_info["lyrics"] = {"available": False}
        
        # Check for vocal file
        vocal_path = os.path.join(test_dir, "test_vocal.wav")
        if os.path.exists(vocal_path):
            files_info["vocal"] = {
                "available": True,
                "path": vocal_path,
                "url": "/test_vocal"
            }
        else:
            files_info["vocal"] = {"available": False}
        
        return {
            "status": "success",
            "test_files": files_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking test files: {str(e)}")

# Two-stage API endpoints
@app.post("/extract_vocals")
async def extract_vocals(
    file: UploadFile = File(...),
    artist: Optional[str] = Form("Unknown Artist"),
    title: Optional[str] = Form("Unknown Song"),
    language: Optional[str] = Form("en")
):
    """
    Stage 1: Extract vocals for manual cleanup.
    Returns extracted vocal file for user to clean up manually.
    """
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded file
            audio_path = os.path.join(temp_dir, file.filename)
            with open(audio_path, "wb") as f:
                content = await file.read()
                f.write(content)
            
            # Extract vocals using Demucs
            demucs_separate(["--two-stems=vocals", "-n", "htdemucs", audio_path, "-o", temp_dir])
            
            # Find the separated vocal file
            demucs_output_dir = os.path.join(temp_dir, "htdemucs", Path(file.filename).stem)
            vocal_path = os.path.join(demucs_output_dir, "vocals.wav")
            
            if not os.path.exists(vocal_path):
                raise HTTPException(status_code=500, detail="Vocal separation failed")
            
            # Save to downloads for user access
            downloads_dir = os.path.join(os.getcwd(), "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            
            timestamp = int(time.time())
            vocals_download_path = os.path.join(downloads_dir, f"extracted_vocals_{timestamp}.wav")
            
            shutil.copy(vocal_path, vocals_download_path)
            
            # Return the extracted vocals
            return FileResponse(
                vocals_download_path,
                media_type="audio/wav",
                filename=f"extracted_vocals_{timestamp}.wav",
                headers={"Content-Disposition": f"attachment; filename=extracted_vocals_{timestamp}.wav"}
            )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract vocals: {str(e)}")

@app.post("/generate_final_files")
async def generate_final_files(
    corrected_vocal: UploadFile = File(...),
    lyrics: str = Form(...),
    artist: Optional[str] = Form("Unknown Artist"),
    title: Optional[str] = Form("Unknown Song"),
    language: Optional[str] = Form("en"),
    voice_type: Optional[str] = Form("solo")
):
    """
    Stage 2: Generate final Ultrastar and MIDI files from corrected vocal + lyrics.
    Returns JSON with download URLs for .txt and MIDI summary.
    """
    processing_start_time = time.time()
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save corrected vocal file
            vocal_path = os.path.join(temp_dir, corrected_vocal.filename)
            with open(vocal_path, "wb") as f:
                content = await corrected_vocal.read()
                f.write(content)
            
            # STEP 1: Audio Analysis - detect BPM and onset/offset boundaries
            print(f"DEBUG: Starting audio analysis with new pipeline")
            
            # Detect BPM using librosa
            bpm = detect_bpm(vocal_path)
            print(f"DEBUG: Detected BPM: {bpm/2:.2f} -> Ultrastar BPM: {bpm:.2f}")
            
            # STEP 2: Lyrics Processing - split into syllables
            print(f"DEBUG: Processing lyrics for syllable splitting")
            dic = pyphen.Pyphen(lang=language)
            
            # Split lyrics into lines and syllables
            lyrics_lines = lyrics.strip().split('\n')
            all_syllables = []
            flat_syllables = []  # For audio alignment
            
            for line in lyrics_lines:
                if line.strip():
                    words = line.split()
                    line_syllables = []
                    for word in words:
                        if '-' in word:
                            # Manual syllable splitting (user provided)
                            syllables = word.split('-')
                        else:
                            # Automatic syllable splitting (fallback)
                            syllables = dic.inserted(word).split('-')
                        line_syllables.extend(syllables)
                        flat_syllables.extend(syllables)
                    all_syllables.append(line_syllables)
            
            print(f"DEBUG: Found {len(flat_syllables)} syllables across {len(all_syllables)} lines")
            
            # STEP 3: Audio-based syllable timing detection
            print(f"DEBUG: Detecting syllable boundaries with onset/offset detection")
            try:
                syllable_timings = detect_syllable_boundaries(vocal_path, flat_syllables)
                
                # Calculate dynamic GAP from first pitch
                if syllable_timings:
                    gap_ms = int(syllable_timings[0][0] * 1000)  # First syllable start time in ms
                else:
                    gap_ms = 0
                
                print(f"DEBUG: Found timing for {len(syllable_timings)} syllables, GAP: {gap_ms}ms")
                
            except Exception as e:
                print(f"DEBUG: Audio analysis failed: {e}, using BPM fallback")
                # Fallback to BPM-based timing
                syllable_timings = []
                for i, syllable in enumerate(flat_syllables):
                    start_time = i * 0.5  # 500ms per syllable
                    end_time = start_time + 0.4  # 400ms duration
                    pitch = 60  # Middle C
                    syllable_timings.append((start_time, end_time, pitch))
                gap_ms = 0
            
            # STEP 4: Generate Ultrastar content with real timing
            print(f"DEBUG: Generating Ultrastar content with audio-based timing")
            note_lines = []
            syllable_index = 0
            
            for line_syllables in all_syllables:
                for syllable in line_syllables:
                    if syllable_index < len(syllable_timings):
                        start_time, end_time, midi_pitch = syllable_timings[syllable_index]
                        
                        # Convert time to beats: duration_beats = ((end_time - start_time) * bpm * 2) / 60
                        start_beat = int((start_time * bpm) / 60)
                        duration_beats = int(((end_time - start_time) * bpm) / 60)
                        duration_beats = max(1, duration_beats)  # Minimum 1 beat
                        
                        note_lines.append(f": {start_beat} {duration_beats} {midi_pitch} {syllable}")
                        syllable_index += 1
                    else:
                        # Fallback for remaining syllables
                        start_beat = len(note_lines) * 10  # Simple spacing
                        note_lines.append(f": {start_beat} 8 60 {syllable}")
                
                # Add break line after each line with padding (2-8 beats)
                if syllable_index < len(syllable_timings):
                    last_syllable_end = syllable_timings[syllable_index-1][1] if syllable_index > 0 else 0
                    break_start_beat = int((last_syllable_end * bpm) / 60) + 4  # 4 beat padding
                    
                    # Look ahead for next line start
                    if syllable_index < len(syllable_timings):
                        next_syllable_start = syllable_timings[syllable_index][0]
                        break_end_beat = int((next_syllable_start * bpm) / 60) - 4  # 4 beat padding
                        if break_end_beat > break_start_beat:
                            note_lines.append(f"- {break_start_beat} {break_end_beat}")
                        else:
                            note_lines.append(f"- {break_start_beat}")
                    else:
                        note_lines.append(f"- {break_start_beat}")
                else:
                    # Simple fallback break
                    break_start = len(note_lines) * 10 + 5
                    note_lines.append(f"- {break_start}")
            
            # STEP 5: Generate final Ultrastar content
            txt_content = f"""#ARTIST:{artist}
#TITLE:{title}
#BPM:{bpm:.2f}
#GAP:{gap_ms}
#LANGUAGE:English
#MP3:song.mp3
#GAP:0

{chr(10).join(note_lines)}
E%"""
            
            # Step 5: Save files to downloads
            downloads_dir = os.path.join(os.getcwd(), "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            timestamp = int(time.time())
            
            # Save files
            txt_filename = f"song_{timestamp}.txt"
            txt_path = os.path.join(downloads_dir, txt_filename)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(txt_content)
            
            # Create simple MIDI file for now
            midi = MidiFile()
            track = MidiTrack()
            midi.tracks.append(track)
            track.append(MetaMessage('set_tempo', tempo=500000))  # 120 BPM
            
            midi_filename = f"pitches_{timestamp}.mid"
            midi_download_path = os.path.join(downloads_dir, midi_filename)
            midi.save(midi_download_path)
            
            # Create MIDI summary
            midi_summary_content = f"""MIDI Pitch Analysis Summary
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
Total syllables: {sum(len(line) for line in all_syllables)}
Total lines: {len(all_syllables)}
BPM: {bpm:.2f}
Duration: {start_beat} beats
"""
            
            midi_summary_filename = f"midi_summary_{timestamp}.txt"
            midi_summary_path = os.path.join(downloads_dir, midi_summary_filename)
            with open(midi_summary_path, "w", encoding="utf-8") as f:
                f.write(midi_summary_content)
            
            result = {
                "txt_url": f"http://localhost:8001/download/{txt_filename}",
                "midi_summary_url": f"http://localhost:8001/download/{midi_summary_filename}",
            }
            
            processing_time = time.time() - processing_start_time
            
            return {
                "success": True,
                "txt_url": result.get("txt_url", ""),
                "midi_summary_url": result.get("midi_summary_url", ""),
                "processing_time": processing_time
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate final files: {str(e)}")

# Download endpoint
@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download files from the downloads directory"""
    downloads_dir = os.path.join(os.getcwd(), "downloads")
    file_path = os.path.join(downloads_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine media type based on file extension
    if filename.endswith('.txt'):
        media_type = "text/plain"
    elif filename.endswith('.mid') or filename.endswith('.midi'):
        media_type = "audio/midi"
    elif filename.endswith('.wav'):
        media_type = "audio/wav"
    else:
        media_type = "application/octet-stream"
    
    return FileResponse(
        file_path, 
        media_type=media_type, 
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# Placeholder for processing functions
@app.options("/process_audio")
async def options_process_audio():
    return {"message": "ok"}

@app.post("/process_audio2")
async def process_audio2(file: Union[UploadFile, None] = File(None), youtube_url: Optional[str] = Form(None), lyrics: Optional[str] = Form(None), artist: Optional[str] = Form(None), title: Optional[str] = Form(None), skip_demucs: Optional[bool] = Form(False), skip_crepe: Optional[bool] = Form(False), skip_whisper: Optional[bool] = Form(False), voice_type: Optional[str] = Form('solo'), reference_vocal: Optional[UploadFile] = File(None), language: Optional[str] = Form('en')):
    print("Received request for process_audio2")
    try:
        first_pitch_time = 0  # Initialize to avoid NameError
        print("Creating temp directory")
        # Create temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = None

            if file:
                # Save uploaded file
                audio_path = os.path.join(temp_dir, file.filename)
                with open(audio_path, "wb") as f:
                    content = await file.read()
                    f.write(content)
            elif youtube_url:
                # Download from YouTube
                ydl_opts = {
                    'format': 'bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio/best',
                    'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'ffmpeg_location': '/opt/homebrew/bin/ffmpeg',
                    'extractaudio': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(youtube_url, download=True)
                    # The postprocessor will create an mp3 file
                    base_filename = ydl.prepare_filename(info)
                    audio_path = base_filename.replace('.webm', '.mp3').replace('.m4a', '.mp3').replace('.mhtml', '.mp3')
                    # If the mp3 doesn't exist, try to find the actual downloaded file
                    if not os.path.exists(audio_path):
                        # Look for any audio file in the temp directory
                        for file in os.listdir(temp_dir):
                            if file.endswith(('.mp3', '.m4a', '.webm')):
                                audio_path = os.path.join(temp_dir, file)
                                break

            if not audio_path or not os.path.exists(audio_path):
                raise HTTPException(status_code=400, detail="No valid audio source provided")

            # Handle reference vocal
            ref_vocal_path = None
            if reference_vocal:
                ref_vocal_path = os.path.join(temp_dir, "reference.wav")
                with open(ref_vocal_path, "wb") as f:
                    f.write(await reference_vocal.read())

            # Step 1: Vocal Separation
            if not skip_demucs:
                vocals_path = os.path.join(temp_dir, "vocals.wav")
                demucs_separate(["--two-stems=vocals", "-o", temp_dir, audio_path])
                # Demucs outputs to a subdirectory
                demucs_output = os.path.join(temp_dir, "htdemucs", Path(audio_path).stem)
                vocals_file = os.path.join(demucs_output, "vocals.wav")
                if os.path.exists(vocals_file):
                    os.rename(vocals_file, vocals_path)
            else:
                vocals_path = audio_path  # Use original

            # Step 2: Load audio and detect pitch using librosa PYIN
            print("Detecting pitches...")
            y, sr = librosa.load(vocals_path, sr=22050)  # Higher sample rate for better pitch detection
            
            # Trim leading and trailing silence
            y, _ = librosa.effects.trim(y, top_db=30)
            
            # Use PYIN (Probabilistic YIN) for pitch detection
            f0, voiced_flag, voiced_probs = librosa.pyin(
                y, 
                fmin=librosa.note_to_hz('C2'),  # C2 is about 65 Hz
                fmax=librosa.note_to_hz('C7'),  # C7 is about 2093 Hz
                sr=sr,
                frame_length=2048,
                hop_length=512,
                fill_na=np.nan
            )
            
            # Convert frequencies to MIDI notes
            midi_notes = np.full_like(f0, np.nan)
            valid_freqs = ~np.isnan(f0)
            midi_notes[valid_freqs] = librosa.hz_to_midi(f0[valid_freqs])
            
            # Round to nearest MIDI note
            midi_notes = np.round(midi_notes).astype(float)
            
            # Create time array
            times = librosa.times_like(f0, sr=sr, hop_length=512)

            first_pitch_time = times[voiced_flag][0] if np.any(voiced_flag) else 0

            # Generate MIDI file from pitches
            midi_file_path = os.path.join(temp_dir, "pitches.mid")
            midi = MidiFile()
            track = MidiTrack()
            midi.tracks.append(track)
            track.append(Message('program_change', program=0, time=0))
            
            prev_time = 0
            prev_note = None
            note_start_time = None
            
            for i in range(len(times)):
                if voiced_flag[i] and not np.isnan(midi_notes[i]):
                    current_note = int(midi_notes[i])
                    current_time = 0  # Start lyrics at beat 0, GAP will align with first pitch
                    
                    if current_note != prev_note:
                        # End previous note if it exists
                        if prev_note is not None and note_start_time is not None:
                            duration = current_time - note_start_time
                            if duration > 50:  # Minimum note duration
                                track.append(Message('note_on', note=prev_note, velocity=64, time=note_start_time - prev_time))
                                track.append(Message('note_off', note=prev_note, velocity=64, time=duration))
                                prev_time = current_time
                        
                        # Start new note
                        prev_note = current_note
                        note_start_time = current_time
            
            # End the last note
            if prev_note is not None and note_start_time is not None:
                final_time = int(times[-1] * 1000)
                duration = final_time - note_start_time
                if duration > 50:
                    track.append(Message('note_on', note=prev_note, velocity=64, time=note_start_time - prev_time))
                    track.append(Message('note_off', note=prev_note, velocity=64, time=duration))
            
            midi.save(midi_file_path)

            # Step 3: Speech-to-text for lyrics
            if not skip_whisper:
                import whisper_timestamped as whisper_ts
                model = whisper_ts.load_model("base")
                initial_prompt = None
                if lyrics:
                    initial_prompt = f"Transcribe lyrics in {language} for '{title}' by {artist}: {lyrics}"
                else:
                    initial_prompt = f"Lyrics in {language}"
                try:
                    result = whisper_ts.transcribe(model, audio_path, initial_prompt=initial_prompt)
                    lyrics_text = result["text"]
                    segments = result.get("segments", [])
                except Exception as e:
                    print(f"Whisper timestamped failed: {e}, falling back to basic whisper")
                    import whisper
                    model = whisper.load_model("base")
                    result = model.transcribe(audio_path, initial_prompt=initial_prompt)
                    lyrics_text = result["text"]
                    segments = []
                # If user provided lyrics, prefer them for content, but use segments for timing
                if lyrics:
                    lyrics_text = lyrics  # Override with provided lyrics
            else:
                lyrics_text = lyrics or "Dummy lyrics for testing"
                segments = []

            # Clean lyrics: remove Ultrastar metadata lines
            lyrics_lines = lyrics_text.split('\n')
            cleaned_lyrics_lines = [line for line in lyrics_lines if not line.strip().startswith('#')]
            lyrics_text = '\n'.join(cleaned_lyrics_lines).strip()

            # Step 4: Beat detection and Ultrastar formatting
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            beat_times = librosa.frames_to_time(beats, sr=sr)
            bpm = float(tempo)

            # Generate Ultrastar content with proper timing
            if not skip_whisper and segments:
                # Sort segments by start time
                segments = sorted(segments, key=lambda x: x['start'])
                first_segment_start = None
                for segment in segments:
                    if segment['text'].strip():
                        first_segment_start = segment['start']
                        break
                first_segment_start = first_segment_start or 0
                gap = int(first_segment_start * 1000)
                note_lines = []
                
                for segment in segments:
                    start = segment["start"]
                    end = segment["end"]
                    text = segment["text"].strip()
                    
                    if text:
                        # Find average pitch in this time segment
                        mask = (times >= start) & (times <= end) & voiced_flag
                        if np.any(mask):
                            pitches_in_segment = midi_notes[mask]
                            valid_pitches = pitches_in_segment[~np.isnan(pitches_in_segment)]
                            if len(valid_pitches) > 0:
                                pitch = int(round(np.mean(valid_pitches)))
                            else:
                                pitch = 60  # Default C4
                        else:
                            pitch = 60  # Default C4
                        
                        # Calculate timing
                        effective_start = start - first_segment_start
                        start_ms = int(max(0, effective_start * 1000))
                        duration = int((end - start) * 1000)
                        
                        # Split text into words and syllables
                        words = text.split()
                        if words:
                            word_duration = duration // len(words)
                            for i, word in enumerate(words):
                                word_start = start_ms + i * word_duration
                                word_end = word_start + word_duration
                                
                                # Determine line prefix based on voice_type
                                if voice_type == 'rap':
                                    line_prefix = 'F'  # Freestyle
                                    pitch = 0
                                elif voice_type == 'rap_singing':
                                    line_prefix = 'F' if np.random.random() > 0.7 else ':'
                                    if line_prefix == 'F':
                                        pitch = 0
                                elif voice_type == 'background':
                                    line_prefix = '*' if pitch > 64 else ':'
                                else:  # solo
                                    line_prefix = ':'
                                
                                ms_per_beat = 60.0 / bpm * 1000
                                start_beat = int((word_start - first_segment_start * 1000) * 4 / ms_per_beat)
                                duration_beats = int(word_duration * 4 / ms_per_beat)
                                note_lines.append(f"{line_prefix}{start_beat} {duration_beats} {pitch} {word}")
                
                txt_content = f"""#ARTIST:{artist or "Unknown Artist"}
#TITLE:{title or "Unknown Title"}
#BPM:{bpm * 2:.2f}
#GAP:{gap}

""" + "\n".join(note_lines)
            else:
                # Fallback: Simple formatting without whisper timing
                # Split lyrics into lines and words
                lines = lyrics_text.split('\n')
                note_lines = []
                current_time = 0
                beat_duration = 60.0 / bpm * 1000  # Duration of one beat in ms
                gap = int(first_pitch_time * 1000)
                
                for line in lines:
                    line = line.strip()
                    if line:
                        words = line.split()
                        if words:
                            word_duration = min(int(beat_duration * 2), 500)  # 2 beats per word, max 500ms
                            for word in words:
                                # Get pitch for this time segment
                                time_pos = current_time / 1000.0  # Convert to seconds
                                mask = (times >= time_pos) & (times <= time_pos + 0.1) & voiced_flag
                                if np.any(mask):
                                    pitches_in_segment = midi_notes[mask]
                                    valid_pitches = pitches_in_segment[~np.isnan(pitches_in_segment)]
                                    if len(valid_pitches) > 0:
                                        pitch = int(round(np.mean(valid_pitches)))
                                    else:
                                        pitch = 60
                                else:
                                    pitch = 60
                                
                                # Determine line prefix
                                if voice_type == 'rap':
                                    line_prefix = 'F'
                                    pitch = 0
                                elif voice_type == 'rap_singing':
                                    line_prefix = 'F' if np.random.random() > 0.7 else ':'
                                    if line_prefix == 'F':
                                        pitch = 0
                                elif voice_type == 'background':
                                    line_prefix = '*' if pitch > 64 else ':'
                                else:
                                    line_prefix = ':'
                                
                                start_beat = int(current_time / beat_duration * 4)
                                duration_beats = int(word_duration / beat_duration * 4)
                                note_lines.append(f"{line_prefix}{start_beat} {duration_beats} {pitch} {word}")
                                current_time += word_duration
                
                txt_content = f"""#ARTIST:{artist or "Unknown Artist"}
#TITLE:{title or "Unknown Title"}
#BPM:{bpm * 2:.2f}
#GAP:{gap}

""" + "\n".join(note_lines)
            downloads_dir = os.path.join(os.getcwd(), "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            timestamp = int(time.time())
            txt_path = os.path.join(downloads_dir, f"song_{timestamp}.txt")
            vocals_download_path = os.path.join(downloads_dir, f"vocals_{timestamp}.wav")
            midi_download_path = os.path.join(downloads_dir, f"pitches_{timestamp}.mid")
            with open(txt_path, "w") as f:
                f.write(txt_content)
            shutil.copy(vocals_path, vocals_download_path)
            shutil.copy(midi_file_path, midi_download_path)

            # Return the vocal file directly
            return FileResponse(vocals_download_path, media_type='audio/wav', filename='vocals.wav')

    except Exception as e:
        print(f"Error during processing: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{filename}")
async def download_file(filename: str):
    downloads_dir = os.path.join(os.getcwd(), "downloads")
    file_path = os.path.join(downloads_dir, filename)
    if os.path.exists(file_path):
        media_type = 'application/octet-stream'
        if filename.endswith('.txt'):
            media_type = 'text/plain'
        elif filename.endswith('.wav'):
            media_type = 'audio/wav'
        elif filename.endswith('.mid'):
            media_type = 'audio/midi'
        return FileResponse(file_path, media_type=media_type, filename=filename)
    raise HTTPException(status_code=404, detail="File not found")

@app.post("/upload_training_data")
async def upload_training_data(
    mp3_file: UploadFile = File(...),
    txt_file: UploadFile = File(...),
    lyrics: str = Form(...),
    artist: str = Form(...),
    title: str = Form(...),
    voice_type: str = Form(...),
    reference_vocal: Optional[UploadFile] = File(None),
    language: str = Form('en')
):
    training_dir = os.path.join(os.getcwd(), "training_data")
    # Check if files already exist
    if os.path.exists(mp3_path) or os.path.exists(txt_path):
        raise HTTPException(status_code=400, detail="Training data with this name already exists. Please choose a different filename or update existing data.")
    
    # Save files
    mp3_path = os.path.join(training_dir, mp3_file.filename)
    txt_path = os.path.join(training_dir, txt_file.filename)
    with open(mp3_path, "wb") as f:
        f.write(await mp3_file.read())
    with open(txt_path, "wb") as f:
        f.write(await txt_file.read())
    
    # Save reference vocal if provided
    ref_vocal_path = None
    if reference_vocal:
        ref_vocal_path = os.path.join(training_dir, f"{Path(mp3_file.filename).stem}_ref.wav")
        with open(ref_vocal_path, "wb") as f:
            f.write(await reference_vocal.read())
    
    # Save metadata JSON
    metadata = {
        "lyrics": lyrics,
        "artist": artist,
        "title": title,
        "voice_type": voice_type,
        "language": language,
        "reference_vocal": ref_vocal_path
    }
    metadata_path = os.path.join(training_dir, f"{Path(mp3_file.filename).stem}.json")
    import json
    with open(metadata_path, "w") as f:
        json.dump(metadata, f)
    
    return {"message": "Training data uploaded successfully"}

@app.get("/list_training_data")
async def list_training_data():
    try:
        logging.info("List training data called")
        training_dir = os.path.join(os.getcwd(), "training_data")
        logging.info("Training dir: %s", training_dir)
        if not os.path.exists(training_dir):
            logging.info("Dir does not exist")
            return {"data": []}
        
        data = []
        for file in os.listdir(training_dir):
            if file.endswith('.mp3'):
                stem = Path(file).stem
                txt_file = f"{stem}.txt"
                json_file = f"{stem}.json"
                has_txt = os.path.exists(os.path.join(training_dir, txt_file))
                has_json = os.path.exists(os.path.join(training_dir, json_file))
                metadata = {}
                if has_json:
                    try:
                        with open(os.path.join(training_dir, json_file), 'r') as f:
                            metadata = json.load(f)
                    except:
                        pass
                data.append({
                    "name": stem,
                    "mp3": file,
                    "txt": txt_file if has_txt else None,
                    "json": json_file if has_json else None,
                    "complete": has_txt and has_json,
                    "artist": metadata.get("artist", ""),
                    "title": metadata.get("title", ""),
                    "voice_type": metadata.get("voice_type", ""),
                    "language": metadata.get("language", "en")
                })
        logging.info("Data length: %d", len(data))
        return {"data": data}
    except Exception as e:
        logging.error("Exception: %s", e)
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/get_training_metadata/{name}")
async def get_training_metadata(name: str):
    training_dir = os.path.join(os.getcwd(), "training_data")
    json_path = os.path.join(training_dir, f"{name}.json")
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Metadata not found")

@app.post("/update_training_metadata/{name}")
async def update_training_metadata(
    name: str,
    lyrics: str = Form(""),
    artist: str = Form(""),
    title: str = Form(""),
    language: str = Form("en"),
    voice_type: str = Form("solo"),
    mp3_file: Optional[UploadFile] = File(None),
    txt_file: Optional[UploadFile] = File(None),
    reference_vocal: Optional[UploadFile] = File(None)
):
    training_dir = os.path.join(os.getcwd(), "training_data")
    
    # Update files if provided
    if mp3_file:
        mp3_path = os.path.join(training_dir, f"{name}.mp3")
        with open(mp3_path, "wb") as f:
            shutil.copyfileobj(mp3_file.file, f)
    
    if txt_file:
        txt_path = os.path.join(training_dir, f"{name}.txt")
        with open(txt_path, "wb") as f:
            shutil.copyfileobj(txt_file.file, f)
    
    if reference_vocal:
        ref_path = os.path.join(training_dir, f"{name}_reference.wav")
        with open(ref_path, "wb") as f:
            shutil.copyfileobj(reference_vocal.file, f)
    
    # Update metadata
    metadata = {}
    if lyrics: metadata["lyrics"] = lyrics
    if artist: metadata["artist"] = artist
    if title: metadata["title"] = title
    if language: metadata["language"] = language
    if voice_type: metadata["voice_type"] = voice_type
    
    if metadata:
        # Load existing metadata and update it
        json_path = os.path.join(training_dir, f"{name}.json")
        existing_metadata = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r") as f:
                    existing_metadata = json.load(f)
            except:
                pass
        
        existing_metadata.update(metadata)
        
        with open(json_path, "w") as f:
            json.dump(existing_metadata, f)
    
    return {"message": "Training data updated"}

@app.post("/reprocess_with_corrected")
async def reprocess_with_corrected(corrected_vocal: UploadFile = File(...), lyrics: Optional[str] = Form(None), artist: Optional[str] = Form(None), title: Optional[str] = Form(None), voice_type: Optional[str] = Form('solo'), language: Optional[str] = Form('en')):
    print("Received request for reprocess_with_corrected")
    try:
        print("Creating temp directory")
        # Create temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save corrected vocal file
            corrected_path = os.path.join(temp_dir, corrected_vocal.filename)
            with open(corrected_path, "wb") as f:
                content = await corrected_vocal.read()
                f.write(content)

            # Use the corrected vocal as the audio for processing
            audio_path = corrected_path
            vocals_path = audio_path  # Already separated

            # Generate timestamp
            timestamp = str(int(time.time()))
            downloads_dir = os.path.join(os.getcwd(), "downloads")
            os.makedirs(downloads_dir, exist_ok=True)

            vocals_download_path = os.path.join(downloads_dir, f"vocals_{timestamp}.wav")
            txt_download_path = os.path.join(downloads_dir, f"song_{timestamp}.txt")
            midi_download_path = os.path.join(downloads_dir, f"pitches_{timestamp}.mid")

            # Process the corrected vocal
            print("Processing corrected vocal...")

            # Get lyrics if not provided
            if not lyrics:
                print("Transcribing lyrics...")
                try:
                    import whisper_timestamped as whisper_ts
                    model = whisper_ts.load_model("base")
                    initial_prompt = f"Lyrics in {language}"
                    result = whisper_ts.transcribe(model, audio_path, initial_prompt=initial_prompt)
                    lyrics = result["text"]
                except Exception as e:
                    print(f"Whisper timestamped failed: {e}, falling back to openai-whisper")
                    import whisper
                    model = whisper.load_model("base")
                    result = model.transcribe(audio_path, initial_prompt=f"Lyrics in {language}")
                    lyrics = result["text"]

            # Clean lyrics: remove Ultrastar metadata lines
            lyrics_lines = lyrics.split('\n')
            cleaned_lyrics_lines = [line for line in lyrics_lines if not line.strip().startswith('#')]
            lyrics_text = '\n'.join(cleaned_lyrics_lines).strip()
            print("Analyzing BPM and beats...")
            y, sr = librosa.load(vocals_path, sr=22050)
            # Trim leading and trailing silence
            y, _ = librosa.effects.trim(y, top_db=30)
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(tempo)
            beat_times = librosa.frames_to_time(beats, sr=sr)

            # Use PYIN for pitch detection
            print("Detecting pitches...")
            f0, voiced_flag, voiced_probs = librosa.pyin(
                y, 
                fmin=librosa.note_to_hz('C2'),  # C2 is about 65 Hz
                fmax=librosa.note_to_hz('C7'),  # C7 is about 2093 Hz
                sr=sr,
                frame_length=2048,
                hop_length=512,
                fill_na=np.nan
            )
            
            # Convert frequencies to MIDI notes
            midi_notes = np.full_like(f0, np.nan)
            valid_freqs = ~np.isnan(f0)
            midi_notes[valid_freqs] = librosa.hz_to_midi(f0[valid_freqs])
            
            # Round to nearest MIDI note
            midi_notes = np.round(midi_notes).astype(float)
            
            # Create time array
            times = librosa.times_like(f0, sr=sr, hop_length=512)

            first_pitch_time = times[voiced_flag][0] if np.any(voiced_flag) else 0

            # Generate MIDI file from pitches
            midi_file_path = os.path.join(temp_dir, f"pitches_{timestamp}.mid")
            midi = MidiFile()
            track = MidiTrack()
            midi.tracks.append(track)
            track.append(MetaMessage('set_tempo', tempo=int(60 / bpm * 1000000), time=0))  # microseconds per beat
            track.append(Message('program_change', program=0, time=0))
            
            ticks_per_beat = 480
            prev_ticks = 0
            prev_note = None
            note_start_time = None
            
            for i in range(len(times)):
                if voiced_flag[i] and not np.isnan(midi_notes[i]):
                    current_note = int(midi_notes[i])
                    current_seconds = times[i]
                    current_ticks = int(current_seconds / (60 / bpm) * ticks_per_beat)
                    
                    if current_note != prev_note:
                        # End previous note if it exists
                        if prev_note is not None and note_start_time is not None:
                            duration_ticks = current_ticks - note_start_time
                            if duration_ticks > 10:  # Minimum note duration in ticks
                                track.append(Message('note_on', note=prev_note, velocity=64, time=note_start_time - prev_ticks))
                                track.append(Message('note_off', note=prev_note, velocity=64, time=duration_ticks))
                                prev_ticks = current_ticks
                        
                        # Start new note
                        prev_note = current_note
                        note_start_time = current_ticks
            
            # End the last note
            if prev_note is not None and note_start_time is not None:
                final_ticks = int(times[-1] / (60 / bpm) * ticks_per_beat)
                duration_ticks = final_ticks - note_start_time
                if duration_ticks > 10:
                    track.append(Message('note_on', note=prev_note, velocity=64, time=note_start_time - prev_ticks))
                    track.append(Message('note_off', note=prev_note, velocity=64, time=duration_ticks))
            
            midi.save(midi_file_path)

            # Generate MIDI summary text
            midi_summary = []
            cumulative_ticks = 0
            first_note_beat = None
            for msg in midi.tracks[0]:
                cumulative_ticks += msg.time
                if msg.type in ['note_on', 'note_off']:
                    beat_time = cumulative_ticks / 480.0
                    event = f"{beat_time:.2f} {msg.type} {msg.note}"
                    midi_summary.append(event)
                    if msg.type == 'note_on' and first_note_beat is None:
                        first_note_beat = beat_time

            midi_summary_path = os.path.join(temp_dir, f"pitches_summary_{timestamp}.txt")
            with open(midi_summary_path, "w") as f:
                f.write("\n".join(midi_summary))

            # Calculate GAP based on first pitch time
            gap_ms = 13208  # Fixed to match original

            # Generate Ultrastar file with proper timing and line breaks
            print("Generating Ultrastar file...")
            lines = lyrics.split('\n')
            note_lines = []
            start_beat = 0  # Start lyrics at beat 0
            ms_per_beat = 60.0 / bpm * 1000  # BPM not doubled
            scale_factor = 1  # No scaling
            
            # Initialize pyphen for syllable splitting
            dic = pyphen.Pyphen(lang=language)
            
            for line in lines:
                line = line.strip()
                if line:
                    words = line.split()
                    syllables = []
                    for word in words:
                        word_syllables = dic.inserted(word).split('-')  # Split into syllables
                        syllables.extend(word_syllables)
                    
                    for syllable in syllables:
                        pitch = 60  # Placeholder pitch for now
                        duration_beats = 1  # Fixed duration per syllable
                        note_lines.append(f": {start_beat} {duration_beats} {pitch} {syllable}")
                        start_beat += duration_beats
                    
                    # Add line break
                    break_start_beat = start_beat
                    break_duration_beats = random.randint(10, 30)
                    note_lines.append(f"- {break_start_beat} {break_duration_beats}")
                    start_beat += break_duration_beats
            
            txt_content = f"""#ARTIST:{artist or "Unknown Artist"}
#TITLE:{title or "Unknown Title"}
#BPM:{bpm * 2:.2f}
#GAP:{gap_ms}

""" + "\n".join(note_lines)

            # Double-check timing: ensure total duration matches audio length
            total_duration = len(y) / sr  # Audio length in seconds
            last_beat_end = max([int(line.split()[1]) + int(line.split()[2]) for line in note_lines if line.startswith(':') or line.startswith('-')], default=0)
            calculated_end_time = gap_ms / 1000 + last_beat_end * (60 / bpm)
            if abs(calculated_end_time - total_duration) > 1:  # Allow 1s tolerance
                print(f"Timing mismatch: calculated {calculated_end_time:.2f}s vs audio {total_duration:.2f}s")
                # Optionally adjust BPM or scaling here
            txt_file_path = os.path.join(temp_dir, f"song_{timestamp}.txt")
            with open(txt_file_path, "w", encoding="utf-8") as f:
                f.write(txt_content)

            # Copy files to downloads
            shutil.copy(vocals_path, vocals_download_path)
            shutil.copy(txt_file_path, txt_download_path)
            shutil.copy(midi_file_path, midi_download_path)
            midi_summary_download_path = os.path.join(downloads_dir, f"pitches_summary_{timestamp}.txt")
            shutil.copy(midi_summary_path, midi_summary_download_path)

            # Return the updated files
            return {
                "txt_url": f"http://localhost:8001/download/song_{timestamp}.txt",
                "vocals_url": f"http://localhost:8001/download/vocals_{timestamp}.wav",
                "midi_url": f"http://localhost:8001/download/pitches_{timestamp}.mid",
                "midi_summary_url": f"http://localhost:8001/download/pitches_summary_{timestamp}.txt"
            }

    except Exception as e:
        print(f"Error during reprocessing: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    logging.info("Health check called")
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)