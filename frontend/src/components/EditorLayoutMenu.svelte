<script>
  /**
   * The top bar's layout menu in the editor: which toolbar controls to show. Saved for the whole app, since it depends
   * on the screen and not the song.
   */
  import { onDestroy } from 'svelte';
  import { editorLayoutOpen, hiddenEditorTools } from '../stores/appStore.js';
  import { EDITOR_TOOLS, toggledTools } from '../lib/editorTools.js';

  let root;

  function onWindowClick(e) {
    if ($editorLayoutOpen && root && !root.contains(e.target)) editorLayoutOpen.set(false);
  }

  function onKey(e) {
    if ($editorLayoutOpen && e.key === 'Escape') editorLayoutOpen.set(false);
  }

  onDestroy(() => editorLayoutOpen.set(false));
</script>

<svelte:window on:click={onWindowClick} on:keydown={onKey} />

<div class="layout-root" bind:this={root}>
  <button class="layout-btn" class:open={$editorLayoutOpen} on:click={() => editorLayoutOpen.update(open => !open)}
    title="Toolbar layout: choose which tools to show" aria-expanded={$editorLayoutOpen}>🎛️</button>
  {#if $editorLayoutOpen}
    <div class="layout-menu" role="dialog" aria-label="Toolbar layout">
      <div class="layout-head">
        <strong>Toolbar</strong>
        <button class="layout-all" disabled={$hiddenEditorTools.size === 0} on:click={() => hiddenEditorTools.set(new Set())}>Show all</button>
      </div>
      {#each EDITOR_TOOLS as group}
        <div class="layout-group">{group.heading}</div>
        {#each group.tools as tool}
          <label>
            <input type="checkbox" checked={!$hiddenEditorTools.has(tool.id)}
              on:change={() => hiddenEditorTools.update(hidden => toggledTools(hidden, tool.id))} />
            {tool.label}
          </label>
        {/each}
      {/each}
      <p class="layout-hint">Shortcuts keep working. A tool in use stays visible.</p>
    </div>
  {/if}
</div>

<style>
  .layout-root { position: relative; display: inline-flex; }
  .layout-btn {
    background: none; border: 1px solid transparent; border-radius: 6px; font-size: 1.1rem; cursor: pointer;
    padding: 0.2rem 0.35rem; line-height: 1; color: #888; transition: background 0.15s, border-color 0.15s;
  }
  .layout-btn:hover, .layout-btn.open { background: #1e2040; border-color: #333; color: #ccc; }
  .layout-menu {
    position: absolute; top: calc(100% + 6px); right: 0; z-index: 1000; width: 250px; max-height: calc(100vh - 70px);
    overflow-y: auto; overscroll-behavior: contain; padding: 0.7rem 0.85rem; display: flex; flex-direction: column;
    gap: 0.3rem; background: #1a1a2a; border: 1px solid #333; border-radius: 10px; color: #e0e0e0; font-size: 0.85rem;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5);
  }
  .layout-head { display: flex; align-items: center; justify-content: space-between; }
  .layout-all { background: #333; color: #e0e0e0; border: none; border-radius: 6px; padding: 0.2rem 0.55rem; font-size: 0.75rem; cursor: pointer; }
  .layout-all:hover:not(:disabled) { background: #444; }
  .layout-all:disabled { opacity: 0.5; cursor: default; }
  .layout-group { margin-top: 0.45rem; color: #888; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }
  label { display: flex; align-items: center; gap: 0.45rem; cursor: pointer; }
  .layout-hint { margin: 0.5rem 0 0; color: #888; font-size: 0.72rem; }
</style>
