/**
 * What is probably a mistake in a chart: shown in the editor and on the export step, never blocking. Two singers singing
 * at once is normal in a duet, so everything here is per singer; a note sung by both counts for both.
 */
import { BOTH } from './ultrastar.js';

const LABELS = {
  overlap: ['note overlaps another note', 'notes overlap another note'],
  breakInside: ['line break is inside a note', 'line breaks are inside a note'],
  empty: ['note has no text', 'notes have no text'],
};

/** A problem's meaning, for one found by the editor's ⚠ button. */
export const PROBLEM_TEXT = {
  overlap: 'This note overlaps another note',
  breakInside: 'A line break is inside this note',
  empty: 'This note has no text',
};

/** {list: [{kind: 'overlap'|'breakInside'|'empty', beat, ids}] in song order, ids: Set of the notes involved}. */
export function chartProblems(notes) {
  const sung = notes.filter(n => n.type !== 'break');
  const breaks = notes.filter(n => n.type === 'break');
  const duet = notes.some(n => n.singer != null);
  const seen = new Set();
  const list = [];

  function add(kind, beat, ids) {
    const key = `${kind}:${[...ids].sort().join(',')}`;   // a linked note is checked for both singers: listed once
    if (!seen.has(key)) {
      seen.add(key);
      list.push({ kind, beat, ids });
    }
  }

  for (const singer of duet ? [1, 2] : [null]) {
    const sings = n => singer === null || n.singer === singer || n.singer === BOTH;
    let longest = null;
    const track = sung.filter(sings).sort((a, b) => a.startBeat - b.startBeat);
    for (const note of track) {
      if (longest && note.startBeat < longest.startBeat + longest.duration) {
        add('overlap', note.startBeat, [longest.id, note.id]);
      }
      if (!longest || note.startBeat + note.duration > longest.startBeat + longest.duration) longest = note;
    }
    for (const line of breaks.filter(b => singer === null || b.singer == null || sings(b))) {
      const inside = track.find(n => n.startBeat < line.startBeat && line.startBeat < n.startBeat + n.duration);
      if (inside) add('breakInside', line.startBeat, [inside.id]);
    }
  }
  for (const note of sung) {
    if (!note.syllable?.trim()) add('empty', note.startBeat, [note.id]);
  }
  list.sort((a, b) => a.beat - b.beat);
  return { list, ids: new Set(list.flatMap(problem => problem.ids)) };
}

/** Why a note is marked: the texts of its problems, one per kind, in the order found ('' if none). */
export function problemTextOf(list, id) {
  const kinds = [...new Set(list.filter(problem => problem.ids.includes(id)).map(problem => problem.kind))];
  return kinds.map(kind => PROBLEM_TEXT[kind]).join('. ');
}

/** "3 notes overlap another note · 1 note has no text", or '' without problems. */
export function describeProblems(list) {
  return Object.entries(LABELS).map(([kind, [one, many]]) => {
    const count = list.filter(problem => problem.kind === kind).length;
    return count ? `${count} ${count === 1 ? one : many}` : '';
  }).filter(Boolean).join(' · ');
}
