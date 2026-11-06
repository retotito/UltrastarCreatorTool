/**
 * A release's notes (RELEASE_NOTES.md, in the update manifest) as blocks to show: ### headings, - bullets and plain
 * lines. No Markdown library and no HTML: the text is shown as text.
 */
export function noteBlocks(notes) {
  const blocks = [];
  for (const raw of (notes || '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const text = line.replace(/\*\*/g, '').replace(/`/g, '');
    if (/^#{1,6}\s/.test(line)) blocks.push({ type: 'heading', text: text.replace(/^#+\s*/, '') });
    else if (/^[-*]\s/.test(line)) blocks.push({ type: 'bullet', text: text.replace(/^[-*]\s*/, '') });
    else blocks.push({ type: 'text', text });
  }
  return blocks;
}
