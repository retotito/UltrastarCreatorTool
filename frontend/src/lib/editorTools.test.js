import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EDITOR_TOOLS, parseHiddenTools, toggledTools } from './editorTools.js';

test('nothing is hidden without a readable stored value', () => {
  for (const stored of [null, '', 'not json', '{"mic":true}', '5']) assert.equal(parseHiddenTools(stored).size, 0);
});

test('stored tools come back; unknown ones are dropped', () => {
  assert.deepEqual([...parseHiddenTools('["mic","gone","duet"]')], ['mic', 'duet']);
});

test('toggling hides and shows without changing the old set', () => {
  const hidden = new Set(['mic']);
  assert.deepEqual([...toggledTools(hidden, 'fix')], ['mic', 'fix']);
  assert.deepEqual([...toggledTools(hidden, 'mic')], []);
  assert.deepEqual([...hidden], ['mic']);
});

test('every tool has its own id', () => {
  const ids = EDITOR_TOOLS.flatMap(group => group.tools.map(tool => tool.id));
  assert.equal(new Set(ids).size, ids.length);
});
