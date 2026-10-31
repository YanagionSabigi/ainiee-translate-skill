// Frozen source identity and the user's explicit current decision determine previews.
export function termPreview(item, draft = {}) {
  let blocks = item.before;
  if (draft.mode === 'accept' && item.proposal) blocks = item.proposal;
  const original = blocks.find(b => b.id === 'dst')?.text ?? '';
  return {source: item.term_info.source,
    translation: draft.mode === 'edit' && Object.hasOwn(draft.edits ?? {}, 'dst')
      ? draft.edits.dst : original};
}
export function familyItems(items, base) {
  return base ? items.filter(i => i.term_info?.base === base) : [];
}
export function familyBatch(items, base, drafts, submittedIds = new Set()) {
  return familyItems(items, base).filter(i => {
    const d = drafts.items[i.id] ?? {};
    const human = d.mode || d.touched || d.comment?.trim() || Object.keys(d.edits ?? {}).length
      || d.quotes?.length || d.shapes?.length;
    return !i.requires_human && !human && !submittedIds.has(i.id)
      && Boolean(termPreview(i).translation.trim());
  });
}
