import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../src/create/AgentBuildCanvas.tsx", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);

test("keeps the React Flow MiniMap implementation disabled for now", () => {
  assert.match(source, /const MINIMAP_ENABLED = false;/);
  assert.match(source, /\{MINIMAP_ENABLED && \(/);
  assert.match(source, /function CanvasMiniMapNode/);
  assert.match(source, /nodeComponent=\{CanvasMiniMapNode\}/);
  assert.match(source, /nodeClassName=\{\(node\)/);
  assert.match(source, /abc-minimap-node-group/);
  assert.match(source, /abc-minimap-node-terminal/);
  assert.match(source, /abc-minimap-node-agent/);
});

test("labels LLM nodes as 智能体", () => {
  assert.match(source, /llm:\s*\{[\s\S]*?label:\s*"智能体"/);
  assert.doesNotMatch(source, /label:\s*"执行步骤"/);
});

test("uses distinct restrained type colors and removes the LLM node icon", () => {
  assert.match(source, /loop:\s*\{[\s\S]*?label:\s*"循环执行"/);
  assert.match(source, /\{type !== "llm" && \(/);
  assert.match(
    customCreateSource,
    /data-active-type=\{node\.agentType \?\? "llm"\}/,
  );
  assert.match(customCreateSource, /data-agent-type=\{t\.id\}/);
});

test("supports a read-only preview without mutation affordances", () => {
  assert.match(source, /readOnly\?: boolean/);
  assert.match(source, /interactivePreview\?: boolean/);
  assert.match(source, /readOnly \? null : \{ onAdd, onInsert, onInsertRoot, onDelete \}/);
  assert.match(source, /nodesDraggable=\{!readOnly\}/);
  assert.match(source, /elementsSelectable=\{!readOnly\}/);
  assert.match(
    source,
    /readOnly[\s\S]*?padding: 0\.16, minZoom: 0\.05, maxZoom: 0\.9/,
  );
  assert.match(source, /panOnDrag=\{!readOnly \|\| interactivePreview\}/);
});
