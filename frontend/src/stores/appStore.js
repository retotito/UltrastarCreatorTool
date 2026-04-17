/**
 * Shared application state using Svelte writable stores.
 */
import { writable, derived } from 'svelte/store';

// Current step (0 = launcher, 1-5 = wizard; step 3 is now a modal, not a persisted step).
// Always start at 0 (home/launcher) on every app launch — the user chooses to resume.
export const currentStep = writable(0);
currentStep.subscribe(v => {
  // Only persist if not on launcher (step 0)
  if (v > 0) {
    localStorage.setItem('currentStep', String(v));
  } else {
    localStorage.removeItem('currentStep');
  }
});

// Session ID from backend
const savedSession = localStorage.getItem('sessionId') || null;
export const sessionId = writable(savedSession);
sessionId.subscribe(v => {
  if (v) localStorage.setItem('sessionId', v);
  else localStorage.removeItem('sessionId');
});

// Step 1: Upload data
const savedUploadRaw = localStorage.getItem('uploadData');
let initialUpload = {
  filename: null,
  hasVocals: false,
  hasOriginal: false,
  vocalUrl: null,
};
if (savedUploadRaw) {
  try {
    initialUpload = { ...initialUpload, ...JSON.parse(savedUploadRaw) };
  } catch (e) {
    // ignore parse error, use defaults
  }
}
export const uploadData = writable(initialUpload);
uploadData.subscribe(v => {
  // Only persist if any field is non-empty
  const hasData = v.filename || v.hasVocals || v.hasOriginal || v.vocalUrl;
  if (hasData) {
    localStorage.setItem('uploadData', JSON.stringify(v));
  } else {
    localStorage.removeItem('uploadData');
  }
});

// Step 2: Lyrics data
const savedLyricsRaw = localStorage.getItem('lyricsData');
let initialLyrics = {
  text: '',
  artist: '',
  title: '',
  language: 'en',
  syllableCount: 0,
  lineCount: 0,
  preview: [],
};
if (savedLyricsRaw) {
  try {
    initialLyrics = { ...initialLyrics, ...JSON.parse(savedLyricsRaw) };
  } catch (e) {
    // ignore parse error, use defaults
  }
}
export const lyricsData = writable(initialLyrics);
lyricsData.subscribe(v => {
  // Only persist if any field is non-empty
  const hasData = v.text || v.artist || v.title || v.language !== 'en';
  if (hasData) {
    localStorage.setItem('lyricsData', JSON.stringify(v));
  } else {
    localStorage.removeItem('lyricsData');
  }
});

// Step 3: Generation result
export const generationResult = writable(null);

// Step 3: Generation log and comparison (preserved across navigation)
export const generationLog = writable([]);
export const generationShowPreview = writable(false);

// Step 4: Editor state
export const editorState = writable({
  notes: [],
  hasChanges: false,
});

// Processing state
export const isProcessing = writable(false);
export const processingStatus = writable('');
export const errorMessage = writable('');

// Generation modal (Step 3 is a modal, not a navigation step)
export const generationModalOpen = writable(false);

// Steps definition (Step 3 is a modal overlay, not a tab)
export const steps = [
  { num: 1, label: 'Upload', icon: '📁' },
  { num: 2, label: 'Lyrics', icon: '📝' },
  { num: 4, display: 3, label: 'Editor', icon: '🎹' },
  { num: 5, display: 4, label: 'Export', icon: '💾' },
];

// Can navigate to a step?
export const canGoToStep = derived(
  [currentStep, sessionId, uploadData, lyricsData, generationResult],
  ([$currentStep, $sessionId, $uploadData, $lyricsData, $generationResult]) => {
    return (step) => {
      if (step === 1) return true;
      if (step === 2) return $uploadData.hasVocals || $uploadData.hasOriginal;
      if (step === 4) return $generationResult !== null;
      if (step === 5) return $generationResult !== null;
      return false;
    };
  }
);

// Reset everything
export function resetSession() {
  localStorage.removeItem('currentStep');
  localStorage.removeItem('sessionId');
  generationModalOpen.set(false);
  currentStep.set(0);
  sessionId.set(null);
  uploadData.set({ filename: null, hasVocals: false, hasOriginal: false, vocalUrl: null });
  localStorage.removeItem('uploadData');
  lyricsData.set({ text: '', artist: '', title: '', language: 'en', syllableCount: 0, lineCount: 0, preview: [] });
  localStorage.removeItem('lyricsData');
  generationResult.set(null);
  generationLog.set([]);
  generationShowPreview.set(false);
  editorState.set({ notes: [], hasChanges: false });
  isProcessing.set(false);
  processingStatus.set('');
  errorMessage.set('');
}
