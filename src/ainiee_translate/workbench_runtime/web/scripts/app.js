import { adjacentItem, navigationStep } from "./navigation.js";
import { api } from "./api.js";
import { el, plain, math, diffText, table } from "./render.js";
import { restoreBackup, getItemDraft, draftDifferences, draftBlocks } from "./drafts.js";
import { termPreview, familyItems, familyBatch } from "./glossary.js";
import { readingNoteGroups, projectQuote } from "./reading-notes.js";

// Refactoring UI §2.1 / §3.3 / §3.3.1: materials first; directory and
// queue are optional navigation. Reuse the existing color/type/spacing tokens.
let queueOpen = false;
let familyPage = 0;
const openDirectories = new Set(["terms"]);

const $ = (s) => document.querySelector(s),
  PAGE_SIZE = 24;
let state,
  drafts,
  activeId,
  group = "all",
  status = "all",
  query = "",
  facets = new Set(),
  page = 0,
  view = "focus";
let dirty = false,
  generation = 0,
  saveTimer,
  inflight = null,
  blocked = false,
  remoteRevision = 0,
  selectionInfo = null;
const errors = new Map();
const texCache = new Map();
function texValid(text) {
  if (texCache.has(text)) return texCache.get(text);
  let valid = true;
  try {
    katex.renderToString(text, {
      throwOnError: true,
      trust: false,
      strict: "error",
      maxExpand: 1000,
      maxSize: 20,
      macros: {},
    });
  } catch {
    valid = false;
  }
  if (texCache.size > 1000) texCache.clear();
  texCache.set(text, valid);
  return valid;
}
const backupKey = () => `review-backup:${state.package.package_id}`;
function notify(message, actions = []) {
  const n = $("#notice");
  n.dataset.tone = message.startsWith("本轮决定已") ? "success" : "error";
  n.replaceChildren(
    el("span", {}, message),
    ...actions.map(([label, fn]) => el("button", { onclick: fn }, label)),
  );
  n.hidden = false;
}
function clearNotice() {
  $("#notice").hidden = true;
}
function itemDraft(i) {
  return getItemDraft(drafts, i.id);
}
function effective(i) {
  const d = itemDraft(i);
  if (d.mode === "accept")
    return (
      i.proposal !== null &&
      i.proposal.every((b) => b.type !== "tex" || texValid(b.text))
    );
  if (d.mode === "edit")
    return (
      d.touched &&
      editable(i).length > 0 &&
      editable(i).every((b) =>
        b.type === "table"
          ? Array.isArray(d.edits?.[b.id]) && d.edits[b.id].length
          : typeof d.edits?.[b.id] === "string" &&
            (d.edits[b.id].trim() || (i.allow_empty_blocks ?? []).includes(b.id)) &&
            (b.type !== "tex" || texValid(d.edits[b.id])),
      )
    );
  return (
    (d.mode === "keep" &&
      i.before.every((b) => b.type !== "tex" || texValid(b.text))) ||
    (d.mode === "comment" && d.comment?.trim())
  );
}
function itemState(i) {
  return effective(i) ? "reviewed" : i.requires_human ? "required" : "pending";
}
function editable(i) {
  return (i.proposal ?? i.before).filter((b) => b.type !== "image");
}
function count() {
  return state.package.items.filter(effective).length;
}
function badge(i) {
  const key = itemState(i);
  return el(
    "span",
    { class: `badge ${key}` },
    { reviewed: "✓ 已审", required: "! 必审", pending: "○ 待审" }[key],
  );
}
function statusName(i) {
  return { reviewed: "已审", required: "必审", pending: "待审" }[itemState(i)];
}
function markDirty() {
  generation++;
  dirty = true;
  $("#save-state").textContent = "待保存";
  try {
    sessionStorage.setItem(
      backupKey(),
      JSON.stringify({ material_hash: drafts.material_hash, drafts }),
    );
  } catch {}
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => flush().catch(() => {}), 400);
}
async function flush() {
  clearTimeout(saveTimer);
  if (inflight) return inflight;
  if (blocked) throw Error("请先解决草稿版本差异");
  if (!dirty) return;
  inflight = (async () => {
    while (dirty) {
      const gen = generation,
        snapshot = structuredClone(drafts);
      snapshot.revision = remoteRevision;
      $("#save-state").textContent = "保存中";
      const saved = await api("/api/drafts", "PUT", {
        drafts: snapshot,
        expected_revision: remoteRevision,
      });
      remoteRevision = saved.revision;
      drafts.revision = saved.revision;
      if (generation === gen) {
        dirty = false;
        try {
          sessionStorage.removeItem(backupKey());
        } catch {}
      }
    }
    $("#save-state").textContent = "已保存";
  })();
  try {
    await inflight;
  } catch (error) {
    $("#save-state").textContent = "未保存";
    if (error.status === 409) {
      blocked = true;
      notify(error.message, [["比较草稿", compareDrafts]]);
    } else
      notify(error.message, [
        [
          "重试",
          () => {
            clearNotice();
            flush().catch(() => {});
          },
        ],
      ]);
    throw error;
  } finally {
    inflight = null;
  }
}
async function compareDrafts() {
  try {
    const remote = await api("/api/state");
    const differences = draftDifferences(state.package.items, drafts, remote.drafts);
    showModal(
      "草稿版本差异",
      [
        el("p", {class: "muted small"}, differences.length
          ? `${differences.length} 项内容不同。选择将应用到整份草稿。`
          : "草稿内容相同，保存版本已更新。"),
        ...differences.map(({item, local, remote: other}) => el("section", {class: "draft-difference"}, [
          el("h3", {}, `${item.id} · ${item.location || "审核条目"}`),
          el("div", {class: "comparison"}, [
            draftVersion(item, local, "本机版本"),
            draftVersion(item, other, "该文件版本"),
          ]),
        ])),
        el("details", {class: "technical-details"}, [
          el("summary", {}, "技术详情"),
          el("pre", {}, JSON.stringify({local: drafts.items, file: remote.drafts.items}, null, 2)),
        ]),
      ],
      [
        [
          "保留该文件版本",
          () => {
            drafts = structuredClone(remote.drafts);
            remoteRevision = drafts.revision;
            dirty = false;
            blocked = false;
            sessionStorage.removeItem(backupKey());
            closeModal();
            clearNotice();
            render();
          },
        ],
        [
          "使用本机版本",
          async () => {
            if (remote.drafts.material_hash !== drafts.material_hash) {
              notify("材料已经改变，请下载本机草稿并建立新一轮。");
              return;
            }
            remoteRevision = remote.drafts.revision;
            drafts.revision = remoteRevision;
            blocked = false;
            dirty = true;
            closeModal();
            clearNotice();
            await flush();
            render();
          },
        ],
      ],
    );
  } catch (error) {
    notify(error.message);
  }
}
function draftVersion(item, draft, title) {
  const body = el("div", {class: "draft-version-body"});
  const names = {accept: "接受建议", keep: "保留原版", edit: "手动修改", comment: "提出修改意见"};
  body.append(el("p", {class: "draft-mode"}, names[draft.mode] || "未选择处理方式"));
  for (const block of draftBlocks(item, draft)) body.append(draftPreview(block));
  if (draft.mode === "edit" && !draft.touched)
    body.append(el("p", {class: "muted small"}, "尚未编辑，不计为已审"));
  if (draft.mode === "comment")
    body.append(el("p", {class: "draft-prose"}, draft.comment?.trim() || "尚未填写意见"));
  for (const quote of draft.quotes ?? [])
    body.append(el("blockquote", {class: "quoted"}, quote.text));
  // Inactive inputs are preserved by mode switching and must remain inspectable.
  const inactive = [];
  if (draft.mode !== "comment" && draft.comment)
    inactive.push(el("p", {class: "draft-prose"}, draft.comment));
  if (draft.mode !== "edit" && Object.keys(draft.edits ?? {}).length) {
    inactive.push(el("h3", {}, "手动修改草稿"));
    for (const block of draftBlocks(item, {...draft, mode: "edit"})) inactive.push(draftPreview(block));
  }
  if (draft.shapes?.length)
    inactive.push(el("p", {class: "muted small"}, `${draft.shapes.length} 条图片标注`));
  if (inactive.length) body.append(el("details", {class: "inactive-draft"}, [
    el("summary", {}, "其他草稿内容"), ...inactive,
  ]));
  return el("section", {class: "panel draft-version"}, [el("div", {class: "panel-label"}, title), body]);
}
function draftPreview(block) {
  if (block.type === "table") return table(block.rows);
  if (block.type === "image") return el("img", {class: "source-image", src: assetUrl(block.asset_id), alt: "草稿中的源图"});
  if (block.type === "tex") {
    const preview = el("div", {class: "math"});
    math(preview, block.text);
    return preview;
  }
  return el("p", {class: "text-source draft-prose"}, block.text || "（空白）");
}
function filtered(hold = false) {
  return state.package.items.filter(
    (i) =>
      (group === "all" || i.group_id === group || (group.startsWith("family:") && i.term_info?.base === group.slice(7))) &&
      (!query ||
        [
          i.id,
          i.location,
          plain(i.before),
          plain(i.proposal ?? []),
          i.rationale,
        ]
          .join(" ")
          .toLowerCase()
          .includes(query.toLowerCase())) &&
      [...facets].every((key) => {
        const [facet, value] = key.split(":");
        return i.facets[facet]?.includes(value);
      }) &&
      (status === "all" ||
        (status === "unreviewed" && itemState(i) !== "reviewed") ||
        (status === "required" && itemState(i) === "required") ||
        (status === "reviewed" && effective(i)) ||
        (status === "conflict" && hasConflict(i)) ||
        (hold && activeId === i.id)),
  );
}
function hasConflict(i) {
  return (
    state.comparison?.items?.some(
      (x) => x.item_id === i.id && x.status === "conflict",
    ) || false
  );
}
function currentPage(hold = true) {
  const list = filtered(hold);
  page = Math.min(page, Math.max(0, Math.ceil(list.length / PAGE_SIZE) - 1));
  return list.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
}
function previewNode(i) {
  if (!i.term_info) return el("span", {}, i.location || i.id);
  const preview = termPreview(i, itemDraft(i));
  return el("span", {class: "term-preview"}, [
    el("span", {class: "term-source"}, preview.source),
    preview.translation ? el("span", {class: "term-translation"}, preview.translation) : null,
  ]);
}
function directoryItem(i) {
  return el("button", {
    class: `term-directory-item status-card ${itemState(i)} ${activeId === i.id ? "active" : ""}`,
    "aria-current": activeId === i.id ? "true" : null,
    "aria-label": `${i.location} · ${statusName(i)}`,
    onclick: () => {
      group = i.term_info?.base ? "family:" + i.term_info.base : i.group_id;
      // Selecting a directory entry must always reveal it, even with stale filters.
      query = ""; status = "all"; facets.clear(); $("#search").value = "";
      const list = filtered(true);
      activeId = i.id; page = Math.floor(list.indexOf(i) / PAGE_SIZE);
      familyPage = Math.floor(familyItems(list, i.term_info?.base).indexOf(i) / PAGE_SIZE);
      render(true);
    },
  }, [previewNode(i), el("span", {class: "small"}, statusName(i))]);
}
function glossaryDirectory(p, side) {
  const nav = el("nav", {class: "nav glossary-directory", "aria-label": "主目录"});
  nav.append(el("button", {onclick: () => {group = "all"; page = 0; activeId = null; render();}}, "全部材料"));
  for (const g of p.groups) {
    const members = p.items.filter(i => i.group_id === g.id);
    if (!members.length) continue;
    const section = el("details", {open: openDirectories.has(g.id) ? "" : null,
      ontoggle: e => e.target.open ? openDirectories.add(g.id) : openDirectories.delete(g.id)},
      el("summary", {}, `${g.title} · ${members.length}`));
    const children = el("div", {class: "directory-children"});
    for (const i of members.filter(i => !i.term_info?.base)) children.append(directoryItem(i));
    const bases = [...new Set(members.map(i => i.term_info?.base).filter(Boolean))];
    for (const base of bases) {
      const key = "family:" + base;
      const family = el("details", {open: openDirectories.has(key) ? "" : null,
        ontoggle: e => e.target.open ? openDirectories.add(key) : openDirectories.delete(key)},
        el("summary", {}, `${base} · 派生词 · ${familyItems(members, base).length}`));
      family.append(el("div", {class: "directory-children"}, familyItems(members, base).map(directoryItem)));
      children.append(family);
    }
    section.append(children); nav.append(section);
  }
  side.append(nav);
}
function renderFamilyQueue() {
  const queue = $("#queue");
  const current = state.package.items.find(i => i.id === activeId);
  const base = current?.term_info?.base;
  if (!base) { queue.replaceChildren(); queue.hidden = true; return; }
  queue.hidden = false;
  const all = familyItems(filtered(true), base);
  familyPage = Math.max(0, Math.min(familyPage, Math.ceil(all.length / PAGE_SIZE) - 1));
  const members = all.slice(familyPage * PAGE_SIZE, (familyPage + 1) * PAGE_SIZE);
  const filteredScope = Boolean(query || status !== "all" || facets.size);
  const header = el("div", {class:"queue-top"}, [
    el("span", {}, `${base} · 派生词 · ${all.length} 项`),
    el("button", {class:"approve-all", disabled: filteredScope,
      title: filteredScope ? "清除搜索和状态筛选后同意完整派生类" : "同意本类各项当前暂定译名，跳过必审和已有人工决定",
      onclick: () => approveFamily(base)}, "同意一类"),
  ]);
  const rows = el("div", {class:"queue-list"}, members.map(i =>
    el("button", {class:`queue-item status-card ${itemState(i)} ${i.id === activeId ? "active" : ""}`,
      "aria-current": i.id === activeId ? "true" : null,
      onclick: () => {
        activeId = i.id; page = Math.floor(filtered(true).indexOf(i) / PAGE_SIZE); render(true);
      }}, [previewNode(i), el("span", {class:"small"}, statusName(i))])));
  queue.replaceChildren(header, rows, el("div", {class:"queue-pagination"}, [
    el("button", {disabled: familyPage === 0, onclick: () => {familyPage--; renderFamilyQueue();}}, "←"),
    el("span", {}, `${familyPage + 1} / ${Math.max(1, Math.ceil(all.length / PAGE_SIZE))}`),
    el("button", {disabled:(familyPage + 1) * PAGE_SIZE >= all.length,
      onclick: () => {familyPage++; renderFamilyQueue();}}, "→"),
  ]));
}
async function approveFamily(base) {
  try {
    await flush();
    const submitted = new Set(state.submissions.flatMap(s => s.decisions.map(d => d.item_id)));
    const eligible = familyBatch(state.package.items, base, drafts, submitted);
    for (const i of eligible) drafts.items[i.id] = {mode:"keep"};
    markDirty(); await flush(); render(true);
  } catch (error) { notify(error.message); }
}
function renderSidebar() {
  const p = state.package,
    side = $("#sidebar");
  side.replaceChildren(el("div", { class: "project-title" }, p.title));
  const progress = el("span");
  progress.style.width = (count() / Math.max(1, p.items.length)) * 100 + "%";
  side.append(
    el("div", { class: "progress" }, progress),
    el("p", { class: "small muted" }, `${count()} / ${p.items.length} 已审`),
    el("div", { class: "nav-label" }, "目录"),
  );
  if (p.review_profile === "glossary") {glossaryDirectory(p, side); return;}
  const nav = el("nav", { class: "nav", "aria-label": "主目录" });
  for (const g of [{ id: "all", title: "全部材料" }, ...p.groups]) {
    const members = p.items.filter(i => g.id === "all" || i.group_id === g.id);
    const groupState = members.length && members.every(effective) ? "reviewed"
      : members.some(i => itemState(i) === "required") ? "required" : "pending";
    nav.append(
      el(
        "button",
        {
          class: `status-card ${groupState} ${group === g.id ? "active" : ""}`,
          "aria-label": `${g.title} · ${{reviewed: "已审", required: "必审", pending: "待审"}[groupState]}`,
          onclick: () => {
            group = g.id;
            page = 0;
            render();
          },
        },
        [
          el("span", {}, g.title),
          el(
            "span",
            { class: "count" },
            p.items.filter((i) => g.id === "all" || i.group_id === g.id).length,
          ),
        ],
      ),
    );
  }
  side.append(nav);
  for (const f of p.facets) {
    side.append(el("div", { class: "nav-label" }, f.title));
    for (const option of f.options) {
      const key = f.id + ":" + option.id;
      side.append(
        el("label", { class: "facet-option" }, [
          el("input", {
            type: "checkbox",
            checked: facets.has(key),
            onchange: (e) => {
              if (e.target.checked) facets.add(key);
              else facets.delete(key);
              page = 0;
              render();
            },
          }),
          option.title,
        ]),
      );
    }
  }
}
function renderStatuses() {
  const all = state.package.items,
    options = [
      ["all", "全部", all.length],
      ["unreviewed", "未审", all.length - count()],
      [
        "required",
        "必审",
        all.filter((i) => itemState(i) === "required").length,
      ],
      ["reviewed", "已审", count()],
    ];
  if (state.comparison?.conflicts.length)
    options.push(["conflict", "冲突", all.filter(hasConflict).length]);
  $("#statuses").replaceChildren(
    ...options.map(([key, title, n]) =>
      el(
        "button",
        {
          class: key === status ? "active" : "",
          onclick: () => {
            status = key;
            page = 0;
            render();
          },
        },
        `${title} ${n}`,
      ),
    ),
  );
}
function renderQueue() {
  if (state.package.review_profile === "glossary") {renderFamilyQueue(); return;}
  $("#queue").hidden = false;
  const list = currentPage(),
    queue = $("#queue");
  const summary = el("div", {class: "queue-summary"}, [
    el("button", {
      id: "queue-toggle", "aria-controls": "queue-content", "aria-expanded": String(queueOpen),
      onclick: () => {queueOpen = !queueOpen; renderQueue(); $("#queue-toggle").focus();},
    }, queueOpen ? "收起条目" : "展开条目"),
  ]);
  if (!list.length) {queue.replaceChildren(summary); return;}
  const top = el("div", { class: "queue-top" }, [
    el("button", {
      class: "approve-all", "aria-label": "全选批准本页",
      title: "全选本页，跳过必审",
      onclick: () => batchApprove(),
    }, [el("span", {class: "select-all-icon", "aria-hidden": "true"}, "☰"), "全选批准"]),
    el("span", {}, `${filtered(true).length} 项`),
  ]);
  const rows = el("div", { class: "queue-list" });
  for (const i of list) {
    const button = el(
      "button",
      {
        class: `queue-item status-card ${itemState(i)} ${activeId === i.id ? "active" : ""}`,
        "aria-current": activeId === i.id ? "true" : null,
        onclick: () => {
          activeId = i.id;
          queueOpen = false;
          render(true);
          $("#queue-toggle").focus();
        },
      },
      [
        el("div", { class: "queue-meta" }, [
          el("span", { class: "mono" }, i.id),
          statusName(i),
        ]),
        el("div", { class: "queue-title" }, i.location || i.id),
      ],
    );
    rows.append(el("div", { class: "queue-row" }, [button]));
  }
  const listCount = filtered(true).length;
  const paging = el("div", { class: "queue-pagination" }, [
    el(
      "button",
      {
        disabled: page === 0,
        onclick: () => {
          page--;
          activeId = null;
          render();
        },
      },
      "←",
    ),
    el(
      "span",
      { class: "small muted" },
      `${page + 1} / ${Math.max(1, Math.ceil(listCount / PAGE_SIZE))}`,
    ),
    el(
      "button",
      {
        disabled: (page + 1) * PAGE_SIZE >= listCount,
        onclick: () => {
          page++;
          activeId = null;
          render();
        },
      },
      "→",
    ),
  ]);
  queue.replaceChildren(summary, el("div", {id: "queue-content", hidden: !queueOpen}, [top, rows, paging]));
}
function assetUrl(id) {
  const asset = state.package.assets.find((a) => a.id === id);
  return asset
    ? "/assets/" + asset.path.split("/").map(encodeURIComponent).join("/")
    : "";
}
function blockNode(b, i, version, paired, projection) {
  const wrapper = el("div", { class: "block" });
  const names = { dst: "译名", render: "人物译名", aliases: "别名", note: "说明", category: "分类", gender: "性别", keep_source: "保留原文" };
  if (!i.term_info && version !== "evidence" && names[b.id])
    wrapper.append(el("div", { class: "field-label" }, names[b.id]));
  if (b.type === "text") {
    const text = el("div", {
      class: "text-source",
      "data-item-id": i.id,
      "data-block-id": b.id,
      "data-version": version,
    });
    if (paired?.type === "text" && ["before", "proposal"].includes(version))
      diffText(
        text,
        version === "before" ? b.text : paired.text,
        version === "before" ? paired.text : b.text,
        version,
      );
    else text.textContent = projection?.text ?? b.text;
    if (projection) text.readingProjection = projection;
    wrapper.append(text);
  } else if (b.type === "tex") {
    const preview = el("div", { class: "math" });
    const ok = math(preview, b.text);
    if (!ok && version === "proposal" && itemDraft(i).mode === "accept")
      errors.set(i.id, "公式无法渲染，请修改或提出意见");
    wrapper.append(preview);
    const code = el(
      "pre",
      {
        class: "tex-code text-source",
        "data-item-id": i.id,
        "data-block-id": b.id,
        "data-version": version,
      },
      b.text,
    );
    wrapper.append(
      el("details", {}, [el("summary", { class: "small muted" }, "TeX"), code]),
    );
  } else if (b.type === "image") {
    wrapper.append(
      el("img", {
        class: "source-image",
        src: assetUrl(b.asset_id),
        alt: i.location || "源图",
        loading: "lazy",
        onclick: () => openImage(b.asset_id),
      }),
    );
  } else wrapper.append(table(b.rows));
  return wrapper;
}
function sourceEvidence(i) {
  if (i.term_info) {
    const info = i.term_info;
    const fields = [["原词", info.source], ["分类领域", info.category], ["上下文", info.context], ["PDF 页码", info.page ?? ""]];
    return el("details", {class:"evidence term-info", open:""}, [
      el("summary", {}, "术语信息"),
      el("dl", {class:"term-info-fields"}, fields.flatMap(([label, value]) => [
        el("dt", {}, label), el("dd", {}, String(value)),
      ])),
    ]);
  }
  if (!i.evidence.length) return null;
  const groups = readingNoteGroups(i.evidence);
  const notes = groups.flatMap(group => group.blocks.map(entry => entry.block));
  const references = i.evidence.filter((b) => !notes.includes(b));
  const body = el(
    "div",
    { class: "evidence-body" },
    references.map((b) => blockNode(b, i, "evidence")),
  );
  const details = el(
    "details",
    {
      class: "evidence",
      open: i.evidence.some((b) => b.type === "image") ? "" : null,
    },
    [el("summary", {}, "原文、候选与核验依据"), body],
  );
  if (!notes.length) return details;
  return el("div", {}, [
    el("div", { class: "reading-notes" }, groups.map(group =>
      el("section", { class: "reading-note", "aria-label": group.title }, [
        el("h2", { class: "reading-note-title" }, group.title),
        el("div", { class: "reading-note-body" }, group.blocks.map(({block, projection}) =>
          blockNode(block, i, "evidence", null, projection))),
      ]))),
    details,
  ]);
}
function makeEditor(i) {
  const d = itemDraft(i),
    section = el("div", { class: "editor-host" });
  if (d.mode === "edit") {
    for (const b of editable(i)) {
      const labels = { dst: "译名", render: "人物译名", aliases: "别名（每行一项）", note: "说明", category: "分类", gender: "性别", keep_source: "保留原文（是 / 否）" };
      const label = labels[b.id] ?? `${b.type === "tex" ? "TeX" : b.type === "table" ? "表格" : "手动修改"}${editable(i).length > 1 ? " · " + b.id.replace("segment-", "第 ") + " 段" : ""}`;
      const edit = el(
        "div",
        { class: "editor" },
        el("label", { for: `edit-${i.id}-${b.id}` }, label),
      );
      if (b.type === "table") {
        const rows = d.edits[b.id];
        edit.append(
          table(rows, true, (r, c, value) => {
            rows[r][c] = value;
            d.touched = true;
            markDirty();
            refreshStatus(i);
          }),
        );
      } else {
        const input = el("textarea", {
          id: `edit-${i.id}-${b.id}`,
          "aria-label": label,
          class: b.type === "tex" ? "mono" : "",
          value: d.edits[b.id],
          oninput: (e) => {
            d.edits[b.id] = e.target.value;
            d.touched = true;
            if (b.type === "tex") checkEditedMath(i, edit, e.target.value);
            markDirty();
            refreshStatus(i);
          },
        });
        edit.append(input);
        if (b.type === "tex") checkEditedMath(i, edit, d.edits[b.id]);
      }
      section.append(edit);
    }
  } else if (d.mode === "comment") {
    const editor = el(
      "div",
      { class: "editor" },
      el("label", { for: `note-${i.id}` }, "修改意见"),
    );
    for (const [n, q] of (d.quotes ?? []).entries())
      editor.append(
        el("blockquote", { class: "quoted" }, [
          el(
            "button",
            {
              "aria-label": "移除引用",
              onclick: () => {
                d.quotes.splice(n, 1);
                markDirty();
                render(true);
              },
            },
            "×",
          ),
          q.text,
        ]),
      );
    editor.append(
      el("textarea", {
        id: `note-${i.id}`,
        value: d.comment ?? "",
        oninput: (e) => {
          d.comment = e.target.value;
          markDirty();
          refreshStatus(i);
        },
      }),
    );
    section.append(editor);
  }
  return section;
}
function checkEditedMath(i, editor, value) {
  let preview = editor.querySelector(".edit-preview");
  if (!preview) {
    preview = el("div", { class: "math edit-preview" });
    editor.append(preview);
  }
  preview.className = "math edit-preview";
  if (!math(preview, value)) errors.set(i.id, "公式无法渲染");
  else errors.delete(i.id);
}
function refreshStatus(i) {
  const card = document.querySelector(`[data-card="${CSS.escape(i.id)}"]`);
  card?.querySelector(".current-badge")?.replaceChildren(badge(i));
  renderSidebar();
  renderStatuses();
  renderQueue();
}
function article(i) {
  errors.delete(i.id);
  const article = el("article", {
    class: "review-card",
    "data-card": i.id,
    "aria-label": i.location || i.id,
  });
  const meta = el("div", { class: "item-meta" }, [
    el("span", { class: "mono small muted" }, i.id),
    el("span", { class: "current-badge" }),
  ]);
  if (hasConflict(i))
    meta.append(
      el(
        "button",
        { class: "quiet conflict-count", onclick: () => showComparison(i.id) },
        "查看冲突",
      ),
    );
  article.append(meta);
  const evidence = sourceEvidence(i);
  if (evidence) article.append(evidence);
  const panels = el("div", { class: "comparison" });
  for (const [version, title] of [
    ["before", i.term_info ? "当前译名" : "当前版本"],
    ["proposal", i.term_info ? "建议译名" : "建议版本"],
  ]) {
    const blocks = i[version];
    const body = el("div", { class: "panel-body" });
    if (blocks)
      for (const b of blocks)
        body.append(
          blockNode(
            b,
            i,
            version,
            (version === "before" ? i.proposal : i.before)?.find(
              (x) => x.id === b.id,
            ),
          ),
        );
    else body.append(el("p", { class: "muted" }, "暂无建议"));
    panels.append(
      el("section", { class: "panel" }, [
        el("div", { class: "panel-label" }, title),
        body,
      ]),
    );
  }
  article.append(panels);
  if (i.rationale)
    article.append(
      el("div", { class: "explanation" }, [
        el("strong", {}, "🤖 修改依据"),
        `　${i.rationale}`,
      ]),
    );
  if (!i.term_info && (i.context || i.location))
    article.append(
      el("details", { class: "source-context" }, [
        el("summary", {}, i.location || "上下文"),
        el("p", {}, i.context || i.location),
      ]),
    );
  const d = itemDraft(i),
    buttons = el("div", {
      class: "decision-actions",
      role: "group",
      "aria-label": "处理方式",
    });
  for (const [mode, title] of [
    ["accept", "接受建议"],
    ["keep", "保留当前版本"],
    ["edit", "手动修改"],
    ["comment", "提出修改意见"],
  ]) {
    const disabled =
      (mode === "accept" && i.proposal === null) ||
      (mode === "edit" && !editable(i).length);
    buttons.append(
      el(
        "button",
        {
          "data-mode": mode,
          "aria-pressed": d.mode === mode ? "true" : "false",
          disabled,
          title: disabled
            ? mode === "accept"
              ? "此项没有推荐方案"
              : "此项没有可编辑内容"
            : null,
          onclick: () => {
            d.mode = mode;
            if (mode === "edit" && !Object.keys(d.edits ?? {}).length)
              d.edits = Object.fromEntries(
                editable(i).map((b) => [
                  b.id,
                  structuredClone(b.type === "table" ? b.rows : b.text),
                ]),
              );
            markDirty();
            render(true);
          },
        },
        title,
      ),
    );
  }
  article.append(
    el("section", { class: "decision" }, [buttons, makeEditor(i)]),
  );
  const error = errors.get(i.id);
  if (error) article.append(el("p", { class: "editor-error" }, error));
  meta.querySelector(".current-badge").append(badge(i));
  article.append(
    el("footer", { class: "item-footer" }, [
      `${state.package.items.indexOf(i) + 1} / ${state.package.items.length}`,
      view === "focus" ? el("div", {class: "item-navigation"}, [
        el("button", {class: "next-item", onclick: () => nextItem(i)}, "下一项 →"),
      ]) : null,
    ]),
  );
  return article;
}
function nextItem(i, step = 1) {
  const list = filtered(false);
  const next = adjacentItem(state.package.items, list, i.id, step);
  activeId = next?.id;
  page = next ? Math.floor(list.indexOf(next) / PAGE_SIZE) : 0;
  render(true);
  $("#articles").scrollIntoView({block: "start"});
}
document.addEventListener("keydown", event => {
  if (!state || view !== "focus" || document.querySelector("dialog[open]")) return;
  const step = navigationStep(event);
  const item = state.package.items.find(i => i.id === activeId);
  if (!step || !item) return;
  event.preventDefault();
  nextItem(item, step);
});
function render(hold = false) {
  if (!state) return;
  const list = currentPage(hold);
  if (!list.some((i) => i.id === activeId)) activeId = list[0]?.id;
  $("#shell").classList.toggle("flow", view === "flow");
  $("#focus-view").setAttribute("aria-pressed", view === "focus");
  $("#flow-view").setAttribute("aria-pressed", view === "flow");
  $("#articles").replaceChildren(
    ...(list.length
      ? view === "focus"
        ? [article(list.find((i) => i.id === activeId))]
        : list.map(article)
      : [
          el("div", { class: "empty" }, [
            el("p", {}, "没有符合条件的材料"),
            el(
              "button",
              {
                class: "quiet",
                onclick: () => {
                  status = "all";
                  group = "all";
                  facets.clear();
                  query = "";
                  $("#search").value = "";
                  render();
                },
              },
              "查看全部",
            ),
          ]),
        ]),
  );
  renderSidebar();
  renderStatuses();
  renderQueue();
}
function showModal(title, nodes, actions = []) {
  $("#modal-title").textContent = title;
  $("#modal-body").replaceChildren(...nodes);
  $("#modal-actions").replaceChildren(
    ...actions.map(([label, fn]) =>
      el(
        "button",
        {
          onclick: () =>
            Promise.resolve(fn()).catch((error) => notify(error.message)),
        },
        label,
      ),
    ),
  );
  if (!$("#modal").open) $("#modal").showModal();
}
function closeModal() {
  $("#modal").close();
}
let batchBusy = false;
async function batchApprove() {
  if (batchBusy) return;
  batchBusy = true;
  try {
    const ids = currentPage().map(i => i.id);
    await flush();
    const result = await api("/api/bulk", "POST", {
      item_ids: ids, expected_revision: remoteRevision,
    });
    drafts = result.drafts;
    remoteRevision = drafts.revision;
    render(true);
    notify(`已批准 ${result.accepted.length} 项（无建议的保留原文），跳过 ${ids.length - result.accepted.length} 项（必审、已有人工草稿或已提交）。`);
  } catch (error) {
    notify(error.message);
  } finally {
    batchBusy = false;
  }
}
async function submit() {
  try {
    await flush();
    const all = state.package.items.filter(effective),
      chosen = new Set(
        all
          .map((i) => i.id),
      );
    const nodes = [
      el(
        "p",
        { class: "muted small" },
        `${all.length} 项可提交，${state.package.items.length - all.length} 项未完成。`,
      ),
    ];
    for (const i of all)
      nodes.push(
        el("label", { class: "range-item" }, [
          el("input", {
            type: "checkbox",
            checked: chosen.has(i.id),
            onchange: (e) =>
              e.target.checked ? chosen.add(i.id) : chosen.delete(i.id),
          }),
          `${i.id} · ${i.location}`,
        ]),
      );
    showModal("提交范围", nodes, [
      ["取消", closeModal],
      [
        "提交",
        async () => {
          if (!chosen.size) {
            notify("请选择提交范围");
            return;
          }
          await api("/api/submit", "POST", {
            item_ids: [...chosen],
            expected_revision: remoteRevision,
          });
          state = await api("/api/state");
          drafts = structuredClone(state.drafts);
          remoteRevision = drafts.revision;
          closeModal();
          render(true);
          notify("本轮决定已提交。请回到聊天说“继续”，开始核验写回。", [
            ["关闭", clearNotice],
          ]);
        },
      ],
    ]);
  } catch (error) {
    notify(error.message);
  }
}
function download(name, data) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = el("a", { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function history() {
  try {
    await flush();
    state = await api("/api/state");
    const nodes = [];
    if (state.comparison?.items.length)
      nodes.push(
        el("button", { onclick: () => showComparison() }, "查看比较结果"),
      );
    for (const s of state.submissions) {
      const row = el("div", { class: "history-entry" }, [
        el("h3", { class: "mono" }, s.submission_id),
        el(
          "p",
          { class: "small muted" },
          `${s.decisions.length} 项 · ${s.base_commit?.slice(0, 12) || "无基准"}`,
        ),
      ]);
      for (const d of s.decisions)
        row.append(
          el("details", {}, [
            el(
              "summary",
              {},
              `${d.item_id} · ${{ accept: "接受建议", keep: "保留原版", edit: "手动修改", comment: "提出修改意见" }[d.action]}`,
            ),
            el("pre", {}, d.instruction ?? plain(d.blocks)),
          ]),
        );
      nodes.push(row);
    }
    if (!nodes.length) nodes.push(el("p", { class: "muted" }, "暂无提交记录"));
    showModal("提交记录", nodes, [
      [
        "导入结果",
        () => {
          const input = el("input", {
            type: "file",
            accept: ".json",
            onchange: async (e) => {
              try {
                const data = JSON.parse(await e.target.files[0].text());
                await api("/api/import-results", "POST", data);
                state = await api("/api/state");
                drafts = structuredClone(state.drafts);
                remoteRevision = drafts.revision;
                history();
              } catch (error) {
                notify(error.message);
              }
            },
          });
          input.click();
        },
      ],
      [
        "下载结果",
        () =>
          download(`${state.package.package_id}-results.json`, {
            schema_version: "1",
            package_id: state.package.package_id,
            base_commit: state.package.base_commit,
            submissions: state.submissions,
          }),
      ],
    ]);
  } catch (error) {
    notify(error.message);
  }
}
function showComparison(itemId) {
  const data = state.comparison;
  if (!data) {
    notify("尚无比较结果，请调用方提供当前工作稿投影。");
    return;
  }
  const target = itemId
    ? state.package.items.find((i) => i.id === itemId)?.target_id
    : null;
  const nodes = data.items
    .filter((x) => !target || x.target_id === target)
    .map((x) => {
      const row = el("section", { class: "conflict-row" }, [
        el(
          "h3",
          {},
          `${x.item_id} · ${{ conflict: "冲突", ready: "可应用", satisfied: "已满足", needs_agent: "待 agent 处理", missing_current: "缺少当前稿" }[x.status]}`,
        ),
        el("p", { class: "small muted mono" }, x.submission_id),
        x.action === "comment"
          ? el("p", {}, x.decision.instruction)
          : el(
              "div",
              { class: "three-way" },
              [
                ["审核基准", x.baseline],
                ["当前工作稿", x.current ?? []],
                ["人工决定", x.decision.blocks],
              ].map(([title, blocks]) =>
                el("div", {}, [
                  el("h3", {}, title),
                  el("pre", {}, plain(blocks)),
                ]),
              ),
            ),
      ]);
      if (x.status === "conflict")
        row.append(
          el(
            "button",
            {
              onclick: async () => {
                try {
                  await flush();
                  await api("/api/resolve", "POST", {
                    target_id: x.target_id,
                    submission_id: x.submission_id,
                    item_id: x.item_id,
                    expected_revision: remoteRevision,
                  });
                  state = await api("/api/state");
                  drafts = structuredClone(state.drafts);
                  remoteRevision = drafts.revision;
                  render(true);
                  showComparison(x.item_id);
                } catch (error) {
                  notify(error.message);
                }
              },
            },
            "采用此决定",
          ),
        );
      return row;
    });
  showModal("版本比较", nodes, [["关闭", closeModal]]);
}
let imageScale = 1,
  imageX = 0,
  imageY = 0,
  currentAsset,
  dragging = null;
function transformImage() {
  $("#image-content").style.transform =
    `translate(${imageX}px,${imageY}px) scale(${imageScale})`;
}
function fitImage() {
  const img = $("#image-content"),
    stage = $("#image-stage");
  imageScale = Math.min(
    stage.clientWidth / img.naturalWidth,
    stage.clientHeight / img.naturalHeight,
  );
  imageX = (stage.clientWidth - img.naturalWidth * imageScale) / 2;
  imageY = (stage.clientHeight - img.naturalHeight * imageScale) / 2;
  transformImage();
}
function zoom(
  factor,
  x = $("#image-stage").clientWidth / 2,
  y = $("#image-stage").clientHeight / 2,
) {
  const scale = Math.min(12, Math.max(0.05, imageScale * factor));
  imageX = x - ((x - imageX) * scale) / imageScale;
  imageY = y - ((y - imageY) * scale) / imageScale;
  imageScale = scale;
  transformImage();
}
function openImage(id) {
  currentAsset = state.package.assets.find((a) => a.id === id);
  const image = $("#image-content");
  image.onload = fitImage;
  image.src = assetUrl(id);
  $("#image-tools").replaceChildren(
    el("button", { onclick: fitImage }, "适应"),
    el(
      "button",
      {
        onclick: () => {
          imageScale = 1;
          imageX = 0;
          imageY = 0;
          transformImage();
        },
      },
      "1:1",
    ),
    el("button", { "aria-label": "缩小", onclick: () => zoom(0.8) }, "−"),
    el("button", { "aria-label": "放大", onclick: () => zoom(1.25) }, "＋"),
  );
  if (currentAsset.full_asset_id)
    $("#image-tools").append(
      el(
        "button",
        { onclick: () => openImage(currentAsset.full_asset_id) },
        "整页",
      ),
    );
  if (!$("#image-modal").open) $("#image-modal").showModal();
}
$("#image-stage").addEventListener("pointerdown", (e) => {
  dragging = { x: e.clientX, y: e.clientY };
  e.currentTarget.setPointerCapture(e.pointerId);
});
$("#image-stage").addEventListener("pointermove", (e) => {
  if (!dragging) return;
  imageX += e.clientX - dragging.x;
  imageY += e.clientY - dragging.y;
  dragging = { x: e.clientX, y: e.clientY };
  transformImage();
});
$("#image-stage").addEventListener("pointerup", () => (dragging = null));
$("#image-stage").addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const r = e.currentTarget.getBoundingClientRect();
    zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX - r.left, e.clientY - r.top);
  },
  { passive: false },
);
document.addEventListener("mouseup", (e) => {
  if (e.target.closest("#quote")) return;
  const sel = getSelection();
  if (!sel || sel.isCollapsed) {
    $("#quote").hidden = true;
    return;
  }
  const host = (
    sel.anchorNode.nodeType === Node.ELEMENT_NODE
      ? sel.anchorNode
      : sel.anchorNode.parentElement
  ).closest(".text-source");
  if (!host || !host.contains(sel.focusNode)) {
    $("#quote").hidden = true;
    return;
  }
  const range = sel.getRangeAt(0),
    prefix = document.createRange();
  prefix.selectNodeContents(host);
  prefix.setEnd(range.startContainer, range.startOffset);
  const start = Array.from(prefix.toString()).length,
    text = range.toString(),
    original = host.textContent;
  selectionInfo = {
    item_id: host.dataset.itemId,
    block_id: host.dataset.blockId,
    version: host.dataset.version,
    text,
    start,
    end: start + Array.from(text).length,
    prefix: Array.from(original)
      .slice(Math.max(0, start - 24), start)
      .join(""),
    suffix: Array.from(original)
      .slice(
        start + Array.from(text).length,
        start + Array.from(text).length + 24,
      )
      .join(""),
    base_commit: state.package.base_commit,
  };
  if (host.readingProjection)
    Object.assign(selectionInfo, projectQuote(host.readingProjection, start, start + Array.from(text).length));
  const r = range.getBoundingClientRect();
  $("#quote").style.left =
    Math.min(Math.max(8, r.left), innerWidth - 80) + "px";
  $("#quote").style.top = Math.max(8, r.top - 44) + "px";
  $("#quote").hidden = false;
});
$("#quote").addEventListener("mousedown", (e) => e.preventDefault());
$("#quote").onclick = () => {
  const i = state.package.items.find((i) => i.id === selectionInfo.item_id),
    d = itemDraft(i);
  d.mode = "comment";
  (d.quotes ??= []).push(selectionInfo);
  $("#quote").hidden = true;
  getSelection().removeAllRanges();
  markDirty();
  render(true);
  $(`#note-${CSS.escape(i.id)}`).focus();
};
$("#search").oninput = (e) => {
  query = e.target.value;
  page = 0;
  render();
};
$("#focus-view").onclick = () => {
  view = "focus";
  render(true);
};
$("#flow-view").onclick = () => {
  view = "flow";
  render(true);
};
function setDirectory(open) {
  $("#shell").classList.toggle("directory-open", open);
  $("#directory-toggle").setAttribute("aria-expanded", String(open));
  const label = open ? "收起目录" : "展开目录";
  $("#directory-toggle").setAttribute("aria-label", label);
  $("#directory-toggle").title = label;
}
$("#directory-toggle").onclick = () => setDirectory(!$("#shell").classList.contains("directory-open"));
setDirectory(false);
$("#submit").onclick = submit;
$("#history-toggle").onclick = history;
$("#modal-close").onclick = closeModal;
$("#image-close").onclick = () => $("#image-modal").close();
addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
async function boot() {
  try {
    state = await api("/api/state");
    drafts = structuredClone(state.drafts);
    remoteRevision = drafts.revision;
    activeId = state.package.items[0]?.id;
    document.title = state.package.title + " · 校对工作台";
    $("#save-state").textContent = "已保存";
    render();
    const local = JSON.parse(sessionStorage.getItem(backupKey()) || "null");
    if (local && local.material_hash === drafts.material_hash)
      notify("发现本机未保存的草稿。", [
        [
          "恢复",
          () => {
            const restored = restoreBackup(local.drafts, drafts);
            drafts = restored.drafts;
            blocked = restored.needsComparison;
            markDirty();
            render(true);
            if (blocked) {
              clearTimeout(saveTimer);
              $("#save-state").textContent = "需比较";
              compareDrafts();
            } else clearNotice();
          },
        ],
        [
          "忽略",
          () => {
            sessionStorage.removeItem(backupKey());
            clearNotice();
          },
        ],
      ]);
  } catch (error) {
    notify(error.message, [["重新连接", boot]]);
    $("#save-state").textContent = "未连接";
  }
}
setInterval(async () => {
  if (!state || inflight) return;
  try {
    const result = await api("/api/ping");
    if (result.revision !== remoteRevision && !blocked) {
      blocked = true;
      notify("另一个页面更新了审核草稿。", [["比较草稿", compareDrafts]]);
    } else if (!dirty && !blocked) $("#save-state").textContent = "已保存";
  } catch (error) {
    $("#save-state").textContent = "连接中断";
    if (!$("#notice").hidden) return;
    notify(error.message, [
      [
        "重试",
        async () => {
          clearNotice();
          if (dirty) await flush();
          else await boot();
        },
      ],
    ]);
  }
}, 10000);
boot();
