<script>
  /**
   * Step 2's LRCLIB window: search again with another artist or title, and pick one of the versions
   * LRCLIB has. Picking one puts its lyrics into the LRCLIB tab.
   */
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';

  export let artist = '';
  export let title = '';
  export let candidates = [];
  export let chosenId = null;
  export let songDuration = null;
  export let searching = false;
  export let message = '';

  const dispatch = createEventDispatcher();
  let queryArtist = artist;
  let queryTitle = title;

  function formatDuration(seconds) {
    if (!seconds) return '';
    const s = Math.round(seconds);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  function search() {
    if (!queryArtist.trim() || !queryTitle.trim() || searching) return;
    dispatch('search', { artist: queryArtist.trim(), title: queryTitle.trim() });
  }

  function onKey(event) {
    if (event.key === 'Escape') dispatch('close');
  }

  // The page underneath doesn't scroll while the window is open. Its scrollbar's width is kept as
  // padding, so the page doesn't shift sideways.
  let previous = null;
  onMount(() => {
    const body = document.body;
    previous = { overflow: body.style.overflow, paddingRight: body.style.paddingRight };
    const scrollbar = window.innerWidth - document.documentElement.clientWidth;
    body.style.overflow = 'hidden';
    if (scrollbar > 0) body.style.paddingRight = `${scrollbar}px`;
  });
  onDestroy(() => {
    if (!previous) return;
    document.body.style.overflow = previous.overflow;
    document.body.style.paddingRight = previous.paddingRight;
  });
</script>

<svelte:window on:keydown={onKey} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="versions-backdrop" on:click={() => dispatch('close')}>
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div class="versions-modal" role="dialog" aria-modal="true" aria-labelledby="versions-title" on:click|stopPropagation>
    <div class="versions-header">
      <h2 id="versions-title">Lyrics from LRCLIB</h2>
      <button class="close-btn" on:click={() => dispatch('close')} aria-label="Close">✕</button>
    </div>

    <form class="versions-search" on:submit|preventDefault={search}>
      <input type="text" bind:value={queryArtist} placeholder="Artist" aria-label="Artist" />
      <input type="text" bind:value={queryTitle} placeholder="Title" aria-label="Title" />
      <button class="btn btn-secondary" type="submit" disabled={searching || !queryArtist.trim() || !queryTitle.trim()}>
        {#if searching}<span class="spinner" aria-hidden="true"></span> Searching…{:else}🔎 Search{/if}
      </button>
    </form>
    <p class="versions-hint">Change artist or title if the version isn't right — only this search uses them, not your song's details.</p>

    {#if searching}<div class="busy-bar" role="progressbar" aria-label="Searching LRCLIB"></div>{/if}
    {#if message}<p class="versions-message">{message}</p>{/if}

    {#if candidates.length}
      <ul class="versions-list">
        {#each candidates as entry (entry.id)}
          <li>
            <button class="version" class:chosen={entry.id === chosenId} on:click={() => dispatch('choose', entry)}>
              <span class="version-title">{entry.track} — {entry.artist}{#if entry.id === chosenId} <span class="in-use">in use</span>{/if}</span>
              <span class="version-meta">
                {#if entry.album}{entry.album} · {/if}{formatDuration(entry.duration)}
                {#if entry.length_match === true}<span class="length-ok" title="Same length as your song ({formatDuration(songDuration)})">✓ same length</span>{/if}
                {#if entry.length_match === false}<span class="length-off" title="Your song is {formatDuration(songDuration)}">other length</span>{/if}
                · {entry.lines} lines{entry.synced ? ' · synced' : ''}
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {:else if searching}
      <p class="versions-empty">Asking lrclib.net…</p>
    {:else}
      <p class="versions-empty">No versions found. Try a shorter title, or check the artist's spelling.</p>
    {/if}
  </div>
</div>

<style>
  .versions-backdrop {
    position: fixed; inset: 0; overscroll-behavior: contain; background: rgba(0, 0, 0, 0.6); z-index: 1000;
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }
  .versions-modal {
    background: #1a1a2a; border: 1px solid #333; border-radius: 10px; width: min(640px, 100%);
    max-height: 85vh; display: flex; flex-direction: column; gap: 0.6rem; padding: 1.25rem; color: #e0e0e0;
  }
  .versions-header { display: flex; align-items: center; justify-content: space-between; }
  .versions-header h2 { margin: 0; font-size: 1.15rem; }
  .close-btn { background: none; border: none; color: #aaa; font-size: 1.1rem; cursor: pointer; }
  .close-btn:hover { color: #fff; }
  .versions-search { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .versions-search input {
    flex: 1 1 160px; min-width: 0; background: #11111d; color: #e0e0e0; border: 1px solid #333;
    border-radius: 6px; padding: 0.5rem 0.6rem; font-size: 0.9rem;
  }
  .versions-search input:focus { outline: none; border-color: #1976d2; }
  .versions-hint, .versions-empty { color: #888; font-size: 0.8rem; margin: 0; }
  .versions-message { color: #ccc; font-size: 0.85rem; margin: 0; }
  .versions-list {
    list-style: none; margin: 0; padding: 0; overflow-y: auto; border: 1px solid #333; border-radius: 6px;
    overscroll-behavior: contain; /* scrolling past the list's end doesn't scroll the page */
  }
  .version {
    display: flex; flex-direction: column; align-items: flex-start; gap: 0.15rem; width: 100%;
    padding: 0.55rem 0.75rem; border: none; border-bottom: 1px solid #2a2a3a;
    background: transparent; color: inherit; text-align: left; cursor: pointer;
  }
  .version:hover, .version:focus-visible { background: rgba(79, 140, 255, 0.15); }
  .version.chosen { background: rgba(76, 175, 80, 0.18); }
  .version-title { font-weight: 600; }
  .version-meta { font-size: 0.85em; opacity: 0.8; }
  .in-use { color: #4caf50; font-weight: normal; font-size: 0.8em; margin-left: 0.25rem; }
  .length-ok { color: #4caf50; margin-left: 0.25rem; }
  .length-off { color: #e0a030; margin-left: 0.25rem; }
  .btn {
    display: inline-block; padding: 0.5rem 1rem; border: none; border-radius: 8px; font-size: 0.85rem;
    cursor: pointer; transition: all 0.2s;
  }
  .btn-secondary { background: #333; color: #ccc; border: 1px solid #555; }
  .btn-secondary:hover:not(:disabled) { background: #444; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .spinner {
    display: inline-block; width: 0.85em; height: 0.85em; vertical-align: -0.1em;
    border: 2px solid rgba(255, 255, 255, 0.25); border-top-color: #fff; border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .busy-bar { height: 3px; border-radius: 2px; background: linear-gradient(90deg, transparent, #4fc3f7, transparent);
    background-size: 50% 100%; background-repeat: no-repeat; animation: slide 1.1s ease-in-out infinite; }
  @keyframes slide { from { background-position: -50% 0; } to { background-position: 150% 0; } }
</style>
