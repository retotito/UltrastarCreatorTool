<script>
  import { sessionId, uploadData, currentStep, isProcessing, processingStatus, errorMessage, lyricsData, generationResult, generationLog, generationShowPreview } from '../stores/appStore.js';
  import { uploadAudio, extractVocals, uploadCorrectedVocals, deleteAudio, getAudioUrl, resumeLastSession, getGenerationResult } from '../services/api.js';

  let dragOver = false;
  let audioPlayer;
  let originalPlayer;

  $: originalUrl = $sessionId && $uploadData.hasOriginal ? getAudioUrl($sessionId, 'original') : null;

  async function handleDeleteAudio(type) {
    errorMessage.set('');
    try {
      const result = await deleteAudio($sessionId, type);
      if (type === 'original') {
        uploadData.update(d => ({ ...d, hasOriginal: false }));
      } else if (type === 'vocals') {
        uploadData.update(d => ({ ...d, hasVocals: false, vocalUrl: null }));
      }
    } catch (err) {
      errorMessage.set(err.message);
    }
  }

  async function handleFileSelect(event) {
    const file = event.target.files?.[0];
    if (file) await processUpload(file);
  }

  function handleDrop(event) {
    event.preventDefault();
    dragOver = false;
    const file = event.dataTransfer.files?.[0];
    if (file) processUpload(file);
  }

  async function processUpload(file) {
    console.log('[Step1] processUpload:', file.name, file.type, file.size, 'bytes');
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Uploading audio...');

    try {
      const result = await uploadAudio(file);
      console.log('[Step1] Upload result:', result);
      sessionId.set(result.session_id);
      uploadData.update(d => ({ ...d, filename: result.filename, hasOriginal: true }));
      processingStatus.set('Upload complete! Choose an option below.');
    } catch (err) {
      console.error('[Step1] Upload error:', err);
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }

  async function handleExtractVocals() {
    console.log('[Step1] handleExtractVocals, session:', $sessionId);
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Extracting vocals with Demucs (this may take a few minutes)...');

    try {
      const result = await extractVocals($sessionId);
      console.log('[Step1] Extract vocals result:', result);
      const vocalUrl = getAudioUrl($sessionId, 'vocals');
      console.log('[Step1] Vocal preview URL:', vocalUrl);
      uploadData.update(d => ({
        ...d,
        hasVocals: true,
        vocalUrl,
      }));
      processingStatus.set('Vocals extracted! Preview below or continue.');
    } catch (err) {
      console.error('[Step1] Extract vocals error:', err);
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }

  async function handleUploadVocals(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    console.log('[Step1] handleUploadVocals:', file.name);

    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Uploading corrected vocals...');

    try {
      await uploadCorrectedVocals($sessionId, file);
      const vocalUrl = getAudioUrl($sessionId, 'vocals');
      console.log('[Step1] Uploaded vocals, preview URL:', vocalUrl);
      uploadData.update(d => ({
        ...d,
        hasVocals: true,
        vocalUrl,
      }));
      processingStatus.set('Vocals uploaded! Preview below or continue.');
    } catch (err) {
      console.error('[Step1] Upload vocals error:', err);
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }

  async function handleSkipToVocals(event) {
    // Upload audio directly as vocals (already isolated)
    const file = event.target.files?.[0];
    if (!file) return;

    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Uploading vocal audio...');

    try {
      const uploadResult = await uploadAudio(file);
      sessionId.set(uploadResult.session_id);
      await uploadCorrectedVocals(uploadResult.session_id, file);
      uploadData.update(d => ({
        ...d,
        filename: file.name,
        hasVocals: true,
        vocalUrl: getAudioUrl(uploadResult.session_id, 'vocals'),
      }));
      processingStatus.set('Vocal audio ready! Preview below or continue.');
    } catch (err) {
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }

  async function handleResumeLast() {
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Resuming last session...');

    try {
      const result = await resumeLastSession();
      console.log('[Resume] API response:', JSON.stringify(result, null, 2));
      console.log('[Resume] session_id:', result.session_id, 'has_lyrics:', result.has_lyrics, 'has_result:', result.has_result);
      sessionId.set(result.session_id);
      uploadData.set({
        filename: result.filename,
        hasVocals: true,
        hasOriginal: true,
        vocalUrl: getAudioUrl(result.session_id, 'vocals'),
      });
      if (result.has_lyrics) {
        console.log('[Resume] Has lyrics, syllables:', result.syllable_count, 'lines:', result.line_count);
        lyricsData.set({
          text: result.lyrics,
          artist: result.artist,
          title: result.title,
          language: result.language,
          syllableCount: result.syllable_count,
          lineCount: result.line_count,
          preview: [],
        });
        // If previous session had a generation result, load it and jump to step 3
        if (result.has_result) {
          console.log('[Resume] has_result=true, fetching generation result for session:', result.session_id);
          try {
            const genResult = await getGenerationResult(result.session_id);
            console.log('[Resume] getGenerationResult response:', genResult);
            console.log('[Resume] genResult.status:', genResult?.status, 'bpm:', genResult?.bpm, 'gap_ms:', genResult?.gap_ms);
            if (genResult && genResult.status === 'ok') {
              generationResult.set(genResult);
              generationShowPreview.set(true);
              generationLog.set([{
                time: new Date().toLocaleTimeString(),
                text: `📂 Restored previous generation (BPM: ${genResult.bpm}, GAP: ${genResult.gap_ms}ms, ${genResult.syllable_count} syllables)`
              }]);
              console.log('[Resume] ✅ generationResult SET, generationShowPreview SET to true');
            } else {
              console.warn('[Resume] ❌ Generation result not ready, status:', genResult?.status);
            }
          } catch (e) {
            console.warn('[Resume] ❌ Could not restore generation result:', e.message, e);
          }
        } else {
          console.log('[Resume] has_result=false — no previous generation');
        }
        // Jump to step 4 (editor) if result was restored, otherwise step 3
        if (result.has_result && $generationResult) {
          console.log('[Resume] Jumping to step 4 (piano roll)');
          currentStep.set(4);
        } else {
          console.log('[Resume] Jumping to step 3');
          currentStep.set(3);
        }
      } else {
        console.log('[Resume] No lyrics, jumping to step 2');
        currentStep.set(2);
      }
      processingStatus.set('');
    } catch (err) {
      console.error('[Resume] ❌ Error:', err.message, err);
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
      console.log('[Resume] Done, isProcessing=false');
    }
  }

</script>

<div class="step-content">
  <h2>Step 1: Upload Audio</h2>

  {#if !$sessionId}
    <!-- Upload area -->
    <div
      class="drop-zone"
      class:drag-over={dragOver}
      role="button"
      tabindex="0"
      on:dragover|preventDefault={() => (dragOver = true)}
      on:dragleave={() => (dragOver = false)}
      on:drop={handleDrop}
    >
      <div class="drop-icon">🎵</div>
      <p>Drag & drop your audio file here</p>
      <p class="hint">MP3, WAV, or other audio format</p>
      
      <div class="upload-options">
        <label class="btn btn-primary">
          Upload Full Song (needs separation)
          <input type="file" accept="audio/*" on:change={handleFileSelect} hidden />
        </label>
        
        <label class="btn btn-secondary">
          Upload Isolated Vocals (skip separation)
          <input type="file" accept="audio/*" on:change={handleSkipToVocals} hidden />
        </label>
      </div>
    </div>

    <div class="divider">or</div>

    <button class="btn btn-test" on:click={handleResumeLast} disabled={$isProcessing}>
      ⏩ Resume Last Session (skip transcription)
    </button>

  {:else if !$uploadData.hasVocals}
    <!-- File uploaded, but no vocals yet — offer extraction or upload -->
    <div class="uploaded-info">
      <p>✅ Uploaded: <strong>{$uploadData.filename}</strong></p>

      {#if $uploadData.hasOriginal}
        <div class="audio-row">
          <span class="audio-label">🎵 Full Mix</span>
          <button class="btn-icon delete" on:click={() => handleDeleteAudio('original')} title="Delete full mix">🗑</button>
        </div>
        <div class="audio-preview">
          <audio bind:this={originalPlayer} controls src={originalUrl}>
            Your browser does not support the audio element.
          </audio>
        </div>
      {/if}

      <p class="hint" style="color: #ffa726">🎤 No vocals track yet</p>
    </div>

    <div class="action-buttons">
      {#if $uploadData.hasOriginal}
        <button class="btn btn-primary" on:click={handleExtractVocals} disabled={$isProcessing}>
          🎤 Extract Vocals from Mix (Demucs)
        </button>
      {/if}
      
      <label class="btn btn-secondary">
        📂 Upload Vocals Audio
        <input type="file" accept="audio/*" on:change={handleUploadVocals} hidden />
      </label>
    </div>

  {:else}
    <!-- Vocals ready -->
    <div class="vocals-ready">
      {#if $uploadData.hasOriginal}
        <div class="audio-row">
          <span class="audio-label">🎵 Full Mix</span>
          <button class="btn-icon delete" on:click={() => handleDeleteAudio('original')} title="Delete full mix">🗑</button>
        </div>
        <div class="audio-preview">
          <audio bind:this={originalPlayer} controls src={originalUrl}>
            Your browser does not support the audio element.
          </audio>
        </div>
      {:else}
        <p>🎵 Full mix: <span style="color: #888">not uploaded</span></p>
      {/if}

      <div class="audio-row">
        <span class="audio-label">🎤 Vocals</span>
        <button class="btn-icon delete" on:click={() => handleDeleteAudio('vocals')} title="Delete vocals">🗑</button>
      </div>
      {#if $uploadData.vocalUrl}
        <div class="audio-preview">
          <audio bind:this={audioPlayer} controls src={$uploadData.vocalUrl}>
            Your browser does not support the audio element.
          </audio>
        </div>
      {/if}

      <div class="action-buttons">
        <label class="btn btn-secondary small">
          ↻ Replace with different vocals
          <input type="file" accept="audio/*" on:change={handleUploadVocals} hidden />
        </label>
      </div>
    </div>
  {/if}

  {#if $processingStatus}
    <div class="status-bar">{$processingStatus}</div>
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

  h2 {
    color: #4fc3f7;
    margin-bottom: 1rem;
  }

  .drop-zone {
    border: 2px dashed #444;
    border-radius: 12px;
    padding: 2rem;
    text-align: center;
    transition: all 0.2s;
  }

  .drop-zone.drag-over {
    border-color: #4fc3f7;
    background: #1a2e4a22;
  }

  .drop-icon {
    font-size: 3rem;
    margin-bottom: 0.5rem;
  }

  .hint {
    color: #666;
    font-size: 0.85rem;
  }

  .upload-options {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 1rem;
  }

  .btn {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 8px;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.2s;
    text-align: center;
  }

  .btn-primary {
    background: #1976d2;
    color: white;
  }
  .btn-primary:hover:not(:disabled) { background: #1565c0; }

  .btn-secondary {
    background: #333;
    color: #ccc;
    border: 1px solid #555;
  }
  .btn-secondary:hover:not(:disabled) { background: #444; }

  .btn-test {
    background: #2e7d32;
    color: white;
    width: 100%;
  }
  .btn-test:hover:not(:disabled) { background: #388e3c; }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn.small { font-size: 0.8rem; padding: 0.5rem 1rem; }

  .divider {
    text-align: center;
    color: #666;
    margin: 1rem 0;
    position: relative;
  }
  .divider::before, .divider::after {
    content: '';
    position: absolute;
    top: 50%;
    width: 40%;
    height: 1px;
    background: #333;
  }
  .divider::before { left: 0; }
  .divider::after { right: 0; }

  .uploaded-info, .vocals-ready {
    background: #1a2e1a;
    border: 1px solid #2e7d32;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .action-buttons {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-top: 1rem;
  }

  .audio-preview {
    margin: 1rem 0;
  }

  .audio-preview audio {
    width: 100%;
    margin-top: 0.5rem;
  }

  .audio-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 0.75rem;
  }

  .audio-label {
    font-weight: 600;
    color: #66bb6a;
    font-size: 0.9rem;
  }

  .btn-icon {
    background: none;
    border: 1px solid #555;
    border-radius: 6px;
    color: #aaa;
    cursor: pointer;
    padding: 0.2rem 0.5rem;
    font-size: 0.85rem;
    transition: all 0.15s;
  }
  .btn-icon.delete:hover {
    border-color: #c62828;
    color: #ef5350;
    background: #3e1a1a;
  }

  .status-bar {
    background: #1a2e4a;
    border: 1px solid #1976d2;
    border-radius: 8px;
    padding: 0.75rem;
    margin-top: 1rem;
    color: #4fc3f7;
    text-align: center;
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
