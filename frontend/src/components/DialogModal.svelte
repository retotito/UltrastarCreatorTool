<script>
  import { dialog } from '../stores/dialogStore.js';

  function handleConfirm() {
    const d = $dialog;
    dialog.set(null);
    d.resolve(true);
  }

  function handleCancel() {
    const d = $dialog;
    dialog.set(null);
    d.resolve(false);
  }

  function handleAlert() {
    const d = $dialog;
    dialog.set(null);
    d.resolve();
  }

  function handleKeydown(e) {
    if (!$dialog) return;
    if (e.key === 'Escape') {
      if ($dialog.type === 'alert') handleAlert();
      else handleCancel();
    }
    if (e.key === 'Enter') {
      if ($dialog.type === 'alert') handleAlert();
      else handleConfirm();
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if $dialog}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="overlay" on:click|self={() => { if ($dialog.type === 'alert') handleAlert(); else handleCancel(); }}>
    <div class="modal" role="dialog" aria-modal="true">
      {#if $dialog.title}
        <h3 class="modal-title">{$dialog.title}</h3>
      {/if}
      <p class="modal-message">{$dialog.message}</p>
      <div class="modal-actions">
        {#if $dialog.type === 'alert'}
          <button class="btn btn-primary" on:click={handleAlert}>{$dialog.label}</button>
        {:else}
          <button class="btn btn-cancel" on:click={handleCancel}>{$dialog.cancelLabel}</button>
          <button class="btn" class:btn-danger={$dialog.danger} class:btn-primary={!$dialog.danger} on:click={handleConfirm}>
            {$dialog.confirmLabel}
          </button>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    backdrop-filter: blur(2px);
  }

  .modal {
    background: #1a1f2e;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.5rem 2rem;
    max-width: 420px;
    width: 90%;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  }

  .modal-title {
    margin: 0 0 0.75rem;
    font-size: 1rem;
    font-weight: 600;
    color: #e0e0e0;
  }

  .modal-message {
    margin: 0 0 1.5rem;
    color: #aaa;
    font-size: 0.92rem;
    line-height: 1.5;
    white-space: pre-wrap;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
  }

  .btn {
    padding: 0.45rem 1.2rem;
    border-radius: 8px;
    font-size: 0.9rem;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s;
  }

  .btn-cancel {
    background: transparent;
    border-color: #444;
    color: #aaa;
  }

  .btn-cancel:hover {
    border-color: #666;
    color: #e0e0e0;
  }

  .btn-primary {
    background: #1e88e5;
    color: #fff;
    border-color: #1e88e5;
  }

  .btn-primary:hover {
    background: #1565c0;
  }

  .btn-danger {
    background: #c62828;
    color: #fff;
    border-color: #c62828;
  }

  .btn-danger:hover {
    background: #b71c1c;
  }
</style>
