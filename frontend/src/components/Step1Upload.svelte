<script>
  import { sessionId, uploadData, referenceData, currentStep, isProcessing, processingStatus, errorMessage, lyricsData, generationResult, generationLog, generationShowPreview } from '../stores/appStore.js';
  import { uploadAudio, extractVocals, uploadCorrectedVocals, getAudioUrl, uploadReference, resumeLastSession, getGenerationResult } from '../services/api.js';

  let dragOver = false;
  let audioPlayer;

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
      // Restore reference data if carried over
      if (result.reference) {
        console.log('[Resume] Restoring reference:', result.reference);
        referenceData.set({
          uploaded: true,
          filename: result.reference.filename,
          notesCount: result.reference.notes_count,
          bpm: result.reference.bpm,
          gap: result.reference.gap,
          comparison: null,
          lyricsComparison: null,
        });
      } else {
        console.log('[Resume] No reference data');
      }
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

  async function handleReferenceUpload(event) {
    const file = event.target.files?.[0];
    if (!file || !$sessionId) return;
    console.log('[Step1] handleReferenceUpload:', file.name);

    errorMessage.set('');
    try {
      const result = await uploadReference($sessionId, file);
      console.log('[Step1] Reference upload result:', result);
      referenceData.set({
        uploaded: true,
        filename: result.filename,
        notesCount: result.notes_count,
        bpm: result.bpm,
        gap: result.gap,
        comparison: null,
        lyricsComparison: result.lyrics_comparison || null,
      });
      if (result.lyrics_comparison) {
        const lc = result.lyrics_comparison;
        if (lc.exact_match) {
          processingStatus.set(`Reference uploaded: ${result.filename} (${result.notes_count} notes) — ✅ Lyrics match!`);
        } else {
          processingStatus.set(`Reference uploaded: ${result.filename} (${result.notes_count} notes) — ⚠️ Lyrics ${Math.round(lc.similarity * 100)}% similar`);
        }
      } else {
        processingStatus.set(`Reference uploaded: ${result.filename} (${result.notes_count} notes) — Enter lyrics first to compare`);
      }
    } catch (err) {
      console.error('[Step1] Reference upload error:', err);
      errorMessage.set(err.message);
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
        <p class="hint">🎵 Full mix available</p>
      {/if}
      {#if !$uploadData.hasVocals}
        <p class="hint" style="color: #ffa726">🎤 No vocals track yet</p>
      {/if}
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
      <div class="audio-status">
        <p>🎤 Vocals: <strong style="color: #66bb6a">{$uploadData.filename}</strong></p>
        {#if $uploadData.hasOriginal}
          <p>🎵 Full mix: <strong style="color: #66bb6a">available</strong></p>
        {:else}
          <p>🎵 Full mix: <span style="color: #888">not uploaded</span></p>
        {/if}
      </div>
      
      {#if $uploadData.vocalUrl}
        <div class="audio-preview">
          <p>Preview vocals:</p>
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

      <!-- Reference file upload (optional, for learning) -->
      <div class="reference-section">
        <h3>📚 Reference File (Optional)</h3>
        <p class="hint">Upload a verified Ultrastar .txt file for this song to help the AI learn.</p>
        {#if $referenceData.uploaded}
          <div class="reference-info">
            ✅ {$referenceData.filename} ({$referenceData.notesCount} notes, BPM: {$referenceData.bpm})
          </div>
          {#if $referenceData.lyricsComparison}
            <div class="lyrics-comparison" class:match={$referenceData.lyricsComparison.exact_match} class:mismatch={!$referenceData.lyricsComparison.exact_match}>
              {#if $referenceData.lyricsComparison.exact_match}
                <span>✅ Lyrics match reference ({$referenceData.lyricsComparison.total_lines_ref} lines)</span>
              {:else}
                <span>⚠️ Lyrics differ from reference — {Math.round($referenceData.lyricsComparison.similarity * 100)}% similar ({$referenceData.lyricsComparison.matching_lines}/{$referenceData.lyricsComparison.total_lines_ref} lines match)</span>
                {#if $referenceData.lyricsComparison.differences.length > 0}
                  <details>
                    <summary>Show differences ({$referenceData.lyricsComparison.differences.length})</summary>
                    <div class="diff-list">
                      {#each $referenceData.lyricsComparison.differences.slice(0, 10) as diff}
                        <div class="diff-item">
                          <span class="diff-line">Line {diff.line}:</span>
                          {#if diff.user}
                            <span class="diff-yours">Yours: "{diff.user}"</span>
                          {:else}
                            <span class="diff-yours">(missing in your lyrics)</span>
                          {/if}
                          {#if diff.reference}
                            <span class="diff-ref">Ref: "{diff.reference}"</span>
                          {:else}
                            <span class="diff-ref">(extra line in your lyrics)</span>
                          {/if}
                        </div>
                      {/each}
                    </div>
                  </details>
                {/if}
              {/if}
            </div>
          {:else}
            <div class="lyrics-comparison hint">Enter lyrics in Step 2, then re-upload reference to compare</div>
          {/if}
        {:else}
          <label class="btn btn-reference small">
            📄 Upload Reference .txt
            <input type="file" accept=".txt" on:change={handleReferenceUpload} hidden />
          </label>
        {/if}
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

  .reference-section {
    margin-top: 1.5rem;
    padding: 1rem;
    border: 1px dashed #555;
    border-radius: 8px;
    background: #1a1a2e;
  }

  .reference-section h3 {
    color: #aaa;
    font-size: 0.9rem;
    margin: 0 0 0.5rem 0;
  }

  .reference-info {
    color: #66bb6a;
    font-size: 0.85rem;
    padding: 0.5rem;
    background: #1a2e1a;
    border-radius: 6px;
  }

  .btn-reference {
    background: #4a148c;
    color: #ce93d8;
    border: 1px solid #7b1fa2;
  }
  .btn-reference:hover { background: #6a1b9a; }

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

  .lyrics-comparison {
    font-size: 0.8rem;
    padding: 0.5rem;
    border-radius: 6px;
    margin-top: 0.5rem;
  }
  .lyrics-comparison.match {
    background: #1a2e1a;
    color: #66bb6a;
    border: 1px solid #2e7d32;
  }
  .lyrics-comparison.mismatch {
    background: #2e2a1a;
    color: #ffb74d;
    border: 1px solid #f57c00;
  }
  .lyrics-comparison.hint {
    color: #666;
    background: #1a1a2e;
    border: 1px solid #333;
  }

  details summary {
    cursor: pointer;
    color: #aaa;
    margin-top: 0.3rem;
    font-size: 0.75rem;
  }

  .diff-list {
    margin-top: 0.3rem;
    font-family: 'Courier New', monospace;
    font-size: 0.7rem;
    max-height: 200px;
    overflow-y: auto;
  }
  .diff-item {
    display: flex;
    flex-direction: column;
    padding: 0.2rem 0;
    border-bottom: 1px solid #333;
  }
  .diff-line { color: #888; font-weight: bold; }
  .diff-yours { color: #ef9a9a; }
  .diff-ref { color: #81c784; }
</style>
