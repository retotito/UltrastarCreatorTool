<script>
  /**
   * One side of Step 2: tabs for the lyric sources (LRCLIB, vocals, cleaned vocals), the tools of the
   * selected source, its text, and "Generate UltraStar file". Each side has its own texts (`sources`, kept in
   * Step 2), so the two sides can be compared and edited independently.
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
  /** LRCLIB: how many versions there are, and whether one of them fills the tab */
  export let versionsCount = 0;
  export let chosen = false;
  export let canGenerate = false;
  export let generateHint = '';
  export let disabled = false;

  const dispatch = createEventDispatcher();
  let textarea;
  let editor = null;
  let shownTab = null;
  let applying = false;

  $: source = sources[tab] || { text: '' };
  $: text = source.text || '';
  $: info = source.info || null;
  $: if (editor) syncEditor(tab, text);

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

  function addMark(from, to, color) {
    const mark = editor.getDoc().markText(from, to, { css: `background-color: ${color};` });
    mark.__highlightColor = color;
  }

  /** Remove the highlights between `from` and `to`; parts of a highlight outside that range stay. */
  function uncolorRange(from, to) {
    const cmp = CodeMirror.cmpPos;
    for (const mark of editor.getAllMarks()) {
      const pos = mark.find();
      if (!pos || cmp(pos.to, from) <= 0 || cmp(pos.from, to) >= 0) continue; // doesn't overlap
      const color = mark.__highlightColor || '#ffff0080';
      mark.clear();
      if (cmp(pos.from, from) < 0) addMark(pos.from, from, color);
      if (cmp(pos.to, to) > 0) addMark(to, pos.to, color);
    }
  }

  function colorSelection(color) {
    const doc = editor.getDoc();
    if (!doc.somethingSelected()) return;
    const from = doc.getCursor('from');
    const to = doc.getCursor('to');
    uncolorRange(from, to); // replace, don't stack colours
    addMark(from, to, color);
    dispatch('change', { source: tab, marks: currentMarks() });
  }

  /** Remove the colour from the selection, or the whole highlight under the cursor when nothing is selected. */
  function uncolorSelection() {
    const doc = editor.getDoc();
    if (doc.somethingSelected()) {
      uncolorRange(doc.getCursor('from'), doc.getCursor('to'));
    } else {
      const cursor = doc.getCursor();
      for (const mark of doc.findMarksAt(cursor)) mark.clear();
    }
    dispatch('change', { source: tab, marks: currentMarks() });
    editor.focus();
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
    dispatch('tab', { side, tab: id });
  }
</script>

<div class="lyrics-panel lyrics-column" data-side={side}>
  <div class="panel-tabs" role="tablist" aria-label="Lyrics source ({side})">
    {#each tabs as t (t.id)}
      <button role="tab" class="panel-tab" class:active={t.id === tab} aria-selected={t.id === tab}
              on:click={() => selectTab(t.id)}>
        {t.label}{#if busy[t.id]} <span class="spinner small" aria-label="working"></span>{/if}
      </button>
    {/each}
  </div>

  <div class="panel-tools">
    {#if tab === 'lrclib'}
      <span class="tool-info">
        {#if busy.lrclib}<span class="spinner" aria-hidden="true"></span> Searching LRCLIB…
        {:else if info?.message}{info.message}
        {:else}Lyrics published online (lrclib.net): search to load a version into this side.{/if}
      </span>
      <button class="link-btn" on:click={() => dispatch('versions')} disabled={disabled || busy.lrclib}>
        {chosen && versionsCount > 1 ? `Choose another version (${versionsCount - 1})` : 'Search LRCLIB…'}
      </button>
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
    <button class="color-btn eraser" on:click={uncolorSelection}
            title="Remove the colour from the selected text (or from the highlight at the cursor)">🧽 Remove colour</button>
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
  .spinner {
    display: inline-block; width: 0.85em; height: 0.85em; vertical-align: -0.1em;
    border: 2px solid rgba(79, 195, 247, 0.3); border-top-color: #4fc3f7; border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  .spinner.small { width: 0.7em; height: 0.7em; border-width: 1.5px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .panel-tab.active { color: #4fc3f7; border-bottom-color: #4fc3f7; font-weight: 600; }
  /* Same height on every tab, so both text fields start at the same line and can be compared. */
  .panel-tools { display: flex; flex-direction: column; justify-content: center; gap: 0.25rem; height: 4.2rem; overflow: hidden; }
  .tool-info { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .tool-row { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
  .tool-info { color: #999; font-size: 0.82rem; }
  .link-btn:disabled { opacity: 0.5; cursor: not-allowed; }
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
  .color-btn.eraser { margin-left: auto; font-size: 0.85rem; }
</style>
