<script>
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { checkSetupStatus, streamSetupDownload } from '../services/api.js';

  export let status = null; // { ffmpeg, whisperx, demucs, ready }

  const dispatch = createEventDispatcher();

  // Step state: 'pending' | 'downloading' | 'done' | 'error' | 'skipped'
  let steps = {
    ffmpeg:   { label: 'ffmpeg (audio tools)',   size: '',         state: 'pending', message: '', elapsed: 0, percent: null },
    whisperx: { label: 'WhisperX speech model',  size: '~1.5 GB', state: 'pending', message: '', elapsed: 0, percent: null },
    demucs:   { label: 'Demucs vocal model',      size: '~80 MB',  state: 'pending', message: '', elapsed: 0, percent: null },
  };

  let downloading = false;
  let allDone = false;
  let stopStream = null;
  let tickers = {};  // key → intervalId

  function startTicker(key) {
    steps[key].elapsed = 0;
    tickers[key] = setInterval(() => { steps[key].elapsed += 1; steps = steps; }, 1000);
  }
  function stopTicker(key) {
    if (tickers[key]) { clearInterval(tickers[key]); delete tickers[key]; }
  }
  function stopAllTickers() {
    Object.keys(tickers).forEach(stopTicker);
  }

  onDestroy(stopAllTickers);

  // Pre-fill states from the initial status check
  $: if (status) {
    if (status.ffmpeg)   steps.ffmpeg.state   = 'done';
    if (status.whisperx) steps.whisperx.state = 'done';
    if (status.demucs)   steps.demucs.state   = 'done';
    if (status.ready) allDone = true;
    steps = steps; // trigger reactivity
  }

  function startDownload() {
    downloading = true;
    // Reset non-done steps to pending so the UI refreshes
    for (const k of Object.keys(steps)) {
      if (steps[k].state !== 'done') { steps[k].state = 'pending'; steps[k].elapsed = 0; }
    }

    stopStream = streamSetupDownload((event) => {
      if (event.type === 'progress') {
        const s = steps[event.step];
        if (s) {
          s.state = 'downloading';
          s.message = event.message;
          if (event.percent != null) s.percent = event.percent;
          steps = steps;
          startTicker(event.step);
        }
      } else if (event.type === 'done') {
        const s = steps[event.step];
        if (s) {
          stopTicker(event.step);
          s.state = event.error ? 'skipped' : 'done';
          s.message = event.message;
          steps = steps;
        }
      } else if (event.type === 'error') {
        const s = steps[event.step];
        if (s) {
          stopTicker(event.step);
          s.state = 'error';
          s.message = event.message;
          steps = steps;
        }
      } else if (event.type === 'complete') {
        stopAllTickers();
        downloading = false;
        allDone = Object.values(steps).every(s => s.state === 'done' || s.state === 'skipped');
        if (stopStream) stopStream();
      }
    });
  }

  function continueToApp() {
    dispatch('done');
  }
</script>

<div class="setup-overlay">
  <div class="setup-card">
    <h1>Ultrastar Creator</h1>
    <p class="subtitle">First-time setup — downloading AI models</p>

    <div class="steps">
      {#each Object.entries(steps) as [key, step]}
        <div class="step" class:done={step.state === 'done'} class:error={step.state === 'error'} class:skipped={step.state === 'skipped'} class:active={step.state === 'downloading'}>
          <div class="step-icon">
            {#if step.state === 'done'}
              ✅
            {:else if step.state === 'downloading'}
              <span class="step-spinner"></span>
            {:else if step.state === 'error'}
              ❌
            {:else if step.state === 'skipped'}
              ⚠️
            {:else}
              ⬜
            {/if}
          </div>
          <div class="step-info">
            <div class="step-label">{step.label} {#if step.size}<span class="size">{step.size}</span>{/if}</div>
            {#if step.state === 'downloading'}
              {#if step.percent != null}
                <div class="step-progress-bar">
                  <div class="step-progress-fill" style="width: {step.percent}%"></div>
                </div>
                <div class="step-percent">{step.percent}%</div>
              {/if}
              <div class="step-elapsed">⏱ {step.elapsed}s elapsed</div>
            {/if}
            {#if step.message}
              <div class="step-message">{step.message}</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>

    {#if !downloading && !allDone}
      <button class="btn-primary" on:click={startDownload}>
        Download Models
      </button>
    {:else if downloading}
      <p class="hint">Downloading… this may take several minutes on first run.</p>
    {:else if allDone}
      <button class="btn-primary" on:click={continueToApp}>
        Continue →
      </button>
    {/if}

    {#if allDone}
      <p class="hint success">All models ready.</p>
    {/if}
  </div>
</div>

<style>
  .setup-overlay {
    position: fixed;
    inset: 0;
    background: #0d1117;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .setup-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 2.5rem;
    max-width: 480px;
    width: 90%;
    text-align: center;
  }

  h1 {
    color: #e0e0e0;
    margin: 0 0 0.25rem;
    font-size: 1.6rem;
  }

  .subtitle {
    color: #8b949e;
    margin: 0 0 2rem;
    font-size: 0.9rem;
  }

  .steps {
    text-align: left;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    margin-bottom: 2rem;
  }

  .step {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 0.75rem 1rem;
  }

  .step.done   { border-color: #238636; }
  .step.error  { border-color: #da3633; }
  .step.skipped { border-color: #9e6a03; }

  .step-icon {
    font-size: 1.1rem;
    line-height: 1.4;
    flex-shrink: 0;
  }

  .step-info { flex: 1; }

  .step-label {
    color: #c9d1d9;
    font-size: 0.9rem;
    font-weight: 500;
  }

  .size {
    color: #8b949e;
    font-weight: 400;
    font-size: 0.82rem;
    margin-left: 0.4rem;
  }

  .step.active { border-color: #388bfd; }

  .step-elapsed {
    font-size: 0.8rem;
    color: #388bfd;
    font-variant-numeric: tabular-nums;
    margin-top: 0.2rem;
  }

  .step-progress-bar {
    margin-top: 0.35rem;
    height: 6px;
    background: #21262d;
    border-radius: 3px;
    overflow: hidden;
  }

  .step-progress-fill {
    height: 100%;
    background: #388bfd;
    border-radius: 3px;
    transition: width 0.3s ease;
  }

  .step-percent {
    font-size: 0.78rem;
    color: #388bfd;
    font-variant-numeric: tabular-nums;
    margin-top: 0.15rem;
  }

  .step-message {
    color: #8b949e;
    font-size: 0.8rem;
    margin-top: 0.2rem;
    word-break: break-word;
  }

  .step.error .step-message  { color: #f85149; }
  .step.skipped .step-message { color: #d29922; }

  .step-spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid #30363d;
    border-top-color: #388bfd;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  .btn-primary {
    background: #238636;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 0.65rem 2rem;
    font-size: 1rem;
    cursor: pointer;
    transition: background 0.15s;
  }

  .btn-primary:hover { background: #2ea043; }

  .hint {
    color: #8b949e;
    font-size: 0.82rem;
    margin-top: 1rem;
  }

  .hint.success { color: #3fb950; }
</style>
