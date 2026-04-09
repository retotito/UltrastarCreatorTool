<script>
  import { sessionId, generationResult, errorMessage, isProcessing, lyricsData, uploadData, currentStep } from '../stores/appStore.js';
  import { getDownloadUrl, getAudioUrl } from '../services/api.js';
  import { resetSession } from '../stores/appStore.js';

  let exported = false;

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
      <div class="info-banner">
        <span>⚠️ {!hasArtist && !hasTitle ? 'Artist and title are' : !hasArtist ? 'Artist is' : 'Title is'} missing — filenames will use "{getBaseFilename()}"</span>
        <button class="link-btn" on:click={() => currentStep.set(2)}>→ Go to Lyrics to add {!hasArtist && !hasTitle ? 'them' : 'it'}</button>
      </div>
    {/if}

    <div class="summary-card">
      <h3>Song Info</h3>
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
        <button class="btn btn-primary download-all" on:click={downloadAll}>
          ⬇ Download All
        </button>
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
</style>
