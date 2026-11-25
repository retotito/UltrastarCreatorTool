import { test } from 'node:test';
import assert from 'node:assert/strict';
import { msOfBeat, beatOfMs, syncTimings, regridNotes, requantize } from './regrid.js';

const note = (id, startBeat, duration, syllable = 'la', extra = {}) => ({ id, startBeat, duration, pitch: 60, syllable, ...extra });
const brk = (id, startBeat, endBeat = null) => ({ id, type: 'break', startBeat, endBeat });
const onlyNotes = list => list.filter(n => n.type !== 'break');
/** The moments (ms) of the notes' starts, rounded to 0.1 ms. */
const startsMs = (list, grid) => onlyNotes(list).map(n => Math.round(msOfBeat(n.startBeat, grid) * 10) / 10);
/** A song as the editor has it after loading: notes and their timings in sync. */
function song(grid) {
  const notes = [note(0, 0, 4, 'Jus'), note(1, 6, 2, 'ta'), note(2, 10, 5, 'men'), brk(3, 20), note(4, 96, 3, 'Irrum'), note(5, 100, 7, 'pes')];
  const timings = syncTimings(onlyNotes(notes).map((n, i) => ({ syllable: n.syllable, line_index: i < 3 ? 0 : 1 })), notes, grid);
  return { notes, timings };
}
/** The largest difference (ms) between the notes' moments on two grids. */
const drift = (before, beforeGrid, after, afterGrid) =>
  Math.max(...startsMs(before, beforeGrid).map((ms, i) => Math.abs(ms - startsMs(after, afterGrid)[i])));

test('a beat and its moment in the song convert both ways', () => {
  const grid = { bpm: 378, gapMs: 14999 };
  assert.equal(msOfBeat(0, grid), 14999);
  assert.ok(Math.abs(msOfBeat(96, grid) - 18808.5) < 0.1);
  assert.ok(Math.abs(beatOfMs(msOfBeat(1234, grid), grid) - 1234) < 1e-9);
});

test('a GAP change keeps every note at its moment in the song', () => {
  const from = { bpm: 400, gapMs: 15000 };
  const to = { bpm: 400, gapMs: 15300 };   // one beat = 37.5 ms, 300 ms = 8 beats
  const { notes, timings } = song(from);
  const result = requantize(notes, timings, from, to);
  assert.deepEqual(startsMs(result.notes, to), startsMs(notes, from));
  assert.deepEqual(onlyNotes(result.notes).map(n => n.startBeat), [-8, -2, 2, 88, 92]);
  const lineBreak = result.notes.find(n => n.type === 'break');
  assert.equal(msOfBeat(lineBreak.startBeat, to), msOfBeat(20, from));
});

test('a BPM change keeps every note at its moment, within half a beat', () => {
  const from = { bpm: 378, gapMs: 14999 };
  const to = { bpm: 544, gapMs: 14999 };
  const { notes, timings } = song(from);
  const result = requantize(notes, timings, from, to, { bpmChanged: true });
  assert.ok(drift(notes, from, result.notes, to) <= 15000 / to.bpm / 2 + 0.01);
});

test('many BPM and GAP changes back and forth end where they started', () => {
  const start = { bpm: 400, gapMs: 15000 };
  let { notes, timings } = song(start);
  const original = notes;
  let grid = start;
  for (const next of [{ bpm: 400, gapMs: 15350 }, { bpm: 560, gapMs: 15350 }, { bpm: 560, gapMs: 14800 },
                      { bpm: 300, gapMs: 14800 }, { bpm: 300, gapMs: 15000 }, { bpm: 400, gapMs: 15000 }]) {
    ({ notes, rawTimings: timings } = requantize(notes, timings, grid, next, { bpmChanged: next.bpm !== grid.bpm }));
    grid = next;
  }
  // Each change rounds to the new grid once; back on the start grid the notes are where they were (±1 beat)
  assert.ok(drift(original, start, notes, start) <= 15000 / start.bpm + 0.01);
});

test('notes moved with the keyboard stay moved when GAP changes afterwards', () => {
  // The bug: the timings were only updated after a mouse drag. Ctrl+A + → moved all notes, the timings stayed at the
  // old places, and the next GAP change rebuilt the notes there: the move was undone.
  const grid = { bpm: 400, gapMs: 15000 };
  const { notes, timings } = song(grid);
  const moved = notes.map(n => n.type === 'break' ? n : { ...n, startBeat: n.startBeat + 6 });   // timings not updated
  const to = { bpm: 400, gapMs: 15300 };
  const result = requantize(moved, timings, grid, to);
  assert.deepEqual(startsMs(result.notes, to), startsMs(moved, grid));
});

test('notes moved with the keyboard stay moved when BPM changes afterwards', () => {
  const grid = { bpm: 400, gapMs: 15000 };
  const { notes, timings } = song(grid);
  const moved = notes.map(n => n.type === 'break' ? n : { ...n, startBeat: n.startBeat + 6 });
  const to = { bpm: 500, gapMs: 15000 };
  const result = requantize(moved, timings, grid, to, { bpmChanged: true });
  assert.ok(drift(moved, grid, result.notes, to) <= 15000 / to.bpm / 2 + 0.01);
});

test('edited syllables and pitches survive the recalculation', () => {
  const grid = { bpm: 400, gapMs: 15000 };
  const { notes, timings } = song(grid);
  const edited = notes.map(n => n.id === 1 ? { ...n, syllable: 'TA', pitch: 67, isGolden: true } : n);
  const result = requantize(edited, timings, grid, { bpm: 400, gapMs: 15100 });
  const second = onlyNotes(result.notes)[1];
  assert.equal(second.syllable, 'TA');
  assert.equal(second.pitch, 67);
  assert.equal(second.isGolden, true);
});

test('with an added note (more notes than timings), a GAP change still keeps the moments', () => {
  const grid = { bpm: 400, gapMs: 15000 };
  const { notes, timings } = song(grid);
  const withExtra = [...notes, note(9, 120, 2, 'extra')];
  const to = { bpm: 400, gapMs: 14700 };
  const result = requantize(withExtra, timings, grid, to);
  assert.deepEqual(startsMs(result.notes, to), startsMs(withExtra, grid));
  assert.equal(onlyNotes(result.notes).length, 6);
});

test('a duet keeps its singers and moments on a GAP change', () => {
  const grid = { bpm: 400, gapMs: 15000 };
  const { notes, timings } = song(grid);
  const sung = notes.map((n, i) => ({ ...n, singer: i % 2 ? 2 : 1 }));
  const to = { bpm: 400, gapMs: 15300 };
  const result = requantize(sung, timings, grid, to, { isDuet: true });
  assert.deepEqual(startsMs(result.notes, to), startsMs(sung, grid));
  assert.deepEqual(result.notes.map(n => n.singer), sung.map(n => n.singer));
});

test('without timings the notes move by their moments (regridNotes)', () => {
  assert.equal(requantize(song({ bpm: 400, gapMs: 0 }).notes, [], { bpm: 400, gapMs: 0 }, { bpm: 400, gapMs: 300 }), null);
  const from = { bpm: 400, gapMs: 15000 };
  const to = { bpm: 400, gapMs: 15300 };
  const { notes } = song(from);
  const moved = regridNotes(notes, from, to);
  assert.deepEqual(startsMs(moved, to), startsMs(notes, from));
  const faster = regridNotes(notes, from, { bpm: 800, gapMs: 15000 });
  assert.deepEqual(onlyNotes(faster).map(n => n.duration), [8, 4, 10, 6, 14]);
});
