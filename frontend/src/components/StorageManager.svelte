<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { getStorageInfo, cleanupOrphans, cleanupDebugData, deleteSession, deleteModelCache } from '../services/api.js';
  import { sessionId as currentSessionId } from '../stores/appStore.js';
  import { showConfirm } from '../stores/dialogStore.js';

  const dispatch = createEventDispatcher();

  let loading = true;
  let error = '';
  let info = null;
  let cleanupRunning = false;
  let cleanupResult = null;
  let debugCleanupRunning = false;
  let debugCleanupResult = null;
  let deletingId = null;
  let deletingModelPath = null;
  let modelDeleteError = '';

  function fmt(bytes) {
    if (bytes == null || bytes < 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
  }

  function fmtDate(ts) {
    if (!ts) return '—';
    return new Date(ts * 1000).toLocaleString();
  }

  async function load() {
    loading = true;
    error = '';
    cleanupResult = null;
    try {
      info = await getStorageInfo();
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function doCleanup() {
    cleanupRunning = true;
    cleanupResult = null;
    debugCleanupResult = null;
    error = '';
    try {
      const res = await cleanupOrphans();
      cleanupResult = res;
      await load(); // refresh counts
    } catch (e) {
      error = e.message;
    } finally {
      cleanupRunning = false;
    }
  }

  async function doDebugCleanup() {
    debugCleanupRunning = true;
    debugCleanupResult = null;
    cleanupResult = null;
    error = '';
    try {
      const res = await cleanupDebugData();
      debugCleanupResult = res;
      await load();
    } catch (e) {
      error = e.message;
    } finally {
      debugCleanupRunning = false;
    }
  }

  async function doDelete(sid) {
    const ok = await showConfirm(`Delete session "${sid}"? This removes all its files.`, { confirmLabel: 'Delete', danger: true });
    if (!ok) return;
    deletingId = sid;
    error = '';
    try {
      await deleteSession(sid);
      await load();
    } catch (e) {
      error = e.message;
    } finally {
      deletingId = null;
    }
  }

  async function doDeleteModel(m) {
    const ok = await showConfirm(`Delete "${m.name}" (${fmt(m.size)}) from your system cache? This cannot be undone — you will need to re-download it to use it again.`, { confirmLabel: 'Delete', danger: true });
    if (!ok) return;
    deletingModelPath = m.path;
    modelDeleteError = '';
    try {
      await deleteModelCache(m.path);
      await load();
    } catch (e) {
      modelDeleteError = e.message;
    } finally {
      deletingModelPath = null;
    }
  }

  onMount(load);

  // Mac / Windows shell commands for manual cleanup
  $: macCmd = info ? `rm -rf "${info.downloads_dir}"/* "${info.uploads_dir}"/*` : '';
  $: winCmd = info ? `del /Q "${info.downloads_dir}\\*" & del /Q "${info.uploads_dir}\\*"` : '';
</script>

<div class="sm-backdrop" role="presentation" on:click|self={() => dispatch('close')} on:keydown={(e) => e.key === 'Escape' && dispatch('close')}>
  <div class="sm-panel" role="dialog" aria-label="Storage Manager">
    <div class="sm-header">
      <h2>⚙️ Storage Manager</h2>
      <button class="sm-close" on:click={() => dispatch('close')}>✕</button>
    </div>

    {#if loading}
      <div class="sm-loading">Loading storage info…</div>
    {:else if error}
      <div class="sm-error">❌ {error}</div>
      <button class="sm-btn" on:click={load}>Retry</button>
    {:else if info}
      <!-- Sessions -->
      <div class="sm-section">
        <div class="sm-section-title">📋 Sessions ({info.sessions.length})</div>
        {#if info.sessions.length === 0}
          <p class="sm-hint">No sessions found.</p>
        {:else}
          <div class="sm-session-list">
            {#each info.sessions as s}
              {@const isCurrent = s.id === $currentSessionId}
              <div class="sm-session-row" class:sm-session-current={isCurrent}>
                <div class="sm-session-info">
                  <div class="sm-session-title">
                    {s.artist} — {s.title}
                    {#if isCurrent}<span class="sm-badge">current</span>{/if}
                    <span class="sm-badge sm-badge-status sm-badge-{s.status}">{s.status}</span>
                  </div>
                  <div class="sm-session-meta">
                    {fmtDate(s.created_at)} · {fmt(s.total_size_bytes)}
                    <span class="sm-session-id">id: {s.id.slice(0, 8)}</span>
                  </div>
                  {#if s.files.length > 0}
                    <details class="sm-file-details">
                      <summary>{s.files.length} file{s.files.length !== 1 ? 's' : ''}</summary>
                      <div class="sm-file-list">
                        {#each s.files as f}
                          <div class="sm-file-row">
                            <span class="sm-file-label">{f.label}</span>
                            <span class="sm-file-name sm-mono">{f.path.split(/[\\/]/).pop()}</span>
                            <span class="sm-file-size">{fmt(f.size)}</span>
                          </div>
                        {/each}
                      </div>
                    </details>
                  {/if}
                  {#if (s.backup_files || []).length > 0}
                    {@const bkSize = s.backup_files.reduce((acc, f) => acc + f.size, 0)}
                    <details class="sm-file-details">
                      <summary>{s.backup_files.length} backup file{s.backup_files.length !== 1 ? 's' : ''} · {fmt(bkSize)}</summary>
                      <div class="sm-file-list">
                        {#each s.backup_files as f}
                          <div class="sm-file-row">
                            <span class="sm-file-label">backup</span>
                            <span class="sm-file-name sm-mono">{f.path.split(/[\\/]/).pop()}</span>
                            <span class="sm-file-size">{fmt(f.size)}</span>
                          </div>
                        {/each}
                      </div>
                    </details>
                  {/if}
                </div>
                {#if !isCurrent}
                  <button
                    class="sm-btn sm-btn-danger sm-btn-sm"
                    on:click={() => doDelete(s.id)}
                    disabled={deletingId === s.id}
                    title="Delete session and all its files"
                  >
                    {deletingId === s.id ? '⏳' : '🗑'}
                  </button>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Unlinked data — files on disk not tied to any session -->
      <div class="sm-section sm-section-unlinked">
        <div class="sm-section-title">
          🗂 Unlinked Data on Disk
          {#if info.orphan_files.length > 0}
            <span class="sm-orphan-badge">{info.orphan_files.length} file{info.orphan_files.length !== 1 ? 's' : ''} · {fmt(info.orphan_size_bytes)}</span>
          {:else}
            <span class="sm-orphan-badge sm-orphan-clean">clean ✓</span>
          {/if}
        </div>
        <p class="sm-hint">Files found on disk that can't be connected to any session (excluding known debug artifacts).</p>
        {#if info.orphan_files.length === 0}
          <p class="sm-hint sm-hint-ok">✓ Nothing to clean up.</p>
        {:else}
          <details class="sm-orphan-details">
            <summary>Show {info.orphan_files.length} file{info.orphan_files.length !== 1 ? 's' : ''}</summary>
            <div class="sm-file-list">
              {#each info.orphan_files as f}
                <div class="sm-file-row">
                  <span class="sm-file-name">{f.name}</span>
                  <span class="sm-file-size">{fmt(f.size)}</span>
                </div>
              {/each}
            </div>
          </details>
          <button class="sm-btn sm-btn-danger" on:click={doCleanup} disabled={cleanupRunning}>
            {cleanupRunning ? '⏳ Cleaning…' : '🗑 Delete Unlinked Files'}
          </button>
          {#if cleanupResult}
            <p class="sm-success">✅ Deleted {cleanupResult.deleted.length} files.{cleanupResult.errors.length > 0 ? ` ${cleanupResult.errors.length} errors.` : ''}</p>
          {/if}
        {/if}
      </div>

      <!-- Debug data — known diagnostics generated by alignment -->
      <div class="sm-section sm-section-debug">
        <div class="sm-section-title">
          🧪 Debug Data
          {#if (info.debug_files || []).length > 0}
            <span class="sm-orphan-badge sm-debug-badge">{info.debug_files.length} file{info.debug_files.length !== 1 ? 's' : ''} · {fmt(info.debug_size_bytes || 0)}</span>
          {:else}
            <span class="sm-orphan-badge sm-orphan-clean">none</span>
          {/if}
        </div>
        <p class="sm-hint">Known debug artifacts (for troubleshooting alignment). They are not session-linked files.</p>
        {#if (info.debug_files || []).length > 0}
          <div class="sm-action-row">
            <div class="sm-action-content">
              <details class="sm-orphan-details">
                <summary>Show {info.debug_files.length} file{info.debug_files.length !== 1 ? 's' : ''}</summary>
                <div class="sm-file-list">
                  {#each info.debug_files as f}
                    <div class="sm-file-row">
                      <span class="sm-file-name">{f.name}</span>
                      <span class="sm-file-size">{fmt(f.size)}</span>
                    </div>
                  {/each}
                </div>
              </details>
              {#if debugCleanupResult}
                <p class="sm-success">✅ Deleted {debugCleanupResult.deleted.length} debug file{debugCleanupResult.deleted.length !== 1 ? 's' : ''}.{debugCleanupResult.errors.length > 0 ? ` ${debugCleanupResult.errors.length} errors.` : ''}</p>
              {/if}
            </div>
            <button
              class="sm-btn sm-btn-danger sm-btn-sm"
              on:click={doDebugCleanup}
              disabled={debugCleanupRunning}
              title="Delete debug files"
              aria-label="Delete debug files"
            >
              {debugCleanupRunning ? '⏳' : '🗑'}
            </button>
          </div>
        {/if}
      </div>

      <!-- AI Models -->
      {#if (info.models || []).length > 0}
        {@const totalModelSize = info.models.reduce((acc, m) => acc + (m.size || 0), 0)}
        <div class="sm-section">
          <div class="sm-section-title">🤖 AI Models <span class="sm-orphan-badge sm-orphan-clean">{fmt(totalModelSize)}</span></div>
          <p class="sm-hint">Downloaded models and tools: vocal separation, transcription, alignment, notes and YouTube downloads. Most live in your system cache and are shared across tools. A deleted one is downloaded again when needed.</p>
          {#if modelDeleteError}<p class="sm-error">❌ {modelDeleteError}</p>{/if}
          <div class="sm-file-list">
            {#each info.models as m}
              {@const inUse = m.in_use ?? (m.name.includes('faster-whisper-medium') || m.name.includes('Demucs') || m.name.includes('Alignment'))}
              <div class="sm-file-row">
                <span class="sm-file-label" title={m.use || ''}>{m.name}{#if inUse} <span class="sm-badge" title="Used by this app">in use</span>{/if}{#if m.use}<span class="sm-model-use">{m.use}</span>{/if}</span>
                <span class="sm-file-name sm-mono" title={m.path}>{m.path.replace(/.*[\\/]/, '…/')}</span>
                <span class="sm-file-size">{fmt(m.size)}</span>
                <button
                  class="sm-btn sm-btn-danger sm-btn-sm"
                  on:click={() => doDeleteModel(m)}
                  disabled={deletingModelPath === m.path}
                  title="Delete from system cache"
                >{deletingModelPath === m.path ? '⏳' : '🗑'}</button>
              </div>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Storage paths -->
      <div class="sm-section">
        <div class="sm-section-title">📁 Storage Locations</div>
        <div class="sm-path-row"><span class="sm-path-label">Sessions</span><code class="sm-path">{info.sessions_dir}</code></div>
        <div class="sm-path-row"><span class="sm-path-label">Downloads</span><code class="sm-path">{info.downloads_dir}</code></div>
        <div class="sm-path-row"><span class="sm-path-label">Uploads</span><code class="sm-path">{info.uploads_dir}</code></div>
      </div>

      <!-- Manual cleanup commands -->
      <div class="sm-section sm-section-manual">
        <div class="sm-section-title">🖥 Manual Cleanup Commands (Full Wipe)</div>
        <p class="sm-hint">⚠️ These commands delete all files in downloads/uploads, including files used by active sessions. They are not session-aware.</p>
        <div class="sm-cmd-block">
          <span class="sm-cmd-os">macOS / Linux</span>
          <code class="sm-cmd">{macCmd}</code>
        </div>
        <div class="sm-cmd-block">
          <span class="sm-cmd-os">Windows</span>
          <code class="sm-cmd">{winCmd}</code>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  .sm-model-use {
    display: block;
    color: #777;
    font-size: 0.72rem;
    font-weight: normal;
  }

  .sm-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.65);
    z-index: 2000;
    display: flex;
    align-items: flex-start;
    justify-content: flex-end;
    padding: 3.5rem 1rem 1rem;
  }

  .sm-panel {
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 10px;
    width: min(640px, 96vw);
    max-height: calc(100vh - 5rem);
    overflow-y: auto;
    box-shadow: 0 8px 32px rgba(0,0,0,0.6);
    display: flex;
    flex-direction: column;
  }

  .sm-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.25rem 0.75rem;
    border-bottom: 1px solid #2a2a4e;
    position: sticky;
    top: 0;
    background: #1a1a2e;
    z-index: 1;
  }

  .sm-header h2 {
    margin: 0;
    font-size: 1.1rem;
    color: #e0e0e0;
  }

  .sm-close {
    background: none;
    border: none;
    color: #888;
    font-size: 1.1rem;
    cursor: pointer;
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
  }
  .sm-close:hover { color: #fff; background: #333; }

  .sm-loading, .sm-error {
    padding: 2rem;
    text-align: center;
    color: #aaa;
  }
  .sm-error { color: #ef5350; }

  .sm-section {
    padding: 0.9rem 1.25rem;
    border-bottom: 1px solid #1e2040;
  }
  .sm-section:last-child { border-bottom: none; }
  .sm-section-manual { background: #141428; }

  .sm-section-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: #7986cb;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.5rem;
  }

  .sm-hint { font-size: 0.85rem; color: #888; margin: 0.2rem 0 0.5rem; }
  .sm-success { font-size: 0.85rem; color: #66bb6a; margin: 0.3rem 0 0; }

  .sm-path-row {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    margin-bottom: 0.3rem;
  }
  .sm-path-label { font-size: 0.8rem; color: #888; min-width: 6rem; }
  .sm-path { font-size: 0.75rem; color: #b0bec5; background: #111; padding: 0.15rem 0.4rem; border-radius: 4px; word-break: break-all; }

  .sm-btn {
    display: inline-block;
    padding: 0.35rem 0.85rem;
    background: #2a3a6e;
    border: 1px solid #3a4a8e;
    color: #c5cae9;
    border-radius: 5px;
    cursor: pointer;
    font-size: 0.82rem;
    margin-top: 0.4rem;
  }
  .sm-btn:hover:not(:disabled) { background: #354a90; }
  .sm-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .sm-btn-danger { background: #4a1a1a; border-color: #7a2a2a; color: #ef9a9a; }
  .sm-btn-danger:hover:not(:disabled) { background: #5a2020; }
  .sm-btn-sm { padding: 0.2rem 0.55rem; font-size: 0.78rem; }

  .sm-session-list { display: flex; flex-direction: column; gap: 0.5rem; }

  .sm-session-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
    background: #11112a;
    border: 1px solid #1e2040;
    border-radius: 6px;
    padding: 0.55rem 0.75rem;
  }
  .sm-session-current { border-color: #4fc3f7; }

  .sm-action-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .sm-action-content { flex: 1; min-width: 0; }

  .sm-session-info { flex: 1; min-width: 0; }
  .sm-session-title { font-size: 0.9rem; color: #ddd; font-weight: 500; display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; }
  .sm-session-meta { font-size: 0.75rem; color: #666; margin-top: 0.15rem; }
  .sm-session-id { margin-left: 0.5rem; font-family: monospace; color: #444; }

  .sm-badge {
    display: inline-block;
    font-size: 0.68rem;
    padding: 0.1rem 0.4rem;
    border-radius: 10px;
    background: #2a2a4e;
    color: #9fa8da;
    font-weight: 600;
    text-transform: uppercase;
  }
  .sm-badge-generated { background: #1b3a1b; color: #66bb6a; }
  .sm-badge-uploaded, .sm-badge-created { background: #2a3a5e; color: #90caf9; }
  .sm-badge-generation_failed { background: #3a1a1a; color: #ef9a9a; }

  .sm-section-unlinked { border-left: 3px solid #7a4a00; }
  .sm-section-debug { border-left: 3px solid #2f4f7f; }

  .sm-orphan-badge {
    display: inline-block;
    margin-left: 0.5rem;
    font-size: 0.75rem;
    padding: 0.1rem 0.5rem;
    border-radius: 10px;
    background: #3a2a0a;
    color: #ffb74d;
    font-weight: 600;
    text-transform: none;
    letter-spacing: 0;
    vertical-align: middle;
  }
  .sm-orphan-clean { background: #1b3a1b; color: #66bb6a; }
  .sm-debug-badge { background: #1b2f4d; color: #90caf9; }
  .sm-hint-ok { color: #66bb6a; }

  .sm-orphan-details, .sm-file-details { margin: 0.4rem 0; }
  .sm-orphan-details summary, .sm-file-details summary {
    font-size: 0.8rem; color: #888; cursor: pointer; user-select: none;
  }

  .sm-file-list { margin-top: 0.35rem; display: flex; flex-direction: column; gap: 0.15rem; }
  .sm-file-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.75rem;
    color: #aaa;
    padding: 0.1rem 0.25rem;
  }
  .sm-file-label { color: #7986cb; min-width: 6rem; font-size: 0.72rem; }
  .sm-file-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sm-mono { font-family: monospace; }
  .sm-file-size { color: #666; min-width: 4rem; text-align: right; white-space: nowrap; }

  .sm-cmd-block { margin-bottom: 0.6rem; }
  .sm-cmd-os { display: block; font-size: 0.75rem; color: #7986cb; margin-bottom: 0.2rem; }
  .sm-cmd {
    display: block;
    background: #0d0d1a;
    border: 1px solid #222;
    border-radius: 5px;
    padding: 0.45rem 0.75rem;
    font-size: 0.78rem;
    color: #a5d6a7;
    font-family: 'Menlo', 'Consolas', monospace;
    word-break: break-all;
    white-space: pre-wrap;
    user-select: all;
  }
</style>
