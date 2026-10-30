export function restoreBackup(local, remote) {
  if (
    local.package_id !== remote.package_id ||
    local.base_commit !== remote.base_commit ||
    local.material_hash !== remote.material_hash
  ) {
    throw new Error("备份属于另一轮材料，不能恢复到当前审核包");
  }
  return {
    drafts: structuredClone(local),
    needsComparison: local.revision !== remote.revision,
  };
}

export function getItemDraft(drafts, id) {
  if (!Object.hasOwn(drafts.items, id))
    drafts.items[id] = {
      mode: null,
      edits: {},
      touched: false,
      comment: "",
      quotes: [],
    };
  return drafts.items[id];
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object")
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  return value;
}
function normalizedDraft(draft) {
  return {mode: null, edits: {}, comment: "", quotes: [], touched: false, shapes: [], ...draft};
}
export function draftDifferences(items, local, remote) {
  return items.flatMap(item => {
    const a = Object.hasOwn(local.items, item.id) ? local.items[item.id] : {};
    const b = Object.hasOwn(remote.items, item.id) ? remote.items[item.id] : {};
    return JSON.stringify(canonical(normalizedDraft(a))) === JSON.stringify(canonical(normalizedDraft(b)))
      ? [] : [{item, local: a, remote: b}];
  });
}
export function draftBlocks(item, draft) {
  if (draft.mode === "keep") return structuredClone(item.before);
  if (draft.mode === "accept") return structuredClone(item.proposal ?? []);
  if (draft.mode !== "edit") return [];
  return (item.proposal ?? item.before).map(block => {
    const result = structuredClone(block);
    if (block.type !== "image" && Object.hasOwn(draft.edits ?? {}, block.id))
      result[block.type === "table" ? "rows" : "text"] = structuredClone(draft.edits[block.id]);
    return result;
  });
}
