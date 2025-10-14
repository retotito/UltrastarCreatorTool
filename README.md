# Ultrastar Song Generator

A comprehensive tool to generate high-quality Ultrastar karaoke song files with professional-grade audio processing and timing accuracy.

## Features

### Core Functionality
- **Manual Audio Input**: Upload pre-processed vocal tracks for optimal quality
- **Lyrics-Driven Processing**: User provides pre-syllabified lyrics for accuracy
- **Advanced Audio Analysis**: PYIN pitch detection, BPM analysis, onset/offset detection
- **Intelligent Timing**: Syllable boundary detection with multiple fallback strategies
- **Multi-Format Output**: Ultrastar .txt, MIDI files, and detailed processing summaries

### Advanced Pipeline
- **Syllable Duration Calculation**: Audio-based timing with onset/offset detection
- **Pitch Grouping**: Noise filtering and multi-pitch handling for stable notes
- **Dynamic GAP Calculation**: Precise timing from first pitch detection
- **Break Line Padding**: Prevents word concatenation in game display
- **Rap Section Support**: Special handling for spoken word sections
- **Comprehensive Logging**: Detailed processing information and fallback tracking

### Technical Features
- **Service Architecture**: Modular backend with specialized audio processing services
- **Change Tracking**: Development safety with modification logging
- **Baseline Validation**: Regression prevention during development
- **Health Monitoring**: System status and configuration endpoints

## Tech Stack

- **Frontend**: Svelte with Vite for responsive user interface
- **Backend**: Python FastAPI with modular service architecture
- **Audio Processing**: librosa (PYIN, BPM), onset detection, pitch analysis
- **Output Generation**: Ultrastar format, MIDI synthesis, processing summaries
- **Development**: Git workflow, comprehensive logging, pipeline documentation

## Pipeline Approach

### Modern Workflow (v3.0)
This tool follows a **manual-input, high-quality output** approach:

1. **User Preparation**: 
   - Manually edit vocal audio to include only sung content
   - Pre-syllabify lyrics using `-` separators (e.g., `beau-ti-ful`)
   - Mark rap sections with special markers

2. **Audio Analysis**:
   - PYIN pitch detection with noise filtering
   - Onset/offset detection for syllable boundaries
   - BPM analysis and dynamic GAP calculation

3. **Intelligent Timing**:
   - Audio-based syllable duration calculation
   - Multiple fallback strategies for unclear sections
   - Break line timing with proper padding

4. **Quality Output**:
   - Accurate Ultrastar .txt files
   - MIDI files for pitch reference
   - Detailed processing summaries for manual refinement

## Architecture

### Service Architecture (v2.0)
The backend has been refactored from a monolithic structure into specialized services:

- **AudioProcessingService**: Handles vocal separation, BPM detection, and pitch analysis
- **LyricsProcessingService**: Manages transcription and syllable splitting
- **UltrastarGeneratorService**: Creates properly formatted Ultrastar files
- **MidiGeneratorService**: Generates MIDI files from pitch data
- **Configuration Management**: Centralized config with locked working values
- **Change Tracking**: Prevents circular debugging by logging all modifications
- **Baseline Validation**: Ensures no regressions during development

### API Endpoints
- `POST /generate_final_files` - Main processing endpoint for Ultrastar generation
- `POST /extract_vocals` - Vocal separation using Demucs (optional preprocessing)
- `GET /test_files` - Load test files for development and validation
- `GET /health` - Service health check
- `GET /status` - System status with configuration and recent changes
- `GET /download/{filename}` - Download generated files

### Pipeline Documentation
See `docs/PIPELINE.md` for comprehensive processing pipeline specification including:
- Detailed syllable timing algorithms
- Audio analysis parameters
- Edge case handling
- Logging and debugging strategies

## Setup

### Prerequisites
- Node.js (for frontend)
- Python 3.8+ (for backend)
- FFmpeg (for audio processing)

### Installation

1. Clone the repository
2. Install frontend dependencies:
   ```bash
   npm install
   ```
3. Install backend dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

### Running

1. Start the backend:
   ```bash
   cd backend
   python main.py
   ```
2. Start the frontend:
   ```bash
   npm run dev
   ```

## Usage

Upload an audio file or paste a YouTube URL, and the app will process it to generate an Ultrastar song file.

## Development

### Systematic Development Practices

To prevent circular debugging and maintain development momentum:

1. **Use Baseline Testing**: Before making changes, run baseline tests:
   ```bash
   cd backend
   python -m pytest tests/test_baseline.py
   ```

2. **Monitor Changes**: All modifications are logged via the change tracking system. Check recent changes:
   ```bash
   curl http://localhost:8000/status
   ```

3. **Validate Before Changes**: Use the validation endpoint to test modifications:
   ```bash
   curl -X POST http://localhost:8000/validate \
     -H "Content-Type: application/json" \
     -d '{"content": "your_ultrastar_content"}'
   ```

4. **Locked Configuration**: Working values in `config.py` are locked. Only change after baseline testing:
   - `REFERENCE_BPM = 272.0`
   - `REFERENCE_GAP = 13208`
   - `SYLLABLE_DURATION_BEATS = 1`

### Service Structure

```
backend/
├── main.py                    # Refactored API endpoints
├── config.py                  # Configuration management
├── models.py                  # Pydantic models
├── services/
│   ├── audio_processor.py     # Audio analysis
│   ├── lyrics_processor.py    # Lyrics processing
│   ├── ultrastar_generator.py # File generation
│   └── midi_generator.py      # MIDI creation
└── tests/
    └── test_baseline.py       # Baseline validation
```

This architecture prevents the circular debugging loops by:
- Isolating functionality into services
- Tracking all changes with timestamps and reasons
- Validating against known working outputs
- Locking proven configuration values