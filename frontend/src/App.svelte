<script>
  import { onMount, onDestroy } from 'svelte';
  import { currentStep, sessionId, uploadData, lyricsData, generationResult, generationModalOpen, resetSession } from './stores/appStore.js';
  import { checkHealth, resumeSession, getAudioUrl, submitLyrics, checkSetupStatus } from './services/api.js';
  import StepNavigation from './components/StepNavigation.svelte';
  import ProjectLauncher from './components/ProjectLauncher.svelte';
  import Step1Upload from './components/Step1Upload.svelte';
  import Step2Lyrics from './components/Step2Lyrics.svelte';
  import Step3Generate from './components/Step3Generate.svelte';
  import Step4Editor from './components/Step4Editor.svelte';
  import Step5Export from './components/Step5Export.svelte';
  import DialogModal from './components/DialogModal.svelte';
  import SetupScreen from './components/SetupScreen.svelte';
  import { showConfirm } from './stores/dialogStore.js';

  let backendStatus = 'checking';
  let healthPollInterval = null;

  // Setup state: null = not checked yet, object = status result, true = done/skipped by user
  let setupStatus = null;
  let showSetup = false;

  async function pollHealth() {
    try {
      const health = await checkHealth();
      backendStatus = health.status;
    } catch (e) {
      backendStatus = 'offline';
    }
  }

  // Show a startup overlay while the backend is warming up, but not once the
  // SetupScreen has taken over (it has its own "waiting" UI).
  $: showStartupOverlay = backendStatus !== 'ok' && !showSetup;

  async function waitForBackendAndResume() {
    // Poll until backend is healthy (max 120 attempts × 1s = 2 minutes).
    for (let i = 0; i < 120; i++) {
      if (backendStatus === 'ok') break;
      await pollHealth();
      if (backendStatus === 'ok') break;
      await new Promise(r => setTimeout(r, 1000));
    }
    if (backendStatus !== 'ok') return;

    // Check setup status (first-run model download)
    try {
      setupStatus = await checkSetupStatus();
      if (!setupStatus.ready) {
        showSetup = true;
        return;
      }
    } catch (e) {
      // If setup check fails just continue
    }

    // Always land on home (step 0) — no auto-resume.
    // Session data is still in localStorage; ProjectLauncher can offer a resume option.
  }

  async function onSetupDone() {
    showSetup = false;
    // Always land on home (step 0) after setup — no auto-resume.
  }

  onMount(async () => {
    await pollHealth();
    healthPollInterval = setInterval(pollHealth, 15000);
    waitForBackendAndResume();
  });

  let homeConfirm = false;

  onDestroy(() => {
    if (healthPollInterval) clearInterval(healthPollInterval);
  });

  // Global error modal
  let errorModalMessage = null;

  function showErrorModal(msg) {
    errorModalMessage = String(msg);
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('error', (e) => {
      showErrorModal(e.message || String(e));
    });
    window.addEventListener('unhandledrejection', (e) => {
      showErrorModal(e.reason?.message || String(e.reason));
    });
  }

  async function goHome() {
    // Save Step2 lyrics before session is cleared
    if ($currentStep === 2 && $sessionId && $lyricsData.text?.trim()) {
      submitLyrics($sessionId, $lyricsData.text, $lyricsData.artist, $lyricsData.title, $lyricsData.language).catch(() => {});
    }
    resetSession();
    currentStep.set(0);
  }
</script>

<DialogModal />

{#if showStartupOverlay}
  <div class="startup-overlay">
    <div class="startup-card">
      <h1>Ultrastar Creator</h1>
      <div class="startup-spinner"></div>
      <p class="startup-msg">Backend is starting up…</p>
      <p class="startup-hint">This can take up to 30 seconds.</p>
    </div>
  </div>
{/if}

{#if errorModalMessage}
  <div class="error-modal-overlay" on:click={() => errorModalMessage = null}>
    <div class="error-modal" on:click|stopPropagation>
      <h2>Unexpected Error</h2>
      <pre class="error-modal-msg">{errorModalMessage}</pre>
      <p class="error-modal-hint">Please screenshot this and report it to the developer.</p>
      <button on:click={() => errorModalMessage = null}>Dismiss</button>
    </div>
  </div>
{/if}

{#if showSetup}
  <SetupScreen {setupStatus} on:done={onSetupDone} />
{/if}

<div class="app" class:full-width={$currentStep === 4}>
  {#if $currentStep === 0}
    <ProjectLauncher />
  {:else}
    <StepNavigation {backendStatus} {goHome} />

    <main>
      {#if $currentStep === 1}
        <Step1Upload />
      {:else if $currentStep === 2}
        <Step2Lyrics />
      {:else if $currentStep === 4}
        <Step4Editor />
      {:else if $currentStep === 5}
        <Step5Export />
      {/if}

      {#if $generationModalOpen}
        <Step3Generate />
      {/if}
    </main>
  {/if}
</div>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    background: #0d1117;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
    overflow-y: scroll; /* always show vertical scrollbar */
  }

  /* Force scrollbar thumb to always be visible on macOS */
  :global(::-webkit-scrollbar) {
    width: 8px;
  }
  :global(::-webkit-scrollbar-track) {
    background: #1a1f2b;
  }
  :global(::-webkit-scrollbar-thumb) {
    background: #555;
    border-radius: 4px;
  }
  :global(::-webkit-scrollbar-thumb:hover) {
    background: #777;
  }

  :global(*) {
    box-sizing: border-box;
  }

  .app {
    max-width: 900px;
    margin: 0 auto;
    padding: 1rem;
  }

  .app.full-width {
    max-width: 100%;
    padding: 0.5rem;
  }

  main {
    margin-top: 0.5rem;
  }

  /* ── Startup overlay ── */
  .startup-overlay {
    position: fixed;
    inset: 0;
    background: #0d1117;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .startup-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.25rem;
    text-align: center;
  }

  .startup-card h1 {
    font-size: 1.8rem;
    font-weight: 700;
    color: #e0e0e0;
    margin: 0;
  }

  .startup-spinner {
    width: 48px;
    height: 48px;
    border: 4px solid #2d333b;
    border-top-color: #4f8ef7;
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .startup-msg {
    color: #c0c8d8;
    font-size: 1rem;
    margin: 0;
  }

  .startup-hint {
    color: #666e7a;
    font-size: 0.82rem;
    margin: 0;
  }

  .error-modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
  }

  .error-modal {
    background: #1e2330;
    border: 1px solid #e05555;
    border-radius: 10px;
    padding: 1.5rem 2rem;
    max-width: 560px;
    width: 90%;
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }

  .error-modal h2 {
    color: #e05555;
    margin: 0;
    font-size: 1.1rem;
  }

  .error-modal-msg {
    background: #111418;
    color: #f0a0a0;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-size: 0.82rem;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 200px;
    overflow-y: auto;
    margin: 0;
  }

  .error-modal-hint {
    color: #888;
    font-size: 0.8rem;
    margin: 0;
  }

  .error-modal button {
    align-self: flex-end;
    background: #e05555;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 0.4rem 1.2rem;
    cursor: pointer;
    font-size: 0.9rem;
  }
</style>
