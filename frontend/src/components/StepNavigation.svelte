<script>
  import { currentStep, steps, canGoToStep, uploadData } from '../stores/appStore.js';

  export let backendStatus = 'checking';
  export let goHome = () => {};

  let showNoAudioWarning = false;
  let pendingStep = null;

  function goToStep(num) {
    if (!$canGoToStep(num)) return;

    // Warn before entering Step 4 if no audio files are present
    if (num === 4 && !$uploadData.hasVocals && !$uploadData.hasOriginal) {
      pendingStep = num;
      showNoAudioWarning = true;
      return;
    }

    currentStep.set(num);
  }

  function confirmGoToStep() {
    showNoAudioWarning = false;
    if (pendingStep !== null) {
      currentStep.set(pendingStep);
      pendingStep = null;
    }
  }

  function goToStep1() {
    showNoAudioWarning = false;
    pendingStep = null;
    currentStep.set(1);
  }
</script>

<div class="topbar">
  <div class="topbar-left">
    <button class="home-btn" on:click={goHome} title="Back to Home">🏠</button>
  </div>

  <nav class="step-nav">
    {#each steps as step}
      <button
        class="step-btn"
        class:active={$currentStep === step.num}
        class:completed={$currentStep > step.num}
        class:disabled={!$canGoToStep(step.num)}
        on:click={() => goToStep(step.num)}
        disabled={!$canGoToStep(step.num)}
      >
        <span class="step-icon">{step.icon}</span>
        <span class="step-label">{step.label}</span>
      </button>
      {#if step.num < steps[steps.length - 1].num}
        <div class="step-line" class:active={$currentStep > step.num}></div>
      {/if}
    {/each}
  </nav>

  <div class="topbar-right">
    <div class="backend-status" class:online={backendStatus === 'ok'} class:offline={backendStatus === 'offline'}>
      <span class="status-dot"></span>
      {#if backendStatus === 'ok'}
        Backend online
      {:else if backendStatus === 'offline'}
        Backend offline
      {:else}
        Checking…
      {/if}
    </div>
  </div>
</div>

<!--
<div class="step-actions">
  <button
    class="nav-btn prev"
    on:click={() => goToStep($currentStep - 1)}
    disabled={$currentStep <= 1}
  >
    ← Back
  </button>
  <span class="step-indicator">Step {$currentStep} of {steps.length}</span>
  <button
    class="nav-btn next"
    on:click={() => goToStep($currentStep + 1)}
    disabled={!$canGoToStep($currentStep + 1)}
  >
    Next →
  </button>
</div>
-->

{#if showNoAudioWarning}
  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
  <div class="modal-overlay" on:click={() => showNoAudioWarning = false} role="dialog" aria-label="No audio warning" tabindex="-1">
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
    <div class="modal-box" on:click|stopPropagation role="document">
      <div class="modal-icon">⚠️</div>
      <h3>No Audio Files Found</h3>
      <p>
        The Piano Roll Editor requires an audio file to play back.
      </p>
      <div class="modal-actions">
        <button class="btn-secondary" on:click={goToStep1}>← Go to Step 1</button>
      </div>
    </div>
  </div>
{/if}

<style>
  /* ── Top bar ── */
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #111827;
    border-bottom: 1px solid #1e293b;
    padding: 0 1rem;
    height: 52px;
    position: sticky;
    top: 0;
    z-index: 100;
  }

  .topbar-left {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-width: 160px;
  }

  .home-btn {
    background: none;
    border: 1px solid #2d3748;
    border-radius: 8px;
    font-size: 1rem;
    cursor: pointer;
    padding: 0.25rem 0.5rem;
    color: #94a3b8;
    transition: all 0.15s;
    line-height: 1;
  }
  .home-btn:hover {
    background: #1e2d40;
    border-color: #4fc3f7;
    color: #e2e8f0;
  }

  .app-name {
    font-size: 0.85rem;
    font-weight: 600;
    color: #4fc3f7;
    white-space: nowrap;
    letter-spacing: 0.01em;
  }

  /* ── Step nav (centered) ── */
  .step-nav {
    display: flex;
    align-items: center;
    gap: 0;
  }

  .step-btn {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.75rem;
    border: 1px solid transparent;
    border-radius: 8px;
    background: none;
    color: #64748b;
    cursor: pointer;
    transition: all 0.15s;
    font-size: 0.8rem;
    white-space: nowrap;
  }
  .step-btn:hover:not(.disabled) {
    background: #1e293b;
    color: #cbd5e1;
  }
  .step-btn.active {
    background: #0f2744;
    border-color: #4fc3f7;
    color: #4fc3f7;
  }
  .step-btn.completed {
    color: #4ade80;
  }
  .step-btn.completed:hover:not(.disabled) {
    background: #0f2a1a;
  }
  .step-btn.disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .step-icon {
    font-size: 1rem;
  }

  .step-label {
    font-weight: 500;
  }

  .step-line {
    width: 20px;
    height: 1px;
    background: #2d3748;
    flex-shrink: 0;
    margin: 0 2px;
    transition: background 0.2s;
  }
  .step-line.active {
    background: #4ade80;
  }

  /* ── Right side status ── */
  .topbar-right {
    min-width: 160px;
    display: flex;
    justify-content: flex-end;
  }

  .backend-status {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 0.72rem;
    color: #475569;
    white-space: nowrap;
  }
  .backend-status.online { color: #4ade80; }
  .backend-status.offline { color: #f87171; }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex-shrink: 0;
  }
  .backend-status.online .status-dot { animation: pulse-dot 2s ease-in-out infinite; }
  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  /* ── No audio warning modal ── */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.65);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2000;
  }

  .modal-box {
    background: #161b22;
    border: 1px solid #f57c00;
    border-radius: 12px;
    padding: 2rem;
    max-width: 420px;
    width: 90%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    text-align: center;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.7);
  }

  .modal-icon {
    font-size: 2.5rem;
  }

  .modal-box h3 {
    color: #ffa726;
    margin: 0;
    font-size: 1.2rem;
  }

  .modal-box p {
    color: #ccc;
    font-size: 0.9rem;
    line-height: 1.5;
    margin: 0;
  }

  .modal-actions {
    display: flex;
    gap: 0.75rem;
    margin-top: 0.5rem;
    flex-wrap: wrap;
    justify-content: center;
  }

  .btn-secondary {
    padding: 0.5rem 1.2rem;
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 8px;
    color: #ccc;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn-secondary:hover { background: #30363d; }
</style>
