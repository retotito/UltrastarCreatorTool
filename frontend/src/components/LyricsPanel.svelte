<script>
  /**
   * One side of Step 2: tabs for the lyric sources (LRCLIB, vocals, cleaned vocals), the tools of the
   * selected source, its text, and "Generate UltraStar file". The texts live in Step 2 (`sources`), so
   * both sides showing the same source show the same text.
   */
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import CodeMirror from 'codemirror';

  export let side = 'left';
  export let tab = 'lrclib';
  /** [{ id, label }] — the tabs to show */
  export let tabs = [];
  /** { lrclib: {text, marks, dividers, info}, vocals: {...}, cleaned: {...} } */
  export let sources = {};
  /** source id → true while it is being produced (search / Whisper) */
  export let busy = {};
  /** LRCLIB suggestions (shared by both sides) */
  export let candidates = [];
  export let chosenCandidateId = null;
  export let songDuration = null;
  export let canSearch = false;
  export let canGenerate = false;
  export let generateHint = '';
  export let disabled = false;

  const dispatch = createEventDispatcher();
  let textarea;
  let editor = null;
  let shownTab = null;
  let applying = false;
  let showCandidates = false;

  $: source = sources[tab] || { text: '' };
  $: text = source.text || '';
  $: info = source.info || null;
  $: if (editor) syncEditor(tab, text);

  function formatDuration(seconds) {
    if (!seconds) return '';
    const s = Math.round(seconds);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  /** Show the selected source's text; only re-render marks when the tab changed or the text came from elsewhere. */
  function syncEditor(currentTab, currentText) {
    const tabChanged = currentTab !== shownTab;
    if (!tabChanged && editor.getValue() === currentText) return;
    applying = true;
    const cursor = editor.getCursor();
    editor.setValue(currentText);
    if (!tabChanged) { try { editor.setCursor(cursor); } catch {} }
    applyMarks(sources[currentTab]?.marks || []);
    applyDividers(sources[currentTab]?.dividers || []);
    shownTab = currentTab;
    applying = false;
  }

  function applyMarks(marks) {
    editor.getAllMarks().forEach(m => m.clear());
    const doc = editor.getDoc();
    for (const mark of marks) {
      if (!mark?.from || !mark?.to || !mark?.color) continue;
      try {
        const cm = doc.markText(mark.from, mark.to, { css: `background-color: ${mark.color};` });
        cm.__highlightColor = mark.color;
      } catch { /* range no longer in the text */ }
    }
  }

  function currentMarks() {
    return editor.getAllMarks()
      .map(m => { const pos = m.find(); return pos ? { from: pos.from, to: pos.to, color: m.__highlightColor || '#ffff0080' } : null; })
      .filter(Boolean);
  }

  function applyDividers(lines) {
    editor.eachLine(handle => {
      if (handle.__lineDividerActive) { editor.removeLineClass(handle, 'wrap', 'cm-line-divider'); handle.__lineDividerActive = false; }
    });
    for (const lineNo of lines) {
      const handle = editor.getLineHandle(lineNo);
      if (!handle) continue;
      editor.addLineClass(handle, 'wrap', 'cm-line-divider');
      handle.__lineDividerActive = true;
    }
  }

  function currentDividers() {
    const lines = [];
    editor.eachLine(handle => { if (handle.__lineDividerActive) lines.push(editor.getLineNumber(handle)); });
    return lines;
  }

  function colorSelection(color) {
    const doc = editor.getDoc();
    if (!doc.somethingSelected()) return;
    const mark = doc.markText(doc.getCursor('from'), doc.getCursor('to'), { css: `background-color: ${color};` });
    mark.__highlightColor = color;
    dispatch('change', { source: tab, marks: currentMarks() });
  }

  function clearColors() {
    editor.getAllMarks().forEach(m => m.clear());
    dispatch('change', { source: tab, marks: [] });
  }

  onMount(() => {
    editor = CodeMirror.fromTextArea(textarea, { lineNumbers: true, lineWrapping: true, mode: null });
    editor.on('change', (cm) => {
      if (applying) return;
      dispatch('change', { source: tab, text: cm.getValue(), marks: currentMarks(), dividers: currentDividers() });
    });
    editor.on('gutterClick', (cm, lineNo) => {
      const handle = cm.getLineHandle(lineNo);
      if (!handle) return;
      if (handle.__lineDividerActive) { cm.removeLineClass(handle, 'wrap', 'cm-line-divider'); handle.__lineDividerActive = false; }
      else { cm.addLineClass(handle, 'wrap', 'cm-line-divider'); handle.__lineDividerActive = true; }
      dispatch('change', { source: tab, dividers: currentDividers() });
    });
    syncEditor(tab, text);
  });

  onDestroy(() => { if (editor) { editor.toTextArea(); editor = null; } });

  function selectTab(id) {
    if (id === tab) return;
    tab = id;
    showCandidates = false;
    dispatch('tab', { side, tab: id });
  }
</script>

<div class="lyrics-panel lyrics-column" data-side={side}>
  <div class="panel-tabs" role="tablist" aria-label="Lyrics source ({side})">
    {#each tabs as t (t.id)}
      <button role="tab" class="panel-tab" class:active={t.id === tab} aria-selected={t.id === tab}
              on:click={() => selectTab(t.id)}>
        {t.label}{#if busy[t.id]} ⏳{/if}
      </button>
    {/each}
  </div>

  <div class="panel-tools">
    {#if tab === 'lrclib'}
      <div class="tool-row">
        <span class="tool-info">
          {#if busy.lrclib}🔎 Searching LRCLIB…
          {:else if info?.message}{info.message}
          {:else}Lyrics published online (lrclib.net), found by artist and title.{/if}
        </span>
        <button class="btn btn-secondary small" on:click={() => dispatch('search')} disabled={disabled || busy.lrclib || !canSearch}
                title="Search lrclib.net by artist and title">🔎 Search</button>
      </div>
      {#if candidates.length > 1 || (candidates.length && chosenCandidateId === null)}
        <button class="link-btn" on:click={() => showCandidates = !showCandidates}>
          {showCandidates ? 'Hide versions' : chosenCandidateId === null ? `Choose from ${candidates.length} suggestions` : `Choose another version (${candidates.length - 1})`}
        </button>
      {/if}
      {#if showCandidates}
        <ul class="lyrics-candidates">
          {#each candidates as entry (entry.id)}
            <li>
              <button class="lyrics-candidate" class:chosen={entry.id === chosenCandidateId}
                      on:click={() => { showCandidates = false; dispatch('choose', entry); }}>
                <span class="candidate-title">{entry.track} — {entry.artist}</span>
                <span class="candidate-meta">
                  {#if entry.album}{entry.album} · {/if}{formatDuration(entry.duration)}
                  {#if entry.length_match === true}<span class="length-ok" title="Same length as your song ({formatDuration(songDuration)})">✓ same length</span>{/if}
                  {#if entry.length_match === false}<span class="length-off" title="Your song is {formatDuration(songDuration)}">other length</span>{/if}
                  · {entry.lines} lines{entry.synced ? ' · synced' : ''}
                </span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    {:else}
      <div class="tool-row">
        <span class="tool-info">
          {#if info?.message}{info.message}
          {:else if tab === 'cleaned'}Whisper listens to the cleaned vocals (your Step 4 cleanup).
          {:else}Whisper listens to the vocals and writes down what it hears.{/if}
        </span>
        <button class="btn btn-transcribe small" on:click={() => dispatch('transcribe', { source: tab })}
                disabled={disabled || busy[tab]}>
          🎙️ {text.trim() ? 'Listen again' : 'Extract lyrics'}
        </button>
      </div>
    {/if}
  </div>

  <textarea bind:this={textarea} rows="15" aria-label="Lyrics ({side}, {tab})"></textarea>

  <div class="color-controls">
    <button class="color-btn yellow" on:click={() => colorSelection('#ffff0080')} title="Highlight in yellow">🟨</button>
    <button class="color-btn red" on:click={() => colorSelection('#ff000080')} title="Highlight in red">🟥</button>
    <button class="color-btn green" on:click={() => colorSelection('#00ff0080')} title="Highlight in green">🟩</button>
    <button class="color-btn blue" on:click={() => colorSelection('#0000ff80')} title="Highlight in blue">🟦</button>
    <button class="color-btn clear" on:click={clearColors} title="Clear all colors">⚪ Clear</button>
  </div>

  <button class="btn btn-primary btn-generate panel-generate" on:click={() => dispatch('generate', { side, source: tab })}
          disabled={disabled || !canGenerate || !text.trim()} title={generateHint}>
    🚀 Generate UltraStar file
  </button>
  {#if generateHint && !disabled}<p class="generate-hint">{generateHint}</p>{/if}
</div>

<style>
  .lyrics-panel { display: flex; flex-direction: column; gap: 0.5rem; min-width: 0; }
  .panel-tabs { display: flex; gap: 0.25rem; border-bottom: 1px solid #333; }
  .panel-tab {
    background: transparent; color: #999; border: none; border-bottom: 2px solid transparent;
    padding: 0.45rem 0.75rem; cursor: pointer; font-size: 0.9rem;
  }
  .panel-tab:hover { color: #ddd; }
  .panel-tab.active { color: #4fc3f7; border-bottom-color: #4fc3f7; font-weight: 600; }
  .panel-tools { display: flex; flex-direction: column; gap: 0.35rem; min-height: 2.4rem; }
  .tool-row { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
  .tool-info { color: #999; font-size: 0.82rem; }
  .lyrics-candidates {
    list-style: none; margin: 0; padding: 0; max-height: 220px; overflow-y: auto;
    border: 1px solid #444; border-radius: 6px;
  }
  .lyrics-candidate {
    display: flex; flex-direction: column; align-items: flex-start; gap: 0.15rem; width: 100%;
    padding: 0.4rem 0.6rem; border: none; border-bottom: 1px solid #333;
    background: transparent; color: inherit; text-align: left; cursor: pointer;
  }
  .lyrics-candidate:hover, .lyrics-candidate:focus-visible { background: rgba(79, 140, 255, 0.15); }
  .lyrics-candidate.chosen { background: rgba(76, 175, 80, 0.18); }
  .candidate-title { font-weight: 600; }
  .candidate-meta { font-size: 0.85em; opacity: 0.8; }
  .length-ok { color: #4caf50; margin-left: 0.25rem; }
  .length-off { color: #e0a030; margin-left: 0.25rem; }
  .link-btn {
    align-self: flex-start; background: none; border: none; color: #4fc3f7; cursor: pointer;
    padding: 0; font-size: 0.82rem; text-decoration: underline;
  }
  .panel-generate { width: 100%; }
  .generate-hint { color: #888; font-size: 0.78rem; margin: 0; }

  /* Same look as the rest of Step 2 (its styles are scoped to it) */
  .btn {
    display: inline-block; padding: 0.75rem 1.5rem; border: none; border-radius: 8px;
    font-size: 0.9rem; cursor: pointer; transition: all 0.2s;
  }
  .btn.small { font-size: 0.8rem; padding: 0.5rem 1rem; }
  .btn-primary { background: #1976d2; color: white; }
  .btn-primary:hover:not(:disabled) { background: #1565c0; }
  .btn-secondary { background: #333; color: #ccc; border: 1px solid #555; }
  .btn-secondary:hover:not(:disabled) { background: #444; }
  .btn-transcribe { background: #6a1b9a; color: white; white-space: nowrap; }
  .btn-transcribe:hover:not(:disabled) { background: #8e24aa; }
  .btn-generate { padding: 0.9rem 2rem; font-size: 1rem; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .color-controls { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .color-btn {
    padding: 0.5rem 0.75rem; border: 1px solid #444; border-radius: 4px; background: #1a1a1a;
    color: #e0e0e0; cursor: pointer; font-size: 1rem; transition: all 0.2s ease; user-select: none;
  }
  .color-btn:hover { border-color: #666; background: #252525; }
  .color-btn:active { transform: scale(0.95); }
  .color-btn.clear { margin-left: auto; background: #2a2a2a; border-color: #555; }
  .color-btn.clear:hover { background: #333; border-color: #777; }
</style>
