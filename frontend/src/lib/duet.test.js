import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  makeDuet, unmakeDuet, moveTo, link, unlink, only, notesOf, byActiveSinger, withNames, namesFromHeaders,
  newBreakSinger, setBreakSinger,
} from './duet.js';

const note = (id, startBeat, singer, duration = 4) => ({ id, startBeat, duration, pitch: 1, syllable: `n${id}`, singer });
const singers = notes => notes.map(n => `${n.id}:${n.singer}`);

test('set and unset a duet', () => {
  const solo = [note(1, 0), { id: 2, type: 'break', startBeat: 6 }, note(3, 8)].map(({ singer, ...n }) => n);
  assert.deepEqual(singers(makeDuet(solo)), ['1:both', '2:both', '3:both']);
  const duet = [note(1, 0, 1), note(2, 8, 2), note(3, 16, 'both')];
  assert.deepEqual(unmakeDuet(duet, 1).map(n => [n.id, 'singer' in n]), [[1, false], [3, false]]);
  assert.deepEqual(unmakeDuet(duet, 2).map(n => n.id), [2, 3]);
  assert.equal(duet[0].singer, 1); // unchanged input
});

test('move to the other singer, refused where that singer already sings', () => {
  const notes = [note(1, 0, 1), note(2, 8, 1), note(3, 9, 2), note(4, 20, 'both')];
  assert.deepEqual(singers(moveTo(notes, new Set([1]), 2).notes), ['1:2', '2:1', '3:2', '4:both']);
  const refused = moveTo(notes, new Set([2]), 2);
  assert.equal(refused.refused, 'clash');
  assert.equal(refused.notes, notes);
});

test('link: both sing it; refused where the other singer has a note there', () => {
  const notes = [note(1, 0, 1), note(2, 8, 1), note(3, 9, 2)];
  assert.deepEqual(singers(link(notes, new Set([1])).notes), ['1:both', '2:1', '3:2']);
  assert.equal(link(notes, new Set([2])).refused, 'clash');
});

test('unlink makes two independent notes; only keeps one singer', () => {
  const notes = [note(1, 0, 'both'), note(2, 8, 1)];
  const { notes: out, nextId } = unlink(notes, new Set([1]), 10);
  assert.deepEqual(singers(out), ['1:1', '10:2', '2:1']);
  assert.equal(nextId, 11);
  assert.deepEqual(singers(only(notes, new Set([1]), 2).notes), ['1:2', '2:1']);
});

test('notes of a singer and the drawing order', () => {
  const notes = [note(1, 0, 1), note(2, 8, 2), note(3, 16, 'both')];
  assert.deepEqual([...notesOf(notes, 2)], [2, 3]);
  assert.deepEqual(byActiveSinger(notes, 2).map(n => n.id), [1, 2, 3]);
  assert.deepEqual(byActiveSinger(notes, 1).map(n => n.id), [2, 1, 3]);
});

test('names in the headers', () => {
  const headers = withNames([{ key: 'COVER', value: 'c.jpg' }, { key: 'DUETSINGERP1', value: 'old' }], { p1: 'Anna', p2: 'Ben' });
  assert.deepEqual(headers.map(h => h.key), ['COVER', 'P1', 'P2']);
  assert.deepEqual(namesFromHeaders(headers), { p1: 'Anna', p2: 'Ben' });
});

test('a new break is shared, unless it falls inside the other singer\'s note', () => {
  const notes = [note(1, 0, 1, 10), note(2, 4, 2, 4)];
  assert.equal(newBreakSinger(notes, 12, 1), 'both');
  assert.equal(newBreakSinger(notes, 6, 1), 1);   // inside singer 2's note 4..8
  assert.equal(newBreakSinger(notes, 6, 2), 2);   // inside singer 1's note 0..10
});

test('a break for one singer or both, refused inside a note of that singer', () => {
  const notes = [note(1, 0, 1, 10), note(2, 12, 2, 4), { id: 3, type: 'break', startBeat: 14, singer: 'both' }];
  assert.deepEqual(singers(setBreakSinger(notes, 3, 1).notes), ['1:1', '2:2', '3:1']);
  assert.equal(setBreakSinger(notes, 3, 2).refused, 'inside');
  assert.equal(setBreakSinger(notes, 3, 'both').refused, 'inside');
});
