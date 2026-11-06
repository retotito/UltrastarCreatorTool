import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chartProblems, describeProblems } from './chartChecks.js';

const note = (id, startBeat, duration, singer, syllable = 'la ') => ({ id, startBeat, duration, pitch: 60, syllable, ...(singer ? { singer } : {}) });
const line = (id, startBeat, singer) => ({ id, type: 'break', startBeat, ...(singer ? { singer } : {}) });
const kinds = notes => chartProblems(notes).list.map(p => [p.kind, p.ids]);

test('a clean chart has no problems; notes that only touch are fine', () => {
  assert.deepEqual(kinds([note(1, 0, 4), note(2, 4, 4), line(3, 8), note(4, 9, 2)]), []);
});

test('overlaps in a solo chart', () => {
  assert.deepEqual(kinds([note(1, 0, 4), note(2, 3, 4)]), [['overlap', [1, 2]]]);
});

test('a long note overlapping a later one past a short one is found', () => {
  assert.deepEqual(kinds([note(1, 0, 20), note(2, 2, 2), note(3, 10, 2)]), [['overlap', [1, 2]], ['overlap', [1, 3]]]);
});

test('two singers at the same time is normal in a duet', () => {
  assert.deepEqual(kinds([note(1, 0, 4, 1), note(2, 0, 4, 2), note(3, 2, 4, 2)]), [['overlap', [2, 3]]]);
  assert.deepEqual(kinds([note(1, 0, 4, 1), note(2, 1, 4, 2)]), []);
});

test('a linked note counts for both singers, listed once', () => {
  assert.deepEqual(kinds([note(1, 0, 4, 'both'), note(2, 2, 4, 1)]), [['overlap', [1, 2]]]);
  assert.deepEqual(kinds([note(1, 0, 4, 'both'), note(2, 0, 4, 'both')]), [['overlap', [1, 2]]]);
});

test('a line break inside a note, only for the singer it belongs to', () => {
  assert.deepEqual(kinds([note(1, 0, 8), line(2, 4)]), [['breakInside', [1]]]);
  assert.deepEqual(kinds([note(1, 0, 8, 2), line(2, 4, 1), note(3, 10, 1, 1)]), []);
  assert.deepEqual(kinds([note(1, 0, 8, 2), line(2, 4, 'both'), note(3, 10, 1, 1)]), [['breakInside', [1]]]);
  assert.deepEqual(kinds([note(1, 0, 4), line(2, 4)]), []);   // at its end: fine
});

test('a note without text, also only spaces', () => {
  assert.deepEqual(kinds([note(1, 0, 4, null, ''), note(2, 5, 1, null, '  ')]), [['empty', [1]], ['empty', [2]]]);
  assert.deepEqual(kinds([note(1, 0, 4, null, '~')]), []);
});

test('problems come in song order, with the notes involved', () => {
  const found = chartProblems([note(1, 50, 4, null, ''), note(2, 0, 4), note(3, 2, 4)]);
  assert.deepEqual(found.list.map(p => p.beat), [2, 50]);
  assert.deepEqual([...found.ids].sort(), [1, 2, 3]);
});

test('described in words', () => {
  assert.equal(describeProblems([]), '');
  assert.equal(describeProblems(chartProblems([note(1, 0, 4), note(2, 3, 4), note(3, 9, 1, null, '')]).list),
    '1 note overlaps another note · 1 note has no text');
  assert.equal(describeProblems([{ kind: 'overlap' }, { kind: 'overlap' }]), '2 notes overlap another note');
});
