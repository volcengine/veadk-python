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
const cssSource = readFileSync(
  new URL("../src/create/AgentBuildCanvas.css", import.meta.url),
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

test("defines canvas workspace variables without relying on the create page shell", () => {
  const rootRule = cssSource.match(/\.abc-root\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(rootRule, /--cw-workspace-ink: 222 24% 13%;/);
  assert.match(rootRule, /--cw-workspace-accent: 162 44% 32%;/);
  assert.match(rootRule, /--cw-workspace-warm: 42 28% 96%;/);
  assert.match(cssSource, /\.abc-terminal\s*\{[\s\S]*?background: hsl\(var\(--cw-workspace-ink\)\);/);
});

test("keeps the root workflow agent visible instead of flattening its children", () => {
  assert.doesNotMatch(
    source,
    /root\.agentType === "sequential" && root\.subAgents\.length > 0/,
  );
  assert.match(source, /const rootId = pathId\(\[\]\);/);
  assert.match(source, /const exits = addTopLevelNode\(root, \[\]\);/);
  assert.match(source, /makeEdge\("terminal-input", rootId\)/);
  assert.doesNotMatch(source, /rootInsert/);
});

test("renders the root LLM agent as a child-capable container", () => {
  assert.match(source, /function rendersAsGroup/);
  assert.match(
    source,
    /type === "llm" && \(path\.length === 0 \|\| agent\.subAgents\.length > 0\)/,
  );
  assert.match(source, /type === "llm"\s*\?\s*"添加子 Agent"/);
  assert.match(source, /智能体 · 可根据任务调用框内子 Agent/);
  assert.match(source, /const childUnit = type === "llm" \? "子 Agent" : "步骤"/);
});

test("shows the concrete group agent name in workflow containers", () => {
  assert.match(source, /<strong title=\{data\.title\}>\{data\.title\}<\/strong>/);
  assert.doesNotMatch(source, /<strong>\{copy\.label\}<\/strong>/);
});

test("does not reserve delete-button space on the non-removable root agent", () => {
  assert.match(source, /actions && data\.path !== undefined && data\.path\.length > 0/);
  assert.match(cssSource, /\.abc-group:has\(> \.abc-node-delete\) \.abc-group-head em\s*\{[\s\S]*?right: 48px;/);
});

test("keeps boundary insertion controls inside the group container", () => {
  assert.match(source, /type !== "parallel" &&/);
  assert.match(source, /className="abc-group-boundary-actions"/);
  assert.match(source, /className="abc-group-boundary-add is-start nodrag nopan"/);
  assert.match(source, /aria-label="添加到最前"/);
  assert.match(source, /actions\.onInsert\(data\.path!, 0\)/);
  assert.match(source, /className="abc-group-boundary-add is-end nodrag nopan"/);
  assert.match(source, /aria-label="添加到最后"/);
  assert.match(source, /className="abc-group-add abc-group-add-empty nodrag nopan"/);
  assert.match(cssSource, /\.abc-group-boundary-actions\s*\{/);
  assert.match(cssSource, /\.abc-group-boundary-add\s*\{/);
  assert.match(cssSource, /\.abc-group-add-empty,\n\.abc-group-add-bottom\s*\{/);
});

test("uses a single bottom add action for parallel groups", () => {
  assert.match(source, /type === "parallel" &&/);
  assert.match(source, /className="abc-group-add abc-group-add-bottom nodrag nopan"/);
  assert.match(source, /GROUP_ADD_GAP \+ GROUP_ADD_HEIGHT/);
  assert.match(source, /sizes\.length && type !== "parallel"/);
  assert.match(cssSource, /\.abc-group-add-empty,\n\.abc-group-add-bottom\s*\{/);
});

test("keeps the group count badge clear of centered title copy", () => {
  const badgeRule = cssSource.match(/\.abc-group-head em\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(cssSource, /\.abc-group-head\s*\{[\s\S]*?padding: 10px 132px 10px 72px;/);
  assert.match(badgeRule, /top: 12px;/);
  assert.doesNotMatch(badgeRule, /text-overflow: ellipsis;/);
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
  assert.match(source, /readOnly \? null : \{ onAdd, onInsert, onDelete \}/);
  assert.match(source, /nodesDraggable=\{!readOnly\}/);
  assert.match(source, /elementsSelectable=\{!readOnly\}/);
  assert.match(
    source,
    /readOnly[\s\S]*?padding: 0\.16, minZoom: 0\.05, maxZoom: 0\.9/,
  );
  assert.match(source, /panOnDrag=\{!readOnly \|\| interactivePreview\}/);
});
