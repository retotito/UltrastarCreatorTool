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

  async function waitForBackendAndResume() {
    // Wait until backend is healthy before attempting session resume
    const sid = $sessionId;

    // Read the original persisted step directly from localStorage (store caps it at 2 on init)
    const persistedStep = parseInt(localStorage.getItem('currentStep') || '0');

    // Poll until healthy (max 120 attempts × 1s = 2 minutes)
    for (let i = 0; i < 120; i++) {
      if (backendStatus === 'ok') break;
      await new Promise(r => setTimeout(r, 1000));
    }
    if (backendStatus !== 'ok') return; // backend never came up, leave session intact

    // Check setup status (first-run model download)
    try {
      setupStatus = await checkSetupStatus();
      if (!setupStatus.ready) {
        showSetup = true;
        return; // don't resume session until setup is done
      }
    } catch (e) {
      // If setup check fails just continue (backend may not support it yet)
    }

    if (!sid || persistedStep < 2) return;

    try {
      const data = await resumeSession(sid);
      const hasVocals = data.has_vocals !== false;
      const hasOriginal = data.has_original !== false;
      uploadData.set({
        filename: data.filename,
        hasVocals,
        hasOriginal,
        vocalUrl: hasVocals ? getAudioUrl(sid, 'vocals') : (hasOriginal ? getAudioUrl(sid, 'original') : null),
      });
      if (data.has_lyrics) {
        lyricsData.set({
          text: data.lyrics || '',
          artist: data.artist || '',
          title: data.title || '',
          language: data.language || 'en',
          syllableCount: data.syllable_count || 0,
          lineCount: data.line_count || 0,
          preview: [],
        });
      }
      if (data.has_result) {
        generationResult.set(data.result || {});
      }
      // Restore the original step now that session is confirmed
      currentStep.set(persistedStep);
      console.log(`[App] Resumed session ${sid} at step ${persistedStep}`);
    } catch (e) {
      console.warn('[App] Failed to resume session, resetting:', e);
      resetSession();
    }
  }

  async function onSetupDone() {
    showSetup = false;
    // Now attempt session resume
    const sid = $sessionId;
    const persistedStep = parseInt(localStorage.getItem('currentStep') || '0');
    if (!sid || persistedStep < 2) return;
    try {
      const data = await resumeSession(sid);
      const hasVocals = data.has_vocals !== false;
      const hasOriginal = data.has_original !== false;
      uploadData.set({
        filename: data.filename,
        hasVocals,
        hasOriginal,
        vocalUrl: hasVocals ? getAudioUrl(sid, 'vocals') : (hasOriginal ? getAudioUrl(sid, 'original') : null),
      });
      if (data.has_lyrics) {
        lyricsData.set({
          text: data.lyrics || '',
          artist: data.artist || '',
          title: data.title || '',
          language: data.language || 'en',
          syllableCount: data.syllable_count || 0,
          lineCount: data.line_count || 0,
          preview: [],
        });
      }
      if (data.has_result) {
        generationResult.set(data.result || {});
      }
      currentStep.set(persistedStep);
    } catch (e) {
      resetSession();
    }
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
</style>
