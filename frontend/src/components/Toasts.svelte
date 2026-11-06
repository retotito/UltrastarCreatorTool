<script>
  /**
   * Errors and status messages (errorMessage, processingStatus) at the top of the window, where they are seen whatever the
   * page's scroll position. An error stays until closed, the next action clears it or the step changes; a status message
   * goes by itself, and waits while the work it describes is running (a busy window shows that).
   */
  import { onDestroy } from 'svelte';
  import { currentStep, errorMessage, isProcessing, processingStatus } from '../stores/appStore.js';

  const STATUS_SEC = 4;
  let shownStatus = '';
  let timer = null;

  $: if ($processingStatus && !$isProcessing) showStatus($processingStatus);

  function showStatus(text) {
    shownStatus = text;
    processingStatus.set('');
    clearTimeout(timer);
    timer = setTimeout(() => { shownStatus = ''; }, STATUS_SEC * 1000);
  }

  let step = $currentStep;
  $: if ($currentStep !== step) {
    step = $currentStep;
    errorMessage.set('');
  }

  onDestroy(() => clearTimeout(timer));
</script>

{#if $errorMessage || shownStatus}
  <div class="toasts">
    {#if $errorMessage}
      <div class="toast toast-error" role="alert">
        <span>❌ {$errorMessage}</span>
        <button on:click={() => errorMessage.set('')} aria-label="Close">✕</button>
      </div>
    {/if}
    {#if shownStatus}
      <div class="toast toast-status" role="status">{shownStatus}</div>
    {/if}
  </div>
{/if}

<style>
  .toasts {
    position: fixed; top: 64px; left: 50%; transform: translateX(-50%); z-index: 10000;
    display: flex; flex-direction: column; align-items: center; gap: 0.5rem; width: min(640px, calc(100vw - 32px));
    pointer-events: none;
  }
  .toast {
    pointer-events: auto; display: flex; align-items: flex-start; gap: 0.75rem; max-height: 40vh; overflow-y: auto;
    padding: 0.6rem 0.9rem; border-radius: 8px; font-size: 0.9rem; line-height: 1.35; overflow-wrap: anywhere;
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.5); animation: toast-in 0.18s ease;
  }
  .toast-error { background: #3a1518; border: 1px solid #ef5350; color: #ffcdd2; }
  .toast-status { background: #15302a; border: 1px solid #4caf7d; color: #c8e6d4; }
  button { background: none; border: none; color: inherit; cursor: pointer; font-size: 0.9rem; padding: 0 0.1rem; }
  button:hover { color: #fff; }
  @keyframes toast-in { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: none; } }
</style>
