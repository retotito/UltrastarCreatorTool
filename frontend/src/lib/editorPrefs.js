// A new chart (generated or imported) starts with a fresh editor (Step4Editor's per-session keys), set up for checking
// the result: MIDI on, playing the vocals the chart was made from (cleaned → 'edited'; the editor falls back to the full
// mix without vocals). Metronome, speed, playhead, scroll and zoom go back to their defaults. Kept: mic, waveform
// height, dialog position, the user's notes and flags.
export function resetEditorState(id, fromCleaned = false) {
  if (!id) return;
  try {
    const key = `editor_ui_prefs_${id}`;
    const { micDeviceId, waveformHeight, vibratoModalX, vibratoModalY } = JSON.parse(localStorage.getItem(key) || 'null') || {};
    localStorage.setItem(key, JSON.stringify({
      micDeviceId, waveformHeight, vibratoModalX, vibratoModalY,
      midiPlayback: true, audioSource: fromCleaned ? 'edited' : 'vocals',
    }));
    localStorage.removeItem(`editor_scroll_${id}`);
  } catch { /* browser storage unavailable: the editor keeps its old view */ }
}
