<script>
  import { onMount } from 'svelte';
  import { currentStep, sessionId, uploadData, lyricsData, generationResult, resetSession } from '../stores/appStore.js';
  import { checkHealth, listSessions, deleteSession, importUltrastar, resumeSession, getAudioUrl } from '../services/api.js';

  let sessions = [];
  let loading = true;
  let backendOnline = false;
  let importing = false;
  let importError = '';
  let showImportPanel = false;

  // 3 file slots for import
  let importTxtFile = null;
  let importMixFile = null;
  let importVocalFile = null;
  let txtError = '';

  onMount(async () => {
    try {
      const health = await checkHealth();
      backendOnline = health.status === 'ok';
    } catch {
      backendOnline = false;
    }
    await loadSessions();
    loading = false;
  });

  async function loadSessions() {
    try {
      const data = await listSessions();
      sessions = data.sessions || [];
    } catch {
      sessions = [];
    }
  }

  function startNewSong() {
    resetSession();
    currentStep.set(1);
  }

  async function openSession(session) {
    try {
      const data = await resumeSession(session.id, { silent: true });
      sessionId.set(data.session_id);
      const hasVocals = data.has_vocals !== false;
      const hasOriginal = data.has_original === true;
      uploadData.set({
        filename: data.filename,
        hasVocals,
        hasOriginal,
        vocalUrl: hasVocals ? getAudioUrl(data.session_id, 'vocals') : (hasOriginal ? getAudioUrl(data.session_id, 'original') : null),
      });
      if (data.has_lyrics) {
        lyricsData.set({
          text: data.lyrics || '',
          artist: data.artist || '',
          title: data.title || '',
          language: data.language || 'en',
          syllableCount: data.syllable_count || 0,
          lineCount: data.line_count || 0,
          preview: [],
        });
      }
      if (data.has_result) {
        generationResult.set(data.result || {});
        currentStep.set(4);
      } else if (data.has_lyrics) {
        currentStep.set(2); // Step 3 is now a modal triggered from Step 2
      } else {
        currentStep.set(2);
      }
    } catch (e) {
      const msg = e?.message || '';
      const isAudioMissing = msg.includes('404') || msg.toLowerCase().includes('audio') || msg.toLowerCase().includes('no longer');
      if (isAudioMissing) {
        // Audio files deleted — load what we know from the session list and go to Step 1
        console.log('[Session] Audio missing — opening at Step 1:', session.id);
        sessionId.set(session.id);
        uploadData.set({ filename: null, hasVocals: false, hasOriginal: false, vocalUrl: null });
        lyricsData.set({
          text: '',
          artist: session.artist || '',
          title: session.title || '',
          language: 'en',
          syllableCount: 0,
          lineCount: 0,
          preview: [],
        });
        currentStep.set(1);
      } else {
        console.error('Failed to open session:', e);
      }
    }
  }

  async function removeSession(e, session) {
    e.stopPropagation();
    if (!confirm(`Delete "${session.title || session.id}"?`)) return;
    try {
      await deleteSession(session.id);
      sessions = sessions.filter(s => s.id !== session.id);
    } catch (e) {
      console.error('Failed to delete session:', e);
    }
  }

  // Import: 3 explicit file slots
  function toggleImportPanel() {
    showImportPanel = !showImportPanel;
    if (!showImportPanel) {
      importTxtFile = null;
      importMixFile = null;
      importVocalFile = null;
      importError = '';
      txtError = '';
    }
  }

  function pickFile(slot) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = slot === 'txt' ? '.txt' : '.mp3,.m4a,.ogg,.wav,.flac';
    input.onchange = (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      if (slot === 'txt') { importTxtFile = file; txtError = ''; }
      else if (slot === 'mix') importMixFile = file;
      else if (slot === 'vocal') importVocalFile = file;
    };
    input.click();
  }

  function clearSlot(slot) {
    if (slot === 'txt') { importTxtFile = null; txtError = ''; }
    else if (slot === 'mix') importMixFile = null;
    else if (slot === 'vocal') importVocalFile = null;
  }

  $: canImport = importTxtFile && (importMixFile || importVocalFile);

  async function handleImport() {
    if (!canImport) return;
    importError = '';
    importing = true;

    try {
      const data = await importUltrastar(importTxtFile, importMixFile, importVocalFile);
      sessionId.set(data.session_id);
      const hasVocals = !!data.has_vocals;
      const hasOriginal = !!data.has_original;
      uploadData.set({
        filename: data.filename,
        hasVocals,
        hasOriginal,
        vocalUrl: hasVocals ? getAudioUrl(data.session_id, 'vocals') : (hasOriginal ? getAudioUrl(data.session_id, 'original') : null),
      });
      lyricsData.set({
        text: data.lyrics || '',
        artist: data.artist || '',
        title: data.title || '',
        language: data.language || 'en',
        syllableCount: data.syllable_count || 0,
        lineCount: data.line_count || 0,
        preview: [],
      });
      generationResult.set(data.result || {});
      currentStep.set(4); // Go straight to editor
    } catch (e) {
      const msg = e.message || 'Import failed';
      // Show .txt-related errors inline on the txt slot
      if (msg.includes('Ultrastar') || msg.includes('notes') || msg.includes('BPM') || msg.includes('headers') || msg.includes('int()') || msg.includes('500')) {
        txtError = 'Please upload a valid Ultrastar .txt file. The file must contain note data (lines starting with : or *).';
        importError = '';
      } else {
        txtError = '';
        importError = msg;
      }
    } finally {
      importing = false;
    }
  }

  function formatTime(timestamp) {
    if (!timestamp) return '';
    const d = new Date(timestamp * 1000);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;
    return d.toLocaleDateString();
  }

  function getStatusLabel(status) {
    switch (status) {
      case 'generated': return '✓ Ready';
      case 'lyrics_submitted': return '◐ Has lyrics';
      case 'vocals_extracted': return '◑ Has vocals';
      default: return '○ Started';
    }
  }

  function getStatusColor(status) {
    switch (status) {
      case 'generated': return '#66bb6a';
      case 'lyrics_submitted': return '#ffa726';
      case 'vocals_extracted': return '#42a5f5';
      default: return '#888';
    }
  }
