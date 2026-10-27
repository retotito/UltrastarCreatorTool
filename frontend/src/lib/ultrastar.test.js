// Duet charts in the editor's reader and writer; the same cases as backend/tests/unit/test_duet.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseUltrastar, notesToUltrastar, singerNames, trackMarker, isDuet, duetHeaderLines, chartHeaders } from './ultrastar.js';

const CHART = `#TITLE:Song
#BPM:300
#GAP:1000
#P1:Anna
#P2:Ben
P1
: 0 4 10 Hel
: 4 4 12 lo
- 10
: 12 4 10 to
: 16 4 10 gether
P2
: 12 4 10 to
: 16 4 5 gether
- 22
: 24 4 7 Hi
E
`;

const brief = els => els.map(e => e.type === 'break' ? `- ${e.startBeat} ${e.singer}` : `${e.syllable} ${e.pitch} ${e.singer}`);

test('track markers', () => {
  assert.equal(trackMarker('P1'), 1);
  assert.equal(trackMarker('P 2'), 2);
  assert.equal(trackMarker('P3'), 'both');
  assert.equal(trackMarker(': 0 4 10 P1'), null);
  assert.ok(isDuet(CHART));
  assert.ok(!isDuet(': 0 4 10 la\nE'));
});

test('a duet is read as one list, shared notes once as both', () => {
  assert.deepEqual(brief(parseUltrastar(CHART)), [
    'Hel 10 1', 'lo 12 1', '- 10 1', 'to 10 both', 'gether 10 1', 'gether 5 2', '- 22 2', 'Hi 7 2',
  ]);
});

test('and written back as the same two tracks', () => {
  assert.equal(notesToUltrastar(parseUltrastar(CHART)), [
    'P1', ': 0 4 10 Hel', ': 4 4 12 lo', '- 10', ': 12 4 10 to', ': 16 4 10 gether',
    'P2', ': 12 4 10 to', ': 16 4 5 gether', '- 22', ': 24 4 7 Hi',
  ].join('\n'));
});

test('a break without notes of that singer on both sides is left out', () => {
  const notes = [
    { startBeat: 0, duration: 4, pitch: 1, syllable: 'a', singer: 1 },
    { type: 'break', startBeat: 6, singer: 'both' },
    { startBeat: 8, duration: 4, pitch: 1, syllable: 'b', singer: 2 },
    { type: 'break', startBeat: 14, singer: 'both' },
    { startBeat: 16, duration: 4, pitch: 1, syllable: 'c', singer: 1 },
  ];
  assert.equal(notesToUltrastar(notes), ['P1', ': 0 4 1 a', '- 6', ': 16 4 1 c', 'P2', ': 8 4 1 b'].join('\n'));
});

test('an old chart\'s P3 part is sung by both', () => {
  assert.deepEqual(brief(parseUltrastar('P1\n: 0 4 1 a\nP3\n: 8 4 2 b\nE')), ['a 1 1', 'b 2 both']);
});

test('a note without singer in a duet is kept for both', () => {
  const notes = [{ startBeat: 0, duration: 4, pitch: 1, syllable: 'a', singer: 1 }, { startBeat: 8, duration: 4, pitch: 2, syllable: 'new' }];
  assert.equal(notesToUltrastar(notes), ['P1', ': 0 4 1 a', ': 8 4 2 new', 'P2', ': 8 4 2 new'].join('\n'));
});

test('all five note types are read and written back', () => {
  const chart = ': 0 4 1 nor\n* 4 4 1 gold\nF 8 4 1 free\nR 12 4 1 rap\nG 16 4 1 goldrap';
  const notes = parseUltrastar(chart + '\nE');
  assert.deepEqual(notes.map(n => [n.isGolden, n.isRap, n.isFreestyle]),
    [[false, false, false], [true, false, false], [false, false, true], [false, true, false], [true, true, false]]);
  assert.equal(notesToUltrastar(notes), chart);
});

test('solo charts are unchanged', () => {
  const solo = parseUltrastar(': 0 4 1 a\n- 6\n* 8 2 3  b\nE');
  assert.ok(solo.every(n => !('singer' in n)));
  assert.equal(notesToUltrastar(solo), ': 0 4 1 a\n- 6\n* 8 2 3  b');
});

test('singer names and headers', () => {
  assert.deepEqual(singerNames(chartHeaders(CHART)), { p1: 'Anna', p2: 'Ben' });
  assert.deepEqual(singerNames({ DUETSINGERP1: 'A', DUETSINGERP2: 'B' }), { p1: 'A', p2: 'B' });
  assert.deepEqual(singerNames({ VIDEO: 'v=x,p1=Whitney Houston,p2=Mariah Carey' }), { p1: 'Whitney Houston', p2: 'Mariah Carey' });
  assert.deepEqual(singerNames({ P1: 'Anna' }), { p1: 'Anna', p2: 'Singer 2' });
  assert.deepEqual(duetHeaderLines({ p1: 'Anna', p2: 'Ben' }), ['#P1:Anna', '#P2:Ben', '#DUETSINGERP1:Anna', '#DUETSINGERP2:Ben']);
});
