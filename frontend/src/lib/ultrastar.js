/**
 * Parse an Ultrastar .txt content string into an array of note objects.
 *
 * Each note object has:
 *   { id, startBeat, duration, pitch, syllable, isRap, isGolden, isFreestyle, confidence, original }
 * Break lines produce:
 *   { id, type: 'break', startBeat, endBeat }
 * In a duet (P1/P2 tracks) notes and breaks also have `singer`: 1, 2 or 'both' (in both tracks, read as one
 * element; an old chart's P3 too), sorted by beat. Twin of backend/services/duet.py.
 */
export function parseUltrastar(content) {
  const lines = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const parsed = [];
  let id = 0;
  let singer = null; // the current track's singer in a duet

  for (const line of lines) {
    const trimmed = line.trimStart(); // trimStart only — trailing space is part of the syllable
    const marker = trackMarker(trimmed);
    if (marker !== null) {
      singer = marker;
      continue;
    }
    if (trimmed.startsWith('*') || trimmed.startsWith(':') || trimmed.startsWith('R ') || trimmed.startsWith('R:') || trimmed.startsWith('F:') || trimmed.startsWith('F ') || trimmed === 'F') {
      const isGolden = trimmed.startsWith('*');
      // R is the standard rap prefix; F: is accepted as legacy
      const isRap = trimmed.startsWith('R ') || trimmed.startsWith('R:') || trimmed.startsWith('F:');
      const isFreestyle = !isRap && trimmed.startsWith('F');
      let prefix;
      if (isRap && (trimmed.startsWith('R ') || trimmed.startsWith('R:'))) prefix = trimmed.startsWith('R:') ? 'R:' : 'R';
      else if (isRap) prefix = 'F:'; // legacy
      else if (isFreestyle) prefix = 'F';
      else if (isGolden) prefix = '*';
      else prefix = ':';
      // Parse 3 numeric fields, then preserve the rest as syllable text
      // (including any leading space which signals a word boundary in Ultrastar)
      const rest = trimmed.substring(prefix.length);
      const match = rest.match(/^\s+(-?\d+)\s+(\d+)\s+(-?\d+) (.*)$/);

      if (match) {
        const startBeat = parseInt(match[1]);
        const duration = parseInt(match[2]);
        const pitch = parseInt(match[3]);
        const syllable = match[4];

        parsed.push({
          id: id++,
          startBeat,
          duration,
          pitch,
          syllable,
          isRap,
          isGolden: isGolden || false,
          isFreestyle: isFreestyle || false,
          confidence: 1.0,
          original: { startBeat, duration, pitch },
          ...(singer !== null ? { singer } : {}),
        });
      }
    } else if (trimmed.startsWith('-')) {
      // Break line — store for rendering
      const parts = trimmed.substring(1).trim().split(/\s+/);
      parsed.push({
        id: id++,
        type: 'break',
        startBeat: parseInt(parts[0]) || 0,
        endBeat: parseInt(parts[1]) || null,
        ...(singer !== null ? { singer } : {}),
      });
    }
  }

  return singer !== null ? mergeShared(parsed) : parsed;
}

// ──── Duets (docs/plans/duets.md) ────

export const BOTH = 'both';

/** The singer a `P1`/`P2` line starts (1, 2), 'both' for an old chart's `P3`, else null. */
export function trackMarker(line) {
  const m = line.trim().match(/^P\s*(\d)$/);
  if (!m) return null;
  return { 1: 1, 2: 2, 3: BOTH }[m[1]] ?? null;
}

export function isDuet(content) {
  return content.split(/\r?\n|\r/).some(line => trackMarker(line) !== null);
}

/** The singers' names from the headers ({KEY: value}, upper-case keys): #P1/#P2, else #DUETSINGERP1/P2, else
 * USDB's p1=/p2= in #VIDEO, else "Singer 1"/"Singer 2". */
