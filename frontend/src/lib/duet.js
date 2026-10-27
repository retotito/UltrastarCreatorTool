/**
 * Duet editing (docs/plans/duets.md): the editor's notes and breaks carry `singer` 1, 2 or 'both' (one linked note
 * sung by both). These functions return new arrays and never change the notes they are given.
 */
import { BOTH, DUET_HEADERS, singerNames } from './ultrastar.js';

export { BOTH };

/** Singer 1 and 2's colours (normal notes, singer chips). Golden/rap/freestyle keep their type colours. */
export const SINGER_COLORS = { 1: '#4fc3f7', 2: '#81c784' };

export const other = singer => (singer === 1 ? 2 : 1);

export function isDuetChart(notes) {
  return notes.some(n => n.singer != null);
}

/** Whether `singer` sings this note (their own, or linked). */
export function sungBy(note, singer) {
  return note.singer === singer || note.singer === BOTH;
}

export function namesFromHeaders(extraHeaders) {
  return singerNames(Object.fromEntries(extraHeaders.map(h => [h.key.toUpperCase(), h.value])));
}

/** The headers with #P1/#P2 set to the names (and the older duet headers left out). */
export function withNames(extraHeaders, names) {
  return [...withoutNames(extraHeaders), { key: 'P1', value: names.p1 }, { key: 'P2', value: names.p2 }];
}

export function withoutNames(extraHeaders) {
  return extraHeaders.filter(h => !DUET_HEADERS.has(h.key.toUpperCase()));
}

/** A solo chart as a duet: every note and break is sung by both. */
export function makeDuet(notes) {
  return notes.map(n => ({ ...n, singer: BOTH }));
}

/** Back to solo, keeping one singer: their notes and the linked ones stay, the other singer's are deleted. */
export function unmakeDuet(notes, keep) {
  return notes.filter(n => n.singer !== other(keep)).map(({ singer, ...n }) => n);
}

const overlap = (a, b) => a.startBeat < b.startBeat + b.duration && b.startBeat < a.startBeat + a.duration;

/** The notes (not in `ids`) that `singer` sings and that overlap one of the notes in `ids`. */
export function clashes(notes, ids, singer) {
  const moving = notes.filter(n => ids.has(n.id) && n.type !== 'break');
  return notes.filter(n => !ids.has(n.id) && n.type !== 'break' && sungBy(n, singer) && moving.some(m => overlap(m, n)));
}

function apply(notes, ids, change) {
  return notes.map(n => (ids.has(n.id) && n.type !== 'break' ? change({ ...n }) : n));
}

/** Give the notes to `target` (from the other singer). Refused (`refused` set) where `target` already sings. */
export function moveTo(notes, ids, target) {
  if (clashes(notes, ids, target).length) return { notes, refused: 'clash' };
  return { notes: apply(notes, ids, n => ({ ...n, singer: target })) };
}

/** Link the notes: both sing them. Refused where the other singer already has a note there. */
export function link(notes, ids) {
  const singers = new Set(notes.filter(n => ids.has(n.id) && n.type !== 'break').map(n => n.singer));
  for (const s of [1, 2]) {
    if (singers.has(other(s)) && clashes(notes, ids, s).length) return { notes, refused: 'clash' };
  }
  return { notes: apply(notes, ids, n => ({ ...n, singer: BOTH })) };
}

/** Linked notes become two independent notes, one per singer (the copy for singer 2 gets a new id). */
export function unlink(notes, ids, nextId) {
  let id = nextId;
  const out = [];
  for (const n of notes) {
    if (ids.has(n.id) && n.singer === BOTH && n.type !== 'break') {
      out.push({ ...n, singer: 1 }, { ...n, id: id++, singer: 2, original: n.original ? { ...n.original } : n.original });
    } else {
      out.push(n);
    }
  }
  return { notes: out, nextId: id };
}

/** Linked notes sung only by `singer` from now on. */
export function only(notes, ids, singer) {
  return { notes: apply(notes, ids, n => (n.singer === BOTH ? { ...n, singer } : n)) };
}

/** Ids of the notes `singer` sings. */
export function notesOf(notes, singer) {
  return new Set(notes.filter(n => n.type !== 'break' && sungBy(n, singer)).map(n => n.id));
}

/** Drawing and clicking order: the other singer's notes first (drawn under, clicked last), then the active
 * singer's and the linked ones. A solo chart keeps its order. */
export function byActiveSinger(notes, active) {
  if (!isDuetChart(notes)) return notes;
  return [...notes.filter(n => !sungBy(n, active)), ...notes.filter(n => sungBy(n, active))];
}
