// Keep native editing, dialog controls and modified shortcuts intact.
export function navigationStep(event) {
  if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey ||
      event.target?.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], dialog, summary, a')) return 0;
  return event.key === "ArrowLeft" ? -1 : ["ArrowRight", " "].includes(event.key) ? 1 : 0;
}

export function adjacentItem(ordered, eligible, activeId, step) {
  const ids = new Set(eligible.map(i => i.id));
  const start = ordered.findIndex(i => i.id === activeId);
  for (let offset = 1; offset <= ordered.length; offset++) {
    const item = ordered[((start < 0 ? (step > 0 ? -1 : 0) : start) + step * offset + ordered.length * 2) % ordered.length];
    if (ids.has(item.id)) return item;
  }
  return null;
}
