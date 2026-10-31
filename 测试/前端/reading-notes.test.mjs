import test from "node:test";
import assert from "node:assert/strict";
import { readingNoteGroups, readingNoteProjection, projectQuote } from "../../src/ainiee_translate/workbench_runtime/web/scripts/reading-notes.js";

test("phone excerpt and thoughts have separate titled sections without changing frozen evidence", () => {
  const evidence = [
    { id: "excerpt", type: "text", text: "手机阅读选区\nSmith 不幸的是，加上他爱把自己写成 J. Lorrain Smith 的\n习惯" },
    { id: "thought-0", type: "text", text: "你的阅读想法\n这里可以调一下语序。\n第二条意见。" },
    { id: "thought-1", type: "text", text: "你的阅读想法\n另一个想法。" },
    { id: "unlinked-0", type: "text", text: "待关联想法（尚未确认关联）\n仍需确认。" },
    { id: "source-0", type: "text", text: "原文\nSource text." },
  ];
  const frozen = structuredClone(evidence);
  const groups = readingNoteGroups(evidence);
  assert.deepEqual(groups.map(g => g.title), ["手机阅读选区", "你的阅读想法", "待关联想法（尚未确认关联）"]);
  assert.equal(groups[0].blocks[0].projection.text, "Smith 不幸的是，加上他爱把自己写成 J. Lorrain Smith 的习惯");
  assert.equal(groups[1].blocks.length, 2);
  assert.equal(groups[1].blocks[0].projection.text, "这里可以调一下语序。\n第二条意见。");
  assert.deepEqual(evidence, frozen);
});

test("phone wraps join Chinese, preserve English spaces and blank paragraphs", () => {
  for (const [raw, expected] of [
    ["手机阅读选区\r\n的 \r\n 习惯", "的习惯"],
    ["手机阅读选区\nJ. Lorrain\nSmith", "J. Lorrain Smith"],
    ["手机阅读选区\n第一行\n接续。\n\n第二段\n接续。", "第一行接续。\n\n第二段接续。"],
    ["无标签的旧选区\n接续。", "无标签的旧选区接续。"],
  ]) assert.equal(readingNoteProjection({id:"excerpt",text:raw}).text, expected);
});

test("quotes across repaired wraps still point to exact Unicode source offsets", () => {
  const raw = "手机阅读选区\n😀的\r\n习惯与 J. Lorrain\nSmith。";
  const projection = readingNoteProjection({id:"excerpt",text:raw});
  const display = Array.from(projection.text);
  const start = display.indexOf("😀"), end = display.indexOf("与");
  const quote = projectQuote(projection, start, end);
  assert.equal(quote.text, "😀的\r\n习惯");
  assert.equal(Array.from(raw).slice(quote.start,quote.end).join(""),quote.text);
  assert.equal(quote.prefix, "手机阅读选区\n");
  const thought = readingNoteProjection({id:"thought-0",text:"你的阅读想法\n😀保留\n换行"});
  assert.equal(projectQuote(thought,0,Array.from(thought.text).length).text,"😀保留\n换行");
});
