import { test } from 'node:test';
import assert from 'node:assert/strict';
import { noteBlocks } from './releaseNotes.js';

test('headings, bullets and text become blocks; Markdown marks go', () => {
  assert.deepEqual(noteBlocks('### New\n\n- **Duets** with `P1`\r\nHello\n'), [
    { type: 'heading', text: 'New' },
    { type: 'bullet', text: 'Duets with P1' },
    { type: 'text', text: 'Hello' },
  ]);
});

test('no notes, no blocks', () => {
  assert.deepEqual(noteBlocks(''), []);
  assert.deepEqual(noteBlocks(undefined), []);
});
