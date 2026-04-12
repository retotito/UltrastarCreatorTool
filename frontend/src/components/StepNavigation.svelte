<script>
  import { currentStep, steps, canGoToStep, uploadData } from '../stores/appStore.js';

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
      <span class="step-num">{step.num}</span>
      <span class="step-label">{step.label}</span>
    </button>
    {#if step.num < steps.length}
      <div class="step-line" class:active={$currentStep > step.num}></div>
    {/if}
  {/each}
</nav>

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
  .step-nav {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    margin: 1.5rem 0;
    padding: 0 1rem;
  }

  .step-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.25rem;
    padding: 0.75rem 1rem;
    border: 2px solid #333;
    border-radius: 12px;
    background: #1a1a2e;
    color: #888;
    cursor: pointer;
    transition: all 0.2s;
    min-width: 80px;
  }

  .step-btn:hover:not(.disabled) {
    border-color: #555;
    color: #ccc;
  }

  .step-btn.active {
    border-color: #4fc3f7;
    color: #4fc3f7;
    background: #1a2e4a;
  }

  .step-btn.completed {
    border-color: #66bb6a;
    color: #66bb6a;
    background: #1a3a2a;
  }

  .step-btn.disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .step-icon {
    font-size: 1.4rem;
  }

  .step-num {
    font-size: 0.7rem;
    opacity: 0.6;
  }

  .step-label {
    font-size: 0.8rem;
    font-weight: 600;
  }

  .step-line {
    width: 30px;
    height: 2px;
    background: #333;
    transition: background 0.2s;
  }

  .step-line.active {
    background: #66bb6a;
  }

  .step-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 1rem 0;
    padding: 0 1rem;
  }

  .nav-btn {
    padding: 0.5rem 1.5rem;
    border: 1px solid #444;
    border-radius: 8px;
    background: #1a1a2e;
    color: #ccc;
    cursor: pointer;
    font-size: 0.9rem;
    transition: all 0.2s;
  }

  .nav-btn:hover:not(:disabled) {
    background: #2a2a4e;
    border-color: #666;
  }

  .nav-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .step-indicator {
    color: #888;
    font-size: 0.85rem;
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

  .modal-hint {
    color: #aaa !important;
    font-size: 0.82rem !important;
  }

  .modal-hint strong {
    color: #4fc3f7;
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

  .btn-primary {
    padding: 0.5rem 1.2rem;
    background: #7a3e00;
    border: 1px solid #f57c00;
    border-radius: 8px;
    color: #ffa726;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.15s;
  }

  .btn-primary:hover { background: #a35200; }
</style>
