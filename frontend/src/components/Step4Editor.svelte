<script>
  import { onMount, onDestroy } from 'svelte';
  import { sessionId, generationResult, editorState, errorMessage, lyricsData, currentStep } from '../stores/appStore.js';
  import { getEditorData, getAudioUrl, saveEditorState } from '../services/api.js';
  import { PitchDetector } from 'pitchy';

  // Canvas refs
  let canvasEl;
  let ctx;

  // Data
  let notes = [];
  let bpm = 272;
  let gapMs = 0;
  let audioDuration = 0;
  let vocalUrl = '';

  // Raw ms timings for BPM re-quantization
  let rawTimings = [];   // syllable_timings from backend (start/end in seconds)
  let pitchMap = [];     // midi pitch per syllable (extracted from initial Ultrastar parse)
  let initialBpm = 0;    // original detected BPM
  let initialGap = 0;    // original detected GAP
  let bpmChanged = false; // track if user modified BPM/GAP

  // Save state
  let isSaving = false;
  let lastSaveTime = null;
  let editCount = 0;
  let hasUnsavedChanges = false;

  // View state
  let scrollX = 0;
  let zoom = 20;          // pixels per beat (default zoomed in)
  let viewHeight = 460;
  let noteHeight = 8;

  // Pitch range (MIDI)
  let minPitch = 36;     // C2
  let maxPitch = 96;     // C7

  // Interaction
  let selectedNote = null;
  let selectedNotes = new Set(); // multi-select
  let dragMode = null;     // 'move' | 'resize-left' | 'resize-right'
  let dragStart = { x: 0, y: 0 };
  let isDragging = false;
  let scrollBarEl;

  // Rubber-band (box) selection
  let isBoxSelecting = false;
  let boxSelectStart = { x: 0, y: 0 };
  let boxSelectEnd = { x: 0, y: 0 };

  // Clipboard (cut/copy/paste)
  let clipboard = null;        // { notes: [...], mode: 'cut'|'copy', sourceBeat: number }
  let pasteMode = false;       // user is positioning the paste
  let pastePreviewBeat = null; // ghost preview beat position
  let cutNoteIds = new Set();  // ids of notes being cut (rendered semi-transparent)

  // Set GAP mode (Ctrl/Cmd+S)
  let setGapMode = false;       // user is picking a new GAP position
  let setGapHoverBeat = null;   // beat of the grid line currently hovered

  // Grid Align mode (Ctrl/Cmd+G)
  let gridAlignMode = false;       // user is sliding the grid
  let gridAlignOffsetMs = 0;       // accumulated offset in ms (preview only)
  let gridAlignOriginalGapMs = 0;  // gapMs before entering mode (for Esc revert)
  let gridAlignDragging = false;   // currently dragging
  let gridAlignDragStartX = 0;     // mouse X at drag start
  let gridAlignDragStartOffsetMs = 0; // offset at drag start

  // Drag pitch preview (oscillator while dragging a note)
  let dragOsc = null;
  let dragGain = null;
  let dragAudioCtx = null;
  let dragLastPitch = null;

  // Context menu
  let contextMenu = { visible: false, x: 0, y: 0, noteId: null, isBreak: false, isEmpty: false, beat: 0, pitch: 0 };
  let editingSyllable = '';
  let contextMenuEl;

  // Undo/Redo history
  let undoStack = [];
  let redoStack = [];
  const MAX_UNDO = 50;

  // Playback
  let audioEl;
  let isPlaying = false;
  let playbackBeat = 0;
  let animFrame;
  let currentTimeSec = 0;  // Reactive time display

  // Scroll mode: notes scroll, cursor stays fixed
  let scrollMode = false;

  // Playback speed
  let playbackRate = 1.0;

  // MIDI pitch playback during track play
  let midiPlayback = false;
  let muteVocal = false;
  let audioVolume = 0.8; // 0..1 audio volume
  let midiAudioCtx = null;
  let midiActiveNotes = new Map(); // noteId -> { osc, gain }
  let midiVolume = 0.25;

  // Loop region
  let loopEnabled = false;
  let loopStartBeat = null;  // beat where loop begins
  let loopEndBeat = null;    // beat where loop ends
  let isSettingLoop = false; // dragging on time axis to set loop
  let loopDragStartBeat = null; // beat where loop drag began
  let loopHandleDrag = null; // 'start' or 'end' when dragging a loop handle

  // Playhead drag / scrub
  let playheadDrag = false;
  let scrubAudio = true; // hear audio while dragging playhead
  let scrubAudioBuffer = null; // decoded AudioBuffer for grain scrub
  let scrubCtx = null;         // AudioContext for scrub grains
  let scrubSource = null;      // current BufferSourceNode
  let scrubGain = null;        // gain node for scrub

  // Metronome
  let metronomeEnabled = false;
  let metronomeCtx = null;
  let lastMetronomeBeat = -1; // tracks which quarter-note beat we last clicked
  let metronomeOffset = 0;    // offset in ultrastar beats (0 = on beat, 4 = half beat / 8th note off)
  const BEATS_PER_QUARTER = 8; // 8 ultrastar beats = 1 real quarter note (BPM is doubled, formula uses /15)
  const BEATS_PER_MEASURE = BEATS_PER_QUARTER * 4; // 32 ultrastar beats = 1 measure (4/4 time)

  // Downbeat offset: ms from audio 0s to first downbeat
  let downbeatOffsetMs = 0;
  let downbeatFromHeader = false; // true if loaded from #DOWNBEATOFFSET header

  // Waveform
  let waveformPeaks = [];   // pre-computed peaks array
  let waveformDuration = 0; // actual decoded audio duration (seconds)
  let showWaveform = true;
  let waveformHeight = 60; // px reserved at top of canvas for waveform (adjustable)

  // Beat Marker BPM Calibration
  // Each marker: { t: seconds, bar: integer (1-based bar number in the song) }
  let beatMarkers = [];
  let beatMarkerMode = false;
  let bpmCalcResult = null; // { bpm, gapMs } computed from linear regression

  // Audio source toggle (vocals vs full mix)
  let audioSource = 'vocals'; // 'vocals' | 'original'
  let originalUrl = '';
  let hasVocalsAudio = true;
  let hasOriginalAudio = true;

  // Mic sing-along
  let micEnabled = false;
  let micShowTrail = true;
  let micStream = null;
  let micAudioCtx = null;
  let micAnalyser = null;
  let micSourceNode = null;
  let micDetector = null;
  let micInputBuffer = null;
  let micPitchTrail = [];    // array of { time, pitch, rawPitch, clarity }
  let micDevices = [];       // available audio input devices
  let micDeviceId = '';      // selected device (empty = default)
  let micClarityThreshold = 0.8;
  let micStarting = false; // true while mic is initializing
  let micRecorder = null;   // MediaRecorder for voice capture
  let micRecordedChunks = []; // recorded audio chunks
  let micRecordingStartTime = 0; // playback time when recording started
  let micGain = 1.0;        // mic volume gain (0-2)
  let micGainNode = null;   // GainNode for mic volume control
  let micLevel = 0;         // current mic input level (0-1) for indicator
  let micLevelTimer = null; // interval for level polling
  // Sticky prediction state for smoothing
  let micLastPitch = -1;
  let micPitchConfidence = 0;
  let micRecentPitches = []; // rolling window for median smoothing

  // USDX-style sung note tracking: Map<noteId, [{beat, sungPitch, isHit}]>
  let micNoteHits = new Map();
  let micShowRawTrail = false; // optional raw pitch trail for debugging

  // Text editor modal
  let showTextEditor = false;
  let textEditorContent = '';

  // Extra Ultrastar headers (e.g. #YOUTUBE, #COVER, etc.) — preserved across edits
  let extraHeaders = [];

  // Total beats for scrollbar
  let totalBeats = 0;

  // Guard: which session has already loaded data (prevent reactive re-load)
  let dataLoadedSession = null;

  // Parse Ultrastar content into notes array
  function parseUltrastar(content) {
    const lines = content.split('\n');
    const parsed = [];
    let id = 0;

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('*') || trimmed.startsWith(':') || trimmed.startsWith('F:')) {
        const isGolden = trimmed.startsWith('*');
        const isRap = trimmed.startsWith('F:');
        let prefix;
        if (isRap) prefix = 'F:';
        else if (isGolden) prefix = '*';
        else prefix = ':';
        // Parse 3 numeric fields, then preserve the rest as syllable text
        // (including any leading space which signals a word boundary in Ultrastar)
        const rest = trimmed.substring(prefix.length);
        const match = rest.match(/^\s+(-?\d+)\s+(\d+)\s+(-?\d+) (.*)$/);
        
        if (match) {
          const startBeat = parseInt(match[1]);
          const duration = parseInt(match[2]);
          const pitch = parseInt(match[3]);
          const syllable = match[4];

          parsed.push({
            id: id++,
            startBeat,
            duration,
            pitch,
            syllable,
            isRap,
            isGolden: isGolden || false,
            confidence: 1.0,
            original: { startBeat, duration, pitch },
          });
        }
      } else if (trimmed.startsWith('-')) {
        // Break line — store for rendering
        const parts = trimmed.substring(1).trim().split(/\s+/);
        parsed.push({
          id: id++,
          type: 'break',
          startBeat: parseInt(parts[0]) || 0,
          endBeat: parseInt(parts[1]) || null,
        });
      }
    }

    return parsed;
  }

  // Calculate pitch range from notes
  function updatePitchRange() {
    const pitchNotes = notes.filter(n => n.pitch !== undefined && n.type !== 'break');
    if (pitchNotes.length === 0) return;
    
    const pitches = pitchNotes.map(n => n.pitch);
    minPitch = Math.min(...pitches) - 6;
    maxPitch = Math.max(...pitches) + 6;
    // Ensure at least 12 semitones visible (one octave)
    if (maxPitch - minPitch < 12) {
      const mid = (minPitch + maxPitch) / 2;
      minPitch = Math.floor(mid - 6);
      maxPitch = Math.ceil(mid + 6);
    }
  }

  // Beat to X pixel
  function beatToX(beat) {
    return (beat * zoom) - scrollX;
  }

  // X pixel to beat
  function xToBeat(x) {
    return (x + scrollX) / zoom;
  }

  // Waveform top offset (only when waveform is visible)
  function waveTop() {
    return showWaveform ? waveformHeight : 0;
  }

  // Pitch to Y pixel (piano area only, excluding time axis at bottom and waveform at top)
  function pitchToY(pitch) {
    const range = maxPitch - minPitch;
    const wt = waveTop();
    const pianoH = viewHeight - 22 - wt; // exclude time axis and waveform
    const ratio = (maxPitch - pitch) / range;
    return wt + ratio * (pianoH - 40) + 20;
  }

  // Y pixel to pitch
  function yToPitch(y) {
    const range = maxPitch - minPitch;
    const wt = waveTop();
    const pianoH = viewHeight - 22 - wt;
    const ratio = (y - wt - 20) / (pianoH - 40);
    return Math.round(maxPitch - ratio * range);
  }

  // Note name helper
  function noteName(midi) {
    const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
    return `${names[((midi % 12) + 12) % 12]}${Math.floor(midi / 12) - 1}`;
  }

  // Beat to time (seconds) conversion
  // Standard Ultrastar: beats are quarter-beats, so time = gap + beat * 15 / BPM
  function beatToTime(beat) {
    const gapSec = gapMs / 1000;
    return gapSec + (beat * 15) / bpm;
  }

  // Time to beat conversion
  function timeToBeat(timeSec) {
    const gapSec = gapMs / 1000;
    return ((timeSec - gapSec) * bpm) / 15;
  }

  // Minimum beat (corresponds to audio time 0) — negative when GAP > 0
  // Pad by 2 beats so the playhead at time 0 is visible and not clipped at the edge
  function getMinBeat() {
    return timeToBeat(0) - 2;
  }

  // Format seconds as m:ss.mmm
  function formatTime(seconds) {
    if (seconds < 0) seconds = 0;
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);
    return `${m}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
  }

  // Time axis height
  const timeAxisHeight = 22;

  // Compute total beats from notes for scrollbar range
  function computeTotalBeats() {
    const realNotes = notes.filter(n => n.type !== 'break');
    if (realNotes.length === 0) {
      totalBeats = Math.max(100, timeToBeat(audioDuration || 60));
    } else {
      const last = realNotes[realNotes.length - 1];
      totalBeats = Math.max(last.startBeat + last.duration + 50, timeToBeat(audioDuration || 60));
    }
  }

  // Update scrollbar from scrollX
  function syncScrollbar() {
    if (scrollBarEl) {
      scrollBarEl.value = scrollX / zoom;
    }
  }

  // ──── BPM Re-quantization ────────────────────
  // Rebuild notes from raw ms timings using the current bpm/gapMs,
  // preserving pitches from the original Ultrastar parse.
  function requantizeFromMs() {
    if (!rawTimings || rawTimings.length === 0) {
      console.log('[Requantize] No rawTimings, skipping');
      return;
    }
    console.log(`[Requantize] bpm=${bpm} gap=${gapMs}ms, ${rawTimings.length} timings`);

    const gapSec = gapMs / 1000;
    let id = 0;
    let prevLineIndex = null;
    let lastEndBeat = 0;
    const newNotes = [];

    for (let i = 0; i < rawTimings.length; i++) {
      const timing = rawTimings[i];
      const startSec = timing.start;
      const endSec = timing.end;
      const lineIndex = timing.line_index ?? 0;

      // Insert break between phrases
      if (prevLineIndex !== null && lineIndex !== prevLineIndex) {
        const breakStart = lastEndBeat + 2;
        const nextStartBeat = Math.max(0, Math.round(((startSec - gapSec) * bpm) / 15));
        const breakEnd = Math.max(breakStart + 1, nextStartBeat - 2);
        if (breakEnd > breakStart) {
          newNotes.push({ id: id++, type: 'break', startBeat: breakStart, endBeat: breakEnd });
        } else {
          newNotes.push({ id: id++, type: 'break', startBeat: breakStart, endBeat: null });
        }
      }

      let startBeat = Math.max(0, Math.round(((startSec - gapSec) * bpm) / 15));
      let endBeat   = Math.max(startBeat + 1, Math.round(((endSec - gapSec) * bpm) / 15));

      // Prevent overlap with previous note
      if (startBeat <= lastEndBeat && newNotes.some(n => n.type !== 'break')) {
        startBeat = lastEndBeat + 1;
        endBeat = Math.max(startBeat + 1, endBeat);
      }

      const duration = Math.max(1, endBeat - startBeat);
      const pitch = pitchMap[i] ?? 60;

      newNotes.push({
        id: id++,
        startBeat,
        duration,
        pitch,
        syllable: timing.syllable,
        isRap: timing.is_rap ?? false,
        confidence: timing.confidence ?? 1.0,
        original: { startBeat, duration, pitch },
      });

      lastEndBeat = startBeat + duration;
      prevLineIndex = lineIndex;
    }

    notes = newNotes;
    console.log(`[Requantize] Built ${newNotes.filter(n => n.type !== 'break').length} notes, ${newNotes.filter(n => n.type === 'break').length} breaks`);
    updatePitchRange();
    computeTotalBeats();
    draw();
  }

  // Track unsaved changes on note edits
  function markUnsaved() {
    hasUnsavedChanges = true;
    editorState.update(s => ({ ...s, hasChanges: true }));
  }

  // ──── Undo / Redo ───────────────────────────
  function snapshot() {
    return {
      notes: JSON.parse(JSON.stringify(notes)),
      bpm,
      gapMs,
      downbeatOffsetMs,
      downbeatFromHeader,
      extraHeaders: JSON.parse(JSON.stringify(extraHeaders)),
    };
  }

  function restoreSnapshot(snap) {
    notes = snap.notes;
    if (snap.bpm !== undefined) bpm = snap.bpm;
    if (snap.gapMs !== undefined) gapMs = snap.gapMs;
    if (snap.downbeatOffsetMs !== undefined) downbeatOffsetMs = snap.downbeatOffsetMs;
    if (snap.downbeatFromHeader !== undefined) downbeatFromHeader = snap.downbeatFromHeader;
    if (snap.extraHeaders !== undefined) extraHeaders = snap.extraHeaders;

    selectedNote = null;
    selectedNotes = new Set();
    closeContextMenu();
    markUnsaved();
    updatePitchRange();
    computeTotalBeats();
    draw();
  }

  function pushUndo() {
    undoStack.push(snapshot());
    if (undoStack.length > MAX_UNDO) undoStack.shift();
    redoStack = []; // new action clears redo
  }

  function undo() {
    if (undoStack.length === 0) return;
    redoStack.push(snapshot());
    restoreSnapshot(undoStack.pop());
    console.log(`[Undo] Restored (${undoStack.length} left, ${redoStack.length} redo)`);
  }

  function redo() {
    if (redoStack.length === 0) return;
    undoStack.push(snapshot());
    restoreSnapshot(redoStack.pop());
    console.log(`[Redo] Restored (${undoStack.length} undo, ${redoStack.length} left)`);
  }

  // Save current editor state to backend
  async function handleSave() {
    if (!$sessionId || isSaving) return;
    isSaving = true;
    try {
      // Serialize notes for the API
      const noteData = notes.map(n => {
        if (n.type === 'break') {
          return { type: 'break', startBeat: n.startBeat, endBeat: n.endBeat || null };
        }
        return {
          startBeat: n.startBeat,
          duration: n.duration,
          pitch: n.pitch,
          syllable: n.syllable,
          isRap: n.isRap || false,
          isGolden: n.isGolden || false,
        };
      });

      // Include downbeat offset in extra headers for persistence
      const headersToSave = [...extraHeaders];
      if (downbeatOffsetMs !== 0) {
        headersToSave.push({ key: 'DOWNBEATOFFSET', value: String(Math.round(downbeatOffsetMs)) });
      }
      const result = await saveEditorState($sessionId, noteData, bpm, gapMs, headersToSave);
      editCount = result.edit_count || editCount + 1;
      lastSaveTime = new Date();
      hasUnsavedChanges = false;
      editorState.update(s => ({ ...s, hasChanges: false }));
      console.log(`[Step4] Saved: ${result.note_count} notes, save #${editCount}`);
    } catch (err) {
      console.error('[Step4] Save error:', err);
      errorMessage.set('Save failed: ' + err.message);
    } finally {
      isSaving = false;
    }
  }

  // Reload editor data from backend (discard unsaved changes)
  async function handleReload() {
    if (hasUnsavedChanges && !confirm('Discard unsaved changes and reload from last save?')) return;
    dataLoadedSession = null; // Force re-load
    await loadData();
    hasUnsavedChanges = false;
    editorState.update(s => ({ ...s, hasChanges: false }));
  }

  // Keyboard shortcut: Ctrl/Cmd+S to enter Set GAP mode (or save if already in setGapMode)
  function handleKeydownSave(e) {
    if (showTextEditor) return; // skip when text editor is open
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
      e.preventDefault();
      if (setGapMode) {
        // Already in set-gap mode — exit
        cancelSetGapMode();
      } else if (!isPlaying) {
        // Enter set-gap mode (not while playing)
        setGapMode = true;
        setGapHoverBeat = null;
        if (canvasEl) canvasEl.style.cursor = 'crosshair';
        draw();
      }
    }
  }

  function cancelSetGapMode() {
    setGapMode = false;
    setGapHoverBeat = null;
    if (canvasEl) canvasEl.style.cursor = '';
    draw();
  }

  // ── Grid Align mode functions ──
  function enterGridAlignMode() {
    if (isPlaying) return; // don't enter while playing
    gridAlignMode = true;
    gridAlignOffsetMs = 0;
    gridAlignOriginalGapMs = gapMs;
    gridAlignDragging = false;
    if (canvasEl) canvasEl.style.cursor = 'ew-resize';
    draw();
  }

  function confirmGridAlign() {
    pushUndo();

    // Shift downbeat by the exact drag amount — grid stays where user placed it
    downbeatOffsetMs += gridAlignOffsetMs;
    downbeatFromHeader = true;

    // Snap GAP to the closest grid line (before or after current GAP)
    const beatDuration = 15000 / bpm; // ms per 1/8-note beat
    const gapRelToDownbeat = gridAlignOriginalGapMs - downbeatOffsetMs; // ms from downbeat to GAP
    const beatsFromDownbeat = gapRelToDownbeat / beatDuration;
    const beatBefore = Math.floor(beatsFromDownbeat);
    const beatAfter = Math.ceil(beatsFromDownbeat);
    const msBefore = downbeatOffsetMs + beatBefore * beatDuration;
    const msAfter = downbeatOffsetMs + beatAfter * beatDuration;
    // Pick whichever grid line is closer to the original GAP
    gapMs = Math.round(
      Math.abs(gridAlignOriginalGapMs - msBefore) <= Math.abs(gridAlignOriginalGapMs - msAfter)
        ? msBefore : msAfter
    );

    gridAlignMode = false;
    gridAlignOffsetMs = 0;
    gridAlignDragging = false;
    if (canvasEl) canvasEl.style.cursor = '';
    handleBpmGapChange();
    markUnsaved();
  }

  function cancelGridAlign() {
    console.log(`[GridAlign] Cancel, reverting to gap=${gridAlignOriginalGapMs}ms`);
    gapMs = gridAlignOriginalGapMs;
    gridAlignMode = false;
    gridAlignOffsetMs = 0;
    gridAlignDragging = false;
    if (canvasEl) canvasEl.style.cursor = '';
    draw();
  }

  /** Convert a ms offset to a pixel offset at the current zoom/bpm */
  function msToPixels(ms) {
    // 1 beat = zoom pixels, 1 beat = 15000/bpm ms
    // so 1ms = zoom * bpm / 15000 pixels
    return (ms / 1000) * (bpm / 15) * zoom;
  }

  /** Convert a pixel offset to ms at the current zoom/bpm */
  function pixelsToMs(px) {
    return (px / zoom) * (15000 / bpm);
  }

  /** Max allowed GAP time (seconds) = earliest raw timing start */
  function getMaxGapSec() {
    if (rawTimings && rawTimings.length > 0) {
      return Math.min(...rawTimings.map(t => t.start));
    }
    // Fallback: earliest note's time
    if (notes.length > 0) {
      const firstBeat = Math.min(...notes.filter(n => n.type !== 'break').map(n => n.startBeat));
      return beatToTime(firstBeat);
    }
    return Infinity;
  }

  /** Find the nearest visible grid line beat to a given x pixel */
  function nearestGridBeat(mx) {
    const beat = xToBeat(mx);
    // Snap to the nearest integer beat (every ultrastar beat is a grid line)
    // But only to lines that are actually visible at the current zoom level
    const beatsPerMeasure = BEATS_PER_QUARTER * 4;
    const beatsPerEighth = BEATS_PER_QUARTER / 2;
    let snapResolution;
    if (zoom >= 4) {
      snapResolution = 1;  // every beat line visible
    } else {
      snapResolution = beatsPerEighth; // only eighth-note and above lines visible
    }
    const snapped = Math.round(beat / snapResolution) * snapResolution;
    return snapped;
  }

  // Handle BPM or GAP adjustment — re-quantize visually
  function handleBpmGapChange() {
    console.log(`[BPM/GAP] bpm=${bpm} gap=${gapMs} (initial: bpm=${initialBpm} gap=${initialGap})`);
    bpmChanged = (bpm !== initialBpm || gapMs !== initialGap);
    // Recalculate playback cursor position with new BPM/GAP
    if (currentTimeSec > 0) {
      const gapSec = gapMs / 1000;
      playbackBeat = ((currentTimeSec - gapSec) * bpm) / 15;
    }
    requantizeFromMs();
  }

  // ──── Beat Marker / BPM Calibration ────────────────────────────────
  function enterBeatMarkerMode() {
    beatMarkers = [];
    bpmCalcResult = null;
    beatMarkerMode = true;
  }

  function exitBeatMarkerMode() {
    beatMarkerMode = false;
    beatMarkers = [];
    bpmCalcResult = null;
  }

  // Linear regression: time = a + b * (barNumber - 1)
  // b = seconds/bar → BPM = 480/b
  // a = time of bar 1 = Ultrastar GAP (first beat of the song)
  function calcBpmFromMarkers(markers) {
    if (markers.length < 2) return null;
    const n = markers.length;
    let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
    for (const m of markers) {
      const xi = m.bar - 1; // bar 1 → x=0, bar 2 → x=1, etc.
      sumX += xi; sumY += m.t;
      sumXY += xi * m.t; sumX2 += xi * xi;
    }
    const denom = n * sumX2 - sumX * sumX;
    if (denom === 0) return null;
    const b = (n * sumXY - sumX * sumY) / denom; // seconds per bar
    const a = (sumY - b * sumX) / n;             // time of bar 1 = GAP
    if (b <= 0) return null;
    return { bpm: Math.round(480 / b * 1000) / 1000, gapMs: Math.round(a * 1000) };
  }

  function applyBpmCalibration() {
    if (!bpmCalcResult) return;
    pushUndo();
    bpm = bpmCalcResult.bpm;
    gapMs = bpmCalcResult.gapMs;
    handleBpmGapChange();
    markUnsaved();
    exitBeatMarkerMode();
  }

  // ──── Drawing ────────────────────────────────
  function draw() {
    if (!ctx || !canvasEl) return;

    const w = canvasEl.width;
    const h = canvasEl.height;
    const wt = waveTop();

    // Clear
    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, w, h);

    // ── Draw waveform at top ──
    // Waveform uses CURRENT BPM/GAP so it always aligns with the beat grid.
    // pixel → beat (current) → time → audio sample
    if (showWaveform && waveformPeaks.length > 0 && bpm > 0) {
      ctx.fillStyle = '#0a0a18';
      ctx.fillRect(0, 0, w, wt);

      const sampleRate = waveformPeaks.length / (waveformDuration || audioDuration || 1);
      const midY = wt / 2;

      ctx.fillStyle = '#4fc3f744';
      for (let px = 0; px < w; px++) {
        const beat = xToBeat(px);  // pixel → beat in CURRENT beat-space
        // Convert beat to absolute time using CURRENT BPM/GAP
        const t = beatToTime(beat);
        const idx = Math.floor(t * sampleRate);
        if (idx < 0 || idx >= waveformPeaks.length) continue;
        const amp = waveformPeaks[idx] * (wt / 2) * 0.9;
        ctx.fillRect(px, midY - amp, 1, amp * 2);
      }

      // Separator line
      ctx.strokeStyle = '#333';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, wt);
      ctx.lineTo(w, wt);
      ctx.stroke();

      // Predicted downbeats (red dots) — shown in calibration mode so user can verify grid alignment
      if (beatMarkerMode && bpm > 0) {
        const firstDownbeatSec = (downbeatOffsetMs || gapMs) / 1000;
        const secPerMeasure = 480 / bpm;
        // Find first visible bar index
        const leftTimeSec = beatToTime(xToBeat(0));
        const startN = Math.max(0, Math.floor((leftTimeSec - firstDownbeatSec) / secPerMeasure));
        const rightTimeSec = beatToTime(xToBeat(w));
        const endN = Math.ceil((rightTimeSec - firstDownbeatSec) / secPerMeasure);
        for (let n = startN; n <= endN; n++) {
          const t = firstDownbeatSec + n * secPerMeasure;
          const x = beatToX(timeToBeat(t));
          if (x < -6 || x > w + 6) continue;
          // Red tick at the bottom edge of the waveform
          ctx.fillStyle = '#ff4444';
          ctx.beginPath();
          ctx.arc(x, wt - 5, 3.5, 0, Math.PI * 2);
          ctx.fill();
          // Bar number label
          ctx.fillStyle = '#ff8888';
          ctx.font = '8px monospace';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'alphabetic';
          ctx.fillText(String(n + 1), x, wt - 10);
        }
      }

      // Beat calibration markers (orange clicks)
      if (beatMarkers.length > 0) {
        beatMarkers.forEach((m, i) => {
          const x = beatToX(timeToBeat(m.t));
          if (x < -10 || x > w + 10) return;
          // Vertical line
          ctx.strokeStyle = i === 0 ? '#ff9f43' : '#ff6b35';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(x, 0);
          ctx.lineTo(x, wt - 1);
          ctx.stroke();
          // Diamond handle at top
          ctx.fillStyle = i === 0 ? '#ff9f43' : '#ff6b35';
          ctx.beginPath();
          ctx.moveTo(x, 1);
          ctx.lineTo(x + 7, 9);
          ctx.lineTo(x, 17);
          ctx.lineTo(x - 7, 9);
          ctx.closePath();
          ctx.fill();
          // Bar number label
          ctx.fillStyle = '#fff';
          ctx.font = 'bold 9px monospace';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(String(m.bar), x, 9);
          ctx.textBaseline = 'alphabetic';
        });
      }
    }

    // Reserve bottom strip for time axis
    const pianoH = h - timeAxisHeight;

    // Grid lines (pitch)
    const pitchRange = maxPitch - minPitch;
    for (let p = minPitch; p <= maxPitch; p++) {
      const y = pitchToY(p);
      if (y > pianoH) continue; // don't draw into time axis
      const isC = ((p % 12) + 12) % 12 === 0;
      
      ctx.strokeStyle = isC ? '#333' : '#1a1a2e';
      ctx.lineWidth = isC ? 1 : 0.5;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();

      // Pitch labels (only C notes)
      if (isC) {
        ctx.fillStyle = '#555';
        ctx.font = '10px monospace';
        ctx.fillText(noteName(p), 2, y - 2);
      }
    }

    // Grid lines (beats) — musical subdivisions
    // BEATS_PER_QUARTER = 8 ultrastar beats per real quarter note
    // Quarter note lines (thickest), 8th note lines (medium), fine lines (thinnest)
    // In gridAlignMode, grid lines are offset by gridAlignOffsetMs (preview shift)
    const gridOffsetPx = gridAlignMode ? msToPixels(gridAlignOffsetMs) : 0;
    const startBeat = Math.floor(xToBeat(0 - gridOffsetPx));
    const endBeat = Math.ceil(xToBeat(w - gridOffsetPx));
    const beatsPerMeasure = BEATS_PER_QUARTER * 4; // 4/4 time = 4 quarter notes per measure
    const beatsPerEighth = BEATS_PER_QUARTER / 2;  // half a quarter note

    // Find the downbeat gridline beat — use fractional offset for sub-beat precision
    let downbeatBeat = -99999;
    let downbeatFracPx = 0; // sub-beat pixel offset for smooth grid positioning
    if (downbeatOffsetMs !== 0) {
      const exactBeat = (downbeatOffsetMs - gapMs) * bpm / 15000;
      downbeatBeat = Math.round(exactBeat);
      downbeatFracPx = (exactBeat - downbeatBeat) * zoom;
    }

    for (let b = startBeat; b <= endBeat; b++) {
      const x = beatToX(b) + gridOffsetPx + (downbeatFromHeader ? downbeatFracPx : 0);
      // When we have a downbeat reference, all grid subdivisions align to it
      const rel = downbeatFromHeader ? b - downbeatBeat : b;
      const isMeasure = ((rel % beatsPerMeasure) + beatsPerMeasure) % beatsPerMeasure === 0;
      const isQuarter = ((rel % BEATS_PER_QUARTER) + BEATS_PER_QUARTER) % BEATS_PER_QUARTER === 0;
      const isEighth = ((rel % beatsPerEighth) + beatsPerEighth) % beatsPerEighth === 0;
      
      if (isMeasure) {
        ctx.strokeStyle = '#7070cc';
        ctx.lineWidth = 2;
      } else if (isQuarter) {
        ctx.strokeStyle = '#404078';
        ctx.lineWidth = 1;
      } else if (isEighth) {
        ctx.strokeStyle = '#30305a';
        ctx.lineWidth = 0.5;
      } else {
        // 16th note level — only show if zoomed in enough (> 4px per beat)
        if (zoom < 4) continue;
        ctx.strokeStyle = '#252545';
        ctx.lineWidth = 0.3;
      }
      ctx.beginPath();
      ctx.moveTo(x, wt);
      ctx.lineTo(x, pianoH);
      ctx.stroke();
    }

    // ── GAP marker (beat 0) — yellow dashed line ──
    {
      const gapX = beatToX(0); // No gridOffsetPx — GAP stays fixed during grid align
      if (gapX >= -1 && gapX <= w + 1) {
        ctx.save();
        ctx.strokeStyle = '#ffd700';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.beginPath();
        ctx.moveTo(gapX, 0);
        ctx.lineTo(gapX, pianoH);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }
    }

    // ── Set GAP mode: yellow hover highlight on nearest grid line ──
    if (setGapMode && setGapHoverBeat !== null) {
      const hoverX = beatToX(setGapHoverBeat);
      if (hoverX >= 0 && hoverX <= w) {
        ctx.save();
        ctx.strokeStyle = '#ffd700';
        ctx.lineWidth = 2.5;
        ctx.globalAlpha = 0.85;
        ctx.beginPath();
        ctx.moveTo(hoverX, 0);
        ctx.lineTo(hoverX, pianoH);
        ctx.stroke();
        // Small label
        ctx.globalAlpha = 1;
        ctx.fillStyle = '#ffd700';
        ctx.font = 'bold 11px monospace';
        ctx.textAlign = 'center';
        const hoverTimeSec = beatToTime(setGapHoverBeat);
        // Show where GAP would be set (the time at this beat position converted to new GAP)
        // New GAP = time of this grid line (since this line becomes beat 0)
        const newGapMs = Math.round(hoverTimeSec * 1000);
        ctx.fillText(`GAP ${newGapMs}ms`, hoverX, 12);
        ctx.restore();
      }
    }

    // ── Time axis (bottom strip) ──
    ctx.fillStyle = '#12121e';
    ctx.fillRect(0, pianoH, w, timeAxisHeight);
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, pianoH);
    ctx.lineTo(w, pianoH);
    ctx.stroke();

    // Determine a nice time interval based on zoom
    // At low zoom we want bigger intervals, at high zoom smaller ones
    const pixelsPerSecond = (bpm / 15) * zoom;
    let timeStep; // seconds between labels
    if (pixelsPerSecond > 40) timeStep = 1;
    else if (pixelsPerSecond > 15) timeStep = 5;
    else if (pixelsPerSecond > 5) timeStep = 10;
    else if (pixelsPerSecond > 2) timeStep = 30;
    else timeStep = 60;

    const startTimeSec = beatToTime(xToBeat(0));
    const endTimeSec = beatToTime(xToBeat(w));
    const firstTick = Math.ceil(startTimeSec / timeStep) * timeStep;

    ctx.fillStyle = '#888';
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';

    for (let t = firstTick; t <= endTimeSec; t += timeStep) {
      const beat = timeToBeat(t);
      const x = beatToX(beat);

      // Tick mark
      ctx.strokeStyle = '#555';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, pianoH);
      ctx.lineTo(x, pianoH + 5);
      ctx.stroke();

      // Label
      ctx.fillText(formatTime(t), x, pianoH + 16);
    }

    ctx.textAlign = 'left'; // Reset

    // Draw notes
    for (const note of notes) {
      if (note.type === 'break') {
        // Draw break line
        const x = beatToX(note.startBeat);
        const isBreakSelected = selectedNote === note.id;
        ctx.strokeStyle = isBreakSelected ? '#ef5350' : '#c6282855';
        ctx.lineWidth = isBreakSelected ? 3 : 2;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x, wt);
        ctx.lineTo(x, pianoH);
        ctx.stroke();
        ctx.setLineDash([]);

        // Draw drag handle (diamond shape at center)
        const handleY = (wt + pianoH) / 2;
        const hs = isBreakSelected ? 7 : 5;
        ctx.fillStyle = isBreakSelected ? '#ef5350' : '#c62828aa';
        ctx.beginPath();
        ctx.moveTo(x, handleY - hs);
        ctx.lineTo(x + hs, handleY);
        ctx.lineTo(x, handleY + hs);
        ctx.lineTo(x - hs, handleY);
        ctx.closePath();
        ctx.fill();

        // Show beat label when selected
        if (isBreakSelected) {
          ctx.fillStyle = '#ef5350';
          ctx.font = '9px monospace';
          ctx.textAlign = 'center';
          ctx.fillText(`break @${note.startBeat}`, x, handleY - hs - 4);
          ctx.textAlign = 'left';
        }
        continue;
      }

      const x = beatToX(note.startBeat);
      const y = pitchToY(note.pitch);
      const width = note.duration * zoom;

      // Note rectangle
      const isSelected = selectedNote === note.id || selectedNotes.has(note.id);
      const isCut = cutNoteIds.has(note.id);
      const hasChanged = note.original && (
        note.startBeat !== note.original.startBeat ||
        note.duration !== note.original.duration ||
        note.pitch !== note.original.pitch
      );

      // Cut notes are semi-transparent
      const cutAlpha = isCut ? '44' : '';

      // When mic is enabled, notes become hollow (faint fill + clear border) — USDX style
      const micHollow = micEnabled && micShowTrail;

      if (note.isGolden) {
        ctx.fillStyle = micHollow ? '#ffd70012' : (isSelected ? '#ffd70088' : (isCut ? '#ffd70022' : '#ffd70044'));
        ctx.strokeStyle = isCut ? '#ffd70066' : '#ffd700';
      } else if (note.isRap) {
        ctx.fillStyle = micHollow ? '#ff980012' : (isSelected ? '#ff980088' : (isCut ? '#ff980022' : '#ff980044'));
        ctx.strokeStyle = isCut ? '#ff980066' : '#ff9800';
      } else if (hasChanged) {
        ctx.fillStyle = micHollow ? '#fdd83512' : (isSelected ? '#fdd83588' : (isCut ? '#fdd83522' : '#fdd83544'));
        ctx.strokeStyle = isCut ? '#fdd83566' : '#fdd835';
      } else {
        ctx.fillStyle = micHollow ? '#4fc3f712' : (isSelected ? '#4fc3f788' : (isCut ? '#4fc3f722' : '#4fc3f744'));
        ctx.strokeStyle = isCut ? '#4fc3f766' : '#4fc3f7';
      }

      ctx.lineWidth = micHollow ? 2 : (isSelected ? 2 : 1);
      ctx.fillRect(x, y - noteHeight / 2, width, noteHeight);
      ctx.strokeRect(x, y - noteHeight / 2, width, noteHeight);

      // Golden star indicator
      if (note.isGolden && width > 14) {
        ctx.fillStyle = '#ffd700';
        ctx.font = 'bold 9px sans-serif';
        ctx.fillText('★', x + width - 12, y + 3);
      }

      // Syllable text
      if (zoom > 1 && width > 10) {
        ctx.fillStyle = '#eee';
        ctx.font = '10px sans-serif';
        ctx.fillText(note.syllable.trim(), x + 2, y + 3);
      }

      // Red dot indicator for mid-word syllables (no leading space)
      // Skip the very first note and the first note after each break
      if (!note.syllable.startsWith(' ')) {
        const noteIdx = notes.indexOf(note);
        const isFirstAfterBreakOrStart = noteIdx === 0 ||
          (noteIdx > 0 && notes[noteIdx - 1].type === 'break');
        if (!isFirstAfterBreakOrStart) {
          const dotR = 3;
          ctx.fillStyle = '#ef5350';
          ctx.beginPath();
          ctx.arc(x + width - dotR - 1, y - noteHeight / 2 + dotR + 1, dotR, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // ── USDX-style sung note blocks ──
    if (micShowTrail && micNoteHits.size > 0) {
      const visibleStartBeat = xToBeat(0);
      const visibleEndBeat = xToBeat(w);

      for (const note of notes) {
        if (note.type === 'break') continue;
        const hits = micNoteHits.get(note.id);
        if (!hits || hits.length === 0) continue;

        const noteEndBeat = note.startBeat + note.duration;
        // Skip notes fully outside visible area
        if (noteEndBeat < visibleStartBeat - 1 || note.startBeat > visibleEndBeat + 1) continue;

        const noteY = pitchToY(note.pitch);
        // Choose hit color based on note type
        const hitColor = note.isGolden ? 'rgba(255, 215, 0, 0.65)'
                       : note.isRap ? 'rgba(255, 152, 0, 0.65)'
                       : 'rgba(102, 187, 106, 0.7)';
        const missColor = 'rgba(255, 100, 100, 0.45)';

        // Estimate beat gap per frame for extending segments
        const beatGap = hits.length > 1 ? Math.abs(hits[1].beat - hits[0].beat) * 1.5 : 0.3;

        let i = 0;
        while (i < hits.length) {
          const sample = hits[i];
          if (sample.isHit) {
            // Group consecutive hits into one filled segment inside the target note
            let endBeat = sample.beat;
            while (i + 1 < hits.length && hits[i + 1].isHit) {
              i++;
              endBeat = hits[i].beat;
            }
            // Extend slightly so consecutive frames connect visually
            const xStart = beatToX(Math.max(sample.beat, note.startBeat));
            const xEnd = beatToX(Math.min(endBeat + beatGap, noteEndBeat));
            ctx.fillStyle = hitColor;
            ctx.fillRect(xStart, noteY - noteHeight / 2, Math.max(xEnd - xStart, 2), noteHeight);
          } else {
            // Group consecutive misses at the same pitch
            const missPitch = sample.sungPitch;
            let endBeat = sample.beat;
            while (i + 1 < hits.length && !hits[i + 1].isHit && hits[i + 1].sungPitch === missPitch) {
              i++;
              endBeat = hits[i].beat;
            }
            const missY = pitchToY(missPitch);
            const xStart = beatToX(sample.beat);
            const xEnd = beatToX(endBeat + beatGap);
            ctx.fillStyle = missColor;
            ctx.fillRect(xStart, missY - noteHeight / 2, Math.max(xEnd - xStart, 2), noteHeight);
          }
          i++;
        }
      }
    }

    // ── Optional raw pitch trail (debug) ──
    if (micShowRawTrail && micPitchTrail.length > 0) {
      const visibleStartBeat = xToBeat(0);
      const visibleEndBeat = xToBeat(w);
      ctx.fillStyle = 'rgba(255, 200, 50, 0.4)';
      for (let i = 0; i < micPitchTrail.length; i++) {
        const s = micPitchTrail[i];
        const beat = timeToBeat(s.time);
        if (beat < visibleStartBeat - 1 || beat > visibleEndBeat + 1) continue;
        const x = beatToX(beat);
        const y = pitchToY(s.pitch);
        if (y < wt || y > h - timeAxisHeight) continue;
        ctx.beginPath();
        ctx.arc(x, y, 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // ── Loop region overlay ──
    if (loopEnabled && loopStartBeat !== null && loopEndBeat !== null) {
      const lx1 = beatToX(Math.min(loopStartBeat, loopEndBeat));
      const lx2 = beatToX(Math.max(loopStartBeat, loopEndBeat));
      const pianoBottom = h - timeAxisHeight;

      // Translucent blue fill
      ctx.fillStyle = '#42a5f522';
      ctx.fillRect(lx1, 0, lx2 - lx1, pianoBottom);

      // Loop boundary lines
      ctx.strokeStyle = '#42a5f5';
      ctx.lineWidth = 2;
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(lx1, 0); ctx.lineTo(lx1, pianoBottom);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(lx2, 0); ctx.lineTo(lx2, pianoBottom);
      ctx.stroke();

      // Loop region on time axis
      ctx.fillStyle = '#42a5f544';
      ctx.fillRect(lx1, pianoBottom, lx2 - lx1, timeAxisHeight);

      // Loop drag handles (triangles at top of boundary lines)
      const handleSize = 8;
      // Left handle (▶ pointing right)
      ctx.fillStyle = '#42a5f5';
      ctx.beginPath();
      ctx.moveTo(lx1, 0);
      ctx.lineTo(lx1 + handleSize, handleSize);
      ctx.lineTo(lx1, handleSize * 2);
      ctx.closePath();
      ctx.fill();
      // Right handle (◀ pointing left)
      ctx.beginPath();
      ctx.moveTo(lx2, 0);
      ctx.lineTo(lx2 - handleSize, handleSize);
      ctx.lineTo(lx2, handleSize * 2);
      ctx.closePath();
      ctx.fill();

      // Bottom handles on time axis
      ctx.beginPath();
      ctx.moveTo(lx1, pianoBottom + timeAxisHeight);
      ctx.lineTo(lx1 + handleSize, pianoBottom + timeAxisHeight - handleSize);
      ctx.lineTo(lx1, pianoBottom + timeAxisHeight - handleSize * 2);
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(lx2, pianoBottom + timeAxisHeight);
      ctx.lineTo(lx2 - handleSize, pianoBottom + timeAxisHeight - handleSize);
      ctx.lineTo(lx2, pianoBottom + timeAxisHeight - handleSize * 2);
      ctx.closePath();
      ctx.fill();

      // Loop label
      ctx.fillStyle = '#42a5f5';
      ctx.font = 'bold 9px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('LOOP', (lx1 + lx2) / 2, pianoBottom + 16);
      ctx.textAlign = 'left';
    }

    // Playback cursor — always visible so user can see position at time 0
    {
      const cx = beatToX(playbackBeat);
      const pianoBottom = h - timeAxisHeight;
      ctx.strokeStyle = isPlaying ? '#ff5252' : '#ff8a80';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, pianoBottom);
      ctx.stroke();

      // Playhead drag handle (inverted triangle ▼ at top)
      if (!isPlaying) {
        const hs = 7;
        ctx.fillStyle = '#ff8a80';
        ctx.beginPath();
        ctx.moveTo(cx - hs, 0);
        ctx.lineTo(cx + hs, 0);
        ctx.lineTo(cx, hs * 1.5);
        ctx.closePath();
        ctx.fill();
        // Small triangle at bottom (on time axis)
        ctx.beginPath();
        ctx.moveTo(cx - hs, pianoBottom + timeAxisHeight);
        ctx.lineTo(cx + hs, pianoBottom + timeAxisHeight);
        ctx.lineTo(cx, pianoBottom + timeAxisHeight - hs * 1.5);
        ctx.closePath();
        ctx.fill();
      }
    }

    // ── Paste ghost preview ──
    if (pasteMode && clipboard && pastePreviewBeat !== null) {
      const offset = pastePreviewBeat - clipboard.sourceBeat;
      ctx.globalAlpha = 0.4;
      for (const cn of clipboard.notes) {
        const gx = beatToX(cn.startBeat + offset);
        const gy = pitchToY(cn.pitch);
        const gw = cn.duration * zoom;
        ctx.fillStyle = '#69f0ae';
        ctx.strokeStyle = '#69f0ae';
        ctx.lineWidth = 1;
        ctx.fillRect(gx, gy - noteHeight / 2, gw, noteHeight);
        ctx.strokeRect(gx, gy - noteHeight / 2, gw, noteHeight);
        if (zoom > 1 && gw > 10) {
          ctx.fillStyle = '#fff';
          ctx.font = '10px sans-serif';
          ctx.fillText(cn.syllable.trim(), gx + 2, gy + 3);
        }
      }
      ctx.globalAlpha = 1.0;

      // Paste insertion line
      const px = beatToX(pastePreviewBeat);
      const pianoBottom = h - timeAxisHeight;
      ctx.strokeStyle = '#69f0ae';
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(px, 0);
      ctx.lineTo(px, pianoBottom);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // ── Rubber-band selection box ──
    if (isBoxSelecting) {
      const bx = Math.min(boxSelectStart.x, boxSelectEnd.x);
      const by = Math.min(boxSelectStart.y, boxSelectEnd.y);
      const bw = Math.abs(boxSelectEnd.x - boxSelectStart.x);
      const bh = Math.abs(boxSelectEnd.y - boxSelectStart.y);
      ctx.fillStyle = '#42a5f518';
      ctx.strokeStyle = '#42a5f5';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.fillRect(bx, by, bw, bh);
      ctx.strokeRect(bx, by, bw, bh);
      ctx.setLineDash([]);
    }

    syncScrollbar();
  }

  // ──── Interaction ────────────────────────────
  function handleMouseDown(event) {
    const rect = canvasEl.getBoundingClientRect();
    const mx = event.clientX - rect.left;
    const my = event.clientY - rect.top;

    const beat = xToBeat(mx);
    const pitch = yToPitch(my);
    console.log(`[Mouse] mouseDown at px(${mx.toFixed(0)}, ${my.toFixed(0)}) beat=${beat.toFixed(1)} pitch=${pitch}`);

    // Ignore right-click — let contextmenu handler deal with it
    if (event.button === 2) return;

    // ── Beat Marker mode: left-click on waveform places a marker ──
    if (beatMarkerMode && showWaveform && my < waveTop()) {
      const t = beatToTime(xToBeat(mx));
      if (t >= 0) {
        // Auto-guess bar number from current BPM or existing regression
        let guessedBar;
        if (beatMarkers.length === 0) {
          guessedBar = 1;
        } else {
          const refBpm = (bpmCalcResult ? bpmCalcResult.bpm : null) || bpm;
          const secPerBar = 480 / refBpm;
          const anchor = beatMarkers[0];
          guessedBar = Math.round((t - anchor.t) / secPerBar) + anchor.bar;
        }
        beatMarkers = [...beatMarkers, { t, bar: guessedBar }].sort((a, b) => a.t - b.t);
        bpmCalcResult = calcBpmFromMarkers(beatMarkers);
        draw();
      }
      return;
    }

    // ── Grid Align mode: start drag ──
    if (gridAlignMode) {
      gridAlignDragging = true;
      gridAlignDragStartX = mx;
      gridAlignDragStartOffsetMs = gridAlignOffsetMs;
      return;
    }

    // ── Set GAP mode click ──
    if (setGapMode && setGapHoverBeat !== null) {
      // Compute the new GAP: the absolute time of the hovered grid line becomes the new GAP
      const newGapSec = beatToTime(setGapHoverBeat);
      const newGapMs = Math.round(newGapSec * 1000);
      console.log(`[SetGAP] Setting GAP to ${newGapMs}ms (beat ${setGapHoverBeat} → time ${newGapSec.toFixed(3)}s)`);
      pushUndo();
      gapMs = newGapMs;
      cancelSetGapMode();
      handleBpmGapChange();
      markUnsaved();
      return;
    }

    // Close context menu on left-click
    if (contextMenu.visible) closeContextMenu();

    // Click on time axis (bottom strip)
    const pianoH = viewHeight - timeAxisHeight;

    // Check playhead handle hit (when paused, 10px zone near playhead line)
    if (!isPlaying && currentTimeSec > 0) {
      const cx = beatToX(playbackBeat);
      if (Math.abs(mx - cx) <= 10) {
        playheadDrag = true;
        console.log('[Playhead] Start drag');
        // Start grain scrub
        if (scrubAudio && scrubAudioBuffer) {
          startScrubGrain(currentTimeSec);
        }
        return;
      }
    }

    // Check loop handle hit zones first (8px hit zone near boundary lines, full height)
    if (loopEnabled && loopStartBeat !== null && loopEndBeat !== null) {
      const lsX = beatToX(loopStartBeat);
      const leX = beatToX(loopEndBeat);
      if (Math.abs(mx - lsX) <= 8) {
        loopHandleDrag = 'start';
        console.log('[Loop] Dragging start handle');
        draw();
        return;
      }
      if (Math.abs(mx - leX) <= 8) {
        loopHandleDrag = 'end';
        console.log('[Loop] Dragging end handle');
        draw();
        return;
      }
    }

    if (my >= pianoH) {
      if (event.metaKey || event.ctrlKey) {
        // Ctrl/Cmd+click on ruler → start loop drag
        isSettingLoop = true;
        loopDragStartBeat = Math.round(beat);
        loopStartBeat = loopDragStartBeat;
        loopEndBeat = loopDragStartBeat;
        loopEnabled = true;
        console.log(`[Loop] Start drag at beat ${loopDragStartBeat}`);
        draw();
        return;
      }
      seekToTime(beatToTime(beat));
      return;
    }

    // Alt+click anywhere → seek playhead
    if (event.altKey) {
      seekToTime(beatToTime(beat));
      return;
    }

    // ── No note editing during playback ──
    if (isPlaying) {
      // Only allow seeking (handled above) — block note selection/dragging
      seekToTime(beatToTime(beat));
      return;
    }

    // ── Paste mode: click to place ──
    if (pasteMode && clipboard) {
      finalizePaste(Math.round(beat));
      return;
    }

    const isMultiKey = event.metaKey || event.ctrlKey;

    // Find clicked note (check regular notes first, then breaks)
    let found = null;
    for (const note of notes) {
      if (note.type === 'break') continue;
      
      const nx = beatToX(note.startBeat);
      const ny = pitchToY(note.pitch);
      const nw = note.duration * zoom;

      if (mx >= nx && mx <= nx + nw && my >= ny - noteHeight / 2 && my <= ny + noteHeight / 2) {
        found = note;

        // Detect resize zones (edges) — only for single note drag, not multi-select toggle
        if (!isMultiKey) {
          if (mx - nx < 5) dragMode = 'resize-left';
          else if (nx + nw - mx < 5) dragMode = 'resize-right';
          else dragMode = 'move';
        }

        break;
      }
    }

    // If no regular note found, check break lines (10px hit zone)
    if (!found) {
      for (const note of notes) {
        if (note.type !== 'break') continue;
        const bx = beatToX(note.startBeat);
        if (Math.abs(mx - bx) <= 6) {
          found = note;
          dragMode = 'move-break';
          break;
        }
      }
    }

    if (found) {
      if (isMultiKey && found.type !== 'break') {
        // Ctrl/Cmd click: toggle note in multi-selection
        if (selectedNotes.has(found.id)) {
          selectedNotes.delete(found.id);
          if (selectedNote === found.id) selectedNote = null;
        } else {
          selectedNotes.add(found.id);
          selectedNote = found.id;
        }
        selectedNotes = new Set(selectedNotes); // trigger reactivity
        dragMode = null;
        console.log(`[Mouse] Multi-select toggle id=${found.id}, count=${selectedNotes.size}`);
      } else {
        // Regular click: single select (clear multi-select unless clicking within it)
        if (selectedNotes.size > 0 && selectedNotes.has(found.id)) {
          // Clicking a note in the multi-selection → drag the whole group
          selectedNote = found.id;
          if (found.type !== 'break') {
            dragMode = 'move';
          }
        } else {
          // Clear multi-select, single select
          selectedNotes = new Set();
          selectedNote = found.id;
        }
        isDragging = true;
        dragStart = { x: mx, y: my, beat: found.startBeat, pitch: found.pitch, duration: found.duration, endBeat: found.endBeat };
        if (found.type !== 'break') {
          pushUndo();
          if (dragMode === 'move') {
            startDragOsc(found.pitch);
          }
          console.log(`[Mouse] Selected note id=${found.id} '${found.syllable}' mode=${dragMode}`);
        } else {
          pushUndo();
          console.log(`[Mouse] Selected break id=${found.id} at beat ${found.startBeat} mode=${dragMode}`);
        }
      }
    } else {
      // No hit — start rubber-band selection or seek
      if (isMultiKey) {
        // Ctrl/Cmd + drag empty space → rubber-band box selection
        isBoxSelecting = true;
        boxSelectStart = { x: mx, y: my };
        boxSelectEnd = { x: mx, y: my };
        console.log('[Mouse] Start box selection');
      } else {
        selectedNote = null;
        selectedNotes = new Set();
        seekToTime(beatToTime(beat));
        console.log(`[Mouse] No note — seek to beat ${beat.toFixed(1)}`);
      }
    }

    draw();
  }

  function handleMouseMove(event) {
    const rect = canvasEl.getBoundingClientRect();
    const mx = event.clientX - rect.left;
    const my = event.clientY - rect.top;

    // Playhead drag (scrub)
    if (playheadDrag) {
      const beat = xToBeat(mx);
      const timeSec = beatToTime(beat);
      const maxTime = audioEl?.duration || audioDuration || 300;
      const clampedTime = Math.max(0, Math.min(maxTime, timeSec));
      currentTimeSec = clampedTime;
      playbackBeat = timeToBeat(clampedTime);
      if (audioEl) audioEl.currentTime = clampedTime;

      // Grain scrub: play tiny loop at current position
      if (scrubAudio && scrubAudioBuffer && !muteVocal) {
        startScrubGrain(clampedTime);
      }

      // Scrub: play MIDI pitch of note under playhead
      if (midiPlayback) {
        ensureMidiCtx();
        updateMidiPlayback(playbackBeat);
      }

      draw();
      return;
    }

    // Loop handle drag
    if (loopHandleDrag) {
      const beat = Math.round(xToBeat(mx));
      const minLoopBeats = 2;
      if (loopHandleDrag === 'start') {
        loopStartBeat = Math.min(beat, loopEndBeat - minLoopBeats);
      } else {
        loopEndBeat = Math.max(beat, loopStartBeat + minLoopBeats);
      }
      draw();
      return;
    }

    // Loop region drag on time axis
    if (isSettingLoop) {
      loopEndBeat = Math.round(xToBeat(mx));
      draw();
      return;
    }

    // ── Grid Align mode: drag to slide grid ──
    if (gridAlignMode) {
      if (gridAlignDragging) {
        const dx = mx - gridAlignDragStartX;
        gridAlignOffsetMs = gridAlignDragStartOffsetMs + pixelsToMs(dx);
      }
      draw();
      return;
    }

    // ── Set GAP mode hover: highlight nearest valid grid line ──
    if (setGapMode) {
      const hoverBeat = nearestGridBeat(mx);
      const hoverTimeSec = beatToTime(hoverBeat);
      const maxGapSec = getMaxGapSec();
      // Only allow if this position is at or before the first note's raw start time
      // Use 1ms tolerance to avoid float rounding rejecting the exact same position
      if (hoverTimeSec <= maxGapSec + 0.001) {
        setGapHoverBeat = hoverBeat;
      } else {
        setGapHoverBeat = null;
      }
      canvasEl.style.cursor = setGapHoverBeat !== null ? 'crosshair' : 'not-allowed';
      draw();
      return;
    }

    // Cursor style based on hover target
    if (!isDragging && !isSettingLoop && !loopHandleDrag && !playheadDrag) {
      let cursor = '';

      // Check playhead handle (when paused)
      if (!isPlaying && currentTimeSec > 0) {
        const cx = beatToX(playbackBeat);
        if (Math.abs(mx - cx) <= 10) {
          cursor = 'col-resize';
        }
      }

      // Check loop handles
      if (loopEnabled && loopStartBeat !== null && loopEndBeat !== null) {
        const lsX = beatToX(loopStartBeat);
        const leX = beatToX(loopEndBeat);
        if (Math.abs(mx - lsX) <= 8 || Math.abs(mx - leX) <= 8) {
          cursor = 'col-resize';
        }
      }

      // Check note hover (if no loop handle matched)
      if (!cursor) {
        for (const note of notes) {
          if (note.type === 'break') {
            const bx = beatToX(note.startBeat);
            if (Math.abs(mx - bx) <= 6) {
              cursor = 'col-resize';
              break;
            }
            continue;
          }
          const nx = beatToX(note.startBeat);
          const ny = pitchToY(note.pitch);
          const nw = note.duration * zoom;
          if (mx >= nx && mx <= nx + nw && my >= ny - noteHeight / 2 && my <= ny + noteHeight / 2) {
            if (mx - nx < 5 || nx + nw - mx < 5) {
              cursor = 'col-resize';
            } else {
              cursor = 'move';
            }
            break;
          }
        }
      }

      canvasEl.style.cursor = pasteMode ? 'crosshair' : cursor;
    }

    // ── Box selection tracking ──
    if (isBoxSelecting) {
      boxSelectEnd = { x: mx, y: my };
      draw();
      return;
    }

    // ── Paste preview tracking ──
    if (pasteMode && clipboard) {
      pastePreviewBeat = Math.round(xToBeat(mx));
      draw();
      return;
    }

    if (!isDragging || selectedNote === null) return;

    const note = notes.find(n => n.id === selectedNote);
    if (!note) return;

    const dx = mx - dragStart.x;
    const dy = my - dragStart.y;

    // Break drag: horizontal only
    if (note.type === 'break' && dragMode === 'move-break') {
      note.startBeat = Math.max(0, Math.round(dragStart.beat + dx / zoom));
      if (note.endBeat !== null && note.endBeat !== undefined) {
        const origDiff = (dragStart.endBeat || note.endBeat) - dragStart.beat;
        note.endBeat = note.startBeat + origDiff;
      }
      editorState.update(s => ({ ...s, hasChanges: true }));
      hasUnsavedChanges = true;
      notes = [...notes];
      draw();
      return;
    }

    if (note.type === 'break') return;

    // ── Multi-note drag ──
    if (dragMode === 'move' && selectedNotes.size > 1 && selectedNotes.has(note.id)) {
      const beatDelta = Math.round(dx / zoom);
      const pitchDelta = yToPitch(dragStart.y + dy) - dragStart.pitch;
      
      if (!dragStart.groupOffsets) {
        // Capture initial positions of all selected notes
        dragStart.groupOffsets = [];
        for (const n of notes) {
          if (selectedNotes.has(n.id) && n.type !== 'break') {
            dragStart.groupOffsets.push({ id: n.id, beat: n.startBeat, pitch: n.pitch });
          }
        }
      }
      
      for (const offset of dragStart.groupOffsets) {
        const n = notes.find(nn => nn.id === offset.id);
        if (n) {
          n.startBeat = Math.max(0, offset.beat + beatDelta);
          n.pitch = Math.max(minPitch, Math.min(maxPitch, offset.pitch + pitchDelta));
        }
      }
      
      if (note.pitch !== dragLastPitch) {
        updateDragOsc(note.pitch);
      }
    } else if (dragMode === 'move') {
      note.startBeat = Math.max(0, Math.round(dragStart.beat + dx / zoom));
      note.pitch = Math.max(minPitch, Math.min(maxPitch, yToPitch(dragStart.y + dy)));
      // Update pitch preview if pitch changed
      if (note.pitch !== dragLastPitch) {
        updateDragOsc(note.pitch);
      }
    } else if (dragMode === 'resize-right') {
      note.duration = Math.max(1, Math.round(dragStart.duration + dx / zoom));
    } else if (dragMode === 'resize-left') {
      const newStart = Math.max(0, Math.round(dragStart.beat + dx / zoom));
      const diff = note.startBeat - newStart;
      note.startBeat = newStart;
      note.duration = Math.max(1, note.duration + diff);
    }

    editorState.update(s => ({ ...s, hasChanges: true }));
    hasUnsavedChanges = true;
    notes = [...notes]; // trigger reactivity
    draw();
  }

  function handleMouseUp() {
    // Finish grid align drag
    if (gridAlignDragging) {
      gridAlignDragging = false;
      console.log(`[GridAlign] Drag done, offset=${gridAlignOffsetMs.toFixed(1)}ms`);
      draw();
      return;
    }

    // Finish playhead drag
    if (playheadDrag) {
      playheadDrag = false;
      stopScrubGrain();
      if (midiPlayback) stopAllMidiNotes();
      canvasEl.style.cursor = '';
      console.log(`[Playhead] Drag done at ${currentTimeSec.toFixed(2)}s`);
      draw();
      return;
    }

    // Finish loop handle drag
    if (loopHandleDrag) {
      console.log(`[Loop] Handle drag done: ${loopStartBeat} → ${loopEndBeat}`);
      loopHandleDrag = null;
      canvasEl.style.cursor = '';
      draw();
      return;
    }

    // Finish loop drag
    if (isSettingLoop) {
      isSettingLoop = false;
      // Normalize so start < end
      if (loopStartBeat !== null && loopEndBeat !== null) {
        const a = Math.min(loopStartBeat, loopEndBeat);
        const b = Math.max(loopStartBeat, loopEndBeat);
        if (b - a < 2) {
          // Too small → clear loop
          loopStartBeat = null;
          loopEndBeat = null;
          loopEnabled = false;
          console.log('[Loop] Cleared (too small)');
        } else {
          loopStartBeat = a;
          loopEndBeat = b;
          console.log(`[Loop] Set region: beat ${a} → ${b}`);
        }
      }
      loopDragStartBeat = null;
      draw();
      return;
    }

    // ── Finish box selection ──
    if (isBoxSelecting) {
      isBoxSelecting = false;
      const x1 = Math.min(boxSelectStart.x, boxSelectEnd.x);
      const x2 = Math.max(boxSelectStart.x, boxSelectEnd.x);
      const y1 = Math.min(boxSelectStart.y, boxSelectEnd.y);
      const y2 = Math.max(boxSelectStart.y, boxSelectEnd.y);

      // Find all notes within the box
      let count = 0;
      for (const note of notes) {
        if (note.type === 'break') continue;
        const nx = beatToX(note.startBeat);
        const ny = pitchToY(note.pitch);
        const nw = note.duration * zoom;
        // Note intersects box if its rectangle overlaps
        if (nx + nw >= x1 && nx <= x2 && ny + noteHeight / 2 >= y1 && ny - noteHeight / 2 <= y2) {
          selectedNotes.add(note.id);
          count++;
        }
      }
      selectedNotes = new Set(selectedNotes); // trigger reactivity
      if (count > 0) selectedNote = [...selectedNotes][0];
      console.log(`[BoxSelect] Selected ${count} notes (total ${selectedNotes.size})`);
      boxSelectStart = null;
      boxSelectEnd = null;
      draw();
      return;
    }

    if (isDragging) {
      console.log('[Mouse] mouseUp, drag ended');
      stopDragOsc();
    }
    isDragging = false;
    dragMode = null;
  }

  // ──── Drag Pitch Preview ─────────────────────
  function startDragOsc(pitch) {
    stopDragOsc(); // clean up any previous
    dragAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    dragOsc = dragAudioCtx.createOscillator();
    dragGain = dragAudioCtx.createGain();
    dragOsc.connect(dragGain);
    dragGain.connect(dragAudioCtx.destination);
    dragOsc.type = 'triangle';
    const freq = 440 * Math.pow(2, (pitch - 69) / 12);
    dragOsc.frequency.value = freq;
    dragGain.gain.value = 0.25;
    dragOsc.start();
    dragLastPitch = pitch;
  }

  function updateDragOsc(pitch) {
    if (!dragOsc || !dragAudioCtx) return;
    const freq = 440 * Math.pow(2, (pitch - 69) / 12);
    dragOsc.frequency.setValueAtTime(freq, dragAudioCtx.currentTime);
    dragLastPitch = pitch;
  }

  function stopDragOsc() {
    if (dragOsc) {
      try {
        dragGain.gain.linearRampToValueAtTime(0, dragAudioCtx.currentTime + 0.05);
        dragOsc.stop(dragAudioCtx.currentTime + 0.06);
      } catch (e) { /* already stopped */ }
      dragOsc = null;
      dragGain = null;
    }
    if (dragAudioCtx) {
      setTimeout(() => { try { dragAudioCtx.close(); } catch(e) {} }, 100);
      dragAudioCtx = null;
    }
    dragLastPitch = null;
  }

  // ──── Clipboard: Cut / Copy / Paste ──────────
  function getSelectedNoteObjects() {
    if (selectedNotes.size > 0) {
      return notes.filter(n => selectedNotes.has(n.id) && n.type !== 'break');
    } else if (selectedNote !== null) {
      const n = notes.find(nn => nn.id === selectedNote && nn.type !== 'break');
      return n ? [n] : [];
    }
    return [];
  }

  function clipboardCut() {
    const sel = getSelectedNoteObjects();
    if (sel.length === 0) return;

    const minBeat = Math.min(...sel.map(n => n.startBeat));
    clipboard = {
      notes: sel.map(n => ({
        startBeat: n.startBeat - minBeat,
        duration: n.duration,
        pitch: n.pitch,
        syllable: n.syllable,
        type: n.type || ':',
        isRap: n.isRap || false,
        isGolden: n.isGolden || false,
      })),
      mode: 'cut',
      sourceBeat: minBeat,
    };
    cutNoteIds = new Set(sel.map(n => n.id));
    pasteMode = true;
    pastePreviewBeat = null;
    console.log(`[Clipboard] Cut ${sel.length} notes from beat ${minBeat}`);
    closeContextMenu();
    draw();
  }

  function clipboardCopy() {
    const sel = getSelectedNoteObjects();
    if (sel.length === 0) return;

    const minBeat = Math.min(...sel.map(n => n.startBeat));
    clipboard = {
      notes: sel.map(n => ({
        startBeat: n.startBeat - minBeat,
        duration: n.duration,
        pitch: n.pitch,
        syllable: n.syllable,
        type: n.type || ':',
        isRap: n.isRap || false,
        isGolden: n.isGolden || false,
      })),
      mode: 'copy',
      sourceBeat: minBeat,
    };
    cutNoteIds = new Set();
    pasteMode = true;
    pastePreviewBeat = null;
    console.log(`[Clipboard] Copied ${sel.length} notes from beat ${minBeat}`);
    closeContextMenu();
    draw();
  }

  function finalizePaste(targetBeat) {
    if (!clipboard || !pasteMode) return;
    pushUndo();

    // If cut mode, remove original notes
    if (clipboard.mode === 'cut' && cutNoteIds.size > 0) {
      notes = notes.filter(n => !cutNoteIds.has(n.id));
      cutNoteIds = new Set();
    }

    // Generate new note IDs and insert copied notes
    let maxId = Math.max(0, ...notes.map(n => typeof n.id === 'number' ? n.id : 0));
    const newNotes = clipboard.notes.map(cn => ({
      id: ++maxId,
      startBeat: targetBeat + cn.startBeat,
      duration: cn.duration,
      pitch: cn.pitch,
      syllable: cn.syllable,
      type: cn.type,
      isRap: cn.isRap,
      isGolden: cn.isGolden,
    }));

    notes = [...notes, ...newNotes].sort((a, b) => a.startBeat - b.startBeat);

    // Select the newly pasted notes
    selectedNotes = new Set(newNotes.map(n => n.id));
    selectedNote = newNotes[0]?.id || null;

    // If copy mode, stay in paste mode for repeated pastes
    if (clipboard.mode === 'copy') {
      pastePreviewBeat = null;
    } else {
      // Cut mode: exit paste mode after placing
      pasteMode = false;
      clipboard = null;
      pastePreviewBeat = null;
    }

    editorState.update(s => ({ ...s, hasChanges: true }));
    hasUnsavedChanges = true;
    console.log(`[Clipboard] Pasted ${newNotes.length} notes at beat ${targetBeat}`);
    draw();
  }

  function cancelPaste() {
    // Restore cut notes (make them visible again)
    cutNoteIds = new Set();
    pasteMode = false;
    clipboard = null;
    pastePreviewBeat = null;
    console.log('[Clipboard] Paste cancelled');
    draw();
  }

  // ──── Context Menu ──────────────────────────
  function handleContextMenu(event) {
    event.preventDefault();
    // No context menu during playback or grid align
    if (isPlaying || gridAlignMode) return;
    const rect = canvasEl.getBoundingClientRect();
    const mx = event.clientX - rect.left;
    const my = event.clientY - rect.top;

    // Beat marker mode: right-click on waveform removes nearest marker
    if (beatMarkerMode && showWaveform && my < waveTop()) {
      if (beatMarkers.length > 0) {
        const t = beatToTime(xToBeat(mx));
        const nearest = beatMarkers.reduce((a, b) => Math.abs(a.t - t) < Math.abs(b.t - t) ? a : b);
        beatMarkers = beatMarkers.filter(m => m !== nearest);
        bpmCalcResult = calcBpmFromMarkers(beatMarkers);
        draw();
      }
      return;
    }

    // Find note under cursor (regular notes first, then breaks)
    let found = null;
    let isBreak = false;
    for (const note of notes) {
      if (note.type === 'break') continue;
      const nx = beatToX(note.startBeat);
      const ny = pitchToY(note.pitch);
      const nw = note.duration * zoom;
      if (mx >= nx && mx <= nx + nw && my >= ny - noteHeight / 2 && my <= ny + noteHeight / 2) {
        found = note;
        break;
      }
    }

    // Check breaks if no regular note hit
    if (!found) {
      for (const note of notes) {
        if (note.type !== 'break') continue;
        const bx = beatToX(note.startBeat);
        if (Math.abs(mx - bx) <= 6) {
          found = note;
          isBreak = true;
          break;
        }
      }
    }

    if (found) {
      selectedNote = found.id;
      // If right-clicking on a note in the multi-selection, keep it; otherwise select just this note
      if (!selectedNotes.has(found.id)) {
        selectedNotes = new Set();
      }
      syllableUndoPushed = false;
      if (!isBreak) editingSyllable = found.syllable;
      // Store the exact beat where user right-clicked (for split-at-cursor)
      const clickBeat = xToBeat(mx);
      // Position menu, clamping to viewport
      const menuW = 220, menuH = isBreak ? 160 : 280;
      const posX = Math.min(event.clientX, window.innerWidth - menuW - 10);
      const posY = Math.min(event.clientY, window.innerHeight - menuH - 10);
      contextMenu = { visible: true, x: posX, y: posY, noteId: found.id, isBreak, isEmpty: false, beat: clickBeat, pitch: 0 };
      draw();
    } else {
      // Empty space — show canvas context menu
      const beat = Math.round(xToBeat(mx));
      const pitch = yToPitch(my);
      const menuW = 220, menuH = 180;
      const posX = Math.min(event.clientX, window.innerWidth - menuW - 10);
      const posY = Math.min(event.clientY, window.innerHeight - menuH - 10);
      selectedNote = null;
      contextMenu = { visible: true, x: posX, y: posY, noteId: null, isBreak: false, isEmpty: true, beat, pitch };
    }
  }

  function closeContextMenu() {
    contextMenu = { visible: false, x: 0, y: 0, noteId: null, isBreak: false, isEmpty: false, beat: 0, pitch: 0 };
  }

  function handleGlobalClick(e) {
    if (contextMenu.visible && contextMenuEl && !contextMenuEl.contains(e.target)) {
      closeContextMenu();
    }
  }

  // ──── Note Actions ──────────────────────────
  function deleteNote(noteId) {
    const id = noteId ?? selectedNote;
    if (id === null) return;
    pushUndo();
    notes = notes.filter(n => n.id !== id);
    if (selectedNote === id) selectedNote = null;
    selectedNotes.delete(id);
    selectedNotes = new Set(selectedNotes);
    markUnsaved();
    closeContextMenu();
    computeTotalBeats();
    draw();
  }

  function splitNote(noteId, splitBeat) {
    const id = noteId ?? selectedNote;
    if (id === null) return;
    const idx = notes.findIndex(n => n.id === id);
    if (idx === -1) return;
    const note = notes[idx];
    if (note.type === 'break' || note.duration < 2) return;

    pushUndo();
    // Use the click position if provided, otherwise split at midpoint
    let halfDur;
    if (splitBeat !== undefined) {
      halfDur = Math.max(1, Math.min(note.duration - 1, Math.round(splitBeat - note.startBeat)));
    } else {
      halfDur = Math.floor(note.duration / 2);
    }
    const maxId = Math.max(...notes.map(n => n.id)) + 1;

    const note1 = { ...note, duration: halfDur };
    const note2 = {
      ...note,
      id: maxId,
      startBeat: note.startBeat + halfDur,
      duration: note.duration - halfDur,
      syllable: ' ~',
      original: { startBeat: note.startBeat + halfDur, duration: note.duration - halfDur, pitch: note.pitch },
    };

    notes = [...notes.slice(0, idx), note1, note2, ...notes.slice(idx + 1)];
    selectedNote = maxId; // select the new second note
    markUnsaved();
    closeContextMenu();
    draw();
  }

  function setNoteType(noteId, type) {
    const id = noteId ?? selectedNote;
    if (id === null) return;
    const note = notes.find(n => n.id === id);
    if (!note || note.type === 'break') return;

    pushUndo();
    if (type === 'golden') {
      note.isRap = false;
      note.isGolden = true;
    } else if (type === 'rap') {
      note.isRap = true;
      note.isGolden = false;
    } else {
      note.isRap = false;
      note.isGolden = false;
    }

    notes = [...notes];
    markUnsaved();
    closeContextMenu();
    draw();
  }

  function insertBreak(noteId, position) {
    const id = noteId ?? selectedNote;
    if (id === null) return;
    const idx = notes.findIndex(n => n.id === id);
    if (idx === -1) return;
    const note = notes[idx];
    if (note.type === 'break') return;

    pushUndo();
    const maxId = Math.max(...notes.map(n => n.id)) + 1;
    const breakBeat = position === 'before'
      ? Math.max(0, note.startBeat - 1)
      : note.startBeat + note.duration + 1;
    const breakNote = { id: maxId, type: 'break', startBeat: breakBeat, endBeat: null };

    const insertIdx = position === 'before' ? idx : idx + 1;
    notes = [...notes.slice(0, insertIdx), breakNote, ...notes.slice(insertIdx)];
    markUnsaved();
    closeContextMenu();
    draw();
  }

  function addBreakAt(beat) {
    pushUndo();
    const maxId = Math.max(0, ...notes.map(n => n.id)) + 1;
    const breakNote = { id: maxId, type: 'break', startBeat: Math.max(0, beat), endBeat: null };
    // Insert in sorted position
    let insertIdx = notes.findIndex(n => {
      const nb = n.type === 'break' ? n.startBeat : n.startBeat;
      return nb > beat;
    });
    if (insertIdx === -1) insertIdx = notes.length;
    notes = [...notes.slice(0, insertIdx), breakNote, ...notes.slice(insertIdx)];
    selectedNote = maxId;
    markUnsaved();
    closeContextMenu();
    draw();
  }

  function addNoteAt(beat, pitch) {
    pushUndo();
    const maxId = Math.max(0, ...notes.map(n => n.id)) + 1;
    const duration = 4; // default 4 beats
    const newNote = {
      id: maxId,
      startBeat: Math.max(0, beat),
      duration,
      pitch: Math.max(minPitch, Math.min(maxPitch, pitch)),
      syllable: ' ~',
      isRap: false,
      isGolden: false,
      confidence: 1.0,
      original: { startBeat: beat, duration, pitch },
    };
    // Insert in sorted position
    let insertIdx = notes.filter(n => n.type !== 'break').findIndex(n => n.startBeat > beat);
    if (insertIdx === -1) {
      // Append after last non-break note
      insertIdx = notes.length;
    } else {
      // Find the actual index in the full notes array
      const targetNote = notes.filter(n => n.type !== 'break')[insertIdx];
      insertIdx = notes.indexOf(targetNote);
    }
    notes = [...notes.slice(0, insertIdx), newNote, ...notes.slice(insertIdx)];
    selectedNote = maxId;
    markUnsaved();
    closeContextMenu();
    computeTotalBeats();
    draw();
  }

  function mergeWithNext(noteId) {
    const id = noteId ?? selectedNote;
    if (id === null) return;
    const realNotes = notes.filter(n => n.type !== 'break');
    const realIdx = realNotes.findIndex(n => n.id === id);
    if (realIdx === -1 || realIdx >= realNotes.length - 1) return;

    const current = realNotes[realIdx];
    const next = realNotes[realIdx + 1];

    pushUndo();
    // Extend current to cover next
    current.duration = (next.startBeat + next.duration) - current.startBeat;
    current.syllable = current.syllable.trimEnd() + next.syllable;

    // Remove next note
    notes = notes.filter(n => n.id !== next.id);
    notes = [...notes];
    markUnsaved();
    closeContextMenu();
    draw();
  }

  function toggleWordSpace(noteId, hasSpace) {
    const note = notes.find(n => n.id === noteId);
    if (!note || note.type === 'break') return;
    pushUndo();
    if (hasSpace && !note.syllable.startsWith(' ')) {
      note.syllable = ' ' + note.syllable;
    } else if (!hasSpace && note.syllable.startsWith(' ')) {
      note.syllable = note.syllable.substring(1);
    }
    editingSyllable = note.syllable;
    notes = [...notes];
    markUnsaved();
    draw();
  }

  function autoFixWordSpaces() {
    // Auto-detect word boundaries and add leading spaces.
    // Rules:
    // - First note of song: no space
    // - First note after a break: no space
    // - '~' ties: no space (keep as-is)
    // - Syllable that looks like a continuation (lowercase, no punctuation before it): no space
    // - Otherwise: add leading space (word start)
    pushUndo();
    let changed = 0;
    let prevWasBreak = true; // treat start of song like after a break
    for (const note of notes) {
      if (note.type === 'break') {
        prevWasBreak = true;
        continue;
      }
      const trimmed = note.syllable.trimStart();
      if (prevWasBreak) {
        // First note after break/start — remove any leading space
        if (note.syllable !== trimmed) {
          note.syllable = trimmed;
          changed++;
        }
        prevWasBreak = false;
        continue;
      }
      // '~' ties: leave as-is
      if (trimmed === '~') {
        prevWasBreak = false;
        continue;
      }
      // If syllable doesn't have a leading space, add one (word boundary)
      if (!note.syllable.startsWith(' ')) {
        note.syllable = ' ' + note.syllable;
        changed++;
      }
      prevWasBreak = false;
    }
    notes = [...notes];
    markUnsaved();
    draw();
    console.log(`[AutoFix] Fixed word spaces on ${changed} notes`);
  }

  // ── Audio source toggle ──
  function switchAudioSource(source) {
    audioSource = source;
    const url = source === 'original' ? originalUrl : vocalUrl;
    const wasPlaying = isPlaying;
    const time = currentTimeSec || audioEl?.currentTime || 0;

    // Pause without resetting position
    if (isPlaying) {
      audioEl?.pause();
      isPlaying = false;
      cancelAnimationFrame(animFrame);
      stopAllMidiNotes();
    }

    if (audioEl) {
      audioEl.src = url;
      audioEl.load();
      audioEl.oncanplay = () => {
        audioEl.currentTime = time;
        audioEl.oncanplay = null;
        if (wasPlaying) {
          togglePlayback();
        }
      };
    }
    // Re-load waveform for new source
    loadWaveform(url);
    console.log('[Step4] Audio source:', source, 'at', time.toFixed(2) + 's', wasPlaying ? '(resuming)' : '(paused)');
  }

  function handleMissingAudio(type) {
    if (type === 'vocals') {
      if (confirm('No vocals track available.\n\nGo to Step 1 to extract vocals from the mix or upload a vocals file?')) {
        currentStep.set(1);
      }
    } else {
      if (confirm('No full mix audio available.\n\nGo to Step 1 to upload the full mix?')) {
        currentStep.set(1);
      }
    }
  }

  // ── Text editor (raw Ultrastar .txt) ──
  function openTextEditor() {
    textEditorContent = buildUltrastarContent();
    showTextEditor = true;
  }

  function buildUltrastarContent() {
    // Reconstruct Ultrastar .txt from current editor notes
    const lines = [];
    // Standard headers
    lines.push(`#TITLE:${$lyricsData?.title || 'Unknown'}`);
    lines.push(`#ARTIST:${$lyricsData?.artist || 'Unknown'}`);
    lines.push(`#BPM:${bpm}`);
    lines.push(`#GAP:${gapMs}`);
    // Downbeat offset
    if (downbeatOffsetMs !== 0) {
      lines.push(`#DOWNBEATOFFSET:${Math.round(downbeatOffsetMs)}`);
    }
    // Extra headers (YOUTUBE, COVER, LANGUAGE, etc.)
    const standardKeys = new Set(['TITLE', 'ARTIST', 'BPM', 'GAP', 'DOWNBEATOFFSET']);
    for (const h of extraHeaders) {
      if (!standardKeys.has(h.key.toUpperCase())) {
        lines.push(`#${h.key}:${h.value}`);
      }
    }
    // Notes
    for (const note of notes) {
      if (note.type === 'break') {
        lines.push(`- ${note.startBeat}`);
      } else {
        const prefix = note.type === 'golden' ? '*' : note.type === 'rap' ? 'F:' : ':';
        lines.push(`${prefix} ${note.startBeat} ${note.duration} ${note.pitch} ${note.syllable}`);
      }
    }
    lines.push('E');
    return lines.join('\n');
  }

  function applyTextEditorContent() {
    const newNotes = parseUltrastar(textEditorContent);
    if (newNotes.length === 0) {
      alert('No valid notes found in the text. Check the format.');
      return;
    }
    // Extract all headers from edited text
    const parsedHeaders = [];
    for (const line of textEditorContent.split('\n')) {
      const m = line.match(/^#([\w]+):(.*)/);
      if (m) {
        const key = m[1];
        const value = m[2];
        if (key.toUpperCase() === 'BPM') bpm = parseFloat(value.replace(',', '.')) || bpm;
        else if (key.toUpperCase() === 'GAP') gapMs = parseInt(value) || gapMs;
        else if (key.toUpperCase() === 'TITLE') { /* handled by lyricsData */ }
        else if (key.toUpperCase() === 'ARTIST') { /* handled by lyricsData */ }
        else parsedHeaders.push({ key, value });
      }
    }
    extraHeaders = parsedHeaders;
    pushUndo();
    notes = newNotes;
    computeTotalBeats();
    markUnsaved();
    draw();
    showTextEditor = false;
    console.log(`[TextEditor] Applied: ${notes.length} notes, BPM=${bpm}, GAP=${gapMs}, ${extraHeaders.length} extra headers`);
    // Auto-save to backend
    handleSave();
  }

  // Track syllable undo only once when the context menu opens (not per keystroke)
  let syllableUndoPushed = false;
  function updateSyllable(noteId, text) {
    const id = noteId ?? contextMenu.noteId;
    if (id === null) return;
    const note = notes.find(n => n.id === id);
    if (!note || note.type === 'break') return;
    if (!syllableUndoPushed) {
      pushUndo();
      syllableUndoPushed = true;
    }
    note.syllable = text;
    notes = [...notes];
    markUnsaved();
    draw();
  }

  function playNotePitch(noteId) {
    const id = noteId ?? selectedNote;
    if (id === null) return;
    const note = notes.find(n => n.id === id);
    if (!note || note.type === 'break') return;

    // Synthesize a tone at the note's MIDI pitch using Web Audio API
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    const freq = 440 * Math.pow(2, (note.pitch - 69) / 12);
    osc.frequency.value = freq;
    osc.type = 'triangle';
    gain.gain.value = 0.35;

    // Sustain at steady volume, then fade out gently at the end
    const durationSec = Math.min(2, (note.duration * 15) / bpm);
    const fadeTime = Math.min(0.15, durationSec * 0.3);
    osc.start();
    gain.gain.setValueAtTime(0.35, audioCtx.currentTime);
    gain.gain.setValueAtTime(0.35, audioCtx.currentTime + durationSec - fadeTime);
    gain.gain.linearRampToValueAtTime(0, audioCtx.currentTime + durationSec);
    osc.stop(audioCtx.currentTime + durationSec + 0.05);

    closeContextMenu();
  }

  function handleWheel(event) {
    event.preventDefault();

    // Grid Align mode: trackpad scroll adjusts grid offset
    if (gridAlignMode) {
      if (Math.abs(event.deltaX) > 0.5) {
        gridAlignOffsetMs -= pixelsToMs(event.deltaX);
        draw();
      }
      return;
    }
    
    if (event.ctrlKey || event.metaKey) {
      // Zoom
      const oldZoom = zoom;
      zoom = Math.max(0.5, Math.min(100, zoom + event.deltaY * -0.01));
      console.log(`[Wheel] Zoom ${oldZoom.toFixed(1)} → ${zoom.toFixed(1)}`);
    } else {
      // Horizontal scroll only
      if (Math.abs(event.deltaX) > 1) {
        scrollX = Math.max(getMinBeat() * zoom, scrollX + event.deltaX);
      }
    }

    draw();
  }

  // Scrollbar input handler
  function handleScrollbar(event) {
    const beat = parseFloat(event.target.value);
    scrollX = beat * zoom;
    draw();
  }

  // ──── Playback ───────────────────────────────
  function togglePlayback() {
    if (!audioEl) {
      console.log('[Play] No audioEl');
      return;
    }
    if (gridAlignMode || setGapMode) return; // block playback during grid/gap modes

    if (isPlaying) {
      console.log(`[Play] Pausing at ${audioEl.currentTime.toFixed(2)}s, beat=${playbackBeat.toFixed(1)}`);
      audioEl.pause();
      currentTimeSec = audioEl.currentTime;
      isPlaying = false;
      cancelAnimationFrame(animFrame);
      stopAllMidiNotes();
      draw(); // Redraw to show paused cursor
    } else {
      // If loop active and playhead is outside loop, jump to loop start
      if (loopEnabled && loopStartBeat !== null && loopEndBeat !== null) {
        if (playbackBeat < loopStartBeat || playbackBeat >= loopEndBeat) {
          const loopStartTime = beatToTime(loopStartBeat);
          currentTimeSec = loopStartTime;
          playbackBeat = loopStartBeat;
          console.log(`[Play] Jumped to loop start beat ${loopStartBeat}`);
        }
      }
      // Resume from our tracked position
      audioEl.currentTime = currentTimeSec;
      audioEl.playbackRate = playbackRate;
      audioEl.preservesPitch = true;
      audioEl.volume = muteVocal ? 0 : audioVolume;
      console.log(`[Play] Starting from ${currentTimeSec.toFixed(2)}s, beat=${playbackBeat.toFixed(1)}, rate=${playbackRate}`);
      audioEl.play();
      isPlaying = true;
      // Initialize metronome to current beat so it doesn't click immediately
      if (metronomeEnabled) {
        const offsetBeat = playbackBeat - metronomeOffset;
        lastMetronomeBeat = Math.floor(offsetBeat / BEATS_PER_QUARTER);
      }
      if (midiPlayback) ensureMidiCtx();
      updatePlayback();
    }
  }

  function stopPlayback() {
    console.log('[Stop] Resetting to 0');
    if (audioEl) {
      audioEl.pause();
      audioEl.currentTime = 0;
    }
    isPlaying = false;
    playbackBeat = 0;
    currentTimeSec = 0;
    cancelAnimationFrame(animFrame);
    stopAllMidiNotes();
    draw();
  }

  // Seek playhead to an absolute time (seconds)
  function seekToTime(timeSec) {
    if (!audioEl) {
      console.log('[Seek] No audioEl');
      return;
    }
    const maxTime = audioEl.duration || audioDuration || 300;
    const t = Math.max(0, Math.min(maxTime, timeSec));
    console.log(`[Seek] seekToTime ${t.toFixed(2)}s`);
    audioEl.currentTime = t;
    currentTimeSec = t;
    playbackBeat = timeToBeat(t);
    // Scroll only if the playhead would be off-screen
    const canvasWidth = canvasEl?.width || 800;
    const px = beatToX(playbackBeat);
    if (px < 0 || px > canvasWidth) {
      const minScrollX = getMinBeat() * zoom;
      scrollX = Math.max(minScrollX, playbackBeat * zoom - canvasWidth * 0.1);
    }
    draw();
  }

  function seekPlayback(deltaSec) {
    if (!audioEl) {
      console.log('[Seek] No audioEl');
      return;
    }
    const maxTime = audioEl.duration || audioDuration || 300;
    const oldTime = currentTimeSec;  // Use our tracked time, not audioEl.currentTime
    const newTime = Math.max(0, Math.min(maxTime, oldTime + deltaSec));
    console.log(`[Seek] delta=${deltaSec}s, old=${oldTime.toFixed(2)}s, new=${newTime.toFixed(2)}s, max=${maxTime.toFixed(2)}s`);
    audioEl.currentTime = newTime;
    currentTimeSec = newTime;
    const gapSec = gapMs / 1000;
    playbackBeat = ((newTime - gapSec) * bpm) / 15;
    // Update scroll position to follow
    const canvasWidth = canvasEl?.width || 800;
    const minScrollX = getMinBeat() * zoom;
    if (scrollMode) {
      scrollX = Math.max(minScrollX, playbackBeat * zoom - canvasWidth * 0.3);
    } else {
      const cursorX = beatToX(playbackBeat);
      if (cursorX < 0 || cursorX > canvasWidth) {
        scrollX = Math.max(minScrollX, (playbackBeat * zoom) - canvasWidth * 0.3);
      }
    }
    draw();
  }

  function handleKeydown(e) {
    // Skip all shortcuts when text editor modal is open
    if (showTextEditor) return;
    // Skip shortcuts when typing in a text/number input field (BPM, GAP, context menu, etc.)
    // Allow Space through on range inputs (volume slider) so play/pause still works
    if (e.target.tagName === 'INPUT' && e.target.type !== 'checkbox' && !(e.target.type === 'range' && e.key === ' ')) return;

    console.log(`[Key] ${e.code} shift=${e.shiftKey} ctrl=${e.ctrlKey} meta=${e.metaKey}`);

    // ── Grid Align mode: only allow Enter (confirm), Escape (cancel), Ctrl+G (cancel) ──
    if (gridAlignMode) {
      if (e.code === 'Enter') { e.preventDefault(); confirmGridAlign(); return; }
      if (e.code === 'Escape') { e.preventDefault(); cancelGridAlign(); return; }
      if ((e.metaKey || e.ctrlKey) && e.code === 'KeyG') { e.preventDefault(); cancelGridAlign(); return; }
      e.preventDefault();
      return;
    }

    // ── No editing shortcuts during playback ──
    // Allow: Space (play/pause), arrows (seek), L (loop), M (mic), Escape, speed
    // Block: undo/redo, clipboard, note editing
    if (isPlaying) {
      // Only allow playback-related keys
      if (e.code === 'Space') { e.preventDefault(); togglePlayback(); return; }
      if (e.code === 'ArrowLeft') { e.preventDefault(); seekPlayback(e.shiftKey ? -1 : -5); return; }
      if (e.code === 'ArrowRight') { e.preventDefault(); seekPlayback(e.shiftKey ? 1 : 5); return; }
      if (e.code === 'KeyL' && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); toggleLoop(); return; }
      if (e.code === 'KeyM' && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); micEnabled = !micEnabled; toggleMic(); return; }
      if (e.code === 'Escape') {
        e.preventDefault();
        if (loopStartBeat !== null) clearLoop();
        return;
      }
      // Block everything else during playback
      return;
    }

    // Undo / Redo (Cmd+Z / Cmd+Shift+Z on Mac, Ctrl+Z / Ctrl+Shift+Z on others)
    if ((e.metaKey || e.ctrlKey) && e.code === 'KeyZ') {
      e.preventDefault();
      if (e.shiftKey) {
        redo();
      } else {
        undo();
      }
      return;
    }

    // ── Select All (Ctrl/Cmd+A) ──
    if ((e.metaKey || e.ctrlKey) && e.code === 'KeyA') {
      e.preventDefault();
      selectedNotes = new Set(notes.filter(n => n.type !== 'break').map(n => n.id));
      if (selectedNotes.size > 0) selectedNote = [...selectedNotes][0];
      draw();
      return;
    }

    // ── Clipboard shortcuts ──
    if ((e.metaKey || e.ctrlKey) && e.code === 'KeyX') {
      e.preventDefault();
      clipboardCut();
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.code === 'KeyC') {
      e.preventDefault();
      clipboardCopy();
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.code === 'KeyV') {
      e.preventDefault();
      if (clipboard) {
        // If already in paste mode, paste at playhead position
        if (pasteMode) {
          finalizePaste(Math.round(playbackBeat));
        } else {
          // Re-enter paste mode
          pasteMode = true;
          pastePreviewBeat = null;
          draw();
        }
      }
      return;
    }

    // Spacebar: toggle play/pause
    if (e.code === 'Space') {
      e.preventDefault();
      if (!setGapMode) togglePlayback();
    }
    // Left arrow: move cursor (seek) — 5s or 1s with Shift
    if (e.code === 'ArrowLeft') {
      e.preventDefault();
      seekPlayback(e.shiftKey ? -1 : -5);
    }
    // Right arrow: move cursor (seek) — 5s or 1s with Shift
    if (e.code === 'ArrowRight') {
      e.preventDefault();
      seekPlayback(e.shiftKey ? 1 : 5);
    }

    // L: toggle loop on/off
    if (e.code === 'KeyL' && !e.ctrlKey && !e.metaKey && !e.altKey && selectedNote === null) {
      e.preventDefault();
      toggleLoop();
    }

    // M: toggle mic sing-along
    if (e.code === 'KeyM' && !e.ctrlKey && !e.metaKey && !e.altKey && selectedNote === null) {
      e.preventDefault();
      micEnabled = !micEnabled;
      toggleMic();
    }
    // Ctrl/Cmd+G: enter Grid Align mode
    if ((e.metaKey || e.ctrlKey) && e.code === 'KeyG') {
      e.preventDefault();
      enterGridAlignMode();
      return;
    }

    // Escape: cancel setGap mode, paste mode, clear loop, or deselect
    if (e.code === 'Escape') {
      e.preventDefault();
      if (beatMarkerMode) {
        exitBeatMarkerMode();
        draw();
      } else if (setGapMode) {
        cancelSetGapMode();
      } else if (pasteMode) {
        cancelPaste();
      } else if (selectedNotes.size > 0) {
        selectedNotes = new Set();
        selectedNote = null;
        draw();
      } else if (loopStartBeat !== null) {
        clearLoop();
      }
    }

    // Note action shortcuts (only when a note is selected and not in an input)
    if (selectedNote !== null && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (e.code === 'KeyP') {
        e.preventDefault();
        playNotePitch(selectedNote);
      }
      if (e.code === 'Delete' || e.code === 'Backspace') {
        e.preventDefault();
        if (selectedNotes.size > 1) {
          pushUndo();
          notes = notes.filter(n => !selectedNotes.has(n.id));
          selectedNotes = new Set();
          selectedNote = null;
          editorState.update(s => ({ ...s, hasChanges: true }));
          hasUnsavedChanges = true;
          draw();
        } else {
          deleteNote(selectedNote);
        }
      }
      if (e.code === 'KeyS' && !e.shiftKey) {
        e.preventDefault();
        splitNote(selectedNote);
      }
      if (e.code === 'KeyM') {
        e.preventDefault();
        mergeWithNext(selectedNote);
      }
    }
  }

  function updatePlayback() {
    if (!isPlaying) return;

    const currentTime = audioEl.currentTime;
    currentTimeSec = currentTime;
    const gapSec = gapMs / 1000;
    playbackBeat = ((currentTime - gapSec) * bpm) / 15;

    // ── Loop wrap ──
    if (loopEnabled && loopStartBeat !== null && loopEndBeat !== null) {
      if (playbackBeat >= loopEndBeat) {
        const loopStartTime = beatToTime(loopStartBeat);
        audioEl.currentTime = loopStartTime;
        currentTimeSec = loopStartTime;
        playbackBeat = loopStartBeat;
        // Stop all midi notes so they retrigger cleanly
        if (midiPlayback) stopAllMidiNotes();
        // Clear sung blocks for notes in the loop region so each pass starts fresh
        if (micEnabled && micNoteHits.size > 0) {
          for (const note of notes) {
            if (note.type === 'break') continue;
            const noteEnd = note.startBeat + note.duration;
            // Clear if note overlaps the loop region
            if (noteEnd > loopStartBeat && note.startBeat < loopEndBeat) {
              micNoteHits.delete(note.id);
            }
          }
        }
        console.log(`[Loop] Wrapped to beat ${loopStartBeat}`);
      }
    }

    // Scroll logic
    const canvasWidth = canvasEl?.width || 800;
    const minScrollX = getMinBeat() * zoom;
    if (loopEnabled && loopStartBeat !== null && loopEndBeat !== null) {
      // During loop: auto-scroll but clamp to loop boundaries
      const loopWidthPx = (loopEndBeat - loopStartBeat) * zoom;
      if (loopWidthPx > canvasWidth) {
        // Loop wider than viewport — scroll with playback, clamped to loop region
        const loopMinScroll = loopStartBeat * zoom - canvasWidth * 0.1;
        const loopMaxScroll = loopEndBeat * zoom - canvasWidth * 0.9;
        if (scrollMode) {
          scrollX = Math.max(loopMinScroll, Math.min(loopMaxScroll, playbackBeat * zoom - canvasWidth * 0.3));
        } else {
          const cursorX = beatToX(playbackBeat);
          if (cursorX > canvasWidth * 0.7 || cursorX < canvasWidth * 0.1) {
            scrollX = Math.max(loopMinScroll, Math.min(loopMaxScroll, playbackBeat * zoom - canvasWidth * 0.3));
          }
        }
      }
      // If loop fits in viewport, no scrolling needed — user can see everything
    } else if (scrollMode) {
      // Fixed cursor: cursor stays at 30%, notes scroll
      scrollX = Math.max(minScrollX, playbackBeat * zoom - canvasWidth * 0.3);
    } else {
      // Classic: auto-scroll when cursor reaches 70%
      const cursorX = beatToX(playbackBeat);
      if (cursorX > canvasWidth * 0.7) {
        scrollX = (playbackBeat * zoom) - canvasWidth * 0.3;
      }
    }

    draw();
    if (midiPlayback) updateMidiPlayback(playbackBeat);
    if (metronomeEnabled) updateMetronome(playbackBeat);
    if (micEnabled && micAnalyser) sampleMicPitch(currentTimeSec);
    animFrame = requestAnimationFrame(updatePlayback);
  }

  // Set playback speed
  function setPlaybackRate(rate) {
    console.log(`[Speed] Set playback rate: ${rate}x`);
    playbackRate = rate;
    if (audioEl) {
      audioEl.playbackRate = rate;
      audioEl.preservesPitch = true;
    }
  }

  // ──── MIDI Pitch Playback ────────────────────
  function ensureMidiCtx() {
    if (!midiAudioCtx || midiAudioCtx.state === 'closed') {
      midiAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
  }

  function updateMidiPlayback(currentBeat) {
    if (!midiAudioCtx) return;

    for (const note of notes) {
      if (note.type === 'break') continue;
      const noteEnd = note.startBeat + note.duration;
      const isInNote = currentBeat >= note.startBeat && currentBeat < noteEnd;

      if (isInNote && !midiActiveNotes.has(note.id)) {
        // Start this note
        const osc = midiAudioCtx.createOscillator();
        const gain = midiAudioCtx.createGain();
        osc.connect(gain);
        gain.connect(midiAudioCtx.destination);
        osc.type = 'triangle';
        const freq = 440 * Math.pow(2, (note.pitch - 69) / 12);
        osc.frequency.value = freq;
        gain.gain.value = midiVolume;
        osc.start();
        midiActiveNotes.set(note.id, { osc, gain });
      } else if (!isInNote && midiActiveNotes.has(note.id)) {
        // Stop this note
        const entry = midiActiveNotes.get(note.id);
        try {
          entry.gain.gain.linearRampToValueAtTime(0, midiAudioCtx.currentTime + 0.03);
          entry.osc.stop(midiAudioCtx.currentTime + 0.04);
        } catch (e) { /* already stopped */ }
        midiActiveNotes.delete(note.id);
      }
    }
  }

  // ──── Metronome ────────────────────────────
  function ensureMetronomeCtx() {
    if (!metronomeCtx || metronomeCtx.state === 'closed') {
      metronomeCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
  }

  function playMetronomeClick(isDownbeat) {
    ensureMetronomeCtx();
    const osc = metronomeCtx.createOscillator();
    const gain = metronomeCtx.createGain();
    osc.connect(gain);
    gain.connect(metronomeCtx.destination);
    osc.type = 'sine';
    // Higher pitch for downbeat (beat 1 of measure), lower for other beats
    osc.frequency.value = isDownbeat ? 1200 : 800;
    gain.gain.setValueAtTime(0.3, metronomeCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, metronomeCtx.currentTime + 0.06);
    osc.start(metronomeCtx.currentTime);
    osc.stop(metronomeCtx.currentTime + 0.06);
  }

  function updateMetronome(currentBeat) {
    // Click on every quarter note (every BEATS_PER_QUARTER ultrastar beats)
    // When we have a downbeat reference, shift the click grid so a click falls on it
    let clickOffset = metronomeOffset;
    let accentPhase = 0;
    if (downbeatFromHeader) {
      const exactBeat = (downbeatOffsetMs - gapMs) * bpm / 15000;
      const dbBeat = Math.round(exactBeat);
      // Shift clicks so one lands exactly on dbBeat
      clickOffset = dbBeat % BEATS_PER_QUARTER;
      // Which quarter-note index the downbeat falls on (for accent every 4 quarters)
      accentPhase = Math.floor((dbBeat - clickOffset) / BEATS_PER_QUARTER) % 4;
    }
    const offsetBeat = currentBeat - clickOffset;
    const quarterBeat = Math.floor(offsetBeat / BEATS_PER_QUARTER);
    if (quarterBeat !== lastMetronomeBeat) {
      lastMetronomeBeat = quarterBeat;
      const isDownbeat = ((quarterBeat - accentPhase) % 4 + 4) % 4 === 0;
      playMetronomeClick(isDownbeat);
    }
  }

  function toggleMetronome() {
    metronomeEnabled = !metronomeEnabled;
    if (metronomeEnabled) ensureMetronomeCtx();
    lastMetronomeBeat = -1;
    console.log('[Metronome]', metronomeEnabled ? 'ON' : 'OFF');
  }

  function stopAllMidiNotes() {
    for (const [id, entry] of midiActiveNotes) {
      try {
        entry.gain.gain.linearRampToValueAtTime(0, (midiAudioCtx?.currentTime || 0) + 0.03);
        entry.osc.stop((midiAudioCtx?.currentTime || 0) + 0.04);
      } catch (e) { /* already stopped */ }
    }
    midiActiveNotes.clear();
  }

  function toggleMidiPlayback() {
    midiPlayback = !midiPlayback;
    if (midiPlayback && isPlaying) {
      ensureMidiCtx();
    } else if (!midiPlayback) {
      stopAllMidiNotes();
    }
    console.log('[MIDI] Pitch playback:', midiPlayback);
  }

  function toggleMuteVocal() {
    muteVocal = !muteVocal;
    if (audioEl) audioEl.volume = muteVocal ? 0 : audioVolume;
    console.log('[Audio] Mute vocal:', muteVocal);
  }

  function handleVolumeChange(e) {
    audioVolume = parseFloat(e.target.value);
    if (audioEl && !muteVocal) audioEl.volume = audioVolume;
  }

  // ──── Mic Sing-Along ────────────────────────────
  async function loadMicDevices() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      micDevices = devices.filter(d => d.kind === 'audioinput');
      console.log('[Mic] Found', micDevices.length, 'input devices');
      // Set dropdown to the active mic (from stream) or first device
      if (!micDeviceId && micStream) {
        const activeTrack = micStream.getAudioTracks()[0];
        if (activeTrack) {
          const settings = activeTrack.getSettings();
          micDeviceId = settings.deviceId || (micDevices[0]?.deviceId ?? '');
        }
      }
      if (!micDeviceId && micDevices.length > 0) {
        micDeviceId = micDevices[0].deviceId;
      }
    } catch (err) {
      console.error('[Mic] Failed to enumerate devices:', err);
    }
  }

  async function startMic() {
    try {
      const audioConstraints = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: false,  // keep off — we want raw pitch, not normalized volume
        ...(micDeviceId ? { deviceId: { exact: micDeviceId } } : {})
      };
      const constraints = { audio: audioConstraints };
      micStream = await navigator.mediaDevices.getUserMedia(constraints);

      micAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
      micSourceNode = micAudioCtx.createMediaStreamSource(micStream);

      // High-pass filter at 200Hz — removes bass bleed from speakers/room rumble
      const highpass = micAudioCtx.createBiquadFilter();
      highpass.type = 'highpass';
      highpass.frequency.value = 200;
      highpass.Q.value = 0.7;

      // Gain node for mic volume control
      micGainNode = micAudioCtx.createGain();
      micGainNode.gain.value = micGain;

      micAnalyser = micAudioCtx.createAnalyser();
      micAnalyser.fftSize = 2048;
      micAnalyser.smoothingTimeConstant = 0;
      micSourceNode.connect(highpass);
      highpass.connect(micGainNode);
      micGainNode.connect(micAnalyser);

      micInputBuffer = new Float32Array(micAnalyser.fftSize);
      micDetector = PitchDetector.forFloat32Array(micAnalyser.fftSize);

      // Start MediaRecorder for voice capture
      try {
        micRecorder = new MediaRecorder(micStream, { mimeType: 'audio/webm;codecs=opus' });
        micRecordedChunks = [];
        micRecorder.ondataavailable = (e) => { if (e.data.size > 0) micRecordedChunks.push(e.data); };
        micRecorder.start(1000); // collect in 1s chunks
        console.log('[Mic] MediaRecorder started');
      } catch (recErr) {
        console.warn('[Mic] MediaRecorder not available:', recErr);
        micRecorder = null;
      }

      // Load device list after permission is granted (labels become available)
      await loadMicDevices();

      // Start mic level polling (for the level indicator)
      micLevelTimer = setInterval(() => {
        if (!micAnalyser) return;
        const buf = new Float32Array(micAnalyser.fftSize);
        micAnalyser.getFloatTimeDomainData(buf);
        let maxVal = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = Math.abs(buf[i]);
          if (v > maxVal) maxVal = v;
        }
        micLevel = Math.min(1, maxVal * 3); // amplify for visibility
      }, 50);

      console.log('[Mic] Started — sampleRate:', micAudioCtx.sampleRate);
    } catch (err) {
      console.error('[Mic] Failed to start:', err);
      micEnabled = false;
    }
  }

  function stopMic() {
    if (micLevelTimer) { clearInterval(micLevelTimer); micLevelTimer = null; }
    micLevel = 0;
    if (micRecorder && micRecorder.state !== 'inactive') {
      micRecorder.stop();
      console.log('[Mic] MediaRecorder stopped,', micRecordedChunks.length, 'chunks');
    }
    if (micStream) {
      micStream.getTracks().forEach(t => t.stop());
      micStream = null;
    }
    if (micGainNode) { micGainNode.disconnect(); micGainNode = null; }
    if (micSourceNode) { micSourceNode.disconnect(); micSourceNode = null; }
    if (micAudioCtx && micAudioCtx.state !== 'closed') {
      micAudioCtx.close().catch(() => {});
    }
    micAudioCtx = null;
    micAnalyser = null;
    micDetector = null;
    micInputBuffer = null;
    console.log('[Mic] Stopped');
  }

  async function toggleMic() {
    // Redraw immediately so trail visibility responds instantly
    draw();
    if (micEnabled) {
      micStarting = true;
      await startMic();
      micStarting = false;
    } else {
      stopMic();
    }
  }

  async function changeMicDevice(e) {
    micDeviceId = e.target.value;
    if (micEnabled) {
      stopMic();
      await startMic();
    }
  }

  function sampleMicPitch(timeSec) {
    if (!micAnalyser || !micDetector || !micInputBuffer) return;

    micAnalyser.getFloatTimeDomainData(micInputBuffer);
    const [frequency, clarity] = micDetector.findPitch(micInputBuffer, micAudioCtx.sampleRate);

    if (clarity < micClarityThreshold || frequency < 60 || frequency > 2000) {
      // Silence: decay confidence, reset sticky pitch and rolling window
      if (micPitchConfidence > 0) micPitchConfidence--;
      if (micPitchConfidence === 0) { micLastPitch = -1; micRecentPitches = []; }
      return;
    }

    // Convert frequency to MIDI pitch
    let midiPitch = Math.round(12 * Math.log2(frequency / 440) + 69);
    const rawPitch = midiPitch;

    // ── Find which note (if any) the current beat falls in ──
    const currentBeat = timeToBeat(timeSec);
    let targetNote = null;
    for (const note of notes) {
      if (note.type === 'break') continue;
      if (currentBeat >= note.startBeat && currentBeat < note.startBeat + note.duration) {
        targetNote = note;
        break;
      }
    }

    // USDX mode: only detect pitch during note regions
    if (!targetNote) {
      // Keep the rolling state alive but don't record anything
      micRecentPitches.push(midiPitch);
      if (micRecentPitches.length > 5) micRecentPitches.shift();
      return;
    }

    const targetPitch = targetNote.pitch;

    // ── Rolling median smoothing (always on — suppresses vibrato) ──
    micRecentPitches.push(midiPitch);
    if (micRecentPitches.length > 5) micRecentPitches.shift();
    const sorted = [...micRecentPitches].sort((a, b) => a - b);
    midiPitch = sorted[Math.floor(sorted.length / 2)];

    // Sticky prediction: hold stable pitch through brief jumps
    if (micLastPitch > 0) {
      const drift = Math.abs(midiPitch - micLastPitch);
      if (drift === 0) {
        micPitchConfidence = Math.min(8, micPitchConfidence + 1);
      } else if (drift <= 2 && micPitchConfidence >= 4) {
        midiPitch = micLastPitch;
        micPitchConfidence--;
      } else {
        micPitchConfidence = 1;
      }
    } else {
      micPitchConfidence = 1;
    }
    micLastPitch = midiPitch;

    // ── Octave correction toward target note ──
    while (midiPitch - targetPitch > 6) midiPitch -= 12;
    while (midiPitch - targetPitch < -6) midiPitch += 12;

    // Clamp to realistic vocal range: C2 (36) to C6 (84)
    if (midiPitch < 36) midiPitch += 12;
    if (midiPitch > 84) midiPitch -= 12;

    // ── Determine hit/miss (±2 semitones = hit, like USDX) ──
    const isHit = Math.abs(midiPitch - targetPitch) <= 2;

    // Store in per-note hit map
    if (!micNoteHits.has(targetNote.id)) {
      micNoteHits.set(targetNote.id, []);
    }
    // Clear-ahead: remove any old hits at or beyond current beat (handles rewind/re-record)
    const hits = micNoteHits.get(targetNote.id);
    if (hits.length > 0 && hits[hits.length - 1].beat >= currentBeat) {
      // Find first hit at or beyond currentBeat and truncate
      let cutIdx = hits.length;
      for (let j = 0; j < hits.length; j++) {
        if (hits[j].beat >= currentBeat - 0.01) { cutIdx = j; break; }
      }
      hits.length = cutIdx;
    }
    hits.push({ beat: currentBeat, sungPitch: midiPitch, isHit });

    // Optional: raw trail for debugging
    if (micShowRawTrail) {
      micPitchTrail.push({ time: timeSec, pitch: midiPitch, rawPitch, clarity, frequency });
      if (micPitchTrail.length > 30000) micPitchTrail = micPitchTrail.slice(-25000);
    }
  }

  function clearMicTrail() {
    micPitchTrail = [];
    micNoteHits = new Map();
    micLastPitch = -1;
    micPitchConfidence = 0;
    micRecentPitches = [];
    draw();
  }

  async function exportMicTrail() {
    // Convert USDX note hits to exportable format
    const noteHitsData = {};
    for (const [noteId, hits] of micNoteHits) {
      const note = notes.find(n => n.id === noteId);
      if (note) {
        noteHitsData[noteId] = {
          target: { start: note.startBeat, dur: note.duration, pitch: note.pitch, text: note.syllable },
          totalSamples: hits.length,
          hitSamples: hits.filter(h => h.isHit).length,
          hitRate: hits.length > 0 ? +(hits.filter(h => h.isHit).length / hits.length * 100).toFixed(1) : 0,
          samples: hits
        };
      }
    }
    const trailData = {
      exported: new Date().toISOString(),
      settings: { mode: 'usdx', clarityThreshold: micClarityThreshold },
      song: { bpm, gapMs, noteCount: notes.filter(n => n.type !== 'break').length },
      noteHits: noteHitsData,
      rawSamples: micPitchTrail.map(s => ({
        time: +s.time.toFixed(4),
        freq: s.frequency ? +s.frequency.toFixed(1) : null,
        rawMidi: s.rawPitch,
        smoothed: s.pitch,
        clarity: +s.clarity.toFixed(3)
      }))
    };
    try {
      // Build FormData with trail JSON + optional audio recording
      const formData = new FormData();
      formData.append('trail', JSON.stringify(trailData));

      if (micRecordedChunks.length > 0) {
        const audioBlob = new Blob(micRecordedChunks, { type: 'audio/webm' });
        formData.append('audio', audioBlob, 'mic-recording.webm');
        console.log(`[Mic] Uploading audio: ${(audioBlob.size / 1024).toFixed(1)} KB`);
      }

      const resp = await fetch(`/api/save-mic-trail/${$sessionId}`, {
        method: 'POST',
        body: formData
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result = await resp.json();
      console.log(`[Mic] Saved ${micPitchTrail.length} samples to server: ${result.filename}`);
      if (result.analysis) {
        console.log('[Mic] Server analysis:', result.analysis);
      }
    } catch (err) {
      console.error('[Mic] Failed to save trail to server:', err);
    }
  }

  // ──── Grain Scrub ────────────────────────────
  function startScrubGrain(timeSec) {
    if (!scrubAudioBuffer) return;

    // Stop previous grain
    stopScrubGrain();

    // Create/reuse context
    if (!scrubCtx || scrubCtx.state === 'closed') {
      scrubCtx = new (window.AudioContext || window.webkitAudioContext)();
    }

    const grainDuration = 0.05; // 50ms grain
    const sampleRate = scrubAudioBuffer.sampleRate;
    const startSample = Math.floor(timeSec * sampleRate);
    const grainSamples = Math.floor(grainDuration * sampleRate);

    if (startSample < 0 || startSample >= scrubAudioBuffer.length) return;

    // Create a short buffer for the grain
    const numChannels = scrubAudioBuffer.numberOfChannels;
    const grainBuffer = scrubCtx.createBuffer(numChannels, grainSamples, sampleRate);

    for (let ch = 0; ch < numChannels; ch++) {
      const source = scrubAudioBuffer.getChannelData(ch);
      const dest = grainBuffer.getChannelData(ch);
      for (let i = 0; i < grainSamples; i++) {
        const idx = startSample + i;
        // Apply tiny fade in/out to avoid clicks
        let env = 1;
        if (i < 64) env = i / 64;
        else if (i > grainSamples - 64) env = (grainSamples - i) / 64;
        dest[i] = (idx < source.length ? source[idx] : 0) * env;
      }
    }

    scrubSource = scrubCtx.createBufferSource();
    scrubSource.buffer = grainBuffer;
    scrubSource.loop = true;

    scrubGain = scrubCtx.createGain();
    scrubGain.gain.value = 1.0;

    scrubSource.connect(scrubGain);
    scrubGain.connect(scrubCtx.destination);
    scrubSource.start();
  }

  function stopScrubGrain() {
    if (scrubSource) {
      try { scrubSource.stop(); } catch (e) {}
      scrubSource = null;
    }
    if (scrubGain) {
      scrubGain = null;
    }
  }

  // ──── Loop Region ────────────────────────────
  function toggleLoop() {
    if (loopEnabled) {
      // Disable — clear region entirely
      loopStartBeat = null;
      loopEndBeat = null;
      loopEnabled = false;
      console.log('[Loop] Disabled and cleared');
      draw();
      return;
    }
    // Enable — always create a fresh loop near the playhead
    const canvasWidth = canvasEl?.width || 800;
    const visibleStartBeat = xToBeat(0);
    const visibleEndBeat = xToBeat(canvasWidth);
    let startBeat;
    if (playbackBeat >= visibleStartBeat && playbackBeat <= visibleEndBeat) {
      // Playhead is visible — snap to full beat just before playhead
      startBeat = Math.floor(playbackBeat);
    } else {
      // Playhead not visible — use center of viewport
      startBeat = Math.floor((visibleStartBeat + visibleEndBeat) / 2);
    }
    loopStartBeat = startBeat;
    loopEndBeat = startBeat + BEATS_PER_QUARTER;
    loopEnabled = true;
    console.log(`[Loop] Created loop: beat ${loopStartBeat} → ${loopEndBeat}`);
    draw();
  }

  function clearLoop() {
    loopStartBeat = null;
    loopEndBeat = null;
    loopEnabled = false;
    console.log('[Loop] Cleared');
    draw();
  }

  // Resize canvas to fit container
  function resizeCanvas() {
    if (!canvasEl) return;
    canvasEl.width = canvasEl.parentElement.clientWidth;
    canvasEl.height = viewHeight;
    console.log(`[Resize] Canvas ${canvasEl.width}x${canvasEl.height}`);
    draw();
  }

  // Load waveform peaks from audio URL via Web Audio API
  async function loadWaveform(url) {
    console.log('[Waveform] Loading from', url);
    try {
      const resp = await fetch(url);
      const arrayBuffer = await resp.arrayBuffer();
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const decoded = await audioCtx.decodeAudioData(arrayBuffer);
      audioCtx.close();

      // Store decoded buffer for grain scrubbing
      scrubAudioBuffer = decoded;

      // Downsample to 200 peaks per second (plenty for visual)
      // Use floating-point sample boundaries to avoid accumulated rounding drift.
      const rawData = decoded.getChannelData(0);
      const peaksPerSec = 200;
      const totalPeaks = Math.ceil(decoded.duration * peaksPerSec);
      const totalSamples = rawData.length;
      const peaks = new Float32Array(totalPeaks);

      for (let i = 0; i < totalPeaks; i++) {
        let max = 0;
        const start = Math.floor(i * totalSamples / totalPeaks);
        const end = Math.min(Math.floor((i + 1) * totalSamples / totalPeaks), totalSamples);
        for (let j = start; j < end; j++) {
          const abs = Math.abs(rawData[j]);
          if (abs > max) max = abs;
        }
        peaks[i] = max;
      }

      waveformPeaks = peaks;
      waveformDuration = decoded.duration;
      console.log(`[Waveform] Loaded ${totalPeaks} peaks for ${decoded.duration.toFixed(1)}s audio`);
      draw();
    } catch (err) {
      console.warn('[Waveform] Failed to load:', err);
      waveformPeaks = [];
    }
  }

  // ──── Lifecycle ──────────────────────────────
  async function loadData() {
    const session = $sessionId;
    console.log('[Step4] loadData, session:', session, 'hasResult:', !!$generationResult);
    if (!$generationResult) return;

    // Skip if already loaded for this session (prevents reactive re-triggers)
    if (dataLoadedSession === session) return;
    dataLoadedSession = session;

    try {
      const data = await getEditorData($sessionId);
      console.log('[Step4] Editor data:', { bpm: data.bpm, gap: data.gap_ms, duration: data.audio_duration, contentLen: data.ultrastar_content?.length });
      
      notes = parseUltrastar(data.ultrastar_content);
      console.log('[Step4] Parsed', notes.length, 'notes/breaks');

      // Parse extra headers from ultrastar content
      const standardKeys = new Set(['TITLE', 'ARTIST', 'BPM', 'GAP', 'DOWNBEATOFFSET']);
      extraHeaders = [];
      let foundDownbeatOffset = false;
      for (const line of (data.ultrastar_content || '').split('\n')) {
        const m = line.match(/^#([\w]+):(.*)/);
        if (m) {
          if (m[1].toUpperCase() === 'DOWNBEATOFFSET') {
            downbeatOffsetMs = parseFloat(m[2]) || 0;
            foundDownbeatOffset = true;
          } else if (!standardKeys.has(m[1].toUpperCase())) {
            extraHeaders.push({ key: m[1], value: m[2] });
          }
        }
      }
      if (foundDownbeatOffset) {
        console.log(`%c🎵 [Downbeat] Found in header: ${downbeatOffsetMs}ms`, 'color: #ff69b4; font-weight: bold');
      } else {
        console.log(`%c🎵 [Downbeat] No value in header`, 'color: #ff69b4; font-weight: bold');
      }
      if (extraHeaders.length > 0) {
        console.log('[Step4] Extra headers:', extraHeaders.map(h => h.key).join(', '));
      }

      bpm = data.bpm;
      gapMs = data.gap_ms;

      // Compute first downbeat once on load
      if (!foundDownbeatOffset) {
        downbeatFromHeader = false;
        const beatsPerMeasure = BEATS_PER_QUARTER * 4;
        const beatAtZero = (-data.gap_ms * data.bpm) / 15000;
        const firstBeat = Math.ceil(beatAtZero / beatsPerMeasure) * beatsPerMeasure;
        downbeatOffsetMs = data.gap_ms + (firstBeat * 15000 / data.bpm);
      } else {
        downbeatFromHeader = true;
      }

      // Store initial values and raw timings for BPM re-quantization
      initialBpm = data.bpm;
      initialGap = data.gap_ms;
      bpmChanged = false;
      rawTimings = data.syllable_timings || [];

      // Extract pitches from parsed notes (non-break, in order) for re-quantization
      pitchMap = notes.filter(n => n.type !== 'break').map(n => n.pitch);
      console.log('[Step4] Stored', rawTimings.length, 'raw timings,', pitchMap.length, 'pitches for re-quantization');
      audioDuration = data.audio_duration;

      // Restore save state
      editCount = data.edit_count || 0;
      lastSaveTime = data.last_saved ? new Date(data.last_saved * 1000) : null;
      hasUnsavedChanges = false;
      hasVocalsAudio = data.has_vocals !== false;
      hasOriginalAudio = data.has_original !== false;
      vocalUrl = data.vocal_url;
      originalUrl = hasOriginalAudio ? `/api/preview-audio/${$sessionId}/original` : '';
      // Default to whichever audio is available
      if (hasVocalsAudio) {
        audioSource = 'vocals';
      } else if (hasOriginalAudio) {
        audioSource = 'original';
      }
      console.log('[Step4] Audio: vocals=' + hasVocalsAudio + ', original=' + hasOriginalAudio + ', source=' + audioSource);
      computeTotalBeats();

      // Position playhead and scroll at GAP (song start)
      const gapSec = gapMs / 1000;
      currentTimeSec = gapSec;
      playbackBeat = 0; // beat 0 = GAP position
      const canvasWidth = canvasEl?.width || 800;
      scrollX = Math.max(getMinBeat() * zoom, (playbackBeat * zoom) - canvasWidth * 0.1);

      // Load waveform
      if (vocalUrl) {
        loadWaveform(vocalUrl);
      }

      updatePitchRange();
      console.log('[Step4] Pitch range:', minPitch, '-', maxPitch);
      draw();
    } catch (err) {
      console.error('[Step4] loadData error:', err);
      errorMessage.set(err.message);
    }
  }

  onMount(() => {
    console.log('[Step4] onMount');
    if (canvasEl) {
      ctx = canvasEl.getContext('2d');
      resizeCanvas();
      loadData();
    }
    window.addEventListener('keydown', handleKeydown);
    window.addEventListener('keydown', handleKeydownSave);
    window.addEventListener('resize', resizeCanvas);
    window.addEventListener('click', handleGlobalClick);
  });

  onDestroy(() => {
    if (hasUnsavedChanges) handleSave(); // autosave on navigate away
    cancelAnimationFrame(animFrame);
    window.removeEventListener('keydown', handleKeydown);
    window.removeEventListener('keydown', handleKeydownSave);
    window.removeEventListener('resize', resizeCanvas);
    window.removeEventListener('click', handleGlobalClick);
    stopMic();
  });

  // Reload when we enter this step (one-shot per session)
  $: if ($generationResult && canvasEl && $sessionId && dataLoadedSession !== $sessionId) {
    loadData();
  }
</script>

<div class="step-content">
  <h2>Step 3: Piano Roll Editor</h2>

  <div class="toolbar">
    <div class="playback-controls">
      <button class="tool-btn" on:click={() => { console.log('[UI] jump to 0s'); seekToTime(0); }} title="Jump to 0s">⏮⏮</button>
      <button class="tool-btn" on:click={() => { console.log('[UI] jump to GAP'); seekToTime(gapMs / 1000); }} title="Jump to GAP (beat 0)">⏮</button>
      <button class="tool-btn" on:click={() => { console.log('[UI] togglePlayback'); togglePlayback(); }} title="Space">
        {isPlaying ? '⏸ Pause' : '▶ Play'}
      </button>
      <span class="time-display">{formatTime(currentTimeSec)}</span>
    </div>

    <div class="zoom-controls">
      <button class="tool-btn" on:click={() => { zoom = Math.max(0.5, zoom - 1); console.log('[UI] zoom-', zoom); draw(); }}>−</button>
      <span class="zoom-label">Zoom: {zoom.toFixed(1)}x</span>
      <button class="tool-btn" on:click={() => { zoom = Math.min(100, zoom + 1); console.log('[UI] zoom+', zoom); draw(); }}>+</button>
    </div>

    <div class="mode-controls">
      <label>
        <input type="checkbox" bind:checked={scrollMode} on:change={() => console.log('[UI] scrollMode', scrollMode)} />
        Scroll
      </label>
      <label>
        <input type="checkbox" bind:checked={showWaveform} on:change={() => { console.log('[UI] waveform', showWaveform); draw(); }} />
        Wave
      </label>
      {#if showWaveform}
        <input type="range" class="wave-height-slider" min="40" max="240" step="10"
               bind:value={waveformHeight}
               on:input={() => { resizeCanvas(); draw(); }}
               title="Waveform height: {waveformHeight}px" />
        <button class="tool-btn sm" class:active={beatMarkerMode}
                on:click={() => beatMarkerMode ? (exitBeatMarkerMode(), draw()) : enterBeatMarkerMode()}
                title="Calibrate BPM by clicking downbeats on the waveform">
          ♪ Cal
        </button>
      {/if}
      <label title="Play MIDI pitch tones during playback">
        <input type="checkbox" checked={midiPlayback} on:change={toggleMidiPlayback} />
        🎹 MIDI
      </label>
      <label title="Mute vocal track">
        <input type="checkbox" checked={muteVocal} on:change={toggleMuteVocal} />
        🔇 Mute
      </label>
      <label title="Metronome click on each beat">
        <input type="checkbox" checked={metronomeEnabled} on:change={toggleMetronome} />
        🥁 Metro
      </label>
      {#if metronomeEnabled}
        <button class="tool-btn sm" class:active={metronomeOffset === 0} on:click={() => { metronomeOffset = 0; lastMetronomeBeat = -1; }} title="On beat">♩</button>
        <button class="tool-btn sm" class:active={metronomeOffset === 4} on:click={() => { metronomeOffset = 4; lastMetronomeBeat = -1; }} title="Half beat offset (8th note)">♩½</button>
      {/if}
      <label title="Loop region (Shift+drag on time ruler to set, L to toggle, Esc to clear)">
        <input type="checkbox" checked={loopEnabled} on:change={toggleLoop} />
        🔁 Loop
      </label>

      <label title="Microphone sing-along (M)">
        <input type="checkbox" bind:checked={micEnabled} on:change={toggleMic} />
        🎙️ Mic
      </label>
      {#if micEnabled}
        <div class="mic-level" title="Mic input level — tap the mic to check">
          <div class="mic-level-bar" style="height:{Math.round(micLevel * 100)}%"
               class:mic-level-hot={micLevel > 0.8}
               class:mic-level-warm={micLevel > 0.3 && micLevel <= 0.8}></div>
        </div>
        <input type="range" class="mic-gain-slider" min="0" max="200" step="1"
               value={Math.round(micGain * 100)}
               on:input={(e) => { micGain = parseInt(e.target.value) / 100; if (micGainNode) micGainNode.gain.value = micGain; }}
               title="Mic volume: {Math.round(micGain * 100)}%" />
        {#if micShowTrail}
          <button class="tool-btn sm active" on:click={() => { micShowTrail = false; draw(); }} title="Hide sung blocks">👁 Sing</button>
        {:else}
          <button class="tool-btn sm" on:click={() => { micShowTrail = true; draw(); }} title="Show sung blocks">👁 Sing</button>
        {/if}
        {#if micNoteHits.size > 0 || micPitchTrail.length > 0}
          <button class="tool-btn sm" on:click={clearMicTrail} title="Clear sung blocks">🗑</button>
        {/if}
        <label class="mic-opt" title="Debug: show raw pitch dots + enable export">
          <input type="checkbox" bind:checked={micShowRawTrail} on:change={() => draw()} />
          Raw
        </label>
        {#if micShowRawTrail && micPitchTrail.length > 0}
          <button class="tool-btn sm" on:click={exportMicTrail} title="Export mic trail as JSON">📋 Export</button>
        {/if}
        {#if micDevices.length > 1}
          <select class="mic-select" value={micDeviceId} on:change={changeMicDevice} title="Select microphone">
            {#each micDevices as device}
              <option value={device.deviceId}>{device.label || `Mic ${micDevices.indexOf(device) + 1}`}</option>
            {/each}
          </select>
        {/if}
      {/if}
    </div>

    <div class="speed-controls">
      <span class="speed-label">Speed</span>
      {#each [0.25, 0.5, 0.75, 1.0, 1.5, 2.0] as rate}
        <button
          class="tool-btn sm"
          class:active={playbackRate === rate}
          on:click={() => setPlaybackRate(rate)}
        >{rate}x</button>
      {/each}
    </div>

    <div class="bpm-controls">
      <span class="bpm-label">BPM</span>
      <button class="tool-btn sm" on:click={() => { bpm = Math.max(10, bpm - 1); handleBpmGapChange(); }}>−</button>
      <button class="tool-btn sm nudge" on:click={() => { bpm = Math.round((Math.max(10, bpm - 0.1)) * 1000) / 1000; handleBpmGapChange(); }}>−.1</button>
      <button class="tool-btn sm nudge" on:click={() => { bpm = Math.round((Math.max(10, bpm - 0.01)) * 1000) / 1000; handleBpmGapChange(); }}>−.01</button>
      <input type="number" class="bpm-input" bind:value={bpm} on:change={() => { console.log('[UI] bpm input', bpm); handleBpmGapChange(); }} step="0.001" min="10" max="1000" />
      <button class="tool-btn sm nudge" on:click={() => { bpm = Math.round((bpm + 0.01) * 1000) / 1000; handleBpmGapChange(); }}>.01+</button>
      <button class="tool-btn sm nudge" on:click={() => { bpm = Math.round((bpm + 0.1) * 1000) / 1000; handleBpmGapChange(); }}>.1+</button>
      <button class="tool-btn sm" on:click={() => { bpm = bpm + 1; handleBpmGapChange(); }}>+</button>

      <span class="bpm-label gap-label">GAP</span>
      <button class="tool-btn sm" on:click={() => { gapMs = Math.max(0, gapMs - 100); console.log('[UI] gap-', gapMs); handleBpmGapChange(); }}>−</button>
      <input type="number" class="gap-input" bind:value={gapMs} on:change={() => { console.log('[UI] gap input', gapMs); handleBpmGapChange(); }} step="100" min="0" />
      <button class="tool-btn sm" on:click={() => { gapMs = gapMs + 100; console.log('[UI] gap+', gapMs); handleBpmGapChange(); }}>+</button>
      <span class="bpm-label">ms</span>
    </div>

    <div class="save-controls">
      <button class="tool-btn save-btn" on:click={handleSave} disabled={isSaving} title="Save">
        {isSaving ? '⏳' : '💾'} Save
      </button>
      <button class="tool-btn" on:click={handleReload} title="Reload from last save">
        🔄 Reload
      </button>
      <button class="tool-btn" on:click={autoFixWordSpaces} title="Auto-add leading spaces for word boundaries">
        🔤 Fix Spaces
      </button>
      <button class="tool-btn" on:click={openTextEditor} title="Edit raw Ultrastar .txt">
        📝 Text
      </button>
      <div class="audio-source-toggle" title="Audio source">
        <button class="tool-btn sm" class:active={audioSource === 'vocals'} class:disabled-audio={!hasVocalsAudio} on:click={() => hasVocalsAudio ? switchAudioSource('vocals') : handleMissingAudio('vocals')} title={hasVocalsAudio ? 'Vocals' : 'No vocals — go to Step 1 to extract or upload'}>🎤</button>
        <button class="tool-btn sm" class:active={audioSource === 'original'} class:disabled-audio={!hasOriginalAudio} on:click={() => hasOriginalAudio ? switchAudioSource('original') : handleMissingAudio('original')} title={hasOriginalAudio ? 'Full mix' : 'No full mix — go to Step 1 to upload'}>🎵</button>
      </div>
      <div class="volume-control" title="Audio volume">
        <span class="volume-icon">{muteVocal ? '🔇' : audioVolume < 0.3 ? '🔈' : audioVolume < 0.7 ? '🔉' : '🔊'}</span>
        <input type="range" min="0" max="1" step="0.05" value={audioVolume} on:input={handleVolumeChange} class="volume-slider" />
      </div>
      {#if hasUnsavedChanges}
        <span class="unsaved-indicator">● unsaved</span>
      {:else if lastSaveTime}
        <span class="saved-indicator">✓ saved {lastSaveTime.toLocaleTimeString()}</span>
      {/if}
    </div>

    <div class="info">
      {#if selectedNote !== null}
        {@const note = notes.find(n => n.id === selectedNote)}
        {#if note && note.type !== 'break'}
          <span class="note-info">
            {note.syllable.trim()} | Beat {note.startBeat} | Dur {note.duration} | {noteName(note.pitch)}
          </span>
        {/if}
      {/if}
    </div>
  </div>

  <div class="canvas-container">
    <canvas
      bind:this={canvasEl}
      on:mousedown={handleMouseDown}
      on:mousemove={handleMouseMove}
      on:mouseup={handleMouseUp}
      on:mouseleave={handleMouseUp}
      on:wheel|nonpassive={handleWheel}
      on:contextmenu={handleContextMenu}
    ></canvas>
    {#if micStarting}
      <div class="mic-starting-overlay">
        <div class="mic-starting-box">
          🎙️ Starting microphone…
        </div>
      </div>
    {/if}
  </div>

  <!-- Grid Align mode overlay bar -->
  {#if gridAlignMode}
    <div class="gridalign-mode-bar">
      <span class="gridalign-mode-text">
        GRID ALIGN MODE — Drag or scroll to slide grid, Enter to confirm, Esc to cancel
      </span>
      <span class="gridalign-mode-offset">
        {gridAlignOffsetMs >= 0 ? '+' : ''}{gridAlignOffsetMs.toFixed(1)}ms
      </span>
      <button class="gridalign-confirm-btn" on:click={confirmGridAlign}>✓ Confirm</button>
      <button class="gridalign-cancel-btn" on:click={cancelGridAlign}>✕ Cancel</button>
    </div>
  {/if}

  <!-- Beat Marker Calibration overlay bar -->
  {#if beatMarkerMode}
    <div class="beatcal-mode-bar">
      <span class="beatcal-mode-text">BPM CAL — click any downbeats on waveform • right-click removes • Esc cancels</span>
      {#if beatMarkers.length > 0}
        <div class="beatcal-marker-list">
          {#each beatMarkers as m, i}
            <span class="beatcal-marker-item">
              bar <input class="beatcal-bar-input" type="number" min="1" step="1"
                value={m.bar}
                on:change={(e) => {
                  const v = parseInt(e.target.value);
                  if (!isNaN(v) && v >= 1) {
                    beatMarkers[i] = { ...m, bar: v };
                    beatMarkers = [...beatMarkers].sort((a, b) => a.t - b.t);
                    bpmCalcResult = calcBpmFromMarkers(beatMarkers);
                    draw();
                  }
                }} /><span class="beatcal-marker-time">@{m.t.toFixed(2)}s</span>
              <button class="beatcal-rm-btn" on:click={() => {
                beatMarkers = beatMarkers.filter((_, j) => j !== i);
                bpmCalcResult = calcBpmFromMarkers(beatMarkers);
                draw();
              }}>×</button>
            </span>
          {/each}
        </div>
      {/if}
      {#if bpmCalcResult}
        <span class="beatcal-result">
          BPM: <strong>{bpmCalcResult.bpm.toFixed(3)}</strong>
          &nbsp;·&nbsp; GAP: <strong>{bpmCalcResult.gapMs}ms</strong>
          &nbsp;({beatMarkers.length} markers)
        </span>
        <button class="beatcal-apply-btn" on:click={applyBpmCalibration}>✓ Apply</button>
      {:else}
        <span class="beatcal-hint">{beatMarkers.length < 2 ? 'Place ≥2 markers' : 'Check bar numbers'}</span>
      {/if}
      <button class="beatcal-cancel-btn" on:click={() => { exitBeatMarkerMode(); draw(); }}>✕ Cancel</button>
    </div>
  {/if}

  <!-- Set GAP mode overlay bar -->
  {#if setGapMode}
    <div class="setgap-mode-bar">
      <span class="setgap-mode-text">
        SET GAP MODE — Click a grid line to set the GAP position, or press Esc to cancel
      </span>
      <button class="setgap-cancel-btn" on:click={cancelSetGapMode}>✕ Cancel</button>
    </div>
  {/if}

  <!-- Paste mode overlay bar -->
  {#if pasteMode}
    <div class="paste-mode-bar">
      <span class="paste-mode-text">
        {clipboard?.mode === 'cut' ? '✂️ CUT' : '📋 COPY'} MODE — Click on the canvas to place {clipboard?.notes.length || 0} note{clipboard?.notes.length !== 1 ? 's' : ''}, or press Esc to cancel
      </span>
      <button class="paste-cancel-btn" on:click={cancelPaste}>✕ Cancel</button>
    </div>
  {/if}

  <!-- Selection count indicator -->
  {#if selectedNotes.size > 1 && !pasteMode}
    <div class="selection-info-bar">
      <span>{selectedNotes.size} notes selected</span>
      <span class="selection-hint">⌘X cut · ⌘C copy · Del delete · Esc deselect</span>
    </div>
  {/if}

  <!-- Context Menu -->
  {#if contextMenu.visible}
    {@const ctxNote = notes.find(n => n.id === contextMenu.noteId)}
    {#if ctxNote}
      <div
        class="context-menu"
        bind:this={contextMenuEl}
        style="left: {contextMenu.x}px; top: {contextMenu.y}px;"
      >
        {#if contextMenu.isBreak}
          <!-- Break context menu -->
          <div class="ctx-header">
            <span class="ctx-break-label">Break @ beat {ctxNote.startBeat}</span>
          </div>
          <div class="ctx-divider"></div>
          <button class="ctx-item" on:click={() => { pushUndo(); const n = notes.find(n2 => n2.id === ctxNote.id); if(n) { n.startBeat = Math.max(0, n.startBeat - 1); notes = [...notes]; markUnsaved(); draw(); } }}>
            ← Nudge Left <span class="ctx-shortcut">-1</span>
          </button>
          <button class="ctx-item" on:click={() => { pushUndo(); const n = notes.find(n2 => n2.id === ctxNote.id); if(n) { n.startBeat += 1; notes = [...notes]; markUnsaved(); draw(); } }}>
            → Nudge Right <span class="ctx-shortcut">+1</span>
          </button>
          <div class="ctx-divider"></div>
          <button class="ctx-item danger" on:click={() => deleteNote(ctxNote.id)}>
            🗑 Delete Break <span class="ctx-shortcut">Del</span>
          </button>
        {:else}
          <!-- Note context menu -->
          <div class="ctx-header">
            <input
              class="ctx-syllable-input"
              type="text"
              bind:value={editingSyllable}
              on:input={() => updateSyllable(ctxNote.id, editingSyllable)}
              on:keydown|stopPropagation={(e) => { if (e.key === 'Escape') closeContextMenu(); }}
              placeholder="syllable"
            />
            <span class="ctx-pitch">{noteName(ctxNote.pitch)}</span>
          </div>
          <label class="ctx-checkbox" class:space-on={ctxNote.syllable.startsWith(' ')} class:space-off={!ctxNote.syllable.startsWith(' ')}>
            <input type="checkbox"
              checked={ctxNote.syllable.startsWith(' ')}
              on:change={(e) => toggleWordSpace(ctxNote.id, e.target.checked)}
            />
            Word space
          </label>
          <div class="ctx-divider"></div>
          <button class="ctx-item" on:click={() => playNotePitch(ctxNote.id)}>
            🔊 Play Pitch <span class="ctx-shortcut">P</span>
          </button>
          <button class="ctx-item" on:click={() => splitNote(ctxNote.id, contextMenu.beat)}>
            ✂️ Split Note <span class="ctx-shortcut">S</span>
          </button>
          <button class="ctx-item" on:click={() => mergeWithNext(ctxNote.id)}>
            🔗 Merge with Next <span class="ctx-shortcut">M</span>
          </button>
          <div class="ctx-divider"></div>
          <div class="ctx-type-group">
            <span class="ctx-type-label">Type:</span>
            <button
              class="ctx-type-btn" class:active={!ctxNote.isGolden && !ctxNote.isRap}
              on:click={() => setNoteType(ctxNote.id, 'normal')}
            >Normal</button>
            <button
              class="ctx-type-btn golden" class:active={ctxNote.isGolden}
              on:click={() => setNoteType(ctxNote.id, 'golden')}
            >★ Golden</button>
            <button
              class="ctx-type-btn rap" class:active={ctxNote.isRap}
              on:click={() => setNoteType(ctxNote.id, 'rap')}
            >F Rap</button>
          </div>
          <div class="ctx-divider"></div>
          <button class="ctx-item" on:click={clipboardCut}>
            ✂️ Cut {selectedNotes.size > 1 ? `(${selectedNotes.size} notes)` : ''} <span class="ctx-shortcut">⌘X</span>
          </button>
          <button class="ctx-item" on:click={clipboardCopy}>
            📋 Copy {selectedNotes.size > 1 ? `(${selectedNotes.size} notes)` : ''} <span class="ctx-shortcut">⌘C</span>
          </button>
          <div class="ctx-divider"></div>
          <button class="ctx-item danger" on:click={() => deleteNote(ctxNote.id)}>
            🗑 Delete Note <span class="ctx-shortcut">Del</span>
          </button>
        {/if}
      </div>
    {:else if contextMenu.isEmpty}
      <!-- Empty space context menu -->
      <div
        class="context-menu"
        bind:this={contextMenuEl}
        style="left: {contextMenu.x}px; top: {contextMenu.y}px;"
      >
        <div class="ctx-header">
          <span class="ctx-location-label">Beat {contextMenu.beat} · {noteName(contextMenu.pitch)}</span>
        </div>
        <div class="ctx-divider"></div>
        <button class="ctx-item" on:click={() => addNoteAt(contextMenu.beat, contextMenu.pitch)}>
          🎵 Add Note
        </button>
        <button class="ctx-item" on:click={() => addBreakAt(contextMenu.beat)}>
          ┃ Add Break
        </button>
        {#if clipboard}
          <div class="ctx-divider"></div>
          <button class="ctx-item" on:click={() => { finalizePaste(contextMenu.beat); closeContextMenu(); }}>
            📌 Paste Here ({clipboard.notes.length} notes)
          </button>
        {/if}
        <div class="ctx-divider"></div>
        <button class="ctx-item" on:click={() => { seekToTime(beatToTime(contextMenu.beat)); closeContextMenu(); }}>
          ⏩ Seek Here
        </button>
      </div>
    {/if}
  {/if}

  <!-- Scrollbar -->
  <div class="scrollbar-container">
    <input
      type="range"
      class="scroll-range"
      bind:this={scrollBarEl}
      min={getMinBeat()}
      max={totalBeats}
      step="1"
      value={scrollX / zoom}
      on:input={handleScrollbar}
    />
  </div>

  <div class="legend">
    <span class="legend-item"><span class="dot blue"></span> Normal note</span>
    <span class="legend-item"><span class="dot yellow"></span> Edited note</span>
    <span class="legend-item"><span class="dot gold"></span> Golden note</span>
    <span class="legend-item"><span class="dot orange"></span> Rap note</span>
    <span class="legend-item"><span class="dot red-line"></span> Break line</span>
  </div>

  <!-- Stats bar for debugging timing -->
  {#if notes.length > 0}
    {@const realNotes = notes.filter(n => n.type !== 'break')}
    {@const firstBeat = realNotes.length > 0 ? realNotes[0].startBeat : 0}
    {@const lastNote = realNotes.length > 0 ? realNotes[realNotes.length - 1] : null}
    {@const lastBeat = lastNote ? lastNote.startBeat + lastNote.duration : 0}
    {@const firstTimeSec = gapMs / 1000 + (firstBeat * 60) / bpm}
    {@const lastTimeSec = gapMs / 1000 + (lastBeat * 60) / bpm}
    <div class="stats-bar">
      <span>
        {bpmChanged ? '⚠ Modified: ' : 'Generated: '}BPM {(bpm ?? 0).toFixed(1)}{bpmChanged ? ` (was ${(initialBpm ?? 0).toFixed(1)})` : ''} | GAP {gapMs ?? 0}ms{bpmChanged ? ` (was ${initialGap ?? 0}ms)` : ''} | Notes {firstBeat}–{lastBeat} beats | {formatTime(firstTimeSec)}–{formatTime(lastTimeSec)} | Audio {formatTime(audioDuration)}
      </span>
    </div>
  {/if}

  <!-- Hidden audio element for playback -->
  {#if vocalUrl}
    <audio bind:this={audioEl} src={vocalUrl} preload="auto"></audio>
  {/if}

  <div class="shortcut-bar">
    <div class="shortcut-group">
      <span class="shortcut-label">Navigate</span>
      <span class="shortcut"><kbd>Scroll</kbd> pan</span>
      <span class="shortcut"><kbd>⌃Scroll</kbd> zoom</span>
      <span class="shortcut"><kbd>←→</kbd> seek ±5s</span>
      <span class="shortcut"><kbd>⇧←→</kbd> ±1s</span>
      <span class="shortcut"><kbd>Space</kbd> play/pause</span>
    </div>
    <div class="shortcut-group">
      <span class="shortcut-label">Edit</span>
      <span class="shortcut"><kbd>Click</kbd> select</span>
      <span class="shortcut"><kbd>Drag</kbd> move</span>
      <span class="shortcut"><kbd>S</kbd> split</span>
      <span class="shortcut"><kbd>M</kbd> merge</span>
      <span class="shortcut"><kbd>Del</kbd> delete</span>
      <span class="shortcut"><kbd>P</kbd> play pitch</span>
    </div>
    <div class="shortcut-group">
      <span class="shortcut-label">Tools</span>
      <span class="shortcut"><kbd>⌘Z</kbd> undo</span>
      <span class="shortcut"><kbd>⇧⌘Z</kbd> redo</span>
      <span class="shortcut"><kbd>⌘S</kbd> set GAP</span>
      <span class="shortcut"><kbd>⌘G</kbd> grid align</span>
      <span class="shortcut"><kbd>L</kbd> loop</span>
    </div>
  </div>

  <!-- Text Editor Modal -->
  {#if showTextEditor}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
    <div class="modal-overlay" on:click={() => showTextEditor = false} on:keydown={(e) => e.key === 'Escape' && (showTextEditor = false)} role="dialog" aria-label="Text Editor" tabindex="-1">
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
      <div class="modal-content text-editor-modal" on:click|stopPropagation role="document">
        <div class="modal-header">
          <h3>Ultrastar Text Editor</h3>
          <button class="modal-close" on:click={() => showTextEditor = false}>✕</button>
        </div>
        <textarea
          class="text-editor-textarea"
          bind:value={textEditorContent}
          spellcheck="false"
        ></textarea>
        <div class="modal-actions">
          <button class="btn btn-secondary" on:click={() => showTextEditor = false}>Cancel</button>
          <button class="btn btn-primary" on:click={applyTextEditorContent}>Apply Changes</button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .step-content {
    max-width: 100%;
    margin: 0 auto;
  }

  h2 { color: #4fc3f7; margin-bottom: 1rem; }

  /* ── Paste mode bar ── */
  .paste-mode-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    background: linear-gradient(90deg, #1a3a2a, #2a5a3a);
    border: 1px solid #4caf50;
    border-radius: 6px;
    padding: 6px 16px;
    margin: 4px 0;
    animation: paste-pulse 1.5s ease-in-out infinite alternate;
  }
  @keyframes paste-pulse {
    from { border-color: #4caf50; }
    to { border-color: #81c784; box-shadow: 0 0 8px rgba(76, 175, 80, 0.3); }
  }
  .paste-mode-text {
    color: #a5d6a7;
    font-size: 0.85rem;
    font-weight: 500;
  }
  .paste-cancel-btn {
    background: #c62828;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.2s;
  }
  .paste-cancel-btn:hover { background: #e53935; }

  /* ── Set GAP mode bar ── */
  .setgap-mode-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    background: linear-gradient(90deg, #3a3a1a, #5a5a2a);
    border: 1px solid #ffd700;
    border-radius: 6px;
    padding: 6px 16px;
    margin: 4px 0;
    animation: setgap-pulse 1.5s ease-in-out infinite alternate;
  }
  @keyframes setgap-pulse {
    from { border-color: #ffd700; }
    to { border-color: #ffeb3b; box-shadow: 0 0 8px rgba(255, 215, 0, 0.3); }
  }
  .setgap-mode-text {
    color: #fff9c4;
    font-size: 0.85rem;
    font-weight: 500;
  }
  .setgap-cancel-btn {
    background: #c62828;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.2s;
  }
  .setgap-cancel-btn:hover { background: #e53935; }

  /* ── Beat Marker Calibration bar ── */
  .beatcal-mode-bar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: linear-gradient(90deg, #1a2a1a, #2a3a2a);
    border: 1px solid #43a047;
    border-radius: 6px;
    padding: 6px 16px;
    margin: 4px 0;
    flex-wrap: wrap;
    animation: beatcal-pulse 1.5s ease-in-out infinite alternate;
  }
  @keyframes beatcal-pulse {
    from { border-color: #43a047; }
    to { border-color: #a5d6a7; box-shadow: 0 0 8px rgba(67,160,71,0.3); }
  }
  .beatcal-mode-text {
    color: #c8e6c9;
    font-size: 0.82rem;
    font-weight: 500;
  }
  .beatcal-result {
    color: #fff;
    font-size: 0.85rem;
    font-family: monospace;
  }
  .beatcal-result strong { color: #69f0ae; }
  .beatcal-hint {
    color: #81c784;
    font-size: 0.8rem;
    font-style: italic;
  }
  .beatcal-marker-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
    max-width: 60vw;
  }
  .beatcal-marker-item {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    background: #1a2a1a;
    border: 1px solid #43a047;
    border-radius: 4px;
    padding: 1px 4px;
    font-size: 0.75rem;
    color: #a5d6a7;
    white-space: nowrap;
  }
  .beatcal-bar-input {
    width: 36px;
    padding: 0 2px;
    background: transparent;
    border: none;
    border-bottom: 1px solid #69f0ae;
    color: #69f0ae;
    font-family: monospace;
    font-size: 0.78rem;
    text-align: center;
    -moz-appearance: textfield;
    appearance: textfield;
  }
  .beatcal-bar-input::-webkit-inner-spin-button,
  .beatcal-bar-input::-webkit-outer-spin-button { -webkit-appearance: none; }
  .beatcal-marker-time { color: #888; font-size: 0.72rem; }
  .beatcal-rm-btn {
    background: none;
    border: none;
    color: #ef9a9a;
    cursor: pointer;
    padding: 0 2px;
    font-size: 0.85rem;
    line-height: 1;
  }
  .beatcal-rm-btn:hover { color: #ff5252; }
  .beatcal-apply-btn {
    background: #2e7d32;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 3px 12px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.2s;
  }
  .beatcal-apply-btn:hover { background: #43a047; }
  .beatcal-cancel-btn {
    background: #c62828;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.2s;
  }
  .beatcal-cancel-btn:hover { background: #e53935; }

  /* ── Grid Align mode bar ── */
  .gridalign-mode-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    background: linear-gradient(90deg, #2a1a3a, #3a2a5a);
    border: 1px solid #9c27b0;
    border-radius: 6px;
    padding: 6px 16px;
    margin: 4px 0;
    animation: gridalign-pulse 1.5s ease-in-out infinite alternate;
  }
  @keyframes gridalign-pulse {
    from { border-color: #9c27b0; }
    to { border-color: #ce93d8; box-shadow: 0 0 8px rgba(156, 39, 176, 0.3); }
  }
  .gridalign-mode-text {
    color: #e1bee7;
    font-size: 0.82rem;
    font-weight: 500;
  }
  .gridalign-mode-offset {
    color: #ffd700;
    font-size: 0.95rem;
    font-weight: bold;
    font-family: monospace;
    min-width: 80px;
    text-align: center;
  }
  .gridalign-confirm-btn {
    background: #2e7d32;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.2s;
  }
  .gridalign-confirm-btn:hover { background: #43a047; }
  .gridalign-cancel-btn {
    background: #c62828;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.2s;
  }
  .gridalign-cancel-btn:hover { background: #e53935; }

  /* ── Selection info bar ── */
  .selection-info-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1.5rem;
    background: rgba(33, 150, 243, 0.1);
    border: 1px solid rgba(33, 150, 243, 0.3);
    border-radius: 6px;
    padding: 4px 16px;
    margin: 4px 0;
    color: #90caf9;
    font-size: 0.82rem;
  }
  .selection-hint {
    color: #607d8b;
    font-size: 0.75rem;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.5rem;
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 8px 8px 0 0;
    flex-wrap: wrap;
  }

  .playback-controls, .zoom-controls {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }

  .time-display {
    color: #aaa;
    font-size: 0.8rem;
    font-family: monospace;
    min-width: 40px;
    margin-left: 0.25rem;
  }

  .tool-btn {
    padding: 0.4rem 0.8rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #222;
    color: #ccc;
    cursor: pointer;
    font-size: 0.85rem;
  }

  .tool-btn:hover { background: #333; }

  .zoom-label {
    color: #888;
    font-size: 0.8rem;
    min-width: 60px;
    text-align: center;
  }

  .info {
    flex: 1;
    text-align: right;
  }

  .note-info {
    color: #4fc3f7;
    font-family: 'Courier New', monospace;
    font-size: 0.8rem;
  }

  .canvas-container {
    position: relative;
    border: 1px solid #333;
    border-top: none;
    overflow: hidden;
    cursor: crosshair;
  }

  canvas {
    display: block;
    width: 100%;
  }

  .mic-starting-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    z-index: 10;
  }

  .mic-starting-box {
    background: rgba(13, 17, 23, 0.85);
    border: 1px solid #4fc3f7;
    border-radius: 8px;
    padding: 12px 24px;
    color: #ccc;
    font-size: 0.9rem;
    animation: mic-pulse 1.2s ease-in-out infinite;
  }

  @keyframes mic-pulse {
    0%, 100% { opacity: 0.7; }
    50% { opacity: 1; }
  }

  .scrollbar-container {
    padding: 0;
    background: #12121e;
    border: 1px solid #333;
    border-top: none;
  }

  .scroll-range {
    width: 100%;
    height: 18px;
    -webkit-appearance: none;
    appearance: none;
    background: transparent;
    cursor: pointer;
    margin: 0;
    display: block;
  }

  .scroll-range::-webkit-slider-runnable-track {
    height: 6px;
    background: #1a1a2e;
    border-radius: 3px;
  }

  .scroll-range::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 40px;
    height: 14px;
    background: #4fc3f7;
    border-radius: 4px;
    margin-top: -4px;
    cursor: grab;
  }

  .scroll-range::-moz-range-track {
    height: 6px;
    background: #1a1a2e;
    border-radius: 3px;
  }

  .scroll-range::-moz-range-thumb {
    width: 40px;
    height: 14px;
    background: #4fc3f7;
    border-radius: 4px;
    border: none;
    cursor: grab;
  }

  .legend {
    display: flex;
    gap: 1.5rem;
    padding: 0.5rem;
    background: #1a1a2e;
    border: 1px solid #333;
    border-top: none;
    border-radius: 0 0 8px 8px;
    font-size: 0.8rem;
    color: #888;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }

  .dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 2px;
  }

  .dot.blue { background: #4fc3f7; }
  .dot.yellow { background: #fdd835; }
  .dot.gold { background: #ffd700; }
  .dot.orange { background: #ff9800; }
  .dot.red-line { background: #c62828; width: 2px; height: 12px; }

  .save-controls {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    border-left: 1px solid #333;
    padding-left: 0.5rem;
  }

  .save-btn {
    background: #2e7d32 !important;
  }
  .save-btn:hover:not(:disabled) {
    background: #388e3c !important;
  }

  .unsaved-indicator {
    color: #ffa726;
    font-size: 0.75rem;
    font-weight: bold;
  }

  .saved-indicator {
    color: #66bb6a;
    font-size: 0.7rem;
  }

  .mode-controls {
    font-size: 0.8rem;
    color: #aaa;
    border-left: 1px solid #333;
    padding-left: 0.5rem;
  }

  .mode-controls label {
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }

  .speed-controls {
    display: flex;
    align-items: center;
    gap: 0.2rem;
    border-left: 1px solid #333;
    padding-left: 0.5rem;
  }

  .speed-label {
    color: #aaa;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.5px;
  }

  .tool-btn.sm.active {
    background: #4fc3f7;
    color: #0d1117;
    border-color: #4fc3f7;
  }

  .bpm-controls {
    display: flex;
    align-items: center;
    gap: 0.2rem;
    padding: 0 0.4rem;
    border-left: 1px solid #333;
  }

  .bpm-label {
    color: #aaa;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.5px;
  }

  .gap-label {
    margin-left: 0.6rem;
  }

  .bpm-input, .gap-input {
    width: 72px;
    padding: 0.25rem 0.3rem;
    background: #1a1a2e;
    border: 1px solid #444;
    border-radius: 4px;
    color: #4fc3f7;
    font-family: monospace;
    font-size: 0.8rem;
    text-align: center;
    -moz-appearance: textfield;
    appearance: textfield;
  }

  .gap-input {
    width: 70px;
  }

  .bpm-input::-webkit-inner-spin-button,
  .bpm-input::-webkit-outer-spin-button,
  .gap-input::-webkit-inner-spin-button,
  .gap-input::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }

  .bpm-input:focus, .gap-input:focus {
    outline: none;
    border-color: #4fc3f7;
  }

  .tool-btn.sm {
    padding: 0.2rem 0.4rem;
    font-size: 0.75rem;
    min-width: 22px;
  }

  .tool-btn.sm.nudge {
    opacity: 0.75;
    font-size: 0.68rem;
    padding: 0.15rem 0.3rem;
    min-width: 28px;
  }
  .tool-btn.sm.nudge:hover { opacity: 1; }

  .wave-height-slider {
    width: 64px;
    height: 4px;
    cursor: pointer;
    accent-color: #4fc3f7;
    vertical-align: middle;
  }

  .shortcut-bar {
    display: flex;
    justify-content: center;
    gap: 1.5rem;
    margin-top: 0.5rem;
    padding: 0.5rem 1rem;
    background: #0a0e14;
    border: 1px solid #1e2433;
    border-radius: 8px;
    flex-wrap: wrap;
  }

  .shortcut-group {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .shortcut-label {
    color: #4fc3f7;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-right: 0.15rem;
  }

  .shortcut {
    color: #667;
    font-size: 0.75rem;
    white-space: nowrap;
  }

  .shortcut kbd {
    display: inline-block;
    background: #1a1f2b;
    border: 1px solid #2a3040;
    border-radius: 3px;
    padding: 0px 4px;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 0.7rem;
    color: #aab;
    margin-right: 2px;
    line-height: 1.5;
  }

  .stats-bar {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.5rem 0.75rem;
    background: #111122;
    border: 1px solid #333;
    border-top: none;
    font-family: 'Courier New', monospace;
    font-size: 0.75rem;
    color: #888;
  }
  .stats-bar span:first-child { color: #4fc3f7; }
  .stats-bar span:nth-child(2) { color: #66bb6a; }

  /* ── Context Menu ── */
  .context-menu {
    position: fixed;
    z-index: 1000;
    min-width: 200px;
    background: #1a1a2e;
    border: 1px solid #444;
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
    padding: 4px 0;
    font-size: 0.85rem;
  }

  .ctx-header {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 6px 10px;
  }

  .ctx-syllable-input {
    flex: 1;
    background: #0d1117;
    border: 1px solid #444;
    border-radius: 4px;
    color: #eee;
    font-family: monospace;
    font-size: 0.85rem;
    padding: 4px 6px;
    outline: none;
  }

  .ctx-syllable-input:focus {
    border-color: #4fc3f7;
  }

  .ctx-pitch {
    color: #888;
    font-family: monospace;
    font-size: 0.75rem;
    white-space: nowrap;
  }

  .ctx-divider {
    height: 1px;
    background: #333;
    margin: 2px 0;
  }

  .ctx-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 6px 10px;
    background: transparent;
    border: none;
    color: #ccc;
    cursor: pointer;
    font-size: 0.83rem;
    text-align: left;
  }

  .ctx-item:hover {
    background: #2a2a4e;
  }

  .ctx-item.danger {
    color: #ef5350;
  }

  .ctx-item.danger:hover {
    background: #3a1a1a;
  }

  .ctx-shortcut {
    color: #666;
    font-size: 0.75rem;
    font-family: monospace;
    margin-left: 1rem;
  }

  .ctx-type-group {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
  }

  .ctx-checkbox {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    color: #ccc;
    font-size: 0.8rem;
    cursor: pointer;
    border-radius: 4px;
  }
  .ctx-checkbox.space-on {
    background: #1b5e2022;
    color: #66bb6a;
  }
  .ctx-checkbox.space-off {
    background: #b7161622;
    color: #ef5350;
  }
  .ctx-checkbox.space-on input[type="checkbox"] {
    accent-color: #66bb6a;
    cursor: pointer;
  }
  .ctx-checkbox.space-off input[type="checkbox"] {
    accent-color: #ef5350;
    cursor: pointer;
  }

  .ctx-type-label {
    color: #888;
    font-size: 0.75rem;
    margin-right: 4px;
  }

  .ctx-type-btn {
    padding: 3px 8px;
    border: 1px solid #444;
    border-radius: 4px;
    background: #222;
    color: #ccc;
    cursor: pointer;
    font-size: 0.75rem;
  }

  .ctx-type-btn:hover {
    background: #333;
  }

  .ctx-type-btn.active {
    background: #4fc3f7;
    color: #0d1117;
    border-color: #4fc3f7;
    font-weight: bold;
  }

  .ctx-type-btn.golden.active {
    background: #ffd700;
    border-color: #ffd700;
  }

  .ctx-type-btn.rap.active {
    background: #ff9800;
    border-color: #ff9800;
  }

  .ctx-break-label {
    color: #ef5350;
    font-family: monospace;
    font-size: 0.8rem;
    font-weight: 600;
  }

  .ctx-location-label {
    color: #aaa;
    font-family: monospace;
    font-size: 0.8rem;
  }

  /* Audio source toggle */
  .audio-source-toggle {
    display: inline-flex;
    gap: 2px;
    margin-left: 4px;
    background: #111;
    border-radius: 6px;
    padding: 1px;
  }

  .volume-control {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    margin-left: 4px;
  }

  .volume-icon {
    font-size: 0.85rem;
    cursor: default;
    user-select: none;
  }

  .volume-slider {
    width: 60px;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: #333;
    border-radius: 2px;
    outline: none;
    cursor: pointer;
  }

  .volume-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #4fc3f7;
    cursor: pointer;
  }

  .volume-slider::-moz-range-thumb {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #4fc3f7;
    cursor: pointer;
    border: none;
  }

  .mic-level {
    display: inline-block;
    width: 8px;
    height: 20px;
    background: #333;
    border: 1px solid #555;
    border-radius: 3px;
    position: relative;
    overflow: hidden;
    vertical-align: middle;
  }

  .mic-level-bar {
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    background: #4caf50;
    border-radius: 2px;
    transition: height 0.05s linear;
  }

  .mic-level-warm {
    background: #ff9800;
  }

  .mic-level-hot {
    background: #f44336;
  }

  .mic-gain-slider {
    width: 50px;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: #444;
    border-radius: 2px;
    outline: none;
    vertical-align: middle;
    cursor: pointer;
  }

  .mic-gain-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #4fc3f7;
    cursor: pointer;
  }

  .mic-select {
    background: #222;
    color: #ccc;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 2px 4px;
    font-size: 0.7rem;
    max-width: 120px;
    cursor: pointer;
  }

  .mic-select:focus {
    outline: 1px solid #4fc3f7;
  }

  .mic-opt {
    font-size: 0.75rem;
    color: #ccc;
    cursor: pointer;
    user-select: none;
  }

  .tool-btn.disabled-audio {
    opacity: 0.3;
    cursor: pointer;
    position: relative;
  }

  .tool-btn.disabled-audio:hover {
    opacity: 0.5;
    background: #3e2723;
  }

  /* Text editor modal */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal-content {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.5rem;
    max-width: 90vw;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
  }

  .text-editor-modal {
    width: 800px;
    height: 80vh;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }

  .modal-header h3 {
    margin: 0;
    color: #4fc3f7;
    font-size: 1.1rem;
  }

  .modal-close {
    background: none;
    border: none;
    color: #888;
    font-size: 1.2rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
  }

  .modal-close:hover {
    color: #ef5350;
    background: rgba(239, 83, 80, 0.1);
  }

  .text-editor-textarea {
    flex: 1;
    width: 100%;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.85rem;
    line-height: 1.5;
    background: #0d1117;
    color: #e0e0e0;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 1rem;
    resize: none;
    outline: none;
    tab-size: 4;
  }

  .text-editor-textarea:focus {
    border-color: #4fc3f7;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    margin-top: 1rem;
  }

  .btn {
    padding: 0.5rem 1.25rem;
    border: none;
    border-radius: 8px;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .btn-secondary {
    background: #21262d;
    color: #ccc;
    border: 1px solid #30363d;
  }

  .btn-secondary:hover {
    background: #30363d;
  }

  .btn-primary {
    background: #238636;
    color: #fff;
  }

  .btn-primary:hover {
    background: #2ea043;
  }
</style>
