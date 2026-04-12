<script>
  import { currentStep, steps, canGoToStep } from '../stores/appStore.js';

  function goToStep(num) {
    if ($canGoToStep(num)) {
      currentStep.set(num);
    }
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
</style>
