<script>
  /**
   * At app start: a newer release on GitHub is offered with what's new (the update manifest's notes). Only in the built
   * app: the updater verifies the release's signature, downloads, stops the backend (its files would stay locked on
   * Windows), installs and restarts. A failed check stays silent: nobody needs to know GitHub was unreachable.
   */
  import { onMount } from 'svelte';
  import { inTauriApp } from '../services/api.js';
  import { noteBlocks } from '../lib/releaseNotes.js';

  const SKIPPED_KEY = 'update_skipped_version';
  const RELEASES_URL = 'https://github.com/retotito/UltrastarCreatorTool/releases/latest';
  let update = null;
  let phase = 'offer';   // 'offer' | 'downloading' | 'installing' | 'failed'
  let percent = null;
  let downloadedMb = 0;
  let errorText = '';
  let backendStopped = false;

  $: blocks = update ? noteBlocks(update.body) : [];

  onMount(async () => {
    if (!inTauriApp || !import.meta.env.PROD) return;
    try {
      const { check } = await import('@tauri-apps/plugin-updater');
      const found = await check();
      let skipped = '';
      try { skipped = localStorage.getItem(SKIPPED_KEY) || ''; } catch { /* no storage: offer it */ }
      if (found && found.version !== skipped) update = found;
    } catch (e) {
      console.warn('[Update] Check failed:', e);
    }
  });

  function skip() {
    try { localStorage.setItem(SKIPPED_KEY, update.version); } catch { /* it is offered again next time */ }
    update = null;
  }

  async function install() {
    phase = 'downloading';
    try {
      let total = 0;
      let done = 0;
      await update.download((event) => {
        if (event.event === 'Started') total = event.data.contentLength || 0;
        else if (event.event === 'Progress') {
          done += event.data.chunkLength;
          downloadedMb = Math.round(done / 1e6);
          percent = total ? Math.min(100, Math.round(done * 100 / total)) : null;
        }
      });
      phase = 'installing';
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('stop_backend');
      backendStopped = true;
      await update.install();
      const { relaunch } = await import('@tauri-apps/plugin-process');
      await relaunch();
    } catch (e) {
      errorText = String(e?.message || e);
      phase = 'failed';
    }
  }

  async function restart() {
    const { relaunch } = await import('@tauri-apps/plugin-process');
    await relaunch();
  }
</script>

{#if update}
  <div class="update-backdrop">
    <div class="update-modal" role="dialog" aria-modal="true" aria-labelledby="update-title">
      <h2 id="update-title">Version {update.version} is available</h2>
      <p class="update-current">You have version {update.currentVersion}.</p>

      {#if phase === 'offer'}
        {#if blocks.length}
          <h3 class="update-new">What's new</h3>
          <div class="update-notes">
            {#each blocks as block}
              {#if block.type === 'heading'}<h4>{block.text}</h4>
              {:else if block.type === 'bullet'}<p class="bullet">{block.text}</p>
              {:else}<p>{block.text}</p>{/if}
            {/each}
          </div>
        {/if}
        <div class="update-actions">
          <button class="btn btn-link" on:click={skip}>Skip this version</button>
          <button class="btn btn-secondary" on:click={() => { update = null; }}>Later</button>
          <button class="btn btn-primary" on:click={install}>Update now</button>
        </div>
      {:else if phase === 'downloading'}
        {#if percent !== null}<progress max="100" value={percent}></progress>{:else}<progress></progress>{/if}
        <p class="update-status">Downloading… {downloadedMb} MB{percent !== null ? ` · ${percent}%` : ''}</p>
        <p class="update-hint">The whole app is downloaded, so this can take a few minutes. Your songs and AI models stay.</p>
      {:else if phase === 'installing'}
        <progress></progress>
        <p class="update-status">Installing… the app restarts by itself.</p>
      {:else}
        <p class="update-error">The update failed: {errorText}</p>
        <p class="update-hint">You can install it by hand from {RELEASES_URL}</p>
        <div class="update-actions">
          {#if backendStopped}
            <button class="btn btn-primary" on:click={restart}>Restart the app</button>
          {:else}
            <button class="btn btn-secondary" on:click={() => { update = null; }}>Close</button>
          {/if}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .update-backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.65); z-index: 9000; overscroll-behavior: contain;
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }
  .update-modal {
    background: #1a1a2a; border: 1px solid #333; border-radius: 10px; width: min(560px, 100%); max-height: 88vh;
    display: flex; flex-direction: column; gap: 0.6rem; padding: 1.4rem; color: #e0e0e0;
  }
  h2 { margin: 0; font-size: 1.2rem; }
  .update-current { margin: 0; color: #999; font-size: 0.85rem; }
  .update-new { margin: 0.4rem 0 0; font-size: 0.95rem; }
  .update-notes { overflow-y: auto; min-height: 0; flex: 1; padding-right: 0.4rem; font-size: 0.87rem; line-height: 1.45; color: #ccc; }
  .update-notes h4 { margin: 0.7rem 0 0.25rem; font-size: 0.87rem; color: #4fc3f7; }
  .update-notes h4:first-child { margin-top: 0; }
  .update-notes p { margin: 0 0 0.3rem; }
  .bullet { padding-left: 1rem; position: relative; }
  .bullet::before { content: '•'; position: absolute; left: 0.1rem; color: #777; }
  .update-actions { display: flex; justify-content: flex-end; align-items: center; gap: 0.5rem; margin-top: 0.4rem; }
  .btn { padding: 0.55rem 1.1rem; border: none; border-radius: 8px; font-size: 0.88rem; cursor: pointer; }
  .btn-primary { background: #1976d2; color: white; }
  .btn-primary:hover { background: #1565c0; }
  .btn-secondary { background: #333; color: #e0e0e0; }
  .btn-secondary:hover { background: #444; }
  .btn-link { background: none; color: #888; margin-right: auto; padding-left: 0; }
  .btn-link:hover { color: #bbb; }
  progress { width: 100%; height: 6px; }
  .update-status { margin: 0; color: #4fc3f7; font-size: 0.88rem; }
  .update-hint { margin: 0; color: #888; font-size: 0.8rem; overflow-wrap: anywhere; }
  .update-error { margin: 0; color: #ef9a9a; font-size: 0.88rem; overflow-wrap: anywhere; }
</style>
