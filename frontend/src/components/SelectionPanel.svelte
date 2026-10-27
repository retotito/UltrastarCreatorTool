<script>
  import { onMount } from 'svelte';

  export let count = 0; // total selected notes (0 = hidden)
  export let onDeselect = () => {};
  export let onGoTo = () => {};

  const STORAGE_KEY = 'editor_selection_panel_pos';

  let x = 18;
  let y = null; // will be set on mount (bottom-anchored default)
  let panelEl;
  // x/y are where the user put it (saved); it is shown there, pushed inside the window when that is smaller (after
  // leaving fullscreen), and back at its place when the window is big enough again
  let viewW = window.innerWidth;
  let viewH = window.innerHeight;
  // measured again when the window or the text ("12 notes") changes
  $: panelW = (viewW, count, panelEl?.offsetWidth || 0);
  $: panelH = (viewH, count, panelEl?.offsetHeight || 0);
  $: shownX = Math.max(0, Math.min(viewW - panelW, x));
  $: shownY = Math.max(0, Math.min(viewH - panelH, y ?? 0));

  // Load saved position
  onMount(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const p = JSON.parse(saved);
        x = p.x ?? 18;
        y = p.y ?? null;
      } catch {}
    }
    if (y === null) {
      y = window.innerHeight - 80;
    }
  });

  function savePos() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ x, y }));
  }

  // Drag logic
  let dragging = false;
  let dragMoved = false;
  let dragOffX = 0;
  let dragOffY = 0;

  function onMouseDown(e) {
    // Only drag on the panel background, not on the close button
    if (e.target.closest('.sel-close')) return;
    e.preventDefault();
    e.stopPropagation();
    dragging = true;
    dragMoved = false;
    // Drag from where it is shown (it may be pushed in from its saved place)
    x = shownX;
    y = shownY;
    dragOffX = e.clientX - x;
    dragOffY = e.clientY - y;
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }

  function onMouseMove(e) {
    if (!dragging) return;
    const dx = Math.abs(e.clientX - dragOffX - x);
    const dy = Math.abs(e.clientY - dragOffY - y);
    if (dx > 4 || dy > 4) dragMoved = true;
    // Clamp to viewport
    x = Math.max(0, Math.min(viewW - panelW, e.clientX - dragOffX));
    y = Math.max(0, Math.min(viewH - panelH, e.clientY - dragOffY));
  }

  function onMouseUp() {
    if (!dragging) return;
    const wasClick = !dragMoved;
    dragging = false;
    dragMoved = false;
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
    if (wasClick) {
      onGoTo();
    } else {
      savePos();
    }
  }

  function handleCloseClick(e) {
    e.stopPropagation();
    onDeselect();
  }
</script>

<svelte:window bind:innerWidth={viewW} bind:innerHeight={viewH} />

{#if count > 0}
  <div
    class="selection-panel"
    class:dragging
    style="left:{shownX}px; top:{shownY}px;"
    bind:this={panelEl}
    on:mousedown|stopPropagation={onMouseDown}
    on:click|stopPropagation={() => {}}
  >
    <span class="sel-label">{count === 1 ? '1 note selected' : `${count} notes selected`}</span>
    <button class="sel-close" on:click={handleCloseClick} title="Deselect (Esc)">✕</button>
  </div>
{/if}

<style>
  .selection-panel {
    position: fixed;
    z-index: 1001; /* above ctx-overlay (999) and context-menu (1000) */
    display: flex;
    align-items: center;
    gap: 10px;
    background: rgba(40, 30, 5, 0.93);
    border: 1px solid rgba(255, 200, 40, 0.55);
    border-radius: 8px;
    padding: 7px 36px 7px 12px;
    color: #ffd54f;
    font-size: 0.8rem;
    white-space: nowrap;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
    cursor: grab;
    user-select: none;
    pointer-events: all;
  }
  .selection-panel.dragging {
    cursor: grabbing;
    opacity: 0.9;
  }
  .sel-label {
    font-weight: 600;
    color: #ffe082;
  }
  .sel-close {
    position: absolute;
    top: 50%;
    right: 6px;
    transform: translateY(-50%);
    background: none;
    border: none;
    color: #a08040;
    cursor: pointer;
    font-size: 1.1rem;
    line-height: 1;
    padding: 4px 6px;
  }
  .sel-close:hover {
    color: #ef9a9a;
  }
</style>
