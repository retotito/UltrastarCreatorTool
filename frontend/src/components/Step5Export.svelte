<script>
  import { sessionId, generationResult, errorMessage, isProcessing, lyricsData, uploadData, currentStep } from '../stores/appStore.js';
  import { getDownloadUrl, getAudioUrl, updateMetadata, getDownloadZipUrl,
           uploadCover, getCoverUrl, uploadBgImage, getBgImageUrl, saveAssetsMeta, getAssetsMeta } from '../services/api.js';
  import { resetSession } from '../stores/appStore.js';

  let exported = false;
  let showEditPopup = false;
  let editArtist = '';
  let editTitle = '';
  let saving = false;

  // ── Song Assets state ──────────────────────────
  const COVER_DISPLAY = 340;
  const COVER_OUTPUT  = 480;

  // BG crop display: 16:9 at a reasonable width
  const BG_DISPLAY_W = 480;
  const BG_DISPLAY_H = 270; // 16:9
  const BG_OUTPUT_W  = 1920;
  const BG_OUTPUT_H  = 1080;

  // Cover
  let coverPreviewUrl = null;
  let coverUploading = false;
  let showCropModal = false;
  let cropImg = null;
  let cropCanvasEl;
  let cropPanX = 0, cropPanY = 0, cropScale = 1;
  let cropDragging = false, cropDragStartX = 0, cropDragStartY = 0, cropPanStartX = 0, cropPanStartY = 0;

  // Background image
  let bgPreviewUrl = null;
  let bgUploading = false;
  let showBgCropModal = false;
  let bgCropImg = null;
  let bgCropCanvasEl;
  let bgCropPanX = 0, bgCropPanY = 0, bgCropScale = 1;
  let bgCropDragging = false, bgCropDragStartX = 0, bgCropDragStartY = 0, bgCropPanStartX = 0, bgCropPanStartY = 0;

  // Video
  let videoFilename = '';
  let videoGap = 0;
  let videoSaved = false;
  let videoSaving = false;

  // Try to load existing assets when session is known
  $: if ($sessionId) loadExistingAssets();

  async function loadExistingAssets() {
    // Probe cover
    try {
      const r = await fetch(getCoverUrl($sessionId));
      if (r.ok) coverPreviewUrl = getCoverUrl($sessionId) + '?t=' + Date.now();
    } catch (_) {}
    // Probe bg image
    try {
      const r = await fetch(getBgImageUrl($sessionId));
      if (r.ok) bgPreviewUrl = getBgImageUrl($sessionId) + '?t=' + Date.now();
    } catch (_) {}
    // Load video meta
    try {
      const meta = await getAssetsMeta($sessionId);
      if (meta?.video_filename) videoFilename = meta.video_filename;
      if (meta?.video_gap != null) videoGap = meta.video_gap;
    } catch (_) {}
  }

  // ── Cover crop ────────────────────────────────
  function onCoverFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    openCropModal(file);
  }

  function onCoverDrop(e) {
    e.preventDefault();
    const file = e.dataTransfer?.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    openCropModal(file);
  }

  function openCropModal(file) {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        cropImg = img;
        const scale = Math.max(COVER_DISPLAY / img.width, COVER_DISPLAY / img.height);
        cropScale = scale;
        cropPanX = (COVER_DISPLAY - img.width * scale) / 2;
        cropPanY = (COVER_DISPLAY - img.height * scale) / 2;
        showCropModal = true;
      };
      img.src = ev.target.result;
    };
    reader.readAsDataURL(file);
  }

  function cropMouseDown(e) {
    cropDragging = true;
    cropDragStartX = e.clientX; cropDragStartY = e.clientY;
    cropPanStartX = cropPanX;   cropPanStartY = cropPanY;
  }
  function cropMouseMove(e) {
    if (!cropDragging) return;
    cropPanX = cropPanStartX + (e.clientX - cropDragStartX);
    cropPanY = cropPanStartY + (e.clientY - cropDragStartY);
    drawCrop();
  }
  function cropMouseUp() { cropDragging = false; }
  function cropWheel(e) {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    const cx = COVER_DISPLAY / 2, cy = COVER_DISPLAY / 2;
    cropPanX = cx + (cropPanX - cx) * factor;
    cropPanY = cy + (cropPanY - cy) * factor;
    cropScale *= factor;
    drawCrop();
  }
  function drawCrop() {
    if (!cropCanvasEl || !cropImg) return;
    const ctx = cropCanvasEl.getContext('2d');
    ctx.clearRect(0, 0, COVER_DISPLAY, COVER_DISPLAY);
    ctx.drawImage(cropImg, cropPanX, cropPanY, cropImg.width * cropScale, cropImg.height * cropScale);
  }
  $: if (showCropModal && cropCanvasEl && cropImg) drawCrop();

  async function confirmCrop() {
    const offscreen = document.createElement('canvas');
    offscreen.width = COVER_OUTPUT;
    offscreen.height = COVER_OUTPUT;
    const ctx = offscreen.getContext('2d');
    const ratio = COVER_OUTPUT / COVER_DISPLAY;
    ctx.drawImage(cropImg,
      cropPanX * ratio, cropPanY * ratio,
      cropImg.width * cropScale * ratio,
      cropImg.height * cropScale * ratio
    );
    offscreen.toBlob(async (blob) => {
      showCropModal = false;
      if (!blob) return;
      coverUploading = true;
      try {
        await uploadCover($sessionId, blob);
        coverPreviewUrl = getCoverUrl($sessionId) + '?t=' + Date.now();
      } finally {
        coverUploading = false;
      }
    }, 'image/jpeg', 0.90);
  }

  function removeCover() { coverPreviewUrl = null; }

  // ── Background crop ───────────────────────────
  function onBgFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    openBgCropModal(file);
  }

  function onBgDrop(e) {
    e.preventDefault();
    const file = e.dataTransfer?.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    openBgCropModal(file);
  }

  function openBgCropModal(file) {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        bgCropImg = img;
        const scale = Math.max(BG_DISPLAY_W / img.width, BG_DISPLAY_H / img.height);
        bgCropScale = scale;
        bgCropPanX = (BG_DISPLAY_W - img.width * scale) / 2;
        bgCropPanY = (BG_DISPLAY_H - img.height * scale) / 2;
        showBgCropModal = true;
      };
      img.src = ev.target.result;
    };
    reader.readAsDataURL(file);
  }

  function bgCropMouseDown(e) {
    bgCropDragging = true;
    bgCropDragStartX = e.clientX; bgCropDragStartY = e.clientY;
    bgCropPanStartX = bgCropPanX; bgCropPanStartY = bgCropPanY;
  }
  function bgCropMouseMove(e) {
    if (!bgCropDragging) return;
    bgCropPanX = bgCropPanStartX + (e.clientX - bgCropDragStartX);
    bgCropPanY = bgCropPanStartY + (e.clientY - bgCropDragStartY);
    drawBgCrop();
  }
  function bgCropMouseUp() { bgCropDragging = false; }
  function bgCropWheel(e) {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    const cx = BG_DISPLAY_W / 2, cy = BG_DISPLAY_H / 2;
    bgCropPanX = cx + (bgCropPanX - cx) * factor;
    bgCropPanY = cy + (bgCropPanY - cy) * factor;
    bgCropScale *= factor;
    drawBgCrop();
  }
  function drawBgCrop() {
    if (!bgCropCanvasEl || !bgCropImg) return;
    const ctx = bgCropCanvasEl.getContext('2d');
    ctx.clearRect(0, 0, BG_DISPLAY_W, BG_DISPLAY_H);
    ctx.drawImage(bgCropImg, bgCropPanX, bgCropPanY, bgCropImg.width * bgCropScale, bgCropImg.height * bgCropScale);
  }
  $: if (showBgCropModal && bgCropCanvasEl && bgCropImg) drawBgCrop();

  async function confirmBgCrop() {
    const offscreen = document.createElement('canvas');
    offscreen.width = BG_OUTPUT_W;
    offscreen.height = BG_OUTPUT_H;
    const ctx = offscreen.getContext('2d');
    const ratioW = BG_OUTPUT_W / BG_DISPLAY_W;
    const ratioH = BG_OUTPUT_H / BG_DISPLAY_H;
    ctx.drawImage(bgCropImg,
      bgCropPanX * ratioW, bgCropPanY * ratioH,
      bgCropImg.width * bgCropScale * ratioW,
      bgCropImg.height * bgCropScale * ratioH
    );
    offscreen.toBlob(async (blob) => {
      showBgCropModal = false;
      if (!blob) return;
      bgUploading = true;
      try {
        await uploadBgImage($sessionId, blob);
        bgPreviewUrl = getBgImageUrl($sessionId) + '?t=' + Date.now();
      } finally {
        bgUploading = false;
      }
    }, 'image/jpeg', 0.90);
  }

  function removeBg() { bgPreviewUrl = null; }

  // ── Video meta ────────────────────────────────
  async function saveVideoMeta() {
    videoSaving = true;
    videoSaved = false;
    try {
      await saveAssetsMeta($sessionId, videoFilename.trim(), videoFilename.trim() ? videoGap : null);
      videoSaved = true;
      setTimeout(() => { videoSaved = false; }, 2000);
    } finally {
      videoSaving = false;
    }
  }

  $: hasArtist = !!($lyricsData?.artist?.trim());
  $: hasTitle = !!($lyricsData?.title?.trim());
  $: missingInfo = !hasArtist || !hasTitle;

  function getBaseFilename() {
    const artist = ($lyricsData?.artist || '').trim();
    const title = ($lyricsData?.title || '').trim();
    if (artist && title) return `${artist} - ${title}`;
    if (title) return title;
    if (artist) return artist;
    return 'Untitled Song';
  }

  function openEditPopup() {
    editArtist = $lyricsData?.artist || '';
    editTitle = $lyricsData?.title || '';
    showEditPopup = true;
  }

  async function saveMetadata() {
    saving = true;
    try {
      await updateMetadata($sessionId, editArtist.trim(), editTitle.trim());
      lyricsData.update(d => ({ ...d, artist: editArtist.trim(), title: editTitle.trim() }));
      showEditPopup = false;
    } catch (e) {
      console.error('Failed to save metadata:', e);
    } finally {
      saving = false;
    }
  }

  function handleEditKeydown(e) {
    if (e.key === 'Enter') saveMetadata();
    if (e.key === 'Escape') showEditPopup = false;
  }

  function downloadZip() {
    const url = getDownloadZipUrl($sessionId);
    const a = document.createElement('a');
    a.href = url;
    a.download = getBaseFilename() + '.zip';
    document.body.appendChild(a);
    a.click();
    a.remove();
    exported = true;
  }

  function downloadFile(type) {
    const url = getDownloadUrl($sessionId, type);
    const base = getBaseFilename();
    const extMap = { txt: '.txt', midi: '.mid', summary: '_summary.txt' };
    const a = document.createElement('a');
    a.href = url;
    a.download = base + (extMap[type] || '.txt');
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function downloadAudio(type) {
    const url = getAudioUrl($sessionId, type);
    const base = getBaseFilename();
    const suffix = type === 'vocals' ? ' [Vocals]' : '';
    const a = document.createElement('a');
    a.href = url;
    a.download = base + suffix;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function downloadAll() {
    // Download each file with a small delay so browser doesn't block them
    const files = ['txt'];
    if ($generationResult?.midi_file) files.push('midi');
    if ($generationResult?.summary_file) files.push('summary');

    for (const type of files) {
      downloadFile(type);
      await new Promise(r => setTimeout(r, 300));
    }
    // Download available audio
    if ($uploadData.hasVocals) {
      downloadAudio('vocals');
      await new Promise(r => setTimeout(r, 300));
    }
    if ($uploadData.hasOriginal) {
      downloadAudio('original');
    }
    exported = true;
  }

  function startOver() {
    resetSession();
  }
</script>

<div class="step-content">
  <h2>Step 4: Export & Download</h2>

  {#if $generationResult}
    {#if missingInfo}
      {@const previewArtist = ($lyricsData?.artist || '').trim() || 'Unknown'}
      {@const previewTitle = ($lyricsData?.title || '').trim() || 'Unknown'}
      <div class="info-banner">
        <span>⚠️ {!hasArtist && !hasTitle ? 'Artist and title are' : !hasArtist ? 'Artist is' : 'Title is'} missing — filenames will use "{previewArtist} - {previewTitle}"</span>
        <button class="link-btn" on:click={openEditPopup}>✏️ Add now</button>
      </div>
    {/if}

    <div class="summary-card">
      <div class="summary-header">
        <h3>Song Info</h3>
        <button class="edit-btn" on:click={openEditPopup} title="Edit artist & title">✏️</button>
      </div>
      <div class="summary-grid">
        <div class="summary-item wide">
          <span class="label">Song</span>
          <span class="value">{$lyricsData?.artist || 'Unknown'} — {$lyricsData?.title || 'Untitled'}</span>
        </div>
        <div class="summary-item">
          <span class="label">BPM</span>
          <span class="value">{$generationResult.bpm}</span>
        </div>
        <div class="summary-item">
          <span class="label">GAP</span>
          <span class="value">{$generationResult.gap_ms}ms</span>
        </div>
        <div class="summary-item">
          <span class="label">Notes</span>
          <span class="value">{$generationResult.syllable_count}</span>
        </div>
      </div>
    </div>

    <!-- Song Assets card -->
    <div class="assets-card">
      <h3>Song Assets</h3>

      <div class="assets-grid">
        <!-- Cover image -->
        <div class="asset-row">
          <span class="asset-label">Cover</span>
          {#if coverPreviewUrl}
            <div class="asset-preview">
              <img src={coverPreviewUrl} alt="Cover" class="asset-thumb" />
              <div class="asset-preview-actions">
                <button class="asset-action-btn" on:click={() => document.getElementById('cover-file-input').click()}>✏️ Change</button>
                <a class="asset-action-btn" href={coverPreviewUrl} download="cover.jpg" title="Download">⬇</a>
                <button class="asset-action-btn danger" on:click={removeCover}>✕</button>
              </div>
            </div>
          {:else}
            <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
            <div class="asset-dropzone" class:uploading={coverUploading}
              on:dragover|preventDefault
              on:drop={onCoverDrop}
              on:click={() => !coverUploading && document.getElementById('cover-file-input').click()}
            >
              <span class="dropzone-icon">{coverUploading ? '⏳' : '🖼'}</span>
              <span class="dropzone-hint">{coverUploading ? 'Uploading…' : 'Drop image or click'}<br>{#if !coverUploading}<small>480×480 crop tool</small>{/if}</span>
            </div>
          {/if}
          <input id="cover-file-input" type="file" accept="image/*" style="display:none" on:change={onCoverFileChange} />
        </div>

        <!-- Background image -->
        <div class="asset-row">
          <span class="asset-label">Background</span>
          {#if bgPreviewUrl}
            <div class="asset-preview">
              <img src={bgPreviewUrl} alt="Background" class="asset-thumb asset-thumb-bg" />
              <div class="asset-preview-actions">
                <button class="asset-action-btn" on:click={() => document.getElementById('bg-file-input').click()}>✏️ Change</button>
                <a class="asset-action-btn" href={bgPreviewUrl} download="background.jpg" title="Download">⬇</a>
                <button class="asset-action-btn danger" on:click={removeBg}>✕</button>
              </div>
            </div>
          {:else}
            <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
            <div class="asset-dropzone" class:uploading={bgUploading}
              on:dragover|preventDefault
              on:drop={onBgDrop}
              on:click={() => document.getElementById('bg-file-input').click()}
            >
              <span class="dropzone-icon">{bgUploading ? '⏳' : '🌄'}</span>
              <span class="dropzone-hint">{bgUploading ? 'Uploading…' : 'Drop image or click'}<br>{#if !bgUploading}<small>16:9 crop tool · 1920×1080</small>{/if}</span>
            </div>
          {/if}
          <input id="bg-file-input" type="file" accept="image/*" style="display:none" on:change={onBgFileChange} />
        </div>

        <!-- Video filename -->
        <div class="asset-row asset-row-video">
          <span class="asset-label">Video</span>
          <div class="video-input-row">
            <input
              class="video-filename-input"
              type="text"
              placeholder="filename.mp4 (leave blank to skip)"
              bind:value={videoFilename}
            />
            {#if videoFilename.trim()}
              <input
                class="video-gap-input"
                type="number"
                step="0.1"
                placeholder="Gap"
                title="VIDEOGAP in seconds"
                bind:value={videoGap}
              />
            {/if}
            <button class="asset-save-btn" on:click={saveVideoMeta} disabled={videoSaving}>
              {videoSaved ? '✓' : 'Save'}
            </button>
          </div>
          <span class="video-hint">File name only — place the video file in the song folder</span>
        </div>
      </div>
    </div>

    <div class="download-section">
      <div class="download-header">
        <h3>Download Files</h3>
        <div class="download-header-buttons">
          <button class="btn btn-primary download-all" on:click={downloadZip}>
            📦 Download ZIP
          </button>
          <button class="btn btn-secondary download-all" on:click={downloadAll}>
            ⬇ All Files Individual
          </button>
        </div>
      </div>

      <div class="download-grid">
        <button class="download-btn" on:click={() => downloadFile('txt')}>
          <span class="file-icon">📄</span>
          <span class="file-name">Ultrastar .txt</span>
          <span class="file-desc">Note file for Ultrastar players</span>
        </button>

        {#if $generationResult?.midi_file}
          <button class="download-btn" on:click={() => downloadFile('midi')}>
            <span class="file-icon">🎵</span>
            <span class="file-name">MIDI</span>
            <span class="file-desc">Pitch data as MIDI</span>
          </button>
        {/if}

        <button class="download-btn" on:click={() => downloadAudio('vocals')} disabled={!$uploadData.hasVocals}>
          <span class="file-icon">🎤</span>
          <span class="file-name">Vocals</span>
          <span class="file-desc">{$uploadData.hasVocals ? 'Separated vocal track' : 'Not available'}</span>
        </button>

        <button class="download-btn" on:click={() => downloadAudio('original')} disabled={!$uploadData.hasOriginal}>
          <span class="file-icon">🎶</span>
          <span class="file-name">Full Mix</span>
          <span class="file-desc">{$uploadData.hasOriginal ? 'Original audio file' : 'Not available'}</span>
        </button>

        {#if $generationResult?.summary_file}
          <button class="download-btn" on:click={() => downloadFile('summary')}>
            <span class="file-icon">📋</span>
            <span class="file-name">Summary</span>
            <span class="file-desc">Processing report</span>
          </button>
        {/if}
      </div>
    </div>

    {#if exported}
      <div class="success-banner">✓ Files downloaded</div>
    {/if}

    <div class="actions">
      <button class="btn btn-secondary" on:click={startOver}>
        ↩ Start New Song
      </button>
    </div>
  {:else}
    <p class="no-result">No generation result yet. Go back to Step 3 to generate files.</p>
  {/if}

  {#if $errorMessage}
    <div class="error-bar">❌ {$errorMessage}</div>
  {/if}

  {#if showCropModal}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="modal-overlay" on:click={() => showCropModal = false}>
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="modal crop-modal" on:click|stopPropagation>
        <h3>Crop Cover Image</h3>
        <p class="crop-hint">Drag to pan · Scroll to zoom · Square crop (480×480)</p>
        <canvas
          bind:this={cropCanvasEl}
          width={COVER_DISPLAY}
          height={COVER_DISPLAY}
          class="crop-canvas"
          on:mousedown={cropMouseDown}
          on:mousemove={cropMouseMove}
          on:mouseup={cropMouseUp}
          on:mouseleave={cropMouseUp}
          on:wheel|preventDefault={cropWheel}
        ></canvas>
        <div class="modal-actions">
          <button class="btn btn-secondary" on:click={() => showCropModal = false}>Cancel</button>
          <button class="btn btn-primary" on:click={confirmCrop}>Use this crop</button>
        </div>
      </div>
    </div>
  {/if}

  {#if showBgCropModal}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="modal-overlay" on:click={() => showBgCropModal = false}>
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="modal crop-modal" on:click|stopPropagation>
        <h3>Crop Background Image</h3>
        <p class="crop-hint">Drag to pan · Scroll to zoom · 16:9 crop (1920×1080)</p>
        <canvas
          bind:this={bgCropCanvasEl}
          width={BG_DISPLAY_W}
          height={BG_DISPLAY_H}
          class="crop-canvas"
          on:mousedown={bgCropMouseDown}
          on:mousemove={bgCropMouseMove}
          on:mouseup={bgCropMouseUp}
          on:mouseleave={bgCropMouseUp}
          on:wheel|preventDefault={bgCropWheel}
        ></canvas>
        <div class="modal-actions">
          <button class="btn btn-secondary" on:click={() => showBgCropModal = false}>Cancel</button>
          <button class="btn btn-primary" on:click={confirmBgCrop}>Use this crop</button>
        </div>
      </div>
    </div>
  {/if}

  {#if showEditPopup}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="modal-overlay" on:click={() => showEditPopup = false}>
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="modal" on:click|stopPropagation>
        <h3>Edit Song Info</h3>
        <div class="modal-field">
          <label for="edit-artist">Artist</label>
          <input id="edit-artist" type="text" bind:value={editArtist} placeholder="Artist name" on:keydown={handleEditKeydown} />
        </div>
        <div class="modal-field">
          <label for="edit-title">Title</label>
          <input id="edit-title" type="text" bind:value={editTitle} placeholder="Song title" on:keydown={handleEditKeydown} />
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" on:click={() => showEditPopup = false}>Cancel</button>
          <button class="btn btn-primary" on:click={saveMetadata} disabled={saving}>
            {saving ? 'Saving...' : '💾 Save'}
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .step-content {
    max-width: 600px;
    margin: 0 auto;
  }

  h2 { color: #4fc3f7; margin-bottom: 1rem; }
  h3 { color: #aaa; margin: 0; font-size: 0.95rem; }

  .summary-card {
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 1rem;
  }

  .summary-card h3 { margin-bottom: 0.75rem; }

  .summary-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
  }
  .summary-header h3 { margin-bottom: 0; }

  .edit-btn {
    background: none;
    border: 1px solid #555;
    border-radius: 6px;
    color: #aaa;
    cursor: pointer;
    padding: 0.2rem 0.5rem;
    font-size: 0.8rem;
    transition: all 0.15s;
  }
  .edit-btn:hover {
    border-color: #4fc3f7;
    color: #4fc3f7;
  }

  .summary-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
  }

  .summary-item {
    text-align: center;
  }

  .summary-item.wide {
    grid-column: 1 / -1;
  }

  .label {
    display: block;
    color: #666;
    font-size: 0.75rem;
    text-transform: uppercase;
  }

  .value {
    display: block;
    color: #4fc3f7;
    font-size: 1rem;
    font-weight: 600;
  }

  .download-section {
    margin-top: 1.5rem;
  }

  .download-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
  }

  .download-all {
    font-size: 0.9rem;
    padding: 0.5rem 1.25rem;
  }

  .download-header-buttons {
    display: flex;
    gap: 0.5rem;
  }

  .download-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
  }

  .download-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    padding: 1.25rem 0.5rem;
    border: 1px solid #444;
    border-radius: 8px;
    background: #1a1a2e;
    color: #ccc;
    cursor: pointer;
    transition: all 0.2s;
  }

  .download-btn:hover:not(:disabled) {
    border-color: #4fc3f7;
    background: #1a2e4a;
  }

  .download-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .file-icon { font-size: 2rem; }
  .file-name { font-weight: 600; font-size: 0.9rem; }
  .file-desc { font-size: 0.7rem; color: #666; text-align: center; }

  .success-banner {
    text-align: center;
    padding: 0.5rem;
    margin-top: 1rem;
    background: #1a3a2a;
    border: 1px solid #66bb6a;
    border-radius: 8px;
    color: #66bb6a;
    font-size: 0.85rem;
  }

  .actions {
    margin-top: 2rem;
    text-align: center;
  }

  .btn {
    padding: 0.6rem 1.5rem;
    border: none;
    border-radius: 8px;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .btn-secondary {
    background: #333;
    color: #ccc;
    border: 1px solid #555;
  }
  .btn-secondary:hover { background: #444; }

  .btn-primary {
    background: #238636;
    color: #fff;
  }
  .btn-primary:hover { background: #2ea043; }

  .no-result {
    color: #666;
    text-align: center;
    padding: 2rem;
  }

  .info-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    background: #2a2a1a;
    border: 1px solid #f9a825;
    border-radius: 8px;
    padding: 0.65rem 1rem;
    margin-bottom: 1rem;
    color: #fdd835;
    font-size: 0.85rem;
  }

  .link-btn {
    background: none;
    border: 1px solid #f9a825;
    border-radius: 6px;
    color: #fdd835;
    cursor: pointer;
    padding: 0.3rem 0.75rem;
    font-size: 0.8rem;
    white-space: nowrap;
    transition: all 0.15s;
  }
  .link-btn:hover {
    background: #3a3a2a;
    border-color: #fdd835;
  }

  .error-bar {
    background: #3e1a1a;
    border: 1px solid #c62828;
    border-radius: 8px;
    padding: 0.75rem;
    margin-top: 1rem;
    color: #ef9a9a;
    text-align: center;
  }

  /* Modal overlay & popup */
  .modal-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: #1a1a2e;
    border: 1px solid #444;
    border-radius: 12px;
    padding: 1.5rem;
    width: 360px;
    max-width: 90vw;
  }

  .modal h3 {
    color: #4fc3f7;
    margin: 0 0 1rem;
  }

  .modal-field {
    margin-bottom: 0.75rem;
  }

  .modal-field label {
    display: block;
    color: #888;
    font-size: 0.75rem;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
  }

  .modal-field input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: 1px solid #555;
    border-radius: 6px;
    background: #111;
    color: #eee;
    font-size: 0.95rem;
    box-sizing: border-box;
  }
  .modal-field input:focus {
    outline: none;
    border-color: #4fc3f7;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 1rem;
  }

  /* ── Song Assets card ─────────────────────── */
  .assets-card {
    background: #1a1a2e;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 1rem;
    margin-top: 1rem;
  }

  .assets-card h3 {
    margin-bottom: 0.85rem;
  }

  .assets-grid {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .asset-row {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
  }

  .asset-row-video {
    flex-direction: column;
    gap: 0.35rem;
  }

  .asset-label {
    width: 80px;
    flex-shrink: 0;
    color: #888;
    font-size: 0.8rem;
    text-transform: uppercase;
    padding-top: 0.6rem;
  }

  .asset-dropzone {
    flex: 1;
    display: flex;
    gap: 0.5rem;
    align-items: center;
    border: 1px dashed #444;
    border-radius: 8px;
    padding: 0.65rem 1rem;
    cursor: pointer;
    transition: border-color 0.15s;
    min-height: 52px;
  }
  .asset-dropzone:hover, .asset-dropzone.uploading {
    border-color: #4fc3f7;
  }

  .dropzone-icon { font-size: 1.4rem; }
  .dropzone-hint { font-size: 0.78rem; color: #777; line-height: 1.3; }

  .asset-preview {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex: 1;
  }

  .asset-thumb {
    width: 64px;
    height: 64px;
    object-fit: cover;
    border-radius: 6px;
    border: 1px solid #444;
  }
  .asset-thumb-bg {
    width: 114px;
    height: 64px;
  }

  .asset-preview-actions {
    display: flex;
    gap: 0.4rem;
  }

  .asset-action-btn {
    background: #21262d;
    border: 1px solid #444;
    border-radius: 6px;
    color: #ccc;
    cursor: pointer;
    padding: 0.25rem 0.6rem;
    font-size: 0.78rem;
    transition: all 0.15s;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
  }
  .asset-action-btn:hover { background: #30363d; }
  .asset-action-btn.danger { color: #f44; border-color: #633; }
  .asset-action-btn.danger:hover { background: #3a1a1a; }

  .video-input-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    width: 100%;
  }

  .video-filename-input {
    flex: 1;
    padding: 0.45rem 0.65rem;
    border: 1px solid #444;
    border-radius: 6px;
    background: #111;
    color: #eee;
    font-size: 0.88rem;
  }
  .video-filename-input:focus { outline: none; border-color: #4fc3f7; }

  .video-gap-input {
    width: 72px;
    padding: 0.45rem 0.5rem;
    border: 1px solid #444;
    border-radius: 6px;
    background: #111;
    color: #eee;
    font-size: 0.88rem;
  }
  .video-gap-input:focus { outline: none; border-color: #4fc3f7; }

  .asset-save-btn {
    background: #238636;
    border: none;
    border-radius: 6px;
    color: #fff;
    cursor: pointer;
    padding: 0.45rem 0.9rem;
    font-size: 0.85rem;
    transition: background 0.15s;
    white-space: nowrap;
  }
  .asset-save-btn:hover:not(:disabled) { background: #2ea043; }
  .asset-save-btn:disabled { opacity: 0.5; cursor: default; }

  .video-hint {
    font-size: 0.72rem;
    color: #555;
    margin-left: 82px;
  }

  /* ── Crop modal ───────────────────────────── */
  .crop-modal {
    width: auto;
    max-width: none;
  }

  .crop-hint {
    color: #666;
    font-size: 0.78rem;
    margin: 0.25rem 0 0.75rem;
    text-align: center;
  }

  .crop-canvas {
    display: block;
    cursor: grab;
    border-radius: 4px;
    border: 1px solid #333;
  }
  .crop-canvas:active { cursor: grabbing; }
</style>
