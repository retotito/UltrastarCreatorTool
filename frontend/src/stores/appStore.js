/**
 * Shared application state using Svelte writable stores.
 */
import { writable, derived } from 'svelte/store';

// Current step (0 = launcher, 1-5 = wizard)
const savedStep = parseInt(localStorage.getItem('currentStep')) || 0;
export const currentStep = writable(savedStep);
currentStep.subscribe(v => localStorage.setItem('currentStep', String(v)));

// Session ID from backend
const savedSession = localStorage.getItem('sessionId') || null;
export const sessionId = writable(savedSession);
sessionId.subscribe(v => {
  if (v) localStorage.setItem('sessionId', v);
  else localStorage.removeItem('sessionId');
});

// Step 1: Upload data
export const uploadData = writable({
  filename: null,
  hasVocals: false,
  hasOriginal: false,
  vocalUrl: null,
});

// Step 2: Lyrics data
export const lyricsData = writable({
  text: '',
  artist: '',
  title: '',
  language: 'en',
  syllableCount: 0,
  lineCount: 0,
  preview: [],
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

// Steps definition
export const steps = [
  { num: 1, label: 'Upload', icon: '📁' },
  { num: 2, label: 'Lyrics', icon: '📝' },
  { num: 3, label: 'Generate', icon: '⚙️' },
  { num: 4, label: 'Editor', icon: '🎹' },
  { num: 5, label: 'Export', icon: '💾' },
];

// Can navigate to a step?
export const canGoToStep = derived(
  [currentStep, sessionId, uploadData, lyricsData, generationResult],
  ([$currentStep, $sessionId, $uploadData, $lyricsData, $generationResult]) => {
    return (step) => {
      if (step === 1) return true;
      if (step === 2) return $uploadData.hasVocals || $uploadData.hasOriginal;
      if (step === 3) return $lyricsData.syllableCount > 0;
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
  currentStep.set(0);
  sessionId.set(null);
  uploadData.set({ filename: null, hasVocals: false, hasOriginal: false, vocalUrl: null });
  lyricsData.set({ text: '', artist: '', title: '', language: 'en', syllableCount: 0, lineCount: 0, preview: [] });
  generationResult.set(null);
  generationLog.set([]);
  generationShowPreview.set(false);
  editorState.set({ notes: [], hasChanges: false });
  isProcessing.set(false);
  processingStatus.set('');
  errorMessage.set('');
}
