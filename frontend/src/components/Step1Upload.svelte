<script>
  import { sessionId, uploadData, currentStep, isProcessing, processingStatus, errorMessage, lyricsData, generationResult, generationLog, generationShowPreview } from '../stores/appStore.js';
  import { uploadAudio, extractVocals, uploadCorrectedVocals, uploadMixAudio, deleteAudio, getAudioUrl, resumeLastSession, getGenerationResult } from '../services/api.js';

  let dragOverMix = false;
  let dragOverVocals = false;
  let audioPlayerMix;
  let audioPlayerVocals;

  $: mixUrl    = $sessionId && $uploadData.hasOriginal ? getAudioUrl($sessionId, 'original') : null;
  $: vocalsUrl = $sessionId && $uploadData.hasVocals   ? getAudioUrl($sessionId, 'vocals')   : null;

  // ── Mix upload ──────────────────────────────────────────
  async function handleMixFile(file) {
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Uploading full mix…');
    try {
      if ($sessionId) {
        await uploadMixAudio($sessionId, file);
        uploadData.update(d => ({ ...d, filename: file.name, hasOriginal: true }));
      } else {
        const result = await uploadAudio(file);
        sessionId.set(result.session_id);
        uploadData.update(d => ({ ...d, filename: result.filename, hasOriginal: true }));
      }
      processingStatus.set('Full mix uploaded.');
    } catch (err) {
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }

  // ── Vocals upload ────────────────────────────────────────
  async function handleVocalsFile(file) {
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Uploading vocals…');
    try {
      if ($sessionId) {
        await uploadCorrectedVocals($sessionId, file);
      } else {
        const result = await uploadAudio(file);
        sessionId.set(result.session_id);
        await uploadCorrectedVocals(result.session_id, file);
      }
      uploadData.update(d => ({
        ...d,
        hasVocals: true,
        vocalUrl: getAudioUrl($sessionId, 'vocals'),
      }));
      processingStatus.set('Vocals uploaded.');
    } catch (err) {
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }

  // ── Vocal extraction ─────────────────────────────────────
  async function handleExtractVocals() {
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Extracting vocals with Demucs (this may take a few minutes)…');
    try {
      await extractVocals($sessionId);
      uploadData.update(d => ({
        ...d,
        hasVocals: true,
        vocalUrl: getAudioUrl($sessionId, 'vocals'),
      }));
      processingStatus.set('Vocals extracted!');
    } catch (err) {
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }

  // ── Delete ───────────────────────────────────────────────
  async function handleDeleteAudio(type) {
    errorMessage.set('');
    try {
      await deleteAudio($sessionId, type);
      if (type === 'original') {
        uploadData.update(d => ({ ...d, hasOriginal: false }));
      } else {
        uploadData.update(d => ({ ...d, hasVocals: false, vocalUrl: null }));
      }
    } catch (err) {
      errorMessage.set(err.message);
    }
  }

  // ── Drag & drop helpers ──────────────────────────────────
  function onDropMix(e) {
    e.preventDefault();
    dragOverMix = false;
    const file = e.dataTransfer.files?.[0];
    if (file) handleMixFile(file);
  }

  function onDropVocals(e) {
    e.preventDefault();
    dragOverVocals = false;
    const file = e.dataTransfer.files?.[0];
    if (file) handleVocalsFile(file);
  }

  // ── Resume last ──────────────────────────────────────────
  async function handleResumeLast() {
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Resuming last session…');
    try {
      const result = await resumeLastSession();
      sessionId.set(result.session_id);
      uploadData.set({
        filename: result.filename,
        hasVocals: true,
        hasOriginal: true,
        vocalUrl: getAudioUrl(result.session_id, 'vocals'),
      });
      if (result.has_lyrics) {
        lyricsData.set({
          text: result.lyrics,
          artist: result.artist,
          title: result.title,
          language: result.language,
          syllableCount: result.syllable_count,
          lineCount: result.line_count,
          preview: [],
        });
        if (result.has_result) {
          try {
            const genResult = await getGenerationResult(result.session_id);
            if (genResult?.status === 'ok') {
              generationResult.set(genResult);
              generationShowPreview.set(true);
              generationLog.set([{ time: new Date().toLocaleTimeString(), text: `📂 Restored previous generation (BPM: ${genResult.bpm}, GAP: ${genResult.gap_ms}ms)` }]);
            }
          } catch {}
        }
        currentStep.set(result.has_result && $generationResult ? 4 : 3);
      } else {
        currentStep.set(2);
      }
      processingStatus.set('');
    } catch (err) {
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }
</script>

<div class="step-content">
  <h2>Step 1: Upload Audio</h2>
  <p class="subtitle">Upload your audio files below. Full mix is optional — vocals are required to proceed.</p>

  <div class="audio-grid">

    <!-- ── Full Mix Card ── -->
    <div class="audio-card" class:has-file={$uploadData.hasOriginal}>
      <div class="card-header">
        <span class="card-title">🎵 Full Mix</span>
        <span class="card-badge optional">optional</span>
      </div>

      {#if $uploadData.hasOriginal}
        <div class="file-info">
          <span class="file-name">✅ {$uploadData.filename || 'mix audio'}</span>
        </div>
        <div class="audio-preview">
          <audio bind:this={audioPlayerMix} controls src={mixUrl}></audio>
        </div>
        <div class="card-actions">
          <label class="btn btn-replace">
            ↻ Replace
            <input type="file" accept="audio/*" on:change={(e) => { const f = e.target.files?.[0]; if (f) handleMixFile(f); e.target.value=''; }} hidden />
          </label>
          <button class="btn btn-delete" on:click={() => handleDeleteAudio('original')} disabled={$isProcessing}>
            🗑
          </button>
        </div>
      {:else}
        <div
          class="drop-zone"
          class:drag-over={dragOverMix}
          role="button"
          tabindex="0"
          on:dragover|preventDefault={() => (dragOverMix = true)}
          on:dragleave={() => (dragOverMix = false)}
          on:drop={onDropMix}
        >
          <div class="drop-icon">🎵</div>
          <p class="drop-text">Drag & drop full mix here</p>
          <p class="drop-hint">MP3, WAV, FLAC, …</p>
          <label class="btn btn-browse" class:disabled={$isProcessing}>
            📁 Browse
            <input type="file" accept="audio/*" on:change={(e) => { const f = e.target.files?.[0]; if (f) handleMixFile(f); e.target.value=''; }} hidden />
          </label>
        </div>
      {/if}
    </div>

    <!-- ── Vocals Card ── -->
    <div class="audio-card" class:has-file={$uploadData.hasVocals}>
      <div class="card-header">
        <span class="card-title">🎤 Vocals</span>
        <span class="card-badge required">required</span>
      </div>

      {#if $uploadData.hasVocals}
        <div class="file-info">
          <span class="file-name">✅ Vocals ready</span>
        </div>
        {#if vocalsUrl}
          <div class="audio-preview">
            <audio bind:this={audioPlayerVocals} controls src={vocalsUrl}></audio>
          </div>
        {/if}
        <div class="card-actions">
          <label class="btn btn-replace">
            ↻ Replace
            <input type="file" accept="audio/*" on:change={(e) => { const f = e.target.files?.[0]; if (f) handleVocalsFile(f); e.target.value=''; }} hidden />
          </label>
          <button class="btn btn-delete" on:click={() => handleDeleteAudio('vocals')} disabled={$isProcessing}>
            🗑
          </button>
        </div>
      {:else}
        <div
          class="drop-zone"
          class:drag-over={dragOverVocals}
          role="button"
          tabindex="0"
          on:dragover|preventDefault={() => (dragOverVocals = true)}
          on:dragleave={() => (dragOverVocals = false)}
          on:drop={onDropVocals}
        >
          <div class="drop-icon">🎤</div>
          <p class="drop-text">Drag & drop vocals here</p>
          <p class="drop-hint">Already isolated? Drop directly</p>
          <label class="btn btn-browse" class:disabled={$isProcessing}>
            📁 Browse
            <input type="file" accept="audio/*" on:change={(e) => { const f = e.target.files?.[0]; if (f) handleVocalsFile(f); e.target.value=''; }} hidden />
          </label>
        </div>

        {#if $uploadData.hasOriginal && $sessionId}
          <button class="btn btn-extract" on:click={handleExtractVocals} disabled={$isProcessing}>
            {$isProcessing ? '⏳ Extracting…' : '⚡ Extract from Mix (Demucs)'}
          </button>
        {/if}
      {/if}
    </div>

  </div>

  {#if $processingStatus}
    <div class="status-bar">{$processingStatus}</div>
  {/if}

  {#if $errorMessage}
    <div class="error-bar">❌ {$errorMessage}</div>
  {/if}
</div>

<style>
  .step-content {
    max-width: 680px;
    margin: 0 auto;
  }

  h2 { color: #4fc3f7; margin-bottom: 0.25rem; }

  .subtitle {
    color: #666;
    font-size: 0.85rem;
    margin-bottom: 1.5rem;
  }

  /* ── Two-column grid ── */
  .audio-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
  }

  @media (max-width: 520px) {
    .audio-grid { grid-template-columns: 1fr; }
  }

  /* ── Audio card ── */
  .audio-card {
    border: 2px solid #2a2a3e;
    border-radius: 12px;
    padding: 1rem;
    background: #12121e;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    transition: border-color 0.2s;
  }

  .audio-card.has-file {
    border-color: #2e7d32;
    background: #0f1e0f;
  }

  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .card-title {
    font-weight: 600;
    font-size: 0.95rem;
    color: #ccc;
  }

  .card-badge {
    font-size: 0.7rem;
    padding: 2px 7px;
    border-radius: 10px;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }

  .card-badge.optional {
    background: #1a1a2e;
    color: #666;
    border: 1px solid #2a2a3e;
  }

  .card-badge.required {
    background: #1a263a;
    color: #4fc3f7;
    border: 1px solid #1976d2;
  }

  /* ── Drop zone ── */
  .drop-zone {
    border: 2px dashed #333;
    border-radius: 10px;
    padding: 1.5rem 1rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.4rem;
  }

  .drop-zone.drag-over {
    border-color: #4fc3f7;
    background: #1a2e4a22;
  }

  .drop-zone:hover { border-color: #555; }

  .drop-icon { font-size: 2rem; }

  .drop-text { color: #aaa; font-size: 0.88rem; margin: 0; }
  .drop-hint { color: #555; font-size: 0.78rem; margin: 0; }

  /* ── File present state ── */
  .file-info { display: flex; align-items: center; }

  .file-name {
    color: #66bb6a;
    font-size: 0.85rem;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .audio-preview audio { width: 100%; height: 36px; }

  .card-actions { display: flex; gap: 0.5rem; }

  /* ── Buttons ── */
  .btn {
    display: inline-block;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.15s;
    border: none;
    text-align: center;
  }

  .btn-browse {
    background: #1a1a2e;
    color: #4fc3f7;
    border: 1px solid #1976d2;
    margin-top: 0.5rem;
  }
  .btn-browse:hover:not(.disabled) { background: #1a2e4a; }
  .btn-browse.disabled { opacity: 0.4; cursor: not-allowed; pointer-events: none; }

  .btn-replace {
    background: #1a1a2e;
    color: #aaa;
    border: 1px solid #444;
    flex: 1;
  }
  .btn-replace:hover { background: #222; border-color: #666; }

  .btn-delete {
    background: transparent;
    color: #666;
    border: 1px solid #333;
    padding: 0.5rem 0.6rem;
  }
  .btn-delete:hover:not(:disabled) {
    background: #3e1a1a;
    border-color: #c62828;
    color: #ef5350;
  }
  .btn-delete:disabled { opacity: 0.4; cursor: not-allowed; }

  .btn-extract {
    width: 100%;
    background: #1a3a26;
    color: #66bb6a;
    border: 1px solid #2e7d32;
    padding: 0.6rem;
    font-size: 0.82rem;
  }
  .btn-extract:hover:not(:disabled) { background: #1e4a2e; }
  .btn-extract:disabled { opacity: 0.45; cursor: not-allowed; }

  /* ── Status / Error bars ── */
  .status-bar {
    background: #1a2e4a;
    border: 1px solid #1976d2;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-top: 1rem;
    color: #4fc3f7;
    font-size: 0.88rem;
    text-align: center;
  }

  .error-bar {
    background: #3e1a1a;
    border: 1px solid #c62828;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-top: 1rem;
    color: #ef9a9a;
    font-size: 0.88rem;
    text-align: center;
  }
</style>
