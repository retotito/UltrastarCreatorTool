<script>
  import { onMount } from 'svelte';
  import { currentStep, sessionId, uploadData, lyricsData, generationResult, generationModalOpen, resetSession } from './stores/appStore.js';
  import { checkHealth, resumeSession, getAudioUrl } from './services/api.js';
  import StepNavigation from './components/StepNavigation.svelte';
  import ProjectLauncher from './components/ProjectLauncher.svelte';
  import Step1Upload from './components/Step1Upload.svelte';
  import Step2Lyrics from './components/Step2Lyrics.svelte';
  import Step3Generate from './components/Step3Generate.svelte';
  import Step4Editor from './components/Step4Editor.svelte';
  import Step5Export from './components/Step5Export.svelte';
  import DialogModal from './components/DialogModal.svelte';
  import { showConfirm } from './stores/dialogStore.js';

  let backendStatus = 'checking';

  onMount(async () => {
    try {
      const health = await checkHealth();
      backendStatus = health.status;
    } catch (e) {
      backendStatus = 'offline';
    }

    // Auto-resume persisted session on refresh
    const sid = $sessionId;
    const step = $currentStep;
    if (sid && step >= 2) {
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
        console.log(`[App] Resumed session ${sid} at step ${step}`);
      } catch (e) {
        console.warn('[App] Failed to resume session, resetting:', e);
        resetSession();
      }
    }
  });

  let homeConfirm = false;

  async function goHome() {
    const ok = await showConfirm('Return to the home screen? Unsaved changes will be lost.', {
      confirmLabel: 'Go Home',
      cancelLabel: 'Stay',
      danger: false,
    });
    if (ok) {
      resetSession();
      currentStep.set(0);
    }
  }
</script>

<DialogModal />

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
