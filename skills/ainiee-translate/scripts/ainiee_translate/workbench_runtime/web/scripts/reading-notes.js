// Display-only projections: frozen evidence and quote offsets stay unchanged.
const labels = [
  ["excerpt", "手机阅读选区"],
  ["thought-", "你的阅读想法"],
  ["unlinked-", "待关联想法（尚未确认关联）"],
];
const matches = (id, key) => key === "excerpt" ? id === key : id.startsWith(key);

export function readingNoteProjection(block) {
  const source = Array.from(block.text), ranges = [], output = [];
  const label = labels.find(([key]) => matches(block.id, key))?.[1];
  const prefix = label && block.text.match(new RegExp("^" + label + "\\r?\\n"));
  let index = prefix ? Array.from(prefix[0]).length : 0;
  const append = (text, start, end) => {
    for (const char of text) { output.push(char); ranges.push([start, end]); }
  };
  while (index < source.length) {
    if (block.id === "excerpt" && /[\t \r\n]/.test(source[index])) {
      let end = index;
      while (end < source.length && /[\t \r\n]/.test(source[end])) end++;
      const whitespace = source.slice(index, end).join("");
      if ((whitespace.match(/\r\n|\r|\n/g) ?? []).length === 1) {
        // Chinese wraps concatenate; English word boundaries retain one space.
        const cjk = /[\p{Script=Han}，。！？；：、（）《》“”‘’…—]/u;
        if (output.length && end < source.length &&
            !cjk.test(output.at(-1)) && !cjk.test(source[end])) append(" ", index, end);
        index = end;
        continue;
      }
      while (index < end) {
        append(source[index], index, index + 1);
        index++;
      }
      continue;
    }
    append(source[index], index, index + 1);
    index++;
  }
  return { text: output.join(""), source, ranges };
}

export function projectQuote(projection, start, end) {
  const first = projection.ranges[start], last = projection.ranges[end - 1];
  if (!first || !last || end <= start) throw Error("引用选区无效");
  const from = first[0], to = last[1], raw = projection.source;
  return {
    text: raw.slice(from, to).join(""), start: from, end: to,
    prefix: raw.slice(Math.max(0, from - 24), from).join(""),
    suffix: raw.slice(to, to + 24).join(""),
  };
}

export function readingNoteGroups(evidence) {
  return labels.map(([key, title]) => ({
    title,
    blocks: evidence.filter(b => b.type === "text" && matches(b.id, key))
      .map(block => ({ block, projection: readingNoteProjection(block) })),
  })).filter(group => group.blocks.length);
}
