<script>
  /**
   * Step 2: the song's artist, title and language, and its lyrics from up to three sources (LRCLIB,
   * Whisper on the vocals, Whisper on the cleaned vocals) shown as tabs on two sides for comparing.
   * Either side generates the UltraStar file from the text it shows; the text is hyphenated on the way
   * (words the user split stay as they are). See docs/plans/step2-lyrics-tabs.md.
   */
  import { onMount, onDestroy } from 'svelte';
  import 'codemirror/lib/codemirror.css';
  import LyricsPanel from './LyricsPanel.svelte';
  import LyricsVersionsModal from './LyricsVersionsModal.svelte';
  import { sessionId, lyricsData, uploadData, currentStep, isProcessing, processingStatus, errorMessage, generationModalOpen, generationUseCleaned, generationResult } from '../stores/appStore.js';
  import { showConfirm } from '../stores/dialogStore.js';
  import { SUPPORTED_LANGUAGES } from '../lib/languages';
  import { submitLyrics, searchLyricsOnline, getLyricsSources, saveLyricsSources, getTestLyrics, hyphenateLyrics, transcribeAudio, cancelTranscribe, getAudioUrl, updateMetadata, getEditorData, generateEmptyUltrastar } from '../services/api.js';

  // ── Song ────────────────────────────────────────────────
  let artist = $lyricsData.artist || '';
  let title = $lyricsData.title || '';
  let language = $lyricsData.language || '';

  // Artist and title of a new upload are a guess until the user confirms them (Step 1's song window, editing
  // them here, or "Yes, search lyrics"); the automatic LRCLIB search waits for that.
  let songConfirmed = true;

  async function syncMetadata() {
    if (!$sessionId || !artist.trim() || !title.trim()) return;
    lyricsData.update(s => ({ ...s, artist: artist.trim(), title: title.trim() }));
    try {
      await updateMetadata($sessionId, artist.trim(), title.trim(), language || undefined);
      songConfirmed = true; // saving the names confirms them
    } catch { /* not critical */ }
  }

  // Keep the store in step with the fields (the lyrics text there is the last generated one).
  $: lyricsData.update(s => ({ ...s, artist, title, language }));

  // ── Lyric sources ───────────────────────────────────────
  const EMPTY = () => ({ text: '', marks: [], dividers: [], info: null });
  let sources = { lrclib: EMPTY(), vocals: EMPTY(), cleaned: EMPTY() };
  let tabs = { left: 'lrclib', right: 'vocals' };
  let sourcesLoadedFor = null;
  let sourcesReady = false;
  let busy = { lrclib: false, vocals: false, cleaned: false };
  let saveTimer = null;

  $: if ($sessionId && sourcesLoadedFor !== $sessionId) loadSources($sessionId);

  async function loadSources(id) {
    sourcesLoadedFor = id;
    sourcesReady = false;
    try {
      const stored = await getLyricsSources(id);
      const merged = { lrclib: EMPTY(), vocals: EMPTY(), cleaned: EMPTY() };
      for (const key of Object.keys(merged)) merged[key] = { ...merged[key], ...(stored.sources?.[key] || {}) };
      if (!stored.sources || Object.keys(stored.sources).length === 0) {
        // Sessions from before the tabs: the left field was "Generated Lyrics", the right one (browser only) "Original".
        merged.vocals.text = $lyricsData.text || '';
        try {
          const old = JSON.parse(localStorage.getItem(`comparison_lyrics_${id}`) || 'null');
          if (old?.text) merged.lrclib = { ...merged.lrclib, text: old.text, marks: old.marks || [] };
        } catch { /* nothing usable */ }
      }
      sources = merged;
      tabs = { left: stored.tabs?.left || 'lrclib', right: stored.tabs?.right || 'vocals' };
      tabsPicked = !!stored.tabs?.left;
      if (!artist && stored.artist) artist = stored.artist;
      if (!title && stored.title) title = stored.title;
      if (!language && stored.language) language = stored.language;
      songConfirmed = stored.song_confirmed !== false;
    } catch (err) {
      console.warn('[Step2] Could not load lyric sources:', err);
    }
    sourcesReady = true;
  }

  function scheduleSave() {
    if (!$sessionId) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flushSave, 600);
  }

  function flushSave() {
    clearTimeout(saveTimer);
    saveTimer = null;
    if (!$sessionId || !sourcesReady) return;
    saveLyricsSources($sessionId, { sources, tabs }).catch(err => console.warn('[Step2] Could not save lyrics:', err));
  }

  function updateSource(id, patch) {
    sources = { ...sources, [id]: { ...sources[id], ...patch } };
    scheduleSave();
  }

  function handlePanelChange(event) {
    const { source, ...patch } = event.detail;
    updateSource(source, patch);
  }

  let tabsPicked = false; // the user chose a tab: no more automatic switching

  function handleTab(event) {
    tabsPicked = true;
    tabs = { ...tabs, [event.detail.side]: event.detail.tab };
    scheduleSave();
  }

  // ── Cleanup (Step 4) ────────────────────────────────────
  let cleanupSegments = [];
  let cleanedAudioAvailable = false;
  let hasOriginalDemucs = false; // legacy sessions
  let hasEditedVocal = false;

  async function loadCleanupSegments() {
    if (!$sessionId || !$generationResult) return; // no chart yet, so no cleanup either
    try {
      const editorData = await getEditorData($sessionId);
      cleanupSegments = editorData.cleanup_segments || [];
      cleanedAudioAvailable = editorData.cleaned_audio_available || false;
      hasOriginalDemucs = editorData.has_original_demucs || false;
      hasEditedVocal = editorData.has_edited_vocal || false;
    } catch (e) {
      console.error('[Step2] Failed to load cleanup segments:', e);
      cleanupSegments = [];
    }
  }

  $: hasVocals = $uploadData.hasVocals;
  $: hasCleaned = !!$sessionId && (hasEditedVocal || (cleanupSegments.length > 0 && cleanedAudioAvailable));
  $: vocalsUrl = $sessionId && hasVocals ? getAudioUrl($sessionId, hasOriginalDemucs && !hasEditedVocal ? 'demucs' : 'vocals') : '';
  $: cleanedUrl = hasCleaned ? getAudioUrl($sessionId, hasEditedVocal ? 'edited' : 'cleaned') : '';
  $: mixUrl = $sessionId && $uploadData.hasOriginal ? getAudioUrl($sessionId, 'original') : '';
  $: tabList = [
    { id: 'lrclib', label: 'LRCLIB' },
    { id: 'vocals', label: 'Vocals' },
    ...(hasCleaned ? [{ id: 'cleaned', label: 'Cleaned vocals' }] : []),
  ];
  // A side left on "Cleaned vocals" when there is no cleanup (any more) shows the vocals.
  $: if (!hasCleaned && (tabs.left === 'cleaned' || tabs.right === 'cleaned')) {
    tabs = { left: tabs.left === 'cleaned' ? 'vocals' : tabs.left, right: tabs.right === 'cleaned' ? 'vocals' : tabs.right };
  }

  $: if ($currentStep === 2 && $sessionId) {
    checkTestSession();
    loadCleanupSegments();
  }

  // ── LRCLIB ──────────────────────────────────────────────
  let lyricsCandidates = [];
  let chosenCandidateId = null;
  let songDuration = null;
  let autoSearchedFor = null;
  let autoSearchTimer = null;

  // Search on its own when artist and title are known and the LRCLIB text is still empty.
  $: if (sourcesReady && songConfirmed && artist.trim() && title.trim() && !sources.lrclib.text.trim() && !busy.lrclib
         && autoSearchedFor !== `${$sessionId}|${artist.trim()}|${title.trim()}`) {
    clearTimeout(autoSearchTimer);
    const key = `${$sessionId}|${artist.trim()}|${title.trim()}`;
    autoSearchTimer = setTimeout(() => { autoSearchedFor = key; autoSearch(); }, 800);
  }

  async function searchLrclib(queryArtist, queryTitle) {
    busy = { ...busy, lrclib: true };
    try {
      const found = await searchLyricsOnline($sessionId, queryArtist, queryTitle);
      lyricsCandidates = found.candidates || [];
      songDuration = found.song_duration || null;
      return found;
    } finally {
      busy = { ...busy, lrclib: false };
    }
  }

  /** On its own when Step 2 opens: fill the LRCLIB tab with the clear match, if there is one. */
  async function autoSearch() {
    const query = `"${artist.trim()} – ${title.trim()}"`;
    try {
      const found = await searchLrclib(artist.trim(), title.trim());
      chosenCandidateId = null;
      if (found.found) {
        useLyricsCandidate(found);
        return;
      }
      updateSource('lrclib', { info: { message: lyricsCandidates.length
        ? `No exact match for ${query}. Search LRCLIB to choose a version.`
        : `No lyrics on LRCLIB for ${query}. Search with another title, or paste the lyrics.` } });
      // Nothing to show on the left: start there with the vocals instead (as long as no tab was picked).
      if (!tabsPicked && tabs.left === 'lrclib' && tabs.right === 'vocals') {
        tabs = { left: 'vocals', right: 'lrclib' };
        scheduleSave();
      }
    } catch (err) {
      updateSource('lrclib', { info: { message: err.message.replace(/^API error \d+: /, '') } });
    }
  }

  // The LRCLIB window: search again and choose a version.
  let versionsOpen = false;
  let versionsMessage = '';

  function openVersions() {
    versionsMessage = '';
    versionsOpen = true;
  }

  async function handleVersionsSearch(event) {
    versionsMessage = '';
    try {
      const found = await searchLrclib(event.detail.artist, event.detail.title);
      if (!lyricsCandidates.length) versionsMessage = '';
      else if (!found.found) versionsMessage = 'No exact match — these are the closest:';
    } catch (err) {
      versionsMessage = err.message.replace(/^API error \d+: /, '');
    }
  }

  function handleVersionChosen(event) {
    useLyricsCandidate(event.detail);
    versionsOpen = false;
  }

  function formatDuration(seconds) {
    if (!seconds) return '';
    const s = Math.round(seconds);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  function useLyricsCandidate(entry) {
    chosenCandidateId = entry.id;
    const length = entry.duration ? ` · ${formatDuration(entry.duration)}` : '';
    updateSource('lrclib', {
      text: entry.text, marks: [], dividers: [],
      info: { message: `✓ ${entry.lines} lines: ${entry.artist} – ${entry.track}${length}${entry.synced ? ' · synced' : ''}. Repeated choruses must be written out.` },
    });
  }

  // ── Whisper ─────────────────────────────────────────────
  let isTranscribing = false;
  let transcribeStatus = '';
  let transcribePhase = '';  // 'loading' | 'transcribing' | 'done' | 'error'
  let transcribeElapsed = 0;
  let transcribeModalOpen = false;
  let whisperFallbackWarning = false;
  let transcribeAbortController = null;
  let transcribeTicker = null;
  const transcribeModelPreset = 'balanced';

  function startTranscribeTicker() {
    transcribeElapsed = 0;
    transcribeTicker = setInterval(() => { transcribeElapsed += 1; }, 1000);
  }
  function stopTranscribeTicker() {
    if (transcribeTicker) { clearInterval(transcribeTicker); transcribeTicker = null; }
  }

  async function handleTranscribe(event) {
    const source = event.detail.source;
    const cleaned = source === 'cleaned';
    if (!$sessionId) { errorMessage.set('No session. Upload audio first.'); return; }
    if (!cleaned && !hasVocals) { errorMessage.set('No vocals yet: extract or upload them in Step 1.'); return; }
    if (sources[source].text.trim() && !(await showConfirm(
      'Listen again and replace this text?', { title: 'Extract lyrics', confirmLabel: 'Replace' },
    ))) return;
    errorMessage.set('');
    isTranscribing = true;
    busy = { ...busy, [source]: true };
    transcribePhase = 'transcribing';
    transcribeStatus = cleaned ? 'Transcribing cleaned vocals with Whisper…' : 'Transcribing vocals with Whisper…';
    transcribeModalOpen = true;
    transcribeAbortController = new AbortController();
    startTranscribeTicker();
    try {
      const result = await transcribeAudio($sessionId, language, transcribeAbortController.signal, cleaned, transcribeModelPreset);
      stopTranscribeTicker();
      updateSource(source, {
        text: result.text, marks: [], dividers: [],
        info: { message: `Whisper (${result.model}): ${result.words} words, ${result.lines} lines — check and correct below` },
      });
      transcribePhase = 'done';
      transcribeStatus = `${result.lines} lines, ${result.words} words (${result.language_name}, ${result.model})`;
      if (result.model && !result.model.startsWith('whisperx-')) whisperFallbackWarning = true;
      setTimeout(() => { transcribeModalOpen = false; }, 1800);
    } catch (err) {
      stopTranscribeTicker();
      if (err.name === 'AbortError') return; // cancelled
      transcribePhase = 'error';
      transcribeStatus = err.message;
      errorMessage.set(err.message);
    } finally {
      isTranscribing = false;
      busy = { ...busy, [source]: false };
    }
  }

  function cancelTranscription() {
    stopTranscribeTicker();
    isTranscribing = false;
    transcribeModalOpen = false;
    transcribePhase = '';
    if (transcribeAbortController) transcribeAbortController.abort();
    cancelTranscribe($sessionId);
  }

  // ── Generate ────────────────────────────────────────────
  $: missing = [!artist.trim() && 'artist', !title.trim() && 'title', !language && 'language', !hasVocals && 'vocals (Step 1)']
    .filter(Boolean);
  $: canGenerate = !!$sessionId && missing.length === 0;
  $: generateHint = missing.length ? `Needs ${missing.join(', ')}` : '';

  /** The audio the timing is made from follows the tab: Vocals → vocals, Cleaned vocals → cleaned vocals,
   * LRCLIB (no audio of its own) → the cleaned vocals when there is a cleanup, else the vocals. */
  function timesWithCleanedVocals(source) {
    return hasCleaned && source !== 'vocals';
  }

  async function handleGenerate(event) {
    const text = sources[event.detail.source]?.text || '';
    if (!text.trim() || !canGenerate) return;
    if ($generationResult && !(await showConfirm(
      'This replaces the UltraStar file you already have, including your changes in the editor.',
      { title: 'Generate again?', confirmLabel: 'Generate', danger: true },
    ))) return;
    errorMessage.set('');
    isProcessing.set(true);
    processingStatus.set('Preparing lyrics…');
    try {
      // Hyphenated on the way, invisibly; words the user split stay as they are.
      const hyphenated = (await hyphenateLyrics(text, language)).hyphenated;
      const result = await submitLyrics($sessionId, hyphenated, artist, title, language);
      lyricsData.set({
        text: hyphenated, artist, title, language,
        syllableCount: result.syllable_count, lineCount: result.line_count, preview: result.preview,
      });
      processingStatus.set(`✅ ${result.syllable_count} syllables across ${result.line_count} lines`);
      generationUseCleaned.set(timesWithCleanedVocals(event.detail.source));
      generationModalOpen.set(true);
    } catch (err) {
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
    }
  }

  let emptyGenerating = false;

  async function handleGenerateEmpty() {
    if (!$sessionId) { errorMessage.set('No session. Please upload audio first.'); return; }
    if (!artist.trim() || !title.trim()) { errorMessage.set('Please enter Artist and Title before generating.'); return; }
    if ($generationResult && !(await showConfirm(
      'This replaces the UltraStar file you already have, including your changes in the editor.',
      { title: 'Create an empty file?', confirmLabel: 'Create', danger: true },
    ))) return;
    isProcessing.set(true);
    emptyGenerating = true;
    processingStatus.set('Creating empty Ultrastar file…');
    try {
      const result = await generateEmptyUltrastar($sessionId);
      generationResult.set(result);
      currentStep.set(4);
    } catch (err) {
      errorMessage.set(err.message);
    } finally {
      isProcessing.set(false);
      emptyGenerating = false;
    }
  }

  // ── Test session ────────────────────────────────────────
  async function checkTestSession() {
    if ($sessionId && $sessionId.startsWith('test-') && !sources.vocals.text.trim()) {
      try {
        const result = await getTestLyrics();
        updateSource('vocals', { text: result.lyrics });
        artist = artist || 'U2';
        title = title || 'Beautiful Day';
      } catch { /* test lyrics not available */ }
    }
  }

  // ── Text field look (CodeMirror is styled globally: it lives in LyricsPanel) ──
  let zebraStyleEl = null;
  onMount(() => {
    if (zebraStyleEl) return;
    zebraStyleEl = document.createElement('style');
    zebraStyleEl.setAttribute('data-step2-cm-zebra', 'true');
    zebraStyleEl.textContent = `
      .lyrics-column .CodeMirror {
        border: 1px solid #444; border-radius: 6px; height: 360px;
        font-family: 'Courier New', monospace; font-size: 0.95rem; line-height: 1.5;
        background: #0d0d0d; color: #e0e0e0;
      }
      .lyrics-column .CodeMirror-focused { border-color: #4a90e2; box-shadow: 0 0 8px rgba(74, 144, 226, 0.3); }
      .lyrics-column .CodeMirror-gutters { background: #161616; border-right: 1px solid #333; }
      .lyrics-column .CodeMirror-linenumber { color: #777; }
      .lyrics-column .CodeMirror-cursor { border-left: 1px solid #ddd; }
      .lyrics-column .CodeMirror-selected { background: rgba(79, 140, 255, 0.35); }
      .lyrics-column .CodeMirror-focused .CodeMirror-selected { background: rgba(79, 140, 255, 0.45); }
      .lyrics-column .CodeMirror-focused .CodeMirror-selectedtext,
      .lyrics-column .CodeMirror-selectedtext { color: #ffffff; }
      .lyrics-column .CodeMirror-code > div:nth-child(even) .CodeMirror-line,
      .lyrics-column .CodeMirror-code > div:nth-child(even) .CodeMirror-gutter-wrapper { background: rgba(255, 255, 255, 0.08); }
      .lyrics-column .CodeMirror-code > div.cm-line-divider .CodeMirror-line,
      .lyrics-column .CodeMirror-code > div.cm-line-divider .CodeMirror-gutter-wrapper,
      .lyrics-column .CodeMirror-code > div.cm-line-divider .CodeMirror-gutter-elt {
        border-bottom: 2px solid rgba(255, 255, 255, 0.55); box-sizing: border-box;
      }
    `;
    document.head.appendChild(zebraStyleEl);
  });

  onDestroy(() => {
    clearTimeout(autoSearchTimer);
    if (saveTimer) flushSave();
    if (zebraStyleEl && zebraStyleEl.parentNode) zebraStyleEl.parentNode.removeChild(zebraStyleEl);
    zebraStyleEl = null;
    if ($sessionId && artist.trim() && title.trim()) {
      updateMetadata($sessionId, artist.trim(), title.trim(), language || undefined).catch(() => {});
    }
  });
</script>
<div class="step-content">
  <style>
    .lang-warning {
      color: #b00;
      font-weight: bold;
      margin-top: 0.5rem;
    }

    .lyrics-comparison-container {
      display: flex;
      align-items: flex-start;
      gap: 1rem;
      width: 100%;
    }

    .lyrics-column {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
    }

    .lyrics-column label {
      min-height: 2.5rem;
    }

    .lyrics-column :global(.CodeMirror) {
      border: 1px solid #444;
      border-radius: 6px;
      height: 360px;
      font-family: 'Courier New', monospace;
      font-size: 0.95rem;
      line-height: 1.5;
      background: #0d0d0d;
      color: #e0e0e0;
    }

    .lyrics-column :global(.CodeMirror-focused) {
      border-color: #4a90e2;
      box-shadow: 0 0 8px rgba(74, 144, 226, 0.3);
    }

    .lyrics-column :global(.CodeMirror-gutters) {
      background: #161616;
      border-right: 1px solid #333;
    }

    .lyrics-column :global(.CodeMirror-linenumber) {
      color: #777;
    }

    .lyrics-column :global(.CodeMirror-cursor) {
      border-left: 1px solid #ddd;
    }

    .color-controls {
      display: flex;
      gap: 0.5rem;
      margin-top: 0.75rem;
      flex-wrap: wrap;
    }

    .color-btn {
      padding: 0.5rem 0.75rem;
      border: 1px solid #444;
      border-radius: 4px;
      background: #1a1a1a;
      color: #e0e0e0;
      cursor: pointer;
      font-size: 1rem;
      transition: all 0.2s ease;
      user-select: none;
    }

    .color-btn:hover {
      border-color: #666;
      background: #252525;
    }

    .color-btn:active {
      transform: scale(0.95);
    }

    .color-btn.clear {
      margin-left: auto;
      background: #2a2a2a;
      border-color: #555;
    }

    .color-btn.clear:hover {
      background: #333;
      border-color: #777;
    }
  </style>
  <h2>Step 2: Lyrics</h2>

  <div class="form-row song-row">
    <div class="form-group">
      <label for="artist">Artist <span class="required">*</span></label>
      <input id="artist" type="text" bind:value={artist} placeholder="Artist name" class:input-missing={!artist.trim()} on:blur={syncMetadata} />
    </div>
    <div class="form-group">
      <label for="title">Title <span class="required">*</span></label>
      <input id="title" type="text" bind:value={title} placeholder="Song title" class:input-missing={!title.trim()} on:blur={syncMetadata} />
    </div>
    <div class="form-group language-group">
      <label for="language">Language <span class="required">*</span></label>
      <select id="language" bind:value={language} on:change={syncMetadata}>
        <option value="" disabled selected>Select language…</option>
        {#each SUPPORTED_LANGUAGES as lang}
          <option value={lang.code}>{lang.label}</option>
        {/each}
      </select>
      {#if !language}<div class="lang-warning">language of the song</div>{/if}
    </div>
  </div>

  {#if !songConfirmed && artist.trim() && title.trim()}
    <p class="confirm-song">
      Is this the right song? Correct artist or title above if not.
      <button class="btn btn-secondary small" on:click={syncMetadata}>✓ Yes, search lyrics</button>
    </p>
  {/if}

  {#if !hasVocals}
    <div class="no-vocals-warning">
      <p>⚠️ No vocal track yet.</p>
      <p class="hint">LRCLIB works without it, but listening and generating need the vocals: go back to
        <button class="link-btn" on:click={() => currentStep.set(1)}>Step 1</button> to extract or upload them.</p>
    </div>
  {/if}

  {#if mixUrl || vocalsUrl || cleanedUrl}
    <div class="players">
      {#if mixUrl}
        <div class="player-row"><span class="player-label">🎵 Full mix</span><audio controls preload="none" src={mixUrl}></audio></div>
      {/if}
      {#if vocalsUrl}
        <div class="player-row"><span class="player-label">🎤 Vocals</span><audio controls preload="none" src={vocalsUrl}></audio></div>
      {/if}
      {#if cleanedUrl}
        <div class="player-row"><span class="player-label">✨ Cleaned vocals</span><audio controls preload="none" src={cleanedUrl}></audio></div>
      {/if}
    </div>
  {/if}

  <div class="lyrics-comparison-container">
    {#each ['left', 'right'] as side (side)}
      <LyricsPanel
        {side}
        tab={tabs[side]}
        tabs={tabList}
        {sources}
        {busy}
        versionsCount={lyricsCandidates.length}
        chosen={chosenCandidateId !== null}
        {canGenerate}
        {generateHint}
        disabled={$isProcessing || isTranscribing}
        on:tab={handleTab}
        on:change={handlePanelChange}
        on:versions={openVersions}
        on:transcribe={handleTranscribe}
        on:generate={handleGenerate}
      />
    {/each}
  </div>

  <div class="generate-row">
    <button class="btn btn-secondary btn-generate" on:click={handleGenerateEmpty} disabled={$isProcessing || !$sessionId || !artist.trim() || !title.trim()} title="Skip note alignment — open editor with empty file">
      📄 Generate empty UltraStar file
    </button>
  </div>

  {#if $processingStatus}
    <div class="status-bar">{$processingStatus}</div>
  {/if}
  {#if $errorMessage}
    <div class="error-bar">❌ {$errorMessage}</div>
  {/if}
</div>

{#if versionsOpen}
  <LyricsVersionsModal
    {artist}
    {title}
    candidates={lyricsCandidates}
    chosenId={chosenCandidateId}
    {songDuration}
    searching={busy.lrclib}
    message={versionsMessage}
    on:search={handleVersionsSearch}
    on:choose={handleVersionChosen}
    on:close={() => versionsOpen = false}
  />
{/if}

{#if whisperFallbackWarning}
  <div class="warning-modal-overlay" on:click={() => whisperFallbackWarning = false}>
    <div class="warning-modal" on:click|stopPropagation>
      <h2>⚠️ WhisperX unavailable</h2>
      <p class="warning-modal-msg">WhisperX failed and vanilla Whisper was used instead. Word timestamps are less precise and char-level sync is not available — results may need more manual correction in the editor.</p>
      <p class="warning-modal-hint">Check the backend log for details. You can still proceed.</p>
      <button on:click={() => whisperFallbackWarning = false}>Dismiss</button>
    </div>
  </div>
{/if}

{#if transcribeModalOpen}
  <div class="transcribe-modal-backdrop">
    <div class="transcribe-modal-box">
      <div class="transcribe-modal-header">
        {#if transcribePhase === 'done'}
          <span class="phase-icon">✅</span>
          <h2>Transcription Complete</h2>
        {:else if transcribePhase === 'error'}
          <span class="phase-icon">❌</span>
          <h2>Transcription Failed</h2>
        {:else}
          <span class="t-spinner"></span>
          <h2>Generating Lyrics…</h2>
        {/if}
      </div>
      <p class="transcribe-modal-status">{transcribeStatus}</p>
      {#if transcribePhase === 'transcribing'}
        <div class="transcribe-elapsed">⏱ {transcribeElapsed}s elapsed</div>
        <div class="transcribe-hint">
          Whisper listens to the full vocal track.<br>
          Typical songs take <strong>30–120 seconds</strong>.
        </div>
      {/if}
      <div class="transcribe-modal-footer">
        <button class="btn btn-cancel" on:click={cancelTranscription}>
          {isTranscribing ? '✕ Cancel' : '← Close'}
        </button>
      </div>
    </div>
  </div>
{/if}

{#if emptyGenerating}
  <div class="empty-gen-overlay">
    <div class="empty-gen-card">
      <div class="empty-gen-spinner"></div>
      <p>Creating empty Ultrastar file…</p>
    </div>
  </div>
{/if}

<style>
  .song-row { display: flex; gap: 1rem; flex-wrap: wrap; align-items: flex-start; }
  .song-row .form-group { flex: 1 1 200px; }
  .song-row .language-group { flex: 0 1 220px; }
  .confirm-song { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; color: #e0a030; font-size: 0.9rem; margin: 0 0 0.75rem; }
  .players { display: flex; flex-direction: column; gap: 0.4rem; margin: 0.25rem 0 1rem; }
  .player-row { display: flex; align-items: center; gap: 0.75rem; }
  .player-label { flex: 0 0 130px; color: #bbb; font-size: 0.85rem; }
  .player-row audio { flex: 1; min-width: 0; height: 34px; }

  .warning-modal {
    background: #1e2330;
    border: 1px solid #f5a623;
    border-radius: 10px;
    padding: 1.5rem 2rem;
    max-width: 520px;
    width: 90%;
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }

  .warning-modal h2 {
    color: #f5a623;
    margin: 0;
    font-size: 1.1rem;
  }

  .warning-modal-msg {
    color: #ffd180;
    font-size: 0.88rem;
    line-height: 1.5;
    margin: 0;
  }

  .warning-modal-hint {
    color: #888;
    font-size: 0.8rem;
    margin: 0;
  }

  .warning-modal button {
    align-self: flex-end;
    background: #f5a623;
    color: #1a1a1a;
    border: none;
    border-radius: 6px;
    padding: 0.4rem 1.2rem;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
  }

  h2 { color: #4fc3f7; margin-bottom: 1rem; }

  .form-row {
    display: flex;
    gap: 1rem;
  }

  .form-group {
    margin-bottom: 1rem;
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


  input, select {
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


  input:focus, select:focus {
    outline: none;
    border-color: #4fc3f7;
  }









  .transcribe-hint {
    color: #888;
    font-size: 0.8rem;
    line-height: 1.4;
    margin: 0;
  }

  .no-vocals-warning {
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.75rem;
    font-size: 0.85rem;
  }


  .no-vocals-warning {
    background: #3e2e1a;
    border: 1px solid #e65100;
    color: #ffcc80;
  }

  .no-vocals-warning p {
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


















  .generate-row {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    margin-top: 28px;
    flex-wrap: wrap;
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
  .btn-secondary { background: #333; color: #ccc; border: 1px solid #555; }
  .btn-secondary:hover:not(:disabled) { background: #444; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }








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

  /* Transcription modal */
  .transcribe-modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.75);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .transcribe-modal-box {
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 12px;
    padding: 2rem;
    width: 90%;
    max-width: 480px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .transcribe-modal-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .transcribe-modal-header h2 {
    margin: 0;
  }

  .phase-icon {
    font-size: 1.4rem;
    line-height: 1;
  }

  .t-spinner {
    width: 20px;
    height: 20px;
    border: 3px solid #333;
    border-top-color: #4fc3f7;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .transcribe-modal-status {
    color: #aaa;
    font-size: 0.9rem;
    margin: 0;
  }

  .transcribe-elapsed {
    font-size: 0.85rem;
    color: #4fc3f7;
    font-variant-numeric: tabular-nums;
  }

  .transcribe-hint {
    font-size: 0.82rem;
    color: #666e7a;
    line-height: 1.5;
  }

  .transcribe-hint strong {
    color: #aaa;
  }

  .transcribe-modal-footer {
    display: flex;
    justify-content: flex-start;
    margin-top: 0.5rem;
  }

  .empty-gen-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .empty-gen-card {
    background: #1e2230;
    border: 1px solid #3a3f5c;
    border-radius: 12px;
    padding: 2rem 3rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    color: #e0e0e0;
  }
  .empty-gen-spinner {
    width: 40px;
    height: 40px;
    border: 4px solid #3a3f5c;
    border-top-color: #7c6af7;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
