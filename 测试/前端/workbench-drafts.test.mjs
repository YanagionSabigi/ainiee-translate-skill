import test from "node:test";
import assert from "node:assert/strict";
import { restoreBackup, getItemDraft, draftDifferences, draftBlocks } from "../../src/ainiee_translate/workbench_runtime/web/scripts/drafts.js";

test("restoring an old backup never upgrades its revision to the disk version", () => {
  const local = {
    package_id: "p",
    base_commit: "same",
    material_hash: "same",
    revision: 0,
    items: { a: { mode: "keep" } },
  };
  const remote = {
    package_id: "p",
    base_commit: "same",
    material_hash: "same",
    revision: 2,
    items: { b: { mode: "comment", comment: "另一页的新意见" } },
  };
  const result = restoreBackup(local, remote);
  assert.equal(result.drafts.revision, 0);
  assert.equal(result.needsComparison, true);
  assert.equal(remote.items.b.comment, "另一页的新意见");
});
test("same-version recovery is safe and creates an independent local copy", () => {
  const local = {
    package_id: "p",
    base_commit: "same",
    material_hash: "same",
    revision: 2,
    items: { a: { mode: "keep" } },
  };
  const result = restoreBackup(local, structuredClone(local));
  assert.equal(result.needsComparison, false);
  result.drafts.items.a.mode = "accept";
  assert.equal(local.items.a.mode, "keep");
});
test("item identifiers that match Object properties still get their own drafts", () => {
  const drafts = { items: {} };
  const value = getItemDraft(drafts, "constructor");
  assert.equal(value.mode, null);
  value.comment = "真实输入";
  assert.equal(drafts.items.constructor.comment, "真实输入");
});

test("draft comparison shows changed items and ignores empty defaults and object key order", () => {
  const items = [{id: "one"}, {id: "two"}, {id: "constructor"}];
  const local = {items: {one: {mode: "edit", edits: {b: "乙", a: "甲"}}}};
  const remote = {items: {one: {edits: {a: "甲", b: "乙"}, mode: "edit"}, two: {mode: null, edits: {}, comment: "", quotes: [], touched: false}}};
  assert.deepEqual(draftDifferences(items, local, remote), []);
  remote.items.one.edits.a = "另一版";
  Object.defineProperty(remote.items, "constructor", {value: {mode: "keep"}, enumerable: true});
  const differences = draftDifferences(items, local, remote);
  assert.deepEqual(differences.map(d => d.item.id), ["one", "constructor"]);
  assert.equal(differences[0].local.edits.a, "甲");
  assert.equal(differences[0].remote.edits.a, "另一版");
});

test("draft projection renders selected text, TeX, table edits and retained images without mutating materials", () => {
  const item = {before: [{id: "text", type: "text", text: "原版"}], proposal: [
    {id: "text", type: "text", text: "建议"},
    {id: "tex", type: "tex", text: "x"},
    {id: "table", type: "table", rows: [["原表"]]},
    {id: "image", type: "image", asset_id: "scan"},
  ]};
  const draft = {mode: "edit", edits: {text: "", tex: "x^2", table: [["新表"]]}};
  assert.deepEqual(draftBlocks(item, {mode: "keep"}), item.before);
  assert.deepEqual(draftBlocks(item, {mode: "accept"}), item.proposal);
  const blocks = draftBlocks(item, draft);
  assert.equal(blocks[0].text, "");
  assert.equal(blocks[1].text, "x^2");
  assert.deepEqual(blocks[2].rows, [["新表"]]);
  assert.equal(blocks[3].asset_id, "scan");
  blocks[2].rows[0][0] = "mutated";
  assert.equal(draft.edits.table[0][0], "新表");
  assert.equal(item.proposal[2].rows[0][0], "原表");
  assert.deepEqual(draftBlocks(item, {mode: "comment", comment: "复查"}), []);
  assert.deepEqual(draftBlocks({...item, proposal: null}, {mode: "accept"}), []);
});
