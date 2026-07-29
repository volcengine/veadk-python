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
const customCreateStyles = readFileSync(
  new URL("../src/create/CustomCreate.css", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const agentWorkspaceSource = readFileSync(
  new URL("../src/ui/AgentWorkspace.tsx", import.meta.url),
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
  const canvasRule = cssSource.match(/\.abc-canvas\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(rootRule, /--cw-workspace-ink: 222 24% 13%;/);
  assert.match(rootRule, /--cw-workspace-accent: 162 44% 32%;/);
  assert.match(rootRule, /--cw-workspace-warm: 42 28% 96%;/);
  assert.match(rootRule, /border-right:\s*0;/);
  assert.match(rootRule, /background:\s*#fff;/);
  assert.match(canvasRule, /background:\s*#fff;/);
  assert.doesNotMatch(canvasRule, /radial-gradient|#fbfbfc/);
  assert.match(
    cssSource,
    /\.abc-terminal\s*\{[\s\S]*?background: hsl\(var\(--secondary\) \/ 0\.68\);[\s\S]*?box-shadow: none;[\s\S]*?color: hsl\(var\(--foreground\) \/ 0\.76\);/,
  );
});

test("starts directly with the workflow canvas without a toolbar", () => {
  assert.doesNotMatch(source, /className="abc-head"/);
  assert.doesNotMatch(source, /onReset|自动整理|重置执行流程/);
  assert.doesNotMatch(cssSource, /\.abc-head/);
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
  assert.match(source, /<small>\{data\.description\}<\/small>/);
});

test("shows the concrete group agent name in workflow containers", () => {
  assert.match(source, /<strong title=\{data\.title\}>\{data\.title\}<\/strong>/);
  assert.doesNotMatch(source, /<strong>\{copy\.label\}<\/strong>/);
});

test("does not reserve delete-button space on the non-removable root agent", () => {
  assert.match(source, /actions && data\.path !== undefined && data\.path\.length > 0/);
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

test("uses the agent description as a two-line subtitle without count badges", () => {
  assert.match(
    source,
    /description: agent\.description\.trim\(\) \|\| PATTERN_COPY\[type\]\.description/,
  );
  assert.match(source, /<small>\{data\.description\}<\/small>/);
  assert.doesNotMatch(source, /data\.childCount && <small>/);
  assert.doesNotMatch(source, /个\{childUnit\}|个步骤<\/small>/);
  assert.doesNotMatch(source, /<em>\{childCount\}/);
  assert.match(
    cssSource,
    /\.abc-group-head small\s*\{[\s\S]*?display: -webkit-box;[\s\S]*?-webkit-line-clamp: 2;/,
  );
  assert.match(
    cssSource,
    /\.abc-node-copy > small\s*\{[\s\S]*?-webkit-line-clamp: 2;/,
  );
});

test("uses distinct restrained type colors and removes the LLM node icon", () => {
  assert.match(source, /loop:\s*\{[\s\S]*?label:\s*"循环执行"/);
  assert.match(source, /\{type !== "llm" && \(/);
  assert.match(customCreateSource, /<Section meta=\{metaOf\("type"\)\}>/);
  assert.match(customCreateSource, /role="radiogroup" aria-label="Agent 类型"/);
  assert.match(customCreateSource, /className="cw-agent-type-radio"/);
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

test("lays out creation vertically while keeping detail and deployment previews horizontal", () => {
  assert.match(source, /direction\?: CanvasDirection/);
  assert.match(source, /rankdir: direction === "vertical" \? "TB" : "LR"/);
  assert.match(source, /direction === "vertical" \? Position\.Top : Position\.Left/);
  assert.match(source, /direction === "vertical" \? Position\.Bottom : Position\.Right/);
  assert.match(customCreateSource, /<AgentBuildCanvas[\s\S]*?direction="vertical"/);
  assert.match(agentWorkspaceSource, /<AgentBuildCanvas[\s\S]*?direction="horizontal"/);
  assert.match(projectPreviewSource, /<AgentBuildCanvas[\s\S]*?direction="horizontal"/);
  assert.match(
    customCreateStyles,
    /\.cw-editor > \.abc-root\s*\{[\s\S]*?flex-basis:\s*42%;[\s\S]*?min-width:\s*380px;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail\s*\{[\s\S]*?flex:\s*1 1 58%;[\s\S]*?max-width:\s*780px;/,
  );
  assert.match(
    customCreateStyles,
    /@media \(max-width: 860px\)[\s\S]*?\.cw-detail\s*\{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*none;/,
  );
});

test("uses concise labels for child agent basics", () => {
  assert.match(customCreateSource, /\{isRootAgent \? "Agent 名称" : "名称"\}/);
  assert.match(customCreateSource, /\{isRootAgent \? "描述" : "智能体描述"\}/);
  assert.doesNotMatch(customCreateSource, /"步骤名称"|"任务说明"/);
});

test("refits the graph after React Flow finishes measuring its nodes", () => {
  assert.match(source, /const nodesInitialized = useNodesInitialized\(\)/);
  assert.match(source, /if \(!nodesInitialized\) return;[\s\S]*?fitAfterLayout\(\)/);
});
