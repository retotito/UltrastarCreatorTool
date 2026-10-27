<script>
  export let onClose = () => {};

  function handleKeydown(e) {
    if (e.key === 'Escape') onClose();
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- Backdrop -->
<div class="help-backdrop" on:mousedown|self={onClose}>
  <div class="help-modal">
    <div class="help-header">
      <span class="help-title">? Help &amp; Shortcuts</span>
      <button class="help-close" on:click={onClose}>✕</button>
    </div>

    <div class="help-body">

      <!-- Legend -->
      <section>
        <h3>Legend</h3>
        <div class="legend-grid">
          <div class="legend-item">
            <span class="swatch" style="background:#4fc3f744;border:1px solid #4fc3f7"></span>
            Normal note
          </div>
          <div class="legend-item">
            <span class="swatch" style="background:#ffd70044;border:1px solid #ffd700"></span>
            Golden note (2× points)
          </div>
          <div class="legend-item">
            <span class="swatch" style="background:#ff980044;border:1px solid #ff9800"></span>
            Rap / Freestyle note
          </div>
          <div class="legend-item">
            <span class="swatch" style="background:#ff980044;border:1px solid #ffd700"></span>
            Golden rap note (G)
          </div>
          <div class="legend-item">
            <span class="swatch" style="background:#ef535044;border:1px solid #ef5350"></span>
            Break line (pause)
          </div>
          <div class="legend-item">
            <span class="swatch dot" style="background:#ef5350"></span>
            Red dot = no trailing space (word continues)
          </div>
          <div class="legend-item">
            <span class="swatch dot" style="background:#7ecbf7"></span>
            Blue dot · = has trailing space
          </div>
          <div class="legend-item">
            <span class="swatch" style="background:rgba(0,220,255,0.55)"></span>
            Blue pitch line (reference vocal)
          </div>
          <div class="legend-item">
            <span class="swatch" style="background:rgba(80,240,120,0.7)"></span>
            Green pitch line (recorded patch)
          </div>
          <div class="legend-item">
            <span class="outline-swatch"></span>
            Yellow outline = selected note
          </div>
        </div>
      </section>

      <div class="divider"></div>

      <!-- Shortcuts -->
      <section>
        <h3>Keyboard Shortcuts</h3>
        <div class="shortcuts-grid">

          <div class="shortcut-group">
            <div class="group-label">Playback</div>
            <div class="row"><kbd>Space</kbd> play / pause</div>
            <div class="row"><kbd>←</kbd> <kbd>→</kbd> seek ±5s</div>
            <div class="row"><kbd>Shift+←→</kbd> seek ±1s</div>
            <div class="row"><kbd>L</kbd> toggle loop</div>
            <div class="row"><kbd>M</kbd> mic &nbsp;·&nbsp; <kbd>Shift+M</kbd> trail</div>
            <div class="row"><kbd>V</kbd> vocal trace &nbsp;·&nbsp; <kbd>Shift+V</kbd> show</div>
          </div>

          <div class="shortcut-group">
            <div class="group-label">Navigate</div>
            <div class="row"><kbd>Scroll</kbd> pan horizontally</div>
            <div class="row"><kbd>Ctrl+Scroll</kbd> zoom</div>
            <div class="row"><kbd>,</kbd> prev position</div>
            <div class="row"><kbd>.</kbd> next position</div>
            <div class="row"><kbd>Shift+,</kbd> prev marker</div>
            <div class="row"><kbd>Shift+.</kbd> next marker</div>
            <div class="row"><kbd>⌘/Ctrl+F</kbd> find syllable (or 🔍)</div>
          </div>

          <div class="shortcut-group">
            <div class="group-label">Select</div>
            <div class="row"><kbd>Click</kbd> select note</div>
            <div class="row"><kbd>Ctrl+Click</kbd> multi-select</div>
            <div class="row"><kbd>Ctrl+Drag</kbd> box select</div>
            <div class="row"><kbd>Tab</kbd> next note</div>
            <div class="row"><kbd>Shift+Tab</kbd> previous note</div>
            <div class="row"><kbd>Esc</kbd> deselect</div>
          </div>

          <div class="shortcut-group">
            <div class="group-label">Edit note</div>
            <div class="row"><kbd>Drag</kbd> move</div>
            <div class="row"><kbd>Shift+Drag</kbd> move X only</div>
            <div class="row"><kbd>↑</kbd> <kbd>↓</kbd> pitch ±1 semitone</div>
            <div class="row"><kbd>Ctrl+↑↓</kbd> pitch ±1 octave</div>
            <div class="row"><kbd>Option+←→</kbd> extend to adjacent</div>
            <div class="row"><kbd>Shift+Option+←→</kbd> move boundary</div>
            <div class="row"><kbd>Ctrl+←→</kbd> resize right edge</div>
            <div class="row"><kbd>Shift+Ctrl+←→</kbd> resize left edge</div>
            <div class="row"><kbd>S</kbd> split &nbsp;·&nbsp; <kbd>Del</kbd> delete</div>
            <div class="row"><kbd>N</kbd> new note at cursor &nbsp;·&nbsp; <kbd>Y</kbd> select at playhead</div>
            <div class="row"><kbd>P</kbd> play pitch &nbsp;·&nbsp; <kbd>E</kbd> edit syllable</div>
          </div>

          <div class="shortcut-group">
            <div class="group-label">Clipboard &amp; Tools</div>
            <div class="row"><kbd>Ctrl+X/C/V</kbd> cut / copy / paste</div>
            <div class="row"><kbd>Ctrl+Z</kbd> undo</div>
            <div class="row"><kbd>Shift+Ctrl+Z</kbd> redo</div>
            <div class="row"><kbd>Ctrl+S</kbd> save</div>
            <div class="row"><kbd>Ctrl+G</kbd> set GAP</div>
            <div class="row"><kbd>9</kbd> MIDI &nbsp;·&nbsp; <kbd>0</kbd> metronome</div>
          </div>

        </div>
      </section>

    </div>
  </div>
</div>

<style>
  .help-backdrop {
    position: fixed;
    inset: 0;
    z-index: 2000;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .help-modal {
    background: #0f1420;
    border: 1px solid #2a3040;
    border-radius: 10px;
    width: min(900px, 95vw);
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.7);
    overflow: hidden;
  }

  .help-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid #1e2433;
    flex-shrink: 0;
  }

  .help-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #90caf9;
  }

  .help-close {
    background: none;
    border: none;
    color: #546e7a;
    cursor: pointer;
    font-size: 1rem;
    padding: 2px 6px;
  }
  .help-close:hover { color: #ef9a9a; }

  .help-body {
    overflow-y: auto;
    padding: 18px 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  section h3 {
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #4fc3f7;
    margin: 0 0 10px 0;
  }

  /* Legend */
  .legend-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 24px;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 0.78rem;
    color: #9ea8b3;
  }

  .swatch {
    display: inline-block;
    width: 28px;
    height: 12px;
    border-radius: 2px;
    flex-shrink: 0;
  }

  .swatch.dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .outline-swatch {
    display: inline-block;
    width: 28px;
    height: 12px;
    border-radius: 3px;
    border: 1.5px solid #ffe082;
    flex-shrink: 0;
  }

  .divider {
    height: 1px;
    background: #1e2433;
  }

  /* Shortcuts */
  .shortcuts-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 16px 28px;
  }

  .shortcut-group {
    min-width: 200px;
    flex: 1;
  }

  .group-label {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #607d8b;
    margin-bottom: 6px;
  }

  .row {
    font-size: 0.76rem;
    color: #7a8a96;
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    gap: 3px;
    flex-wrap: wrap;
  }

  kbd {
    display: inline-block;
    background: #1a1f2b;
    border: 1px solid #2a3040;
    border-radius: 3px;
    padding: 1px 5px;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 0.68rem;
    color: #aab;
    line-height: 1.5;
    white-space: nowrap;
  }
</style>
