<script>
  /**
   * Cmd/Ctrl+A in a duet: which notes to select. The singer you edit is checked at first; the other singer and the
   * synced (linked) notes can be added. Each note is selected once, so an edit moves it once. Enter applies, Esc
   * cancels.
   */
  import { createEventDispatcher, onMount } from 'svelte';
  import { SINGER_COLORS } from '../lib/duet.js';

  export let active = 1;
  export let names = { p1: 'Singer 1', p2: 'Singer 2' };
  export let counts = { 1: 0, 2: 0, both: 0 };
  export let choice = { active: true, other: false, synced: false };

  const dispatch = createEventDispatcher();
  const otherSinger = active === 1 ? 2 : 1;
  const name = s => (s === 1 ? names.p1 : names.p2);
  let applyBtn;

  $: none = !choice.active && !choice.other && !choice.synced;

  function apply() {
    if (!none) dispatch('apply', { ...choice });
  }

  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); dispatch('close'); }
    else if (e.key === 'Enter') { e.preventDefault(); apply(); }
  }

  onMount(() => applyBtn?.focus());
</script>

<svelte:window on:keydown={onKey} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="sa-backdrop" on:click={() => dispatch('close')}>
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="sa-modal" on:click|stopPropagation role="dialog" aria-label="Select all">
    <h2>Select all</h2>
    <label>
      <input type="checkbox" bind:checked={choice.active} />
      <span class="dot" style="background:{SINGER_COLORS[active]}"></span>
      {name(active)} <span class="sa-note">(editing) · {counts[active]}</span>
    </label>
    <label>
      <input type="checkbox" bind:checked={choice.other} />
      <span class="dot" style="background:{SINGER_COLORS[otherSinger]}"></span>
      {name(otherSinger)} <span class="sa-note">· {counts[otherSinger]}</span>
    </label>
    <label>
      <input type="checkbox" bind:checked={choice.synced} />
      <span class="dot both" style="--a:{SINGER_COLORS[1]}; --b:{SINGER_COLORS[2]}"></span>
      Synced notes <span class="sa-note">· {counts.both}</span>
    </label>
    <p class="sa-hint">Synced notes belong to both singers: an edit changes them for both.</p>
    <div class="sa-actions">
      <button class="btn btn-secondary" on:click={() => dispatch('close')}>Cancel</button>
      <button class="btn btn-primary" bind:this={applyBtn} disabled={none} on:click={apply}>Apply</button>
    </div>
  </div>
</div>

<style>
  .sa-backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5); z-index: 1000;
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }
  .sa-modal {
    background: #1a1a2a; border: 1px solid #333; border-radius: 10px; width: min(340px, 100%); padding: 1.1rem 1.25rem;
    display: flex; flex-direction: column; gap: 0.55rem; color: #e0e0e0; font-size: 0.9rem;
  }
  h2 { margin: 0 0 0.2rem; font-size: 1.05rem; }
  label { display: flex; align-items: center; gap: 0.45rem; cursor: pointer; }
  .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; }
  .dot.both { background: linear-gradient(90deg, var(--a) 50%, var(--b) 50%); }
  .sa-note { color: #888; font-size: 0.8rem; }
  .sa-hint { margin: 0.2rem 0 0; color: #999; font-size: 0.78rem; }
  .sa-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.3rem; }
  .btn { padding: 0.5rem 1.1rem; border: none; border-radius: 8px; font-size: 0.85rem; cursor: pointer; }
  .btn-primary { background: #1976d2; color: white; }
  .btn-primary:hover:not(:disabled) { background: #1565c0; }
  .btn-secondary { background: #333; color: #e0e0e0; }
  .btn-secondary:hover { background: #444; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
