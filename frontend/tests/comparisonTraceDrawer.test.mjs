import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../src/create/comparison/ComparisonTraceDrawer.tsx", import.meta.url),
  "utf8",
);

test("comparison Trace drawer explains deterministic cross-run alignment and preserves unmatched rows", () => {
  assert.match(source, /getGeneratedAgentTestTrace/);
  assert.match(source, /alignTraceEvidence/);
  assert.match(source, /baselineSpans\.map/);
  assert.match(source, /unmatchedCandidateIds/);
  assert.match(source, /无对应项/);
  assert.match(source, /优先按精确 invocation ID 或 Tool Call ID 对齐/);
  assert.match(source, /相同调用路径、确定的操作类型与同名节点顺序/);
  assert.match(source, /parent_span_id/);
});
