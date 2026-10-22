<script>
  /**
   * "Which song is this?" after an upload or a YouTube download: a proposal for artist and title, songs on
   * LRCLIB that fit the file or video name, and fields to correct. Saving the names confirms them, and
   * Step 2 then searches the lyrics with them.
   */
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import { identifySong, updateMetadata } from '../services/api.js';

  export let sessionId;
  export let artist = '';
  export let title = '';

  const dispatch = createEventDispatcher();
  let names = [];
  let matches = [];
  let songDuration = null;
  let searching = false;
  let saving = false;
  let message = '';
  let picked = null;

  function formatDuration(seconds) {
    if (!seconds) return '';
    const s = Math.round(seconds);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  async function lookUp(query = '') {
    searching = true;
    message = '';
    try {
      const found = await identifySong(sessionId, query);
      matches = found.matches || [];
      songDuration = found.song_duration || null;
      if (!query) {
        names = found.names || [];
        artist = found.proposal?.artist ?? artist;
        title = found.proposal?.title ?? title;
        picked = matches.findIndex(m => m.artist === artist && m.title.startsWith(title));
        if (picked < 0) picked = null;
      }
      if (!matches.length) {
        message = query ? 'Nothing found online for that. Check the spelling, or keep your names.'
                        : 'No match online for this name. Type the artist and title below.';
      }
    } catch (err) {
      message = err.message.replace(/^API error \d+: /, '');
    } finally {
      searching = false;
    }
  }

  function pick(index) {
    picked = index;
    artist = matches[index].artist;
    title = matches[index].title;
  }

  function swap() {
    [artist, title] = [title, artist];
    picked = null;
  }

  async function confirm() {
    if (!artist.trim() || !title.trim()) return;
    saving = true;
    try {
      await updateMetadata(sessionId, artist.trim(), title.trim());
      dispatch('confirm', { artist: artist.trim(), title: title.trim() });
    } catch (err) {
      message = err.message.replace(/^API error \d+: /, '');
    } finally {
      saving = false;
    }
  }

  function onKey(event) {
    if (event.key === 'Escape') dispatch('skip');
  }

  // Lock the page underneath (same as the LRCLIB window).
  let previous = null;
  onMount(() => {
    const body = document.body;
    previous = { overflow: body.style.overflow, paddingRight: body.style.paddingRight };
    const scrollbar = window.innerWidth - document.documentElement.clientWidth;
    body.style.overflow = 'hidden';
    if (scrollbar > 0) body.style.paddingRight = `${scrollbar}px`;
    lookUp();
  });
  onDestroy(() => {
    if (!previous) return;
    document.body.style.overflow = previous.overflow;
    document.body.style.paddingRight = previous.paddingRight;
  });
</script>

<svelte:window on:keydown={onKey} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="song-backdrop">
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div class="song-modal" role="dialog" aria-modal="true" aria-labelledby="song-title" on:click|stopPropagation>
    <h2 id="song-title">Which song is this?</h2>
    {#if names.length}
      <p class="song-from">From: <span>"{names[0]}"</span></p>
    {/if}

    {#if searching}
      <div class="busy-bar" role="progressbar" aria-label="Looking the song up"></div>
      <p class="song-hint">Looking it up on lrclib.net…</p>
    {:else if matches.length}
      <p class="song-label">Found online — click to use:</p>
      <ul class="song-matches">
        {#each matches as match, i}
          <li>
            <button class="song-match" class:picked={picked === i} on:click={() => pick(i)}>
              <span class="match-name">{match.artist} – {match.title}</span>
              <span class="match-meta">
                {#if match.album}{match.album} · {/if}{formatDuration(match.duration)}
                {#if match.length_match === true}<span class="length-ok" title="Same length as your song ({formatDuration(songDuration)})">✓ same length</span>{/if}
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
    {#if message}<p class="song-message">{message}</p>{/if}

    <form class="song-fields" on:submit|preventDefault={confirm}>
      <label>Artist <input type="text" bind:value={artist} on:input={() => picked = null} placeholder="Artist" /></label>
      <button type="button" class="swap-btn" on:click={swap} title="Swap artist and title">⇄</button>
      <label>Title <input type="text" bind:value={title} on:input={() => picked = null} placeholder="Song title" /></label>
    </form>
    <button class="link-btn" on:click={() => lookUp(`${artist} ${title}`.trim())}
            disabled={searching || !(artist.trim() || title.trim())}>🔎 Search online with these names</button>

    <div class="song-actions">
      <button class="btn btn-secondary" on:click={() => dispatch('skip')}>Skip for now</button>
      <button class="btn btn-primary" on:click={confirm} disabled={saving || !artist.trim() || !title.trim()}>
        {saving ? 'Saving…' : '✓ Use this'}
      </button>
    </div>
  </div>
</div>

<style>
  .song-backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); z-index: 1000; overscroll-behavior: contain;
    display: flex; align-items: center; justify-content: center; padding: 1rem;
  }
  .song-modal {
    background: #1a1a2a; border: 1px solid #333; border-radius: 10px; width: min(600px, 100%); max-height: 88vh;
    overflow-y: auto; display: flex; flex-direction: column; gap: 0.6rem; padding: 1.25rem; color: #e0e0e0;
  }
  h2 { margin: 0; font-size: 1.15rem; }
  .song-from { margin: 0; color: #888; font-size: 0.85rem; }
  .song-from span { color: #bbb; }
  .song-label, .song-hint { margin: 0; color: #999; font-size: 0.82rem; }
  .song-message { margin: 0; color: #e0a030; font-size: 0.85rem; }
  .song-matches { list-style: none; margin: 0; padding: 0; border: 1px solid #333; border-radius: 6px; overscroll-behavior: contain; }
  .song-match {
    display: flex; flex-direction: column; align-items: flex-start; gap: 0.1rem; width: 100%; padding: 0.5rem 0.75rem;
    border: none; border-bottom: 1px solid #2a2a3a; background: transparent; color: inherit; text-align: left; cursor: pointer;
  }
  .song-match:hover, .song-match:focus-visible { background: rgba(79, 140, 255, 0.15); }
  .song-match.picked { background: rgba(76, 175, 80, 0.2); }
  .match-name { font-weight: 600; }
  .match-meta { font-size: 0.82em; opacity: 0.8; }
  .length-ok { color: #4caf50; margin-left: 0.25rem; }
  .song-fields { display: flex; gap: 0.5rem; align-items: flex-end; flex-wrap: wrap; }
  .song-fields label { flex: 1 1 200px; display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.82rem; color: #aaa; }
  .song-fields input {
    background: #11111d; color: #e0e0e0; border: 1px solid #333; border-radius: 6px; padding: 0.5rem 0.6rem; font-size: 0.95rem;
  }
  .song-fields input:focus { outline: none; border-color: #1976d2; }
  .swap-btn {
    background: #262636; color: #ccc; border: 1px solid #444; border-radius: 6px; padding: 0.45rem 0.6rem;
    cursor: pointer; font-size: 1rem; margin-bottom: 1px;
  }
  .swap-btn:hover { background: #303045; }
  .link-btn {
    align-self: flex-start; background: none; border: none; color: #4fc3f7; cursor: pointer; padding: 0;
    font-size: 0.82rem; text-decoration: underline;
  }
  .link-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .song-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.25rem; }
  .btn { padding: 0.6rem 1.2rem; border: none; border-radius: 8px; font-size: 0.9rem; cursor: pointer; }
  .btn-primary { background: #1976d2; color: white; }
  .btn-primary:hover:not(:disabled) { background: #1565c0; }
  .btn-secondary { background: #333; color: #ccc; border: 1px solid #555; }
  .btn-secondary:hover:not(:disabled) { background: #444; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .busy-bar { height: 3px; border-radius: 2px; background: linear-gradient(90deg, transparent, #4fc3f7, transparent);
    background-size: 50% 100%; background-repeat: no-repeat; animation: slide 1.1s ease-in-out infinite; }
  @keyframes slide { from { background-position: -50% 0; } to { background-position: 150% 0; } }
</style>
