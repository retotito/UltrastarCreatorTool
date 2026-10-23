<script>
  /**
   * "Which song is this?" after an upload or a YouTube download: a proposal for artist and title to check and
   * correct, and the language(s) it is sung in (a second one for bilingual songs: "#LANGUAGE:English, German").
   * The artist/title proposal is checked against lrclib.net in the background (it tells "Title - Artist" from
   * "Artist - Title" and ignores wrong tags). Saving the names confirms them, names the song's audio file
   * "Artist - Title", and Step 2 then searches the lyrics with them.
   */
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import { identifySong, updateMetadata } from '../services/api.js';
  import { SUPPORTED_LANGUAGES } from '../lib/languages';

  export let sessionId;
  export let artist = '';
  export let title = '';
  export let language = '';
  export let language2 = '';

  const dispatch = createEventDispatcher();
  let searching = false;
  let saving = false;
  let message = '';

  async function propose() {
    searching = true;
    message = '';
    try {
      const found = await identifySong(sessionId);
      artist = found.proposal?.artist ?? artist;
      title = found.proposal?.title ?? title;
      if (!(found.matches || []).length && !(artist.trim() && title.trim())) {
        message = "Couldn't recognise the song from its name. Please type artist and title.";
      }
    } catch {
      // Offline or LRCLIB busy: keep the names from the file / video and let the user check them.
    } finally {
      searching = false;
    }
  }

  function swap() {
    [artist, title] = [title, artist];
  }

  // Why Confirm is disabled, shown as its tooltip.
  $: missingHint = !artist.trim() ? 'Enter the artist' : !title.trim() ? 'Enter the song title'
    : !language ? 'Select the language the song is sung in' : '';

  async function confirm() {
    if (!artist.trim() || !title.trim() || !language) return;
    saving = true;
    try {
      const second = language2 && language2 !== language ? language2 : '';
      const saved = await updateMetadata(sessionId, artist.trim(), title.trim(), language, second);
      dispatch('confirm', { artist: artist.trim(), title: title.trim(), language, language2: second,
                            filename: saved?.filename || '' });
    } catch (err) {
      message = err.message.replace(/^API error \d+: /, '');
    } finally {
      saving = false;
    }
  }

  // Lock the page underneath (same as the LRCLIB window).
  let previous = null;
  onMount(() => {
    const body = document.body;
    previous = { overflow: body.style.overflow, paddingRight: body.style.paddingRight };
    const scrollbar = window.innerWidth - document.documentElement.clientWidth;
    body.style.overflow = 'hidden';
    if (scrollbar > 0) body.style.paddingRight = `${scrollbar}px`;
    propose();
  });
  onDestroy(() => {
    if (!previous) return;
    document.body.style.overflow = previous.overflow;
    document.body.style.paddingRight = previous.paddingRight;
  });
</script>

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="song-backdrop">
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div class="song-modal" role="dialog" aria-modal="true" aria-labelledby="song-title" on:click|stopPropagation>
    <h2 id="song-title">Which song is this?</h2>
    {#if searching}
      <div class="busy-bar" role="progressbar" aria-label="Recognising the song"></div>
    {/if}
    <p class="song-hint">Please check the artist and song name, and choose the language it is sung in (a second one if the song mixes two).</p>
    {#if message}<p class="song-message">{message}</p>{/if}

    <form class="song-fields" on:submit|preventDefault={confirm}>
      <label>Artist <input type="text" bind:value={artist} placeholder="Artist" disabled={searching} /></label>
      <button type="button" class="swap-btn" on:click={swap} title="Swap artist and title">⇄</button>
      <label>Title <input type="text" bind:value={title} placeholder="Song title" disabled={searching} /></label>
    </form>
    <div class="song-languages">
      <label class="song-language">Language
        <select bind:value={language}>
          <option value="" disabled>Select language…</option>
          {#each SUPPORTED_LANGUAGES as lang}
            <option value={lang.code}>{lang.label}</option>
          {/each}
        </select>
      </label>
      <label class="song-language">Language 2 (optional)
        <select bind:value={language2}>
          <option value="">None</option>
          {#each SUPPORTED_LANGUAGES.filter(l => l.code !== language) as lang}
            <option value={lang.code}>{lang.label}</option>
          {/each}
        </select>
      </label>
    </div>

    <div class="song-actions">
      <!-- The tooltip sits on a wrapper: a disabled button gets no hover, so it shows no title of its own. -->
      <span title={missingHint}>
        <button class="btn btn-primary" on:click={confirm} disabled={saving || searching || !!missingHint}>
          {saving ? 'Saving…' : '✓ Confirm'}
        </button>
      </span>
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
  .song-hint { margin: 0; color: #999; font-size: 0.82rem; }
  .song-message { margin: 0; color: #e0a030; font-size: 0.85rem; }
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
  .song-languages { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .song-language { flex: 1 1 200px; display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.82rem; color: #aaa; }
  .song-language select {
    background: #11111d; color: #e0e0e0; border: 1px solid #333; border-radius: 6px; padding: 0.5rem 0.6rem; font-size: 0.95rem;
  }
  .song-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.25rem; }
  .btn { padding: 0.6rem 1.2rem; border: none; border-radius: 8px; font-size: 0.9rem; cursor: pointer; }
  .btn-primary { background: #1976d2; color: white; }
  .btn-primary:hover:not(:disabled) { background: #1565c0; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; pointer-events: none; }
  .song-actions span:has(.btn:disabled) { cursor: not-allowed; }
  .busy-bar { height: 3px; border-radius: 2px; background: linear-gradient(90deg, transparent, #4fc3f7, transparent);
    background-size: 50% 100%; background-repeat: no-repeat; animation: slide 1.1s ease-in-out infinite; }
  @keyframes slide { from { background-position: -50% 0; } to { background-position: 150% 0; } }
</style>
