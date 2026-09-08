import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/transcriptRows.ts", import.meta.url))],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
const { buildTranscriptRows } = await import(moduleUrl);

const node = (name, type, children = []) => ({
  name,
  description: "",
  type,
  model: "",
  tools: [],
  skills: [],
  path: [name],
  mentionable: true,
  children,
});
const root = node("root", "sequential", [
  node("opening", "llm"),
  node("research", "parallel", [
    node("facts", "llm"),
    node("risks", "llm"),
    node("options", "llm"),
    node("costs", "llm"),
  ]),
  node("review_loop", "loop", [node("reviewer", "llm")]),
  node("closing", "llm"),
]);

const assistant = (author, invocationId = "inv-1") => ({
  role: "assistant",
  blocks: [{ kind: "text", text: author }],
  meta: { author, invocationId },
});

test("groups only direct children from the same parallel stage", () => {
  const turns = [
    { role: "user", blocks: [{ kind: "text", text: "start" }] },
    assistant("opening"),
    assistant("facts"),
    assistant("risks"),
    assistant("options"),
    assistant("costs"),
    assistant("reviewer"),
    assistant("reviewer"),
    assistant("closing"),
  ];

  const rows = buildTranscriptRows(turns, root);
  assert.deepEqual(rows.map((row) => row.turnIndexes), [
    [0],
    [1],
    [2, 3, 4, 5],
    [6],
    [7],
    [8],
  ]);
  assert.equal(rows[2].parallelParent, "research");
});

test("does not group parallel responses from different invocations", () => {
  const rows = buildTranscriptRows([
    assistant("facts", "inv-1"),
    assistant("risks", "inv-2"),
  ], root);
  assert.deepEqual(rows.map((row) => row.turnIndexes), [[0], [1]]);
  assert.equal(rows[0].parallelParent, "research");
  assert.notEqual(rows[0].key, rows[1].key);
});
