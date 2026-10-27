<script>
  import TransferModal from './TransferModal.svelte';
  import { sessionId, uploadData, currentStep, isProcessing, processingStatus, errorMessage, lyricsData, generationResult, generationLog, generationShowPreview } from '../stores/appStore.js';
  import SongNameModal from './SongNameModal.svelte';
  import { languageHeader } from '../lib/languages';
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
  let extractEngine = 'demucs';   // 'demucs' | 'roformer'
  let extractPercent = null;      // RoFormer reports progress (download, separation)
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
  let songModalIdentify = true;   // a new song: propose names; "✏️ Change": keep the confirmed ones

  /** After an upload or download: the backend marks every new song (a new full mix, or vocals alone) unconfirmed,
   * so the song window asks for its names and languages. Languages are pre-selected only when the session or
   * YouTube knows them; otherwise the user has to choose. */
  function askForSong(result) {
    lyricsData.update(d => ({ ...d, artist: result.artist || d.artist || '', title: result.title || d.title || '' }));
    if (result.song_confirmed === false) {
      lyricsData.update(d => ({ ...d, language: result.language || '', language2: result.language2 || '' }));
      songModalIdentify = true;
      songModalOpen = true;
    }
  }

  function handleSongConfirmed(event) {
    lyricsData.update(d => ({ ...d, artist: event.detail.artist, title: event.detail.title, language: event.detail.language,
                               language2: event.detail.language2 || '' }));
    // The audio file is now named "Artist - Title" (an uploaded vocals-only file "Artist - Title [Vocals]").
    const name = event.detail.filename;
    if (name && $uploadData.hasOriginal) uploadData.update(d => ({ ...d, filename: name }));
    else if (name && $uploadData.hasVocals) uploadData.update(d => ({ ...d, vocalsFilename: name }));
    songModalOpen = false;
  }

  // ── Getting a song: upload or YouTube download ─────────
  // While a file uploads or YouTube downloads, a window with a spinner blocks the page until it is done or
  // cancelled. Then "Which song is this?" asks for the names and languages and the file is named "Artist - Title".
  let youtubeLink = '';
  let transfer = null;   // { title, status, percent, cancel } while busy

  $: if (typeof document !== 'undefined') document.body.style.overflow = transfer ? 'hidden' : '';

  /** Runs `job(control)` behind the busy window. `control.signal` is aborted on Cancel; `control.onCancel(fn)`
   *  adds more to do then (e.g. closing the YouTube stream). Returns the job's result, or null if cancelled. */
  async function runTransfer(title, status, job) {
    errorMessage.set('');
    isProcessing.set(true);
    const abort = new AbortController();
    const extra = [];
    transfer = { title, status, percent: null, cancel: () => { abort.abort(); extra.forEach(fn => fn()); } };
    const control = {
      signal: abort.signal,
      onCancel: (fn) => extra.push(fn),
      progress: (status, percent = null) => { if (transfer) transfer = { ...transfer, status, percent }; },
    };
    try {
      return await job(control);
    } catch (err) {
      if (!abort.signal.aborted) errorMessage.set(err.message);
      return null;
    } finally {
      if (abort.signal.aborted) processingStatus.set('Cancelled.');
      transfer = null;
      isProcessing.set(false);
    }
  }

  function cancelled(signal) {
    if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
  }

  /** The YouTube download as a promise: resolves with the "done" event, rejects with the error. */
  function downloadFromYouTube(videoId, control) {
    return new Promise((resolve, reject) => {
      const stop = streamYouTubeImport(videoId, $sessionId, (event) => {
        if (event.phase === 'error') reject(new Error(event.message));
        else if (event.phase === 'done') resolve(event);
        else control.progress(event.message, event.percent ?? null);
      });
      control.onCancel(() => { stop(); reject(new DOMException('Cancelled', 'AbortError')); });
    });
  }

  async function handleYouTube() {
    const link = youtubeLink.trim();
    if (!link) return;
    const done = await runTransfer('Downloading from YouTube',
      'Getting the video… (the first time this also downloads the YouTube tools, about a minute)',
      async (control) => {
        const video = await inspectYouTube(link, control.signal);
        cancelled(control.signal);
        control.progress('Downloading the audio…');
        return downloadFromYouTube(video.video_id, control);
      });
    if (!done) return;
    sessionId.set(done.session_id);
    uploadData.update(d => ({ ...d, filename: done.filename, hasOriginal: true }));
    youtubeLink = '';
    processingStatus.set('Audio downloaded from YouTube.');
    askForSong(done);   // done.language: what YouTube knows, if anything
  }

  // ── Mix upload ──────────────────────────────────────────
  async function handleMixFile(file) {
    const result = await runTransfer('Uploading the full mix', file.name, (control) =>
      $sessionId ? uploadMixAudio($sessionId, file, control.signal) : uploadAudio(file, control.signal));
    if (!result) return;
    if (!$sessionId) sessionId.set(result.session_id);
    uploadData.update(d => ({ ...d, filename: result.filename || file.name, hasOriginal: true }));
    processingStatus.set('Full mix uploaded.');
    askForSong(result);
  }

  // ── Vocals upload ────────────────────────────────────────
  async function handleVocalsFile(file) {
    const uploaded = await runTransfer('Uploading the vocals', file.name, async (control) => {
      let id = $sessionId;
      if (!id) {
        // Create a blank session (no original_audio) so vocals-only doesn't
        // falsely appear as having a full-mix track in Step 4.
        id = (await newSession()).session_id;
        cancelled(control.signal);
        sessionId.set(id);
      }
      return uploadCorrectedVocals(id, file, control.signal);
    });
    if (!uploaded) return;
    uploadData.update(d => ({
      ...d,
      hasVocals: true,
      vocalUrl: getAudioUrl($sessionId, 'vocals'),
      vocalsFilename: d.hasOriginal ? '' : file.name,
    }));
    processingStatus.set('Vocals uploaded.');
    askForSong(uploaded);
  }

  // ── Vocal extraction ─────────────────────────────────────
  function handleExtractVocals(engine = 'demucs') {
    errorMessage.set('');
    extractDone = false;
    extractStatus = '';
    extractPhase = 'loading';
    extractElapsed = 0;
    extractEngine = engine;
    extractPercent = null;
    extractModalOpen = true;

    stopExtractStream = streamExtractVocals($sessionId, (event) => {
      extractPhase = event.phase;
      if (event.message) extractStatus = event.message;
      if (event.percent !== undefined) extractPercent = event.percent;

      if (event.phase === 'separating') {
        extractPercent = 0;
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

  {#if transfer}
    <TransferModal title={transfer.title} status={transfer.status} percent={transfer.percent} on:cancel={transfer.cancel} />
  {/if}

  {#if $sessionId && ($uploadData.hasOriginal || $uploadData.hasVocals) && !songModalOpen}
    <p class="song-line">
      🎵 <strong>{$lyricsData.artist || '?'} – {$lyricsData.title || '?'}</strong>
      <span class="song-languages">{$lyricsData.language ? languageHeader($lyricsData.language, $lyricsData.language2) : 'no language selected'}</span>
      <button class="link-btn" on:click={() => { songModalIdentify = false; songModalOpen = true; }}>✏️ Change</button>
    </p>
  {/if}

  {#if songModalOpen && $sessionId}
    <SongNameModal sessionId={$sessionId} artist={$lyricsData.artist} title={$lyricsData.title} identify={songModalIdentify} on:cancel={() => songModalOpen = false}
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
                   aria-label="YouTube link" disabled={$isProcessing}
                   on:keydown={(e) => { if (e.key === 'Enter') handleYouTube(); }} />
            <button class="btn btn-browse" on:click={handleYouTube}
                    disabled={$isProcessing || !youtubeLink.trim()}>⬇ Download</button>
          </div>
          <p class="youtube-note">Audio only. Only download songs you have the right to use.</p>
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
          <span class="file-name">✅ {$uploadData.vocalsFilename || 'Vocals ready'}</span>
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
          <button class="btn btn-extract" on:click={() => handleExtractVocals('demucs')} disabled={$isProcessing}>
            {$isProcessing ? '⏳ Extracting…' : '⚡ Extract from Mix (Demucs)'}
          </button>
          <button class="btn btn-extract btn-extract-slow" on:click={() => handleExtractVocals('roformer')} disabled={$isProcessing}
                  title="Mel-Band RoFormer: cleaner where voices overlap (duets, backing vocals). About 10 minutes per song; downloads its model (464 MB) the first time.">
            ✨ Better separation (slow, ~10 min)
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

      {#if extractPhase === 'downloading' && extractPercent !== null}
        <progress max="100" value={extractPercent}></progress>
        <div class="extract-elapsed">{extractPercent}%</div>
      {/if}
      {#if extractPhase === 'separating' || extractPhase === 'heartbeat'}
        {#if extractEngine === 'roformer' && extractPercent !== null}
          <progress max="100" value={extractPercent}></progress>
        {/if}
        <div class="extract-elapsed">⏱ {extractElapsed}s elapsed{extractEngine === 'roformer' && extractPercent !== null ? ` · ${extractPercent}%` : ''}</div>
        <div class="extract-hint">
          {#if extractEngine === 'roformer'}
            Mel-Band RoFormer separates vocals from the full mix, cleaner where voices overlap.<br>
            It takes about <strong>2–3× the song's length</strong> (≈ 10 minutes).
          {:else}
            Demucs AI separates vocals from the full mix.<br>
            Typical songs take <strong>1–5 minutes</strong>.
          {/if}
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


  /* ── YouTube link ── */
  .song-line { color: #bbb; font-size: 0.9rem; margin: 0 0 1rem; display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .song-languages { color: #888; font-size: 0.85rem; }
  .song-languages::before { content: '· '; }
  .link-btn { background: none; border: none; color: #4fc3f7; cursor: pointer; text-decoration: underline; font-size: 0.85rem; padding: 0; }
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
  .youtube-note { color: #555; font-size: 0.72rem; margin: 0; }

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

  .btn-extract.btn-extract-slow { background: #2a2440; color: #b39ddb; border-color: #5e4b8b; margin-top: 0.4rem; }
  .btn-extract.btn-extract-slow:hover:not(:disabled) { background: #362d55; }
  .extract-modal-box progress { width: 100%; height: 6px; }

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
