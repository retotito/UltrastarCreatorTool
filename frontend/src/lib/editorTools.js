// The editor's toolbar controls that can be hidden from the top bar's layout menu (small screens). Everything is shown
// until the user hides it. Hiding only removes the control: shortcuts keep working, and a tool in use shows anyway
// (Step4Editor's show… values).
export const EDITOR_TOOLS = [
  { heading: 'Checking pitch', tools: [
    { id: 'mic', label: 'Mic' },
    { id: 'vocal', label: 'Vocal trace' },
    { id: 'pitch', label: 'Pitch line' },
  ] },
  { heading: 'Song timing', tools: [
    { id: 'tap', label: 'Tap (BPM)' },
    { id: 'start', label: 'START' },
    { id: 'end', label: 'END' },
    { id: 'metronome', label: 'Metronome' },
  ] },
  { heading: 'Files', tools: [
    { id: 'fix', label: 'Fix' },
    { id: 'txt', label: '.txt' },
    { id: 'notes', label: 'Notes' },
    { id: 'backup', label: 'Backup' },
  ] },
  { heading: 'Playback', tools: [
    { id: 'jump0', label: 'Jump to 0s' },
    { id: 'jumpGap', label: 'Jump to GAP' },
    { id: 'loop', label: 'Loop' },
    { id: 'scrollMode', label: 'Scroll / Page' },
    { id: 'speed', label: 'Speed' },
  ] },
  { heading: 'Duet', tools: [
    { id: 'duet', label: 'Duet (a duet song always shows it)' },
  ] },
];

const IDS = new Set(EDITOR_TOOLS.flatMap(group => group.tools.map(tool => tool.id)));

/** The hidden tools from their stored JSON. Anything unreadable or unknown (an older version's tool) is ignored. */
export function parseHiddenTools(json) {
  try {
    const stored = JSON.parse(json);
    return new Set(Array.isArray(stored) ? stored.filter(id => IDS.has(id)) : []);
  } catch {
    return new Set();
  }
}

export function toggledTools(hidden, id) {
  const next = new Set(hidden);
  if (!next.delete(id)) next.add(id);
  return next;
}