export function singerNames(headers) {
  const video = Object.fromEntries((headers.VIDEO || '').split(',').filter(p => p.includes('='))
    .map(p => [p.slice(0, p.indexOf('=')), p.slice(p.indexOf('=') + 1)]));
  const names = {};
  for (const n of ['1', '2']) {
    names[`p${n}`] = (headers[`P${n}`] || headers[`DUETSINGERP${n}`] || video[`p${n}`] || '').trim() || `Singer ${n}`;
  }
  return names;
}

function elementKey(el) {
  if (el.type === 'break') return `break|${el.startBeat}`;
  return [el.startBeat, el.duration, el.pitch, el.syllable, !!el.isGolden, !!el.isRap, !!el.isFreestyle].join('|');
}

const byBeat = (a, b) => (a.startBeat - b.startBeat) || ((a.type === 'break' ? 0 : 1) - (b.type === 'break' ? 0 : 1));

/** Elements in both tracks (same beat, length, pitch, syllable, type) become one, sung by 'both'. Sorted by beat,
 * a break before the notes starting at its beat. */
export function mergeShared(elements) {
  const first = new Map();
  for (const el of elements) if (el.singer === 1 && !first.has(elementKey(el))) first.set(elementKey(el), el);
  const used = new Set();
  const out = [];
  for (const el of elements) {
    if (el.singer === 2) {
      const twin = first.get(elementKey(el));
      if (twin && !used.has(twin)) {
        used.add(twin);
        twin.singer = BOTH;
        continue;
      }
    }
    out.push(el);
  }
  return out.sort(byBeat);
}

/** One singer's notes and breaks, in order, without breaks that would leave an empty line. In a duet an element
 * without a singer (made by a tool that doesn't know about duets) counts as sung by both, so it isn't lost. */
export function track(elements, singer) {
  const out = [];
  for (const el of elements.filter(e => e.singer === singer || e.singer === BOTH || e.singer == null).sort(byBeat)) {
    if (el.type === 'break') {
      if (out.length && out[out.length - 1].type !== 'break') out.push(el);
    } else {
      out.push(el);
    }
  }
  while (out.length && out[out.length - 1].type === 'break') out.pop();
  return out;
}

/** #P1/#P2 (format 1.0) and #DUETSINGERP1/P2 (older games, YASS) with the singers' names. */
export function duetHeaderLines(names) {
  return [`#P1:${names.p1}`, `#P2:${names.p2}`, `#DUETSINGERP1:${names.p1}`, `#DUETSINGERP2:${names.p2}`];
}

export const DUET_HEADERS = new Set(['P1', 'P2', 'P3', 'DUETSINGERP1', 'DUETSINGERP2', 'DUETSINGERP3']);

/**
 * Serialize an array of note objects (as produced by parseUltrastar) into
 * Ultrastar note lines (no headers, no trailing "E").
 *
 * Supports both the `isGolden`/`isRap`/`isFreestyle` boolean style (from parseUltrastar) and
 * the `type` string style ('golden', 'rap', 'freestyle', 'break') used internally by the editor.
 */
export function notesToUltrastar(notes) {
  // Duet: a P1 and a P2 track
  if (notes.some(n => n.singer != null)) {
    return [1, 2].map(s => [`P${s}`, notesToUltrastar(track(notes, s).map(({ singer, ...n }) => n))]
      .filter(Boolean).join('\n')).join('\n');
  }
  const lines = [];
  for (const note of notes) {
    const isBreak = note.type === 'break';
    if (isBreak) {
      lines.push(`- ${note.startBeat}`);
    } else {
      const isGolden = note.isGolden || note.type === 'golden';
      const isRap = note.isRap || note.type === 'rap';
      const isFreestyle = note.isFreestyle || note.type === 'freestyle';
      const prefix = isRap ? 'R' : isFreestyle ? 'F' : isGolden ? '*' : ':';
      lines.push(`${prefix} ${note.startBeat} ${note.duration} ${note.pitch} ${note.syllable}`);
    }
  }
  return lines.join('\n');
}
