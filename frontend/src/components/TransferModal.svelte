<script>
  /**
   * The busy window for uploads and downloads (Step 1, the import panel): spinner, status, progress and Cancel. It
   * blocks the page until the transfer is done or cancelled.
   */
  import { createEventDispatcher } from 'svelte';

  export let title = '';
  export let status = '';
  export let percent = null;   // null: no percentage yet, an indeterminate bar

  const dispatch = createEventDispatcher();
</script>

<div class="transfer-backdrop">
  <div class="transfer-modal" role="alertdialog" aria-modal="true" aria-labelledby="transfer-title" aria-busy="true">
    <span class="transfer-spinner" aria-hidden="true"></span>
    <h2 id="transfer-title">{title}</h2>
    <p class="transfer-status">{status}{percent !== null ? ` ${percent}%` : ''}</p>
    {#if percent !== null}
      <progress max="100" value={percent}></progress>
    {:else}
      <progress></progress>
    {/if}
    <button class="transfer-cancel" on:click={() => dispatch('cancel')}>Cancel</button>
  </div>
</div>

<style>
  .transfer-backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); z-index: 1000; overscroll-behavior: contain;
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }
  .transfer-modal {
    background: #1a1a2a; border: 1px solid #333; border-radius: 10px; width: min(420px, 100%); padding: 1.5rem;
    display: flex; flex-direction: column; align-items: center; gap: 0.75rem; color: #e0e0e0;
  }
  h2 { margin: 0; font-size: 1.1rem; }
  progress { width: 100%; height: 6px; }
  .transfer-status { color: #4fc3f7; font-size: 0.85rem; margin: 0; text-align: center; min-height: 1.2em; }
  .transfer-spinner {
    width: 32px; height: 32px; border: 3px solid #333; border-top-color: #4fc3f7; border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .transfer-cancel {
    background: #333; color: #e0e0e0; padding: 0.5rem 1.2rem; border: none; border-radius: 8px; font-size: 0.85rem;
    cursor: pointer;
  }
  .transfer-cancel:hover { background: #444; }
</style>