</script>

<div class="launcher">
  <div class="hero">
    <h1>🎤 Ultrastar Song Creator</h1>
    <p class="subtitle">Create and edit Ultrastar karaoke songs with AI</p>
    {#if !backendOnline && !loading}
      <div class="backend-warning">⚠ Backend offline — start the backend server first</div>
    {/if}
  </div>

  <div class="cards">
    <!-- Create New -->
    <button class="card card-new" on:click={startNewSong} disabled={!backendOnline}>
      <div class="card-icon">✨</div>
      <h3>Create New Song</h3>
      <p>Upload audio + lyrics and generate an Ultrastar song from scratch</p>
    </button>

    <!-- Import Existing -->
    <button class="card card-import" on:click={toggleImportPanel} disabled={!backendOnline || importing}>
      <div class="card-icon">{importing ? '⏳' : '📂'}</div>
      <h3>{importing ? 'Importing...' : 'Import Existing Song'}</h3>
      <p>Open an Ultrastar <strong>.txt</strong> with audio files in the piano roll editor</p>
      <span class="card-hint">{showImportPanel ? 'click to close' : 'click to select files'}</span>
    </button>
  </div>

  {#if showImportPanel}
    <div class="import-panel">
      <div class="import-slots">
        <!-- TXT slot (required) -->
        <div class="import-slot" class:filled={importTxtFile} class:slot-error={txtError}>
          <div class="slot-header">
            <span class="slot-label">📄 Ultrastar .txt</span>
            <span class="slot-badge required">required</span>
          </div>
          {#if importTxtFile}
            <div class="slot-file">
              <span class="slot-filename">{importTxtFile.name}</span>
              <button class="slot-clear" on:click={() => clearSlot('txt')}>✕</button>
            </div>
          {:else}
            <button class="slot-pick" on:click={() => pickFile('txt')}>Select .txt file</button>
          {/if}
          {#if txtError}
            <p class="slot-error-msg">{txtError}</p>
          {/if}
        </div>

        <!-- Mix audio slot (optional) -->
        <div class="import-slot" class:filled={importMixFile}>
          <div class="slot-header">
            <span class="slot-label">🎵 Full Mix Audio</span>
            <span class="slot-badge optional">optional</span>
          </div>
          {#if importMixFile}
            <div class="slot-file">
              <span class="slot-filename">{importMixFile.name}</span>
              <button class="slot-clear" on:click={() => clearSlot('mix')}>✕</button>
            </div>
          {:else}
            <button class="slot-pick" on:click={() => pickFile('mix')}>Select audio file</button>
          {/if}
        </div>

        <!-- Vocals audio slot (optional) -->
        <div class="import-slot" class:filled={importVocalFile}>
          <div class="slot-header">
            <span class="slot-label">🎤 Vocals Audio</span>
            <span class="slot-badge optional">optional</span>
          </div>
          {#if importVocalFile}
            <div class="slot-file">
              <span class="slot-filename">{importVocalFile.name}</span>
              <button class="slot-clear" on:click={() => clearSlot('vocal')}>✕</button>
            </div>
          {:else}
            <button class="slot-pick" on:click={() => pickFile('vocal')}>Select vocals file</button>
          {/if}
        </div>
      </div>

      {#if !importTxtFile || (!importMixFile && !importVocalFile)}
        <p class="import-hint">
          {#if !importTxtFile}
            Select an Ultrastar .txt file to start
          {:else}
            Add at least one audio file (mix or vocals)
          {/if}
        </p>
      {/if}

      {#if importError}
        <div class="import-error">{importError}</div>
      {/if}

      <button class="btn-import" on:click={handleImport} disabled={!canImport || importing}>
        {importing ? '⏳ Importing...' : '📥 Import Song'}
      </button>
    </div>
  {/if}

  <!-- Recent Sessions -->
  {#if sessions.length > 0}
    <div class="recent">
      <h2>Recent Sessions</h2>
      <div class="session-list">
        {#each sessions as session}
          <button class="session-row" on:click={() => openSession(session)}>
            <div class="session-info">
              <span class="session-title">{session.artist || 'Unknown'} — {session.title || 'Untitled'}</span>
              <span class="session-meta">
                <span class="session-status" style="color: {getStatusColor(session.status)}">{getStatusLabel(session.status)}</span>
                <span class="session-time">{formatTime(session.created_at)}</span>
              </span>
            </div>
            <button class="session-delete" on:click={(e) => removeSession(e, session)} title="Delete session">✕</button>
          </button>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .launcher {
    max-width: 700px;
    margin: 0 auto;
    padding: 2rem 1rem;
  }

  .hero {
    text-align: center;
    margin-bottom: 2rem;
  }

  .hero h1 {
    font-size: 2.2rem;
    font-weight: 300;
    color: #4fc3f7;
    margin: 0 0 0.5rem;
  }

  .subtitle {
    color: #888;
    font-size: 1rem;
    margin: 0;
  }

  .backend-warning {
    margin-top: 1rem;
    padding: 0.5rem 1rem;
    background: #3e2723;
    border: 1px solid #ef5350;
    border-radius: 8px;
    color: #ef9a9a;
    font-size: 0.85rem;
  }

  .cards {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin-bottom: 1.5rem;
    padding: 4px;
    border-radius: 16px;
  }

  .card {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 2rem 1.5rem;
    background: #161b22;
    border: 2px solid #30363d;
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.2s;
    color: #e0e0e0;
    font-family: inherit;
  }

  .card:hover:not(:disabled) {
    border-color: #4fc3f7;
    background: #1a2a3e;
    transform: translateY(-2px);
  }

  .card:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .card-icon {
    font-size: 2.5rem;
    margin-bottom: 0.75rem;
  }

  .card h3 {
    margin: 0 0 0.5rem;
    font-size: 1.1rem;
    color: #e0e0e0;
  }

  .card p {
    margin: 0;
    font-size: 0.85rem;
    color: #888;
    line-height: 1.4;
  }

  .card-hint {
    margin-top: 0.75rem;
    font-size: 0.75rem;
    color: #555;
  }

  .card-import:hover:not(:disabled) .card-hint {
    color: #4fc3f7;
  }

  /* Import panel with 3 file slots */
  .import-panel {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
  }

  .import-slots {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .import-slot {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    padding: 0.75rem 1rem;
    background: #0d1117;
    border: 1px dashed #30363d;
    border-radius: 8px;
    transition: all 0.2s;
  }

  .import-slot.filled {
    border-style: solid;
    border-color: #2ea043;
    background: #0d1117;
  }

  .slot-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .slot-label {
    font-size: 0.85rem;
    color: #c9d1d9;
    font-weight: 500;
  }

  .slot-badge {
    font-size: 0.65rem;
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
    text-transform: uppercase;
    font-weight: 600;
    letter-spacing: 0.03em;
  }

  .slot-badge.required {
    background: #3e2723;
    color: #ef9a9a;
  }

  .slot-badge.optional {
    background: #1a2e4a;
    color: #4fc3f7;
  }

  .slot-file {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0.6rem;
    background: #1a2e1a;
    border-radius: 6px;
  }

  .slot-filename {
    font-size: 0.8rem;
    color: #66bb6a;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .slot-clear {
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    padding: 0.1rem 0.3rem;
    border-radius: 4px;
    font-size: 0.8rem;
  }

  .slot-clear:hover {
    color: #ef5350;
    background: rgba(239, 83, 80, 0.1);
  }

  .slot-pick {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #8b949e;
    padding: 0.4rem 0.8rem;
    cursor: pointer;
    font-size: 0.8rem;
    transition: all 0.15s;
    font-family: inherit;
  }

  .slot-pick:hover {
    background: #30363d;
    color: #c9d1d9;
    border-color: #4fc3f7;
  }

  .import-slot.slot-error {
    border-color: #ef5350;
    border-style: solid;
    background: #1a0d0d;
  }

  .slot-error-msg {
    margin: 0.3rem 0 0;
    font-size: 0.75rem;
    color: #ef9a9a;
    line-height: 1.3;
  }

  .import-hint {
    text-align: center;
    color: #666;
    font-size: 0.8rem;
    margin: 0.75rem 0 0;
  }

  .import-error {
    text-align: center;
    padding: 0.5rem 1rem;
    margin-top: 0.75rem;
    background: #3e2723;
    border: 1px solid #ef5350;
    border-radius: 8px;
    color: #ef9a9a;
    font-size: 0.85rem;
  }

  .btn-import {
    display: block;
    width: 100%;
    margin-top: 1rem;
    padding: 0.75rem;
    background: #1976d2;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.95rem;
    cursor: pointer;
    transition: all 0.2s;
    font-family: inherit;
    font-weight: 500;
  }

  .btn-import:hover:not(:disabled) {
    background: #1565c0;
  }

  .btn-import:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .recent h2 {
    font-size: 1rem;
    font-weight: 600;
    color: #888;
    margin: 0 0 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .session-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .session-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.15s;
    color: inherit;
    font-family: inherit;
    text-align: left;
    width: 100%;
  }

  .session-row:hover {
    background: #1a2a3e;
    border-color: #30363d;
  }

  .session-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    min-width: 0;
  }

  .session-title {
    font-size: 0.95rem;
    color: #e0e0e0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .session-meta {
    display: flex;
    gap: 0.75rem;
    font-size: 0.8rem;
  }

  .session-status {
    font-weight: 600;
  }

  .session-time {
    color: #555;
  }

  .session-delete {
    background: none;
    border: none;
    color: #555;
    font-size: 1rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    transition: all 0.15s;
  }

  .session-delete:hover {
    color: #ef5350;
    background: rgba(239, 83, 80, 0.1);
  }
</style>
