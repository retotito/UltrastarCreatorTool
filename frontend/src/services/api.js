/**
 * API service — all AJAX calls to the backend.
 * 
 * Uses the Vite proxy so all requests go to /api/... 
 * which gets forwarded to http://localhost:8001/api/...
 */

const BASE = '/api';

async function request(method, path, body = null, isFormData = false) {
  const url = `${BASE}${path}`;
  const options = { method };

  if (body) {
    if (isFormData) {
      options.body = body;
    } else {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(body);
    }
  }

  console.log(`[API] ${method} ${url}`);
  const response = await fetch(url, options);
  
  if (!response.ok) {
    let errorDetail = '';
    try {
      const errData = await response.json();
      errorDetail = errData.detail || errData.message || response.statusText;
    } catch {
      errorDetail = response.statusText;
    }
    console.error(`[API] ❌ ${method} ${url} → ${response.status}: ${errorDetail}`);
    throw new Error(`API error ${response.status}: ${errorDetail}`);
  }

  const data = await response.json();
  console.log(`[API] ✅ ${method} ${url} →`, data);
  return data;
}

// ─── Health ────────────────────────────────────
export async function checkHealth() {
  return request('GET', '/health');
}
// ─── Sessions ──────────────────────────────────────────────
export async function listSessions() {
  return request('GET', '/sessions');
}

export async function deleteSession(sessionId) {
  return request('DELETE', `/sessions/${sessionId}`);
}

export async function resumeSession(sessionId) {
  return request('POST', `/resume/${sessionId}`);
}

export async function importUltrastar(txtFile, audioFile) {
  const form = new FormData();
  form.append('txt_file', txtFile);
  form.append('audio_file', audioFile);
  return request('POST', '/import', form, true);
}
// ─── Step 1: Upload ────────────────────────────
export async function uploadAudio(file) {
  const form = new FormData();
  form.append('audio', file);
  return request('POST', '/upload', form, true);
}

export async function extractVocals(sessionId) {
  return request('POST', `/extract-vocals/${sessionId}`);
}

export async function uploadCorrectedVocals(sessionId, file) {
  const form = new FormData();
  form.append('vocals', file);
  return request('POST', `/upload-vocals/${sessionId}`, form, true);
}

export function getAudioUrl(sessionId, type) {
  const url = `${BASE}/preview-audio/${sessionId}/${type}`;
  console.log(`[API] Audio URL: ${url}`);
  return url;
}

// ─── Step 2: Lyrics ────────────────────────────
export async function transcribeAudio(sessionId, language = 'en') {
  const form = new FormData();
  form.append('language', language);
  return request('POST', `/transcribe/${sessionId}`, form, true);
}

export async function submitLyrics(sessionId, lyrics, artist, title, language) {
  const form = new FormData();
  form.append('lyrics', lyrics);
  form.append('artist', artist);
  form.append('title', title);
  form.append('language', language);
  return request('POST', `/lyrics/${sessionId}`, form, true);
}

export async function hyphenateLyrics(lyrics, language = 'en') {
  const form = new FormData();
  form.append('lyrics', lyrics);
  form.append('language', language);
  return request('POST', '/hyphenate', form, true);
}

export async function getTestLyrics() {
  return request('GET', '/test-lyrics');
}

// ─── Test session ──────────────────────────────
export async function loadTestSession() {
  return request('POST', '/load-test-session');
}

export async function resumeLastSession() {
  return request('POST', '/resume-last');
}

// ─── Step 3: Generate ──────────────────────────
export async function generateUltrastar(sessionId) {
  return request('POST', `/generate/${sessionId}`);
}

export async function getGenerationResult(sessionId) {
  return request('GET', `/generate/result/${sessionId}`);
}

// ─── Step 4: Editor ────────────────────────────
export async function getEditorData(sessionId) {
  return request('GET', `/editor-data/${sessionId}`);
}

export async function saveCorrections(sessionId, corrections) {
  return request('POST', `/corrections/${sessionId}`, corrections);
}

export async function applyBpm(sessionId, bpm, gapMs) {
  const form = new FormData();
  form.append('bpm', bpm);
  form.append('gap_ms', gapMs);
  return request('POST', `/apply-bpm/${sessionId}`, form, true);
}

export async function saveEditorState(sessionId, notes, bpm, gapMs) {
  return request('POST', `/save-editor/${sessionId}`, { notes, bpm, gap_ms: gapMs });
}

// ─── Step 5: Export ────────────────────────────
export async function exportFiles(sessionId, correctedContent = null) {
  if (correctedContent) {
    const form = new FormData();
    form.append('corrected_content', correctedContent);
    return request('POST', `/export/${sessionId}`, form, true);
  }
  return request('POST', `/export/${sessionId}`);
}

export function getDownloadUrl(sessionId, fileType) {
  return `${BASE}/download/${sessionId}/${fileType}`;
}

// ─── Reference Comparison ──────────────────────
export async function uploadReference(sessionId, file) {
  const form = new FormData();
  form.append('reference', file);
  return request('POST', `/reference/upload/${sessionId}`, form, true);
}

export async function compareReference(sessionId) {
  return request('POST', `/reference/compare/${sessionId}`);
}

export async function getReferenceStats() {
  return request('GET', '/reference/stats');
}

export async function getReferenceNotes(sessionId) {
  return request('GET', `/reference/notes/${sessionId}`);
}
