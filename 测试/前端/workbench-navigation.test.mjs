import test from "node:test";
import assert from "node:assert/strict";
import { adjacentItem, navigationStep } from "../../src/ainiee_translate/workbench_runtime/web/scripts/navigation.js";

test("arrows and space navigate without stealing editing or dialog keys", () => {
  const event = {key: "ArrowLeft", target: {closest: () => null}};
  assert.equal(navigationStep(event), -1);
  assert.equal(navigationStep({...event, key: "ArrowRight"}), 1);
  assert.equal(navigationStep({...event, key: " "}), 1);
  for (const change of [{ctrlKey: true}, {altKey: true}, {metaKey: true}, {shiftKey: true}, {isComposing: true}, {defaultPrevented: true}, {target: {closest: () => ({})}}])
    assert.equal(navigationStep({...event, ...change}), 0);
});

test("navigation wraps and finds neighbors when a reviewed item leaves the filter", () => {
  const all = [{id: "a"}, {id: "b"}, {id: "c"}];
  assert.equal(adjacentItem(all, all, "c", 1).id, "a");
  assert.equal(adjacentItem(all, all, "a", -1).id, "c");
  const remaining = [all[0], all[2]];
  assert.equal(adjacentItem(all, remaining, "b", 1).id, "c");
  assert.equal(adjacentItem(all, remaining, "b", -1).id, "a");
  assert.equal(adjacentItem(all, [], "b", 1), null);
});
