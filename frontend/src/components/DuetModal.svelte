<script>
  /**
   * The editor's Duet dialog (docs/plans/duets.md). A solo chart: "Set as duet" with the singers' names (every note
   * starts as sung by both). A duet: rename the singers, swap them, or unset the duet keeping one singer (the other
   * singer's notes are deleted; the linked ones stay).
   */
  import { createEventDispatcher } from 'svelte';
  import { SINGER_COLORS } from '../lib/duet.js';

  export let isDuet = false;
  export let names = { p1: 'Singer 1', p2: 'Singer 2' };
  export let counts = { 1: 0, 2: 0, both: 0 };   // notes per singer (a duet)

  const dispatch = createEventDispatcher();
  let p1 = names.p1;
  let p2 = names.p2;
  let unsetting = false;   // "which singer do you keep?" shown
  let keep = 1;

  $: cleanNames = { p1: p1.trim() || 'Singer 1', p2: p2.trim() || 'Singer 2' };
  $: renamed = cleanNames.p1 !== names.p1 || cleanNames.p2 !== names.p2;
  $: dropped = keep === 1 ? counts[2] : counts[1];

  function onKey(e) {
    if (e.key === 'Escape') dispatch('close');
  }
</script>

<svelte:window on:keydown={onKey} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="duet-backdrop" on:click={() => dispatch('close')}>
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
  <div class="duet-modal" on:click|stopPropagation role="dialog" aria-label="Duet">
    <h2>🎤 Duet</h2>
    {#if !isDuet}
      <p class="duet-hint">Two singers in this song. Every note starts as sung by both; then select notes and give
        them to one singer with the right-click menu.</p>
    {:else}
      <p class="duet-hint">{counts[1]} notes for {names.p1}, {counts[2]} for {names.p2}, {counts.both} sung by both.</p>
    {/if}

    <div class="duet-fields">
      <label>
        <span><span class="dot" style="background:{SINGER_COLORS[1]}"></span> Singer 1</span>
        <input bind:value={p1} placeholder="Singer 1" />
      </label>
      {#if isDuet}
        <button class="swap-btn" on:click={() => dispatch('swap')}
          title="Singer 1 becomes singer 2 and the other way round: names and notes">⇄</button>
      {/if}
      <label>
        <span><span class="dot" style="background:{SINGER_COLORS[2]}"></span> Singer 2</span>
        <input bind:value={p2} placeholder="Singer 2" />
      </label>
    </div>

    {#if isDuet && unsetting}
      <div class="duet-unset">
        <p>Which singer do you keep? The song becomes a solo chart.</p>
        <label><input type="radio" bind:group={keep} value={1} /> {names.p1}</label>
        <label><input type="radio" bind:group={keep} value={2} /> {names.p2}</label>
        <p class="duet-warning">The other singer's {dropped} {dropped === 1 ? 'note is' : 'notes are'} deleted. The
          {counts.both} notes sung by both stay. (Undo brings them back.)</p>
      </div>
    {/if}

    <div class="duet-actions">
      {#if !isDuet}
        <button class="btn btn-secondary" on:click={() => dispatch('close')}>Cancel</button>
        <button class="btn btn-primary" on:click={() => dispatch('set', cleanNames)}>Set as duet</button>
      {:else if unsetting}
        <button class="btn btn-secondary" on:click={() => (unsetting = false)}>Back</button>
        <button class="btn btn-danger" on:click={() => dispatch('unset', { keep })}>Unset duet</button>
      {:else}
        <button class="btn btn-secondary btn-left" on:click={() => (unsetting = true)}>Unset duet…</button>
        <button class="btn btn-secondary" on:click={() => dispatch('close')}>Close</button>
        <button class="btn btn-primary" disabled={!renamed} on:click={() => dispatch('rename', cleanNames)}>Save names</button>
      {/if}
    </div>
  </div>
</div>

<style>
  .duet-backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); z-index: 1000; overscroll-behavior: contain;
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }
  .duet-modal {
    background: #1a1a2a; border: 1px solid #333; border-radius: 10px; width: min(520px, 100%); max-height: 88vh;
    overflow-y: auto; display: flex; flex-direction: column; gap: 0.7rem; padding: 1.25rem; color: #e0e0e0;
  }
  h2 { margin: 0; font-size: 1.15rem; }
  .duet-hint { margin: 0; color: #999; font-size: 0.82rem; }
  .duet-fields { display: flex; gap: 0.5rem; align-items: flex-end; flex-wrap: wrap; }
  .duet-fields label { flex: 1 1 180px; display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.82rem; color: #aaa; }
  .duet-fields input {
    background: #11111d; color: #e0e0e0; border: 1px solid #333; border-radius: 6px; padding: 0.5rem 0.6rem; font-size: 0.95rem;
  }
  .duet-fields input:focus { outline: none; border-color: #1976d2; }
  .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 3px; }
  .swap-btn {
    background: #262636; color: #ccc; border: 1px solid #444; border-radius: 6px; padding: 0.45rem 0.6rem;
    cursor: pointer; font-size: 1rem; margin-bottom: 1px;
  }
  .swap-btn:hover { background: #303045; }
  .duet-unset { background: #221a1a; border: 1px solid #553; border-radius: 8px; padding: 0.6rem 0.8rem; font-size: 0.88rem; }
  .duet-unset p { margin: 0 0 0.4rem; }
  .duet-unset label { display: block; margin: 0.2rem 0; cursor: pointer; }
  .duet-warning { color: #e0a030; margin-top: 0.5rem !important; }
  .duet-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.25rem; }
  .btn-left { margin-right: auto; }
  .btn { padding: 0.6rem 1.2rem; border: none; border-radius: 8px; font-size: 0.9rem; cursor: pointer; }
  .btn-primary { background: #1976d2; color: white; }
  .btn-primary:hover:not(:disabled) { background: #1565c0; }
  .btn-secondary { background: #333; color: #e0e0e0; }
  .btn-secondary:hover:not(:disabled) { background: #444; }
  .btn-danger { background: #c62828; color: white; }
  .btn-danger:hover { background: #b71c1c; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
