export function el(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value === null || value === undefined) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (["checked", "disabled", "hidden", "value"].includes(key))
      node[key] = value;
    else node.setAttribute(key, value);
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child !== null && child !== undefined)
      node.append(
        child instanceof Node ? child : document.createTextNode(String(child)),
      );
  }
  return node;
}
export function plain(blocks) {
  return blocks
    .map((b) =>
      b.type === "table"
        ? b.rows.map((r) => r.join("\t")).join("\n")
        : (b.text ?? `[图像 ${b.asset_id}]`),
    )
    .join("\n\n");
}
export function math(node, text) {
  node.replaceChildren();
  node.classList.remove("math-error");
  try {
    if (!globalThis.katex) throw Error("公式渲染资源未加载");
    katex.render(text, node, {
      displayMode: true,
      throwOnError: true,
      trust: false,
      strict: "error",
      maxExpand: 1000,
      maxSize: 20,
      macros: {},
    });
    return true;
  } catch (error) {
    node.classList.add("math-error");
    node.textContent = String(error.message);
    return false;
  }
}
export function segments(before, after) {
  if (before === after) return [[0, before]];
  const a = Array.from(before),
    b = Array.from(after);
  let prefix = 0,
    suffix = 0;
  while (prefix < a.length && prefix < b.length && a[prefix] === b[prefix])
    prefix++;
  while (
    suffix < a.length - prefix &&
    suffix < b.length - prefix &&
    a[a.length - 1 - suffix] === b[b.length - 1 - suffix]
  )
    suffix++;
  const x = a.slice(prefix, a.length - suffix),
    y = b.slice(prefix, b.length - suffix),
    out = [];
  if (prefix) out.push([0, a.slice(0, prefix).join("")]);
  if (x.length * y.length > 800000) {
    if (x.length) out.push([-1, x.join("")]);
    if (y.length) out.push([1, y.join("")]);
  } else {
    const width = y.length + 1,
      dp = new Uint32Array((x.length + 1) * width);
    for (let i = x.length - 1; i >= 0; i--)
      for (let j = y.length - 1; j >= 0; j--)
        dp[i * width + j] =
          x[i] === y[j]
            ? 1 + dp[(i + 1) * width + j + 1]
            : Math.max(dp[(i + 1) * width + j], dp[i * width + j + 1]);
    let i = 0,
      j = 0;
    const push = (kind, value) => {
      if (out.length && out.at(-1)[0] === kind) out.at(-1)[1] += value;
      else out.push([kind, value]);
    };
    while (i < x.length || j < y.length) {
      if (i < x.length && j < y.length && x[i] === y[j]) {
        push(0, x[i]);
        i++;
        j++;
      } else if (
        i < x.length &&
        (j === y.length || dp[(i + 1) * width + j] >= dp[i * width + j + 1])
      )
        push(-1, x[i++]);
      else push(1, y[j++]);
    }
  }
  if (suffix) out.push([0, a.slice(a.length - suffix).join("")]);
  return out;
}
export function diffText(node, before, after, side) {
  for (const [kind, text] of segments(before, after)) {
    if (kind === 0) node.append(document.createTextNode(text));
    else if (side === "before" && kind === -1) node.append(el("del", {}, text));
    else if (side === "proposal" && kind === 1)
      node.append(el("ins", {}, text));
  }
}
export function table(rows, editable = false, onchange = () => {}) {
  const table = el("table");
  for (let i = 0; i < rows.length; i++) {
    const tr = el("tr");
    for (let j = 0; j < rows[i].length; j++) {
      const td = el(i === 0 ? "th" : "td");
      if (editable)
        td.append(
          el("input", {
            "aria-label": `第 ${i + 1} 行，第 ${j + 1} 列`,
            value: rows[i][j],
            oninput: (e) => onchange(i, j, e.target.value),
          }),
        );
      else td.textContent = rows[i][j];
      tr.append(td);
    }
    table.append(tr);
  }
  return el("div", { class: "table-wrap" }, table);
}
