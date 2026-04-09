<script>
  import { onMount } from 'svelte';
  import { currentStep, sessionId, uploadData, lyricsData, generationResult, resetSession } from './stores/appStore.js';
  import { checkHealth, resumeSession, getAudioUrl } from './services/api.js';
  import StepNavigation from './components/StepNavigation.svelte';
  import ProjectLauncher from './components/ProjectLauncher.svelte';
  import Step1Upload from './components/Step1Upload.svelte';
  import Step2Lyrics from './components/Step2Lyrics.svelte';
  import Step3Generate from './components/Step3Generate.svelte';
  import Step4Editor from './components/Step4Editor.svelte';
  import Step5Export from './components/Step5Export.svelte';

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

  function goHome() {
    if (confirm('Return to the home screen? Unsaved changes will be lost.')) {
      resetSession();
      currentStep.set(0);
    }
  }
</script>

<div class="app" class:full-width={$currentStep === 4}>
  {#if $currentStep === 0}
    <ProjectLauncher />
  {:else}
    <header>
      <button class="home-btn" on:click={goHome} title="Back to Home">🏠</button>
      <h1>🎤 Ultrastar Song Generator</h1>
      <div class="backend-status" class:online={backendStatus === 'ok'} class:offline={backendStatus === 'offline'}>
        {#if backendStatus === 'ok'}
          ● Backend online
        {:else if backendStatus === 'offline'}
          ● Backend offline — start the backend server
        {:else}
          ● Checking backend...
        {/if}
      </div>
    </header>

    <StepNavigation />

    <main>
      {#if $currentStep === 1}
        <Step1Upload />
      {:else if $currentStep === 2}
        <Step2Lyrics />
      {:else if $currentStep === 3}
        <Step3Generate />
      {:else if $currentStep === 4}
        <Step4Editor />
      {:else if $currentStep === 5}
        <Step5Export />
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

  header {
    text-align: center;
    margin-bottom: 0.5rem;
    position: relative;
  }

  .home-btn {
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: 1px solid #333;
    border-radius: 8px;
    font-size: 1.2rem;
    cursor: pointer;
    padding: 0.3rem 0.6rem;
    transition: all 0.2s;
  }

  .home-btn:hover {
    background: #1a2a3e;
    border-color: #4fc3f7;
  }

  h1 {
    font-size: 1.8rem;
    font-weight: 300;
    color: #4fc3f7;
    margin: 0.5rem 0;
  }

  .backend-status {
    font-size: 0.75rem;
    color: #666;
    margin-bottom: 0.5rem;
  }

  .backend-status.online {
    color: #66bb6a;
  }

  .backend-status.offline {
    color: #ef5350;
  }

  main {
    margin-top: 1rem;
  }
</style>
