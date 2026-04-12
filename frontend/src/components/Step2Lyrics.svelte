<script>
  async function handleLoadTestLyrics() {
    try {
      const result = await getTestLyrics();
      lyricsText = result.lyrics;
      artist = 'U2';
      title = 'Beautiful Day';
    } catch (err) {
      errorMessage.set(err.message);
    }
  }

  async function handleAutoHyphenate() {
    if (!lyricsText.trim()) {
      errorMessage.set('Enter lyrics first');
      return;
    }
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Auto-hyphenating lyrics...');
    try {
      const result = await hyphenateLyrics(lyricsText, language);
      hyphenationResult = result;
      lyricsText = result.hyphenated;
      processingStatus.set(`✅ Auto-hyphenated: ${result.total_syllables} syllables (${result.method})`);
    } catch (err) {
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }

  async function handleSubmit() {
    if (!lyricsText.trim()) {
      errorMessage.set('Please enter lyrics');
      return;
    }
    if (!$sessionId) {
      errorMessage.set('No session. Please upload audio first.');
      return;
    }
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Validating lyrics...');
    try {
      const result = await submitLyrics($sessionId, lyricsText, artist, title, language);
      lyricsData.set({
        text: lyricsText,
        artist,
        title,
        language,
        syllableCount: result.syllable_count,
        lineCount: result.line_count,
        preview: result.preview,
      });
      processingStatus.set(`✅ ${result.syllable_count} syllables across ${result.line_count} lines`);
      generationModalOpen.set(true);
    } catch (err) {
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }
  // Restore checkTestSession function
  async function checkTestSession() {
    if ($sessionId && $sessionId.startsWith('test-')) {
      try {
        const result = await getTestLyrics();
        lyricsText = result.lyrics;
        artist = 'U2';
        title = 'Beautiful Day';
        // Optionally auto-submit or set more fields here
      } catch (e) {
        // Test lyrics not available, user can enter manually
      }
    }
  }
  import { onDestroy } from 'svelte';
  import { sessionId, lyricsData, uploadData, currentStep, isProcessing, processingStatus, errorMessage, generationModalOpen } from '../stores/appStore.js';
  import { SUPPORTED_LANGUAGES } from '../lib/languages';
  import { submitLyrics, getTestLyrics, loadTestSession, hyphenateLyrics, transcribeAudio, getAudioUrl } from '../services/api.js';


  // If coming from test session, lyrics may already be loaded
  let lyricsText = $lyricsData.text || '';
  let artist = $lyricsData.artist || '';
  let title = $lyricsData.title || '';
  let language = $lyricsData.language || '';
  let hyphenationResult = null;
  let isTranscribing = false;
  let transcribeInfo = null;

  // Keep lyricsData in sync with local fields
  $: lyricsData.set({
    text: lyricsText,
    artist,
    title,
    language,
    syllableCount: $lyricsData.syllableCount,
    lineCount: $lyricsData.lineCount,
    preview: $lyricsData.preview
  });

  // Handle file upload for .txt lyrics
  function handleFileUpload(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      lyricsText = e.target.result;
    };
    reader.readAsText(file);
  }

  // Audio
  $: hasVocals = $uploadData.hasVocals;
  $: audioSrc = $sessionId && hasVocals ? getAudioUrl($sessionId, 'vocals') : '';

  // Sync from store ONCE on mount (e.g. when navigating back to Step 2)
  let initializedFromStore = false;
  $: if ($lyricsData.text && !initializedFromStore) {
    initializedFromStore = true;
    lyricsText = $lyricsData.text;
    artist = $lyricsData.artist || artist;
    // Removed invalid async/await/try/catch from reactive statement
  }

  $: if ($currentStep === 2 && $sessionId) {
    checkTestSession();
  }

  onDestroy(() => {
    if ($sessionId && lyricsText.trim()) {
      submitLyrics($sessionId, lyricsText, artist, title, language).catch(() => {});
    }
  });

  // ── Whisper transcription ──
  async function handleTranscribe() {
    if (!$sessionId) {
      errorMessage.set('No session. Upload audio first.');
      return;
    }

    errorMessage.set('');
    isTranscribing = true;
    processingStatus.set('🎙️ Transcribing with Whisper (this may take a minute)...');

    try {
      const result = await transcribeAudio($sessionId, language);
      console.log('[Step2] Whisper result:', result);
      lyricsText = result.text;
      transcribeInfo = result;
      processingStatus.set(`✅ Transcribed: ${result.lines} lines, ${result.words} words (${result.language_name}, model: ${result.model})`);
    } catch (err) {
      console.error('[Step2] Transcription error:', err);
      errorMessage.set(err.message);
    } finally {
      isTranscribing = false;
    }
  }
</script>

<div class="step-content">
  <h2>Step 2: Lyrics</h2>

  <div class="form-group" style="margin-bottom:2rem;">
    <label for="language"><strong>Language (required)</strong></label>
    <select id="language" bind:value={language}>
      <option value="" disabled selected>Select language…</option>
      {#each SUPPORTED_LANGUAGES as lang}
        <option value={lang.code}>{lang.label}</option>
      {/each}
    </select>
    {#if !language}
      <div class="lang-warning">language of the song</div>
    {/if}
  </div>

  {#if language}
    {#if !hasVocals}
      <div class="no-vocals-warning">
        <p>⚠️ No vocal track found.</p>
        <p class="hint">Please go back to <button class="link-btn" on:click={() => currentStep.set(1)}>Step 1</button> to extract or upload vocals before generating lyrics.</p>
      </div>
      <!--
      <div class="back-btn-row">
        <button class="btn btn-secondary" on:click={() => currentStep.set(1)}>← Back to Step 1</button>
      </div>
      -->
    {:else}
      <div class="audio-section">
        <audio controls src={audioSrc}>
          Your browser does not support the audio element.
        </audio>
        <div class="transcribe-area">
          <button
            class="btn btn-transcribe"
            on:click={handleTranscribe}
            disabled={isTranscribing || $isProcessing}
          >
            {isTranscribing ? '⏳ Generating Lyrics...' : '🎙️ Generate Lyrics from Vocals'}
          </button>
          <p class="transcribe-hint">This will use AI to listen to your vocal track and automatically generate lyrics. You can review and edit the result below.</p>
        </div>
        {#if transcribeInfo}
          <div class="transcribe-info">
            Whisper ({transcribeInfo.model}): {transcribeInfo.words} words, {transcribeInfo.lines} lines — review and correct below
          </div>
        {/if}
      </div>
    {/if}

    <div class="form-row">
      <div class="form-group half">
        <label for="artist">Artist <span class="required">*</span></label>
        <input id="artist" type="text" bind:value={artist} placeholder="Artist name" class:input-missing={!artist.trim()} />
      </div>
      <div class="form-group half">
        <label for="title">Title <span class="required">*</span></label>
        <input id="title" type="text" bind:value={title} placeholder="Song title" class:input-missing={!title.trim()} />
      </div>
    </div>

    <div class="form-group">
      <label for="lyrics">
        Lyrics
        <span class="hint">(one line per phrase, use - for syllable splits: beau-ti-ful)</span>
      </label>
      <textarea
        id="lyrics"
        bind:value={lyricsText}
        rows="15"
        placeholder="The heart is a bloom&#10;Shoots up through the sto-ny ground&#10;There's no room&#10;..."
      ></textarea>
    </div>

    <div class="action-row">
      <button class="btn btn-hyphen small" on:click={handleAutoHyphenate} disabled={$isProcessing || !lyricsText.trim()}>
        ✂️ Auto-Hyphenate
      </button>
    </div>
    <div class="generate-row">
      <button class="btn btn-primary btn-generate" on:click={handleSubmit} disabled={$isProcessing || !lyricsText.trim() || !artist.trim() || !title.trim() || !$sessionId}>
        🚀 Generate Ultrastar Files
      </button>
    </div>
    {#if !$isProcessing}
      {@const missing = [!artist.trim() && 'Artist', !title.trim() && 'Title', !lyricsText.trim() && 'Lyrics'].filter(Boolean)}
      {#if missing.length > 0}
        <p class="missing-hint">Required to generate: {missing.join(', ')}</p>
      {/if}
    {/if}
  {/if}
  <style>
    .lang-warning {
      color: #b00;
      font-weight: bold;
      margin-top: 0.5rem;
    }
  </style>

  {#if $lyricsData.preview.length > 0 && !$generationModalOpen}
    <div class="preview-section">
      <h3>Syllable Preview ({$lyricsData.syllableCount} syllables, {$lyricsData.lineCount} lines)</h3>
      <div class="preview-lines">
        {#each $lyricsData.preview as line}
          <div class="preview-line">
            <span class="line-num">L{line.line}</span>
            <div class="syllables">
              {#each line.syllables as syl}
                <span class="syllable">{syl}</span>
              {/each}
            </div>
          </div>
        {/each}
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

  h2 { color: #4fc3f7; margin-bottom: 1rem; }
  h3 { color: #aaa; margin: 1rem 0 0.5rem; font-size: 0.95rem; }

  .form-row {
    display: flex;
    gap: 1rem;
  }

  .form-group {
    margin-bottom: 1rem;
  }

  .form-group.half {
    flex: 1;
  }

  label {
    display: block;
    color: #aaa;
    font-size: 0.85rem;
    margin-bottom: 0.3rem;
  }

  .hint {
    color: #666;
    font-size: 0.75rem;
  }

  .required {
    color: #e57373;
    font-size: 0.8rem;
  }

  .input-missing {
    border-color: #555 !important;
    background: #1e1a1a !important;
  }

  .missing-hint {
    font-size: 0.8rem;
    color: #888;
    margin: 0.3rem 0 0;
    text-align: right;
  }

  input, select, textarea {
    width: 100%;
    padding: 0.6rem;
    border: 1px solid #444;
    border-radius: 6px;
    background: #1a1a2e;
    color: #eee;
    font-size: 0.9rem;
    font-family: inherit;
    box-sizing: border-box;
  }

  textarea {
    resize: vertical;
    font-family: 'Courier New', monospace;
    line-height: 1.5;
  }

  input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: #4fc3f7;
  }

  .btn-transcribe { background: #6a1b9a; color: white; font-size: 0.85rem; padding: 0.5rem 1rem; }
  .btn-transcribe:hover:not(:disabled) { background: #8e24aa; }
  .btn-transcribe:disabled { opacity: 0.5; cursor: not-allowed; }

  .audio-section {
    margin-bottom: 1.25rem;
  }

  .audio-section audio {
    width: 100%;
    margin-bottom: 0.75rem;
  }

  .transcribe-area {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .transcribe-hint {
    color: #888;
    font-size: 0.8rem;
    line-height: 1.4;
    margin: 0;
  }

  .no-audio-warning, .no-vocals-warning {
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.75rem;
    font-size: 0.85rem;
  }

  .no-audio-warning {
    background: #3e1a1a;
    border: 1px solid #c62828;
    color: #ef9a9a;
  }

  .no-vocals-warning {
    background: #3e2e1a;
    border: 1px solid #e65100;
    color: #ffcc80;
  }

  .no-audio-warning p, .no-vocals-warning p {
    margin: 0;
  }

  .link-btn {
    background: none;
    border: none;
    color: #4fc3f7;
    cursor: pointer;
    text-decoration: underline;
    font-size: inherit;
    padding: 0;
  }
  .link-btn:hover { color: #81d4fa; }

  .transcribe-info {
    background: #1a0e2e;
    border: 1px solid #6a1b9a;
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    color: #ce93d8;
    font-size: 0.8rem;
    margin-bottom: 1rem;
  }

  .action-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .generate-row {
    display: flex;
    justify-content: flex-end;
    margin-top: 0.75rem;
  }

  .btn-generate {
    padding: 0.9rem 2rem;
    font-size: 1rem;
  }

  .btn {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 8px;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  .btn.small { font-size: 0.8rem; padding: 0.5rem 1rem; }
  .btn-primary { background: #1976d2; color: white; }
  .btn-primary:hover:not(:disabled) { background: #1565c0; }
  .btn-secondary { background: #333; color: #ccc; border: 1px solid #555; }
  .btn-secondary:hover:not(:disabled) { background: #444; }
  .btn-hyphen { background: #e65100; color: white; }
  .btn-hyphen:hover:not(:disabled) { background: #f57c00; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .hyphenation-info {
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: #2e1a00;
    border: 1px solid #e65100;
    border-radius: 8px;
    color: #ffcc80;
    font-size: 0.85rem;
  }

  .hyphenation-info .hint {
    color: #999;
    margin-top: 0.3rem;
  }

  .preview-section {
    margin-top: 1rem;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 1rem;
    background: #111;
    max-height: 300px;
    overflow-y: auto;
  }

  .preview-line {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
  }

  .line-num {
    color: #666;
    font-size: 0.75rem;
    min-width: 2rem;
    padding-top: 0.2rem;
  }

  .syllables {
    display: flex;
    flex-wrap: wrap;
    gap: 0.2rem;
  }

  .syllable {
    background: #1a2e4a;
    border: 1px solid #2a4a6e;
    border-radius: 4px;
    padding: 0.15rem 0.4rem;
    font-size: 0.8rem;
    color: #4fc3f7;
    font-family: 'Courier New', monospace;
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
