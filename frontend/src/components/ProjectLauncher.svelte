<script>
  import { onMount } from 'svelte';
  import { currentStep, sessionId, uploadData, lyricsData, generationResult, resetSession } from '../stores/appStore.js';
  import { checkHealth, listSessions, deleteSession, importUltrastar, resumeSession, getAudioUrl } from '../services/api.js';

  let sessions = [];
  let loading = true;
  let backendOnline = false;
  let importing = false;
  let importError = '';
  let dragOver = false;

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
      const data = await resumeSession(session.id);
      sessionId.set(data.session_id);
      uploadData.set({
        filename: data.filename,
        hasVocals: true,
        vocalUrl: getAudioUrl(data.session_id, 'vocals'),
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
        currentStep.set(3);
      } else {
        currentStep.set(2);
      }
    } catch (e) {
      console.error('Failed to open session:', e);
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

  // Import: accept .txt + .mp3 via file picker or drag-and-drop
  async function handleImportClick() {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = '.txt,.mp3,.m4a,.ogg,.wav,.flac';
    input.onchange = (e) => handleImportFiles(Array.from(e.target.files));
    input.click();
  }

  function handleDragOver(e) {
    e.preventDefault();
    dragOver = true;
  }

  function handleDragLeave() {
    dragOver = false;
  }

  function handleDrop(e) {
    e.preventDefault();
    dragOver = false;
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) handleImportFiles(files);
  }

  async function handleImportFiles(files) {
    importError = '';
    importing = true;
    
    const txtFile = files.find(f => f.name.toLowerCase().endsWith('.txt'));
    const audioFile = files.find(f => /\.(mp3|m4a|ogg|wav|flac)$/i.test(f.name));
    
    if (!txtFile) {
      importError = 'Please include an Ultrastar .txt file';
      importing = false;
      return;
    }
    if (!audioFile) {
      importError = 'Please include an audio file (.mp3, .m4a, .wav, etc.)';
      importing = false;
      return;
    }

    try {
      const data = await importUltrastar(txtFile, audioFile);
      sessionId.set(data.session_id);
      uploadData.set({
        filename: data.filename,
        hasVocals: true,
        vocalUrl: getAudioUrl(data.session_id, 'original'),
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
      importError = e.message || 'Import failed';
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

  <div class="cards" class:drag-over={dragOver} role="region" aria-label="Project actions" on:dragover={handleDragOver} on:dragleave={handleDragLeave} on:drop={handleDrop}>
    <!-- Create New -->
    <button class="card card-new" on:click={startNewSong} disabled={!backendOnline}>
      <div class="card-icon">✨</div>
      <h3>Create New Song</h3>
      <p>Upload audio + lyrics and generate an Ultrastar song from scratch</p>
    </button>

    <!-- Import Existing -->
    <button class="card card-import" on:click={handleImportClick} disabled={!backendOnline || importing}>
      <div class="card-icon">{importing ? '⏳' : '📂'}</div>
      <h3>{importing ? 'Importing...' : 'Import Existing Song'}</h3>
      <p>Open an Ultrastar .txt + audio file to edit in the piano roll</p>
      <span class="card-hint">or drag & drop files here</span>
    </button>
  </div>

  {#if importError}
    <div class="import-error">{importError}</div>
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
    margin-bottom: 2rem;
    padding: 4px;
    border-radius: 16px;
    transition: outline 0.2s;
  }

  .cards.drag-over {
    outline: 2px dashed #4fc3f7;
    outline-offset: 4px;
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

  .import-error {
    text-align: center;
    padding: 0.5rem 1rem;
    margin-bottom: 1.5rem;
    background: #3e2723;
    border: 1px solid #ef5350;
    border-radius: 8px;
    color: #ef9a9a;
    font-size: 0.85rem;
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
