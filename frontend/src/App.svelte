<script>
  import { onMount } from 'svelte';
  import { currentStep } from './stores/appStore.js';
  import { checkHealth } from './services/api.js';
  import StepNavigation from './components/StepNavigation.svelte';
  import Step1Upload from './components/Step1Upload.svelte';
  import Step2Lyrics from './components/Step2Lyrics.svelte';
  import Step3Generate from './components/Step3Generate.svelte';
  import Step4Editor from './components/Step4Editor.svelte';
  import Step5Export from './components/Step5Export.svelte';

  let backendStatus = 'checking';
  let backendModels = {};

  onMount(async () => {
    try {
      const health = await checkHealth();
      backendStatus = health.status;
      backendModels = health.models || {};
    } catch (e) {
      backendStatus = 'offline';
    }
  });
</script>

<div class="app" class:full-width={$currentStep === 4}>
  <header>
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
</div>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    background: #0d1117;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
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
