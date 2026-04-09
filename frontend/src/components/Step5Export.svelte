<script>
  import { sessionId, generationResult, errorMessage, isProcessing, lyricsData, uploadData, currentStep } from '../stores/appStore.js';
  import { getDownloadUrl, getAudioUrl, updateMetadata, getDownloadZipUrl } from '../services/api.js';
  import { resetSession } from '../stores/appStore.js';

  let exported = false;
  let showEditPopup = false;
  let editArtist = '';
  let editTitle = '';
  let saving = false;

  $: hasArtist = !!($lyricsData?.artist?.trim());
  $: hasTitle = !!($lyricsData?.title?.trim());
  $: missingInfo = !hasArtist || !hasTitle;

  function getBaseFilename() {
    const artist = ($lyricsData?.artist || '').trim();
    const title = ($lyricsData?.title || '').trim();
    if (artist && title) return `${artist} - ${title}`;
    if (title) return title;
    if (artist) return artist;
    return 'Untitled Song';
  }

  function openEditPopup() {
    editArtist = $lyricsData?.artist || '';
    editTitle = $lyricsData?.title || '';
    showEditPopup = true;
  }

  async function saveMetadata() {
    saving = true;
    try {
      await updateMetadata($sessionId, editArtist.trim(), editTitle.trim());
      lyricsData.update(d => ({ ...d, artist: editArtist.trim(), title: editTitle.trim() }));
      showEditPopup = false;
    } catch (e) {
      console.error('Failed to save metadata:', e);
    } finally {
      saving = false;
    }
  }

  function handleEditKeydown(e) {
    if (e.key === 'Enter') saveMetadata();
    if (e.key === 'Escape') showEditPopup = false;
  }

  function downloadZip() {
    const url = getDownloadZipUrl($sessionId);
    const a = document.createElement('a');
    a.href = url;
    a.download = getBaseFilename() + '.zip';
    document.body.appendChild(a);
    a.click();
    a.remove();
    exported = true;
  }

  function downloadFile(type) {
    const url = getDownloadUrl($sessionId, type);
    const base = getBaseFilename();
    const extMap = { txt: '.txt', midi: '.mid', summary: '_summary.txt' };
    const a = document.createElement('a');
    a.href = url;
    a.download = base + (extMap[type] || '.txt');
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function downloadAudio(type) {
    const url = getAudioUrl($sessionId, type);
    const base = getBaseFilename();
    const suffix = type === 'vocals' ? ' [Vocals]' : '';
    const a = document.createElement('a');
    a.href = url;
    a.download = base + suffix;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function downloadAll() {
    // Download each file with a small delay so browser doesn't block them
    const files = ['txt'];
    if ($generationResult?.midi_file) files.push('midi');
    if ($generationResult?.summary_file) files.push('summary');

    for (const type of files) {
      downloadFile(type);
      await new Promise(r => setTimeout(r, 300));
    }
    // Download available audio
    if ($uploadData.hasVocals) {
      downloadAudio('vocals');
      await new Promise(r => setTimeout(r, 300));
    }
    if ($uploadData.hasOriginal) {
      downloadAudio('original');
    }
    exported = true;
  }

  function startOver() {
    resetSession();
  }
</script>

<div class="step-content">
  <h2>Step 5: Export & Download</h2>

  {#if $generationResult}
    {#if missingInfo}
      {@const previewArtist = ($lyricsData?.artist || '').trim() || 'Unknown'}
      {@const previewTitle = ($lyricsData?.title || '').trim() || 'Unknown'}
      <div class="info-banner">
        <span>⚠️ {!hasArtist && !hasTitle ? 'Artist and title are' : !hasArtist ? 'Artist is' : 'Title is'} missing — filenames will use "{previewArtist} - {previewTitle}"</span>
        <button class="link-btn" on:click={openEditPopup}>✏️ Add now</button>
      </div>
    {/if}

    <div class="summary-card">
      <div class="summary-header">
        <h3>Song Info</h3>
        <button class="edit-btn" on:click={openEditPopup} title="Edit artist & title">✏️</button>
      </div>
      <div class="summary-grid">
        <div class="summary-item wide">
          <span class="label">Song</span>
          <span class="value">{$lyricsData?.artist || 'Unknown'} — {$lyricsData?.title || 'Untitled'}</span>
        </div>
        <div class="summary-item">
          <span class="label">BPM</span>
          <span class="value">{$generationResult.bpm}</span>
        </div>
        <div class="summary-item">
          <span class="label">GAP</span>
          <span class="value">{$generationResult.gap_ms}ms</span>
        </div>
        <div class="summary-item">
          <span class="label">Notes</span>
          <span class="value">{$generationResult.syllable_count}</span>
        </div>
      </div>
    </div>

    <div class="download-section">
      <div class="download-header">
        <h3>Download Files</h3>
        <div class="download-header-buttons">
          <button class="btn btn-primary download-all" on:click={downloadZip}>
            📦 Download ZIP
          </button>
          <button class="btn btn-secondary download-all" on:click={downloadAll}>
            ⬇ All Files Individual
          </button>
        </div>
      </div>

      <div class="download-grid">
        <button class="download-btn" on:click={() => downloadFile('txt')}>
          <span class="file-icon">📄</span>
          <span class="file-name">Ultrastar .txt</span>
          <span class="file-desc">Note file for Ultrastar players</span>
        </button>

        {#if $generationResult?.midi_file}
          <button class="download-btn" on:click={() => downloadFile('midi')}>
            <span class="file-icon">🎵</span>
            <span class="file-name">MIDI</span>
            <span class="file-desc">Pitch data as MIDI</span>
          </button>
        {/if}

        <button class="download-btn" on:click={() => downloadAudio('vocals')} disabled={!$uploadData.hasVocals}>
          <span class="file-icon">🎤</span>
          <span class="file-name">Vocals</span>
          <span class="file-desc">{$uploadData.hasVocals ? 'Separated vocal track' : 'Not available'}</span>
        </button>

        <button class="download-btn" on:click={() => downloadAudio('original')} disabled={!$uploadData.hasOriginal}>
          <span class="file-icon">🎶</span>
          <span class="file-name">Full Mix</span>
          <span class="file-desc">{$uploadData.hasOriginal ? 'Original audio file' : 'Not available'}</span>
        </button>

        {#if $generationResult?.summary_file}
          <button class="download-btn" on:click={() => downloadFile('summary')}>
            <span class="file-icon">📋</span>
            <span class="file-name">Summary</span>
            <span class="file-desc">Processing report</span>
          </button>
        {/if}
      </div>
    </div>

    {#if exported}
      <div class="success-banner">✓ Files downloaded</div>
    {/if}

    <div class="actions">
      <button class="btn btn-secondary" on:click={startOver}>
        ↩ Start New Song
      </button>
    </div>
  {:else}
    <p class="no-result">No generation result yet. Go back to Step 3 to generate files.</p>
  {/if}

  {#if $errorMessage}
    <div class="error-bar">❌ {$errorMessage}</div>
  {/if}

  {#if showEditPopup}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="modal-overlay" on:click={() => showEditPopup = false}>
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="modal" on:click|stopPropagation>
        <h3>Edit Song Info</h3>
        <div class="modal-field">
          <label for="edit-artist">Artist</label>
          <input id="edit-artist" type="text" bind:value={editArtist} placeholder="Artist name" on:keydown={handleEditKeydown} />
        </div>
        <div class="modal-field">
          <label for="edit-title">Title</label>
          <input id="edit-title" type="text" bind:value={editTitle} placeholder="Song title" on:keydown={handleEditKeydown} />
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" on:click={() => showEditPopup = false}>Cancel</button>
          <button class="btn btn-primary" on:click={saveMetadata} disabled={saving}>
            {saving ? 'Saving...' : '💾 Save'}
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .step-content {
    max-width: 600px;
    margin: 0 auto;
  }

  h2 { color: #4fc3f7; margin-bottom: 1rem; }
  h3 { color: #aaa; margin: 0; font-size: 0.95rem; }

  .summary-card {
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 1rem;
  }

  .summary-card h3 { margin-bottom: 0.75rem; }

  .summary-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
  }
  .summary-header h3 { margin-bottom: 0; }

  .edit-btn {
    background: none;
    border: 1px solid #555;
    border-radius: 6px;
    color: #aaa;
    cursor: pointer;
    padding: 0.2rem 0.5rem;
    font-size: 0.8rem;
    transition: all 0.15s;
  }
  .edit-btn:hover {
    border-color: #4fc3f7;
    color: #4fc3f7;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
  }

  .summary-item {
    text-align: center;
  }

  .summary-item.wide {
    grid-column: 1 / -1;
  }

  .label {
    display: block;
    color: #666;
    font-size: 0.75rem;
    text-transform: uppercase;
  }

  .value {
    display: block;
    color: #4fc3f7;
    font-size: 1rem;
    font-weight: 600;
  }

  .download-section {
    margin-top: 1.5rem;
  }

  .download-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
  }

  .download-all {
    font-size: 0.9rem;
    padding: 0.5rem 1.25rem;
  }

  .download-header-buttons {
    display: flex;
    gap: 0.5rem;
  }

  .download-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
  }

  .download-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    padding: 1.25rem 0.5rem;
    border: 1px solid #444;
    border-radius: 8px;
    background: #1a1a2e;
    color: #ccc;
    cursor: pointer;
    transition: all 0.2s;
  }

  .download-btn:hover:not(:disabled) {
    border-color: #4fc3f7;
    background: #1a2e4a;
  }

  .download-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .file-icon { font-size: 2rem; }
  .file-name { font-weight: 600; font-size: 0.9rem; }
  .file-desc { font-size: 0.7rem; color: #666; text-align: center; }

  .success-banner {
    text-align: center;
    padding: 0.5rem;
    margin-top: 1rem;
    background: #1a3a2a;
    border: 1px solid #66bb6a;
    border-radius: 8px;
    color: #66bb6a;
    font-size: 0.85rem;
  }

  .actions {
    margin-top: 2rem;
    text-align: center;
  }

  .btn {
    padding: 0.6rem 1.5rem;
    border: none;
    border-radius: 8px;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .btn-secondary {
    background: #333;
    color: #ccc;
    border: 1px solid #555;
  }
  .btn-secondary:hover { background: #444; }

  .btn-primary {
    background: #238636;
    color: #fff;
  }
  .btn-primary:hover { background: #2ea043; }

  .no-result {
    color: #666;
    text-align: center;
    padding: 2rem;
  }

  .info-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    background: #2a2a1a;
    border: 1px solid #f9a825;
    border-radius: 8px;
    padding: 0.65rem 1rem;
    margin-bottom: 1rem;
    color: #fdd835;
    font-size: 0.85rem;
  }

  .link-btn {
    background: none;
    border: 1px solid #f9a825;
    border-radius: 6px;
    color: #fdd835;
    cursor: pointer;
    padding: 0.3rem 0.75rem;
    font-size: 0.8rem;
    white-space: nowrap;
    transition: all 0.15s;
  }
  .link-btn:hover {
    background: #3a3a2a;
    border-color: #fdd835;
  }

  .error-bar {
    background: #3e1a1a;
    border: 1px solid #c62828;
    border-radius: 8px;
    padding: 0.75rem;
    margin-top: 1rem;
    color: #ef9a9a;
    text-align: center;
  }

  /* Modal overlay & popup */
  .modal-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: #1a1a2e;
    border: 1px solid #444;
    border-radius: 12px;
    padding: 1.5rem;
    width: 360px;
    max-width: 90vw;
  }

  .modal h3 {
    color: #4fc3f7;
    margin: 0 0 1rem;
  }

  .modal-field {
    margin-bottom: 0.75rem;
  }

  .modal-field label {
    display: block;
    color: #888;
    font-size: 0.75rem;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
  }

  .modal-field input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid #555;
    border-radius: 6px;
    background: #111;
    color: #eee;
    font-size: 0.95rem;
    box-sizing: border-box;
  }
  .modal-field input:focus {
    outline: none;
    border-color: #4fc3f7;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 1rem;
  }
</style>
