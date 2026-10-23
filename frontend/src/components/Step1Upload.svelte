<script>
  import { sessionId, uploadData, currentStep, isProcessing, processingStatus, errorMessage, lyricsData, generationResult, generationLog, generationShowPreview } from '../stores/appStore.js';
  import SongNameModal from './SongNameModal.svelte';
  import { inspectYouTube, streamYouTubeImport, newSession, uploadAudio, extractVocals, cancelExtractVocals, streamExtractVocals, uploadCorrectedVocals, uploadMixAudio, deleteAudio, getAudioUrl, resumeLastSession, getGenerationResult } from '../services/api.js';

  let audioPlayerMix;
  let audioPlayerVocals;
  let audioPlayerInstrumental;
  let hasInstrumental = false;
  let instrumentalProbeKey = '';
  let instrumentalProbeSeq = 0;



  // ── Extract vocals modal ─────────────────────────────────
  let extractModalOpen = false;
  let extractDone = false;
  let extractStatus = '';
  let extractPhase = '';   // 'loading'|'separating'|'heartbeat'|'done'|'error'|'cancelled'
  let extractElapsed = 0;
  let stopExtractStream = null;
  let elapsedTicker = null;

  function startElapsedTicker() {
    extractElapsed = 0;
    elapsedTicker = setInterval(() => { extractElapsed += 1; }, 1000);
  }
  function stopElapsedTicker() {
    if (elapsedTicker) { clearInterval(elapsedTicker); elapsedTicker = null; }
  }

  $: mixUrl    = $sessionId && $uploadData.hasOriginal ? getAudioUrl($sessionId, 'original') + '?t=' + Date.now() : null;
  $: vocalsUrl = $sessionId && $uploadData.hasVocals   ? getAudioUrl($sessionId, 'vocals')   + '?t=' + Date.now() : null;
  $: instrumentalUrl = $sessionId && hasInstrumental ? getAudioUrl($sessionId, 'instrumental') + '?t=' + Date.now() : null;

  $: {
    const probeKey = `${$sessionId || ''}|${$uploadData.hasOriginal}|${$uploadData.hasVocals}`;
    if (!$sessionId || (!$uploadData.hasOriginal && !$uploadData.hasVocals)) {
      hasInstrumental = false;
      instrumentalProbeKey = '';
    } else if (probeKey !== instrumentalProbeKey) {
      instrumentalProbeKey = probeKey;
      void probeInstrumentalExists($sessionId);
    }
  }

  async function probeInstrumentalExists(id) {
    const seq = ++instrumentalProbeSeq;
    try {
      // The preview endpoint is GET-only; use a tiny range request for existence check.
      const res = await fetch(getAudioUrl(id, 'instrumental'), {
        method: 'GET',
        headers: { Range: 'bytes=0-1' },
      });
      if (seq !== instrumentalProbeSeq) return;
      hasInstrumental = res.ok;
    } catch {
      if (seq !== instrumentalProbeSeq) return;
      hasInstrumental = false;
    }
  }

  // ── Song name ("Which song is this?") ───────────────────
  let songModalOpen = false;

  /** After a new song arrives: ask for artist, title and language unless they were confirmed before. A new song's
   * language is only pre-selected when its source knows it (YouTube); otherwise the user has to choose it. */
  function askForSong(result) {
    lyricsData.update(d => ({ ...d, artist: result.artist || d.artist || '', title: result.title || d.title || '' }));
    if (result.song_confirmed === false) {
      lyricsData.update(d => ({ ...d, language: result.language || '', language2: '' }));
      songModalOpen = true;
    }
  }

  function handleSongConfirmed(event) {
    lyricsData.update(d => ({ ...d, artist: event.detail.artist, title: event.detail.title, language: event.detail.language,
                               language2: event.detail.language2 || '' }));
    // The audio file is now named "Artist - Title".
    if (event.detail.filename && $uploadData.hasOriginal) uploadData.update(d => ({ ...d, filename: event.detail.filename }));
    songModalOpen = false;
  }

  // ── YouTube link ────────────────────────────────────────
  let youtubeLink = '';
  let youtubePreview = null;   // details of the pasted video
  let youtubeBusy = false;
  let youtubeStatus = '';
  let youtubePercent = null;

  function formatDuration(seconds) {
    if (!seconds) return '';
    const s = Math.round(seconds);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  async function handleYouTubeInspect() {
    if (!youtubeLink.trim()) return;
    errorMessage.set('');
    youtubePreview = null;
    youtubeBusy = true;
    youtubeStatus = 'Getting the video details… (the first time this also downloads the YouTube tools, about a minute)';
    try {
      youtubePreview = await inspectYouTube(youtubeLink.trim());
      youtubeStatus = '';
    } catch (err) {
      youtubeStatus = '';
      errorMessage.set(err.message);
    } finally {
      youtubeBusy = false;
    }
  }

  function handleYouTubeImport() {
    if (!youtubePreview) return;
    errorMessage.set('');
    youtubeBusy = true;
    isProcessing.set(true);
    youtubePercent = null;
    youtubeStatus = 'Starting…';
    streamYouTubeImport(youtubePreview.video_id, $sessionId, (event) => {
      if (event.phase === 'error') {
        errorMessage.set(event.message);
        youtubeStatus = '';
        youtubeBusy = false;
        isProcessing.set(false);
        return;
      }
      youtubeStatus = event.message;
      youtubePercent = event.percent ?? null;
      if (event.phase === 'done') {
        sessionId.set(event.session_id);
        uploadData.update(d => ({ ...d, filename: event.filename, hasOriginal: true }));
        askForSong(event);   // event.language: what YouTube knows, if anything
        processingStatus.set(`Audio from YouTube: ${event.artist ? event.artist + ' – ' : ''}${event.title}`);
        youtubePreview = null;
        youtubeLink = '';
        youtubeStatus = '';
        youtubePercent = null;
        youtubeBusy = false;
        isProcessing.set(false);
      }
    });
  }

  // ── Mix upload ──────────────────────────────────────────
  async function handleMixFile(file) {
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Uploading full mix…');
    try {
      const result = $sessionId ? await uploadMixAudio($sessionId, file) : await uploadAudio(file);
      if (!$sessionId) sessionId.set(result.session_id);
      uploadData.update(d => ({ ...d, filename: result.filename || file.name, hasOriginal: true }));
      askForSong(result);
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
      let uploaded;
      if ($sessionId) {
        uploaded = await uploadCorrectedVocals($sessionId, file);
      } else {
        // Create a blank session (no original_audio) so vocals-only doesn't
        // falsely appear as having a full-mix track in Step 4.
        const result = await newSession();
        sessionId.set(result.session_id);
        uploaded = await uploadCorrectedVocals(result.session_id, file);
      }
      askForSong(uploaded);
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
  function handleExtractVocals() {
    errorMessage.set('');
    extractDone = false;
    extractStatus = '';
    extractPhase = 'loading';
    extractElapsed = 0;
    extractModalOpen = true;

    stopExtractStream = streamExtractVocals($sessionId, (event) => {
      extractPhase = event.phase;
      if (event.message) extractStatus = event.message;

      if (event.phase === 'separating') {
        startElapsedTicker();
      } else if (event.phase === 'done') {
        stopElapsedTicker();
        uploadData.update(d => ({
          ...d,
          hasVocals: true,
          vocalUrl: getAudioUrl($sessionId, 'vocals'),
        }));
        void probeInstrumentalExists($sessionId);
        extractDone = true;
        if (stopExtractStream) { stopExtractStream(); stopExtractStream = null; }
        setTimeout(() => { extractModalOpen = false; }, 1800);
      } else if (event.phase === 'error') {
        stopElapsedTicker();
        extractDone = true;
        if (stopExtractStream) { stopExtractStream(); stopExtractStream = null; }
      } else if (event.phase === 'cancelled') {
        stopElapsedTicker();
        extractModalOpen = false;
        if (stopExtractStream) { stopExtractStream(); stopExtractStream = null; }
      }
    });
  }

  function cancelExtraction() {
    stopElapsedTicker();
    if (stopExtractStream) { stopExtractStream(); stopExtractStream = null; }
    cancelExtractVocals($sessionId);
    extractModalOpen = false;
    extractDone = false;
    extractPhase = '';
  }

  // ── Delete ───────────────────────────────────────────────
  async function handleDeleteAudio(type) {
    errorMessage.set('');
    try {
      await deleteAudio($sessionId, type);
      if (type === 'original') {
        uploadData.update(d => ({ ...d, hasOriginal: false, filename: null }));
      } else if (type === 'instrumental') {
        hasInstrumental = false;
      } else {
        uploadData.update(d => ({ ...d, hasVocals: false, vocalUrl: null }));
      }
    } catch (err) {
      errorMessage.set(err.message);
    }
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
        hasVocals: result.has_vocals !== false,
        vocalsFilename: result.vocals_filename || null,
        hasOriginal: result.has_original === true,
        vocalUrl: getAudioUrl(result.session_id, 'vocals'),
      });
      void probeInstrumentalExists(result.session_id);
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
        currentStep.set(result.has_result && $generationResult ? 4 : 2);
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

  {#if $sessionId && ($uploadData.hasOriginal || $uploadData.hasVocals)}
    <p class="song-line">
      🎵 Song: <strong>{$lyricsData.artist || '?'} – {$lyricsData.title || '?'}</strong>
      <button class="link-btn" on:click={() => songModalOpen = true}>✏️ Change</button>
    </p>
  {/if}

  {#if songModalOpen && $sessionId}
    <SongNameModal sessionId={$sessionId} artist={$lyricsData.artist} title={$lyricsData.title}
                   language={$lyricsData.language} language2={$lyricsData.language2 || ''} on:confirm={handleSongConfirmed} />
  {/if}

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
          <button class="btn btn-delete" on:click={() => handleDeleteAudio('original')} disabled={$isProcessing}>
            🗑 Delete
          </button>
        </div>
      {:else}
        <div class="upload-zone">
          <div class="upload-icon">🎵</div>
          <p class="upload-text">Full mix audio</p>
          <p class="upload-hint">MP3, WAV, FLAC, M4A, …</p>
          <label class="btn btn-browse" class:disabled={$isProcessing}>
            📁 Browse
            <input type="file" accept="audio/*" on:change={(e) => { const f = e.target.files?.[0]; if (f) handleMixFile(f); e.target.value=''; }} hidden />
          </label>
        </div>

        <div class="youtube-import">
          <p class="upload-hint">or from a YouTube link</p>
          <div class="youtube-row">
            <input type="url" bind:value={youtubeLink} placeholder="https://www.youtube.com/watch?v=…"
                   aria-label="YouTube link" disabled={$isProcessing || youtubeBusy}
                   on:keydown={(e) => { if (e.key === 'Enter') handleYouTubeInspect(); }} />
            <button class="btn btn-browse" on:click={handleYouTubeInspect}
                    disabled={$isProcessing || youtubeBusy || !youtubeLink.trim()}>▶ Get</button>
          </div>
          {#if youtubePreview}
            <div class="youtube-preview">
              {#if youtubePreview.thumbnail}<img src={youtubePreview.thumbnail} alt="" />{/if}
              <div class="youtube-meta">
                <strong>{youtubePreview.video_title}</strong>
                <span>{youtubePreview.channel}{youtubePreview.duration ? ' · ' + formatDuration(youtubePreview.duration) : ''}</span>
                <span>Song: {youtubePreview.artist ? youtubePreview.artist + ' – ' : ''}{youtubePreview.title}</span>
              </div>
            </div>
            <button class="btn btn-extract" on:click={handleYouTubeImport} disabled={$isProcessing || youtubeBusy}>
              ⬇ Download audio
            </button>
            <p class="youtube-note">Only download songs you have the right to use.</p>
          {/if}
          {#if youtubeStatus}
            <p class="youtube-status">{youtubeStatus}{youtubePercent !== null ? ` ${youtubePercent}%` : ''}</p>
            {#if youtubePercent !== null}<progress max="100" value={youtubePercent}></progress>{/if}
          {/if}
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
          <button class="btn btn-delete" on:click={() => handleDeleteAudio('vocals')} disabled={$isProcessing}>
            🗑 Delete
          </button>
        </div>
      {:else}
        <div class="upload-zone">
          <div class="upload-icon">🎤</div>
          <p class="upload-text">Vocals audio</p>
          <p class="upload-hint">Already isolated? Upload directly</p>
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

    <!-- ── Instrumental Card (auto-created if available) ── -->
    {#if hasInstrumental}
    <div class="audio-card has-file">
      <div class="card-header">
        <span class="card-title">🥁 Instrumental</span>
        <span class="card-badge optional">auto</span>
      </div>

        <div class="file-info">
          <span class="file-name">✅ Instrumental ready</span>
        </div>
        {#if instrumentalUrl}
          <div class="audio-preview">
            <audio bind:this={audioPlayerInstrumental} controls src={instrumentalUrl}></audio>
          </div>
        {/if}
        <div class="card-actions">
          <button class="btn btn-delete" on:click={() => handleDeleteAudio('instrumental')} disabled={$isProcessing}>
            🗑 Delete
          </button>
        </div>
    </div>
    {/if}

  </div>

  {#if $processingStatus}
    <div class="status-bar">{$processingStatus}</div>
  {/if}

  {#if $errorMessage}
    <div class="error-bar">❌ {$errorMessage}</div>
  {/if}
</div>

{#if extractModalOpen}
  <div class="extract-modal-backdrop">
    <div class="extract-modal-box">
      <div class="extract-modal-header">
        {#if extractPhase === 'done'}
          <span class="phase-icon">✅</span>
          <h2>Vocals Extracted!</h2>
        {:else if extractPhase === 'error'}
          <span class="phase-icon">❌</span>
          <h2>Extraction Failed</h2>
        {:else}
          <span class="e-spinner"></span>
          <h2>Extracting Vocals…</h2>
        {/if}
      </div>

      <p class="extract-modal-status">{extractStatus}</p>

      {#if extractPhase === 'separating' || extractPhase === 'heartbeat'}
        <div class="extract-elapsed">⏱ {extractElapsed}s elapsed</div>
        <div class="extract-hint">
          Demucs AI separates vocals from the full mix.<br>
          Typical songs take <strong>1–5 minutes</strong>.
        </div>
      {/if}

      <div class="extract-modal-footer">
        <button class="btn btn-cancel" on:click={cancelExtraction}>
          {extractDone ? '← Close' : '✕ Cancel'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .step-content {
    
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

  /* ── Upload zone ── */
  .upload-zone {
    border: 2px solid #2a2a3e;
    border-radius: 10px;
    padding: 1.5rem 1rem;
    text-align: center;
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.4rem;
  }

  .upload-icon { font-size: 2rem; }

  .upload-text { color: #aaa; font-size: 0.88rem; margin: 0; }
  .upload-hint { color: #555; font-size: 0.78rem; margin: 0; }

  .song-line { color: #bbb; font-size: 0.9rem; margin: 0 0 1rem; display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
  .song-line .link-btn { background: none; border: none; color: #4fc3f7; cursor: pointer; text-decoration: underline; font-size: 0.85rem; padding: 0; }

  /* ── YouTube link ── */
  .youtube-import { display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.75rem; }
  .youtube-row { display: flex; gap: 0.4rem; }
  .youtube-row input {
    flex: 1; min-width: 0;
    background: #11111d; color: #e0e0e0;
    border: 1px solid #2a2a3e; border-radius: 6px;
    padding: 0.4rem 0.6rem; font-size: 0.85rem;
  }
  .youtube-row input:focus { outline: none; border-color: #1976d2; }
  .youtube-row .btn-browse { margin-top: 0; }
  .youtube-preview { display: flex; gap: 0.6rem; align-items: center; text-align: left; }
  .youtube-preview img { width: 120px; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 6px; flex-shrink: 0; }
  .youtube-meta { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; font-size: 0.82rem; }
  .youtube-meta strong { color: #e0e0e0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .youtube-meta span { color: #888; }
  .youtube-note { color: #555; font-size: 0.72rem; margin: 0; }
  .youtube-status { color: #4fc3f7; font-size: 0.8rem; margin: 0; }
  .youtube-import progress { width: 100%; height: 6px; }

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

  /* Extract Vocals modal */
  .extract-modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.75);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .extract-modal-box {
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 12px;
    padding: 2rem;
    width: 90%;
    max-width: 440px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .extract-modal-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .extract-modal-header h2 {
    margin: 0;
    color: #4fc3f7;
  }

  .phase-icon {
    font-size: 1.4rem;
    line-height: 1;
  }

  .e-spinner {
    width: 20px;
    height: 20px;
    border: 3px solid #333;
    border-top-color: #66bb6a;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .extract-modal-status {
    color: #aaa;
    font-size: 0.9rem;
    margin: 0;
  }

  .extract-elapsed {
    font-size: 0.85rem;
    color: #4fc3f7;
    font-variant-numeric: tabular-nums;
  }

  .extract-hint {
    font-size: 0.82rem;
    color: #666e7a;
    line-height: 1.5;
  }

  .extract-hint strong {
    color: #aaa;
  }

  .extract-modal-footer {
    display: flex;
    justify-content: flex-start;
    margin-top: 0.5rem;
  }

  .btn-cancel {
    background: #2a1a1a;
    color: #ef9a9a;
    border: 1px solid #c62828;
    border-radius: 8px;
    padding: 0.5rem 1.2rem;
    font-size: 0.88rem;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-cancel:hover { background: #3e1a1a; }
</style>
