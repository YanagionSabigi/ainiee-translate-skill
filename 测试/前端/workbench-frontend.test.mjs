import test from "node:test";
import assert from "node:assert/strict";
import { segments } from "../../src/ainiee_translate/workbench_runtime/web/scripts/render.js";

test("Chinese and Unicode diff reconstructs both exact versions", () => {
  for (const [a, b] of [
    ["这项研究显著提升了理解。", "这项研究加深了理解。"],
    ["😀 α\n数学", "😀 β\n数学"],
    ["", "新增"],
    ["删除", ""],
    ["相同", "相同"],
  ]) {
    const pieces = segments(a, b);
    assert.equal(
      pieces
        .filter(([k]) => k !== 1)
        .map(([, s]) => s)
        .join(""),
      a,
    );
    assert.equal(
      pieces
        .filter(([k]) => k !== -1)
        .map(([, s]) => s)
        .join(""),
      b,
    );
  }
});
test("Long changes stay bounded and preserve exact content", () => {
  const a = "甲".repeat(2000),
    b = "乙".repeat(2000),
    pieces = segments(a, b);
  assert.equal(
    pieces
      .filter(([k]) => k !== 1)
      .map(([, s]) => s)
      .join(""),
    a,
  );
  assert.equal(
    pieces
      .filter(([k]) => k !== -1)
      .map(([, s]) => s)
      .join(""),
    b,
  );
});
