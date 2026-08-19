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
const builderChatSource = readFileSync(
  new URL("../src/create/AgentBuilderChatPanel.tsx", import.meta.url),
  "utf8",
);
const builderChatStyles = readFileSync(
  new URL("../src/create/AgentBuilderChatPanel.css", import.meta.url),
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
const createAgentIconsSource = readFileSync(
  new URL("../src/ui/icons/CreateAgentIcons.tsx", import.meta.url),
  "utf8",
);
const capabilityIconsSource = readFileSync(
  new URL("../src/ui/CapabilityIcons.tsx", import.meta.url),
  "utf8",
);
const groupSource = source.slice(
  source.indexOf("function AgentGroupNode"),
  source.indexOf("function ParallelJunctionNode"),
);

test("matches the Figma configuration header icon geometry", () => {
  assert.match(
    customCreateStyles,
    /\.cw-detail-header\s*\{[\s\S]*?padding:\s*0 20px;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail-agent-icon\s*\{[\s\S]*?width:\s*40px;[\s\S]*?height:\s*40px;[\s\S]*?border-radius:\s*6px;[\s\S]*?background:\s*#e8ebf9;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail-agent-icon svg\s*\{[\s\S]*?width:\s*24px;[\s\S]*?height:\s*24px;/,
  );
  assert.match(
    createAgentIconsSource,
    /export function AgentFaceSquareIcon[\s\S]*?d="M5\.5 6V7\.5M14\.5 6V7\.5[\s\S]*?strokeWidth="2"/,
  );
});

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

test("shows missing Agent names in red on the canvas and configuration card", () => {
  assert.match(source, /return agent\.name\.trim\(\) \|\| "名称未配置"/);
  assert.match(source, /nameMissing: type !== "a2a" && agent\.name\.trim\(\)\.length === 0/);
  assert.match(source, /className=\{data\.nameMissing \? "is-name-missing" : undefined\}/);
  assert.match(
    cssSource,
    /\.abc-agent-card-head strong\.is-name-missing\s*\{[\s\S]*?color: hsl\(var\(--destructive\)\);/,
  );
  assert.match(customCreateSource, /node\.name\.trim\(\) \|\| "名称未配置"/);
  assert.match(
    customCreateStyles,
    /\.cw-detail-header strong\.is-name-missing\s*\{[\s\S]*?color: hsl\(var\(--destructive\)\);/,
  );
});

test("defines canvas workspace variables without relying on the create page shell", () => {
  const rootRule = cssSource.match(/\.abc-root\s*\{[^}]*\}/)?.[0] ?? "";
  const canvasRule = cssSource.match(/\.abc-canvas\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(rootRule, /--cw-workspace-ink: 222 24% 13%;/);
  assert.match(rootRule, /--cw-workspace-accent: 162 44% 32%;/);
  assert.match(rootRule, /--cw-workspace-warm: 42 28% 96%;/);
  assert.match(rootRule, /border-right:\s*0;/);
  assert.match(rootRule, /background:\s*#f0f0f0;/);
  assert.match(canvasRule, /background:\s*#f0f0f0;/);
  assert.match(source, /<Background gap=\{18\} size=\{2\} color="#D8D8D8" \/>/);
  assert.doesNotMatch(canvasRule, /radial-gradient|#fbfbfc/);
  assert.match(
    cssSource,
    /\.abc-terminal\s*\{[\s\S]*?box-sizing:\s*border-box;[\s\S]*?width:\s*120px;[\s\S]*?height:\s*52px;[\s\S]*?border:\s*0;[\s\S]*?border-radius:\s*10px;[\s\S]*?background:\s*#fff;[\s\S]*?box-shadow:\s*none;[\s\S]*?color:\s*#0c0d0e;[\s\S]*?font-size:\s*13px;[\s\S]*?font-weight:\s*500;[\s\S]*?line-height:\s*20px;/,
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
  assert.match(
    source,
    /makeEdge\("terminal-input", rootId, undefined, \{ figmaFlow: true \}\)/,
  );
  assert.doesNotMatch(source, /rootInsert/);
});

test("renders the root LLM agent as a child-capable container", () => {
  assert.match(source, /function rendersAsGroup/);
  assert.match(
    source,
    /type === "llm" && \(path\.length === 0 \|\| agent\.subAgents\.length > 0\)/,
  );
  assert.match(source, /function AgentCardContent/);
  assert.match(source, /添加子 Agent/);
  assert.match(source, /actions\.onAdd\(data\.path!\)/);
});

test("owns nested Agents inside the clicked parent container", () => {
  assert.match(
    source,
    /parentId,\s*extent: "parent",\s*position,\s*style: \{ width: NODE_WIDTH, height \},\s*data:/,
  );
  assert.match(
    source,
    /return addContainedNode\(\s*child,\s*\[\.\.\.path, index\],\s*id,\s*childPosition,\s*type,/,
  );
  assert.match(source, /childCount > 0 \? " has-children" : " is-empty"/);
  assert.match(source, /aria-label=\{`\$\{data\.title\} 的子 Agent 容器`\}/);
  assert.match(cssSource, /\.abc-group-body\s*\{[\s\S]*?inset:\s*0;/);
  assert.match(
    cssSource,
    /\.abc-group-head\s*\{[\s\S]*?width:\s*calc\(100% - 16px\);[\s\S]*?height:\s*38px;[\s\S]*?margin:\s*8px 8px 0;/,
  );
  assert.doesNotMatch(source, /abc-group-body-label/);
});

test("shows the concrete group agent name in workflow containers", () => {
  assert.match(
    source,
    /<strong[\s\S]*?title=\{data\.title\}[\s\S]*?>[\s\S]*?\{data\.title\}[\s\S]*?<\/strong>/,
  );
  assert.doesNotMatch(source, /<strong>\{copy\.label\}<\/strong>/);
});

test("does not reserve delete-button space on the non-removable root agent", () => {
  assert.match(source, /actions && data\.path !== undefined && data\.path\.length > 0/);
});

test("uses the dashed add action without duplicate group boundary buttons", () => {
  assert.match(groupSource, /className="abc-group-summary-add nodrag nopan"/);
  assert.doesNotMatch(groupSource, /abc-group-boundary-actions/);
  assert.doesNotMatch(groupSource, /aria-label="添加到最前"|aria-label="添加到最后"/);
  assert.doesNotMatch(cssSource, /\.abc-group-boundary-add/);
});

test("keeps the sub-Agent action inside every editable Agent card", () => {
  assert.match(source, /className="abc-agent-card-add nodrag nopan"/);
  assert.match(source, /<p title=\{data\.description\}>\{data\.description\}<\/p>[\s\S]*?abc-agent-card-add/);
  assert.match(source, /onAdd=\{[\s\S]*?actions && data\.path !== undefined/);
  assert.match(
    cssSource,
    /\.abc-agent-card-add\s*\{[\s\S]*?width:\s*100% !important;[\s\S]*?height:\s*26px !important;[\s\S]*?justify-content:\s*center !important;[\s\S]*?padding:\s*4px 6px !important;[\s\S]*?border:\s*1px dashed #d8dddb !important;[\s\S]*?font-size:\s*11px !important;[\s\S]*?font-weight:\s*400 !important;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-add::before\s*\{[\s\S]*?box-shadow:\s*none !important;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-add:hover\s*\{[\s\S]*?border-color:\s*var\(--abc-agent-card-tone\) !important;[\s\S]*?background:\s*var\(--abc-agent-card-tone\) !important;/,
  );
  assert.match(groupSource, /className="abc-group-summary-add nodrag nopan"/);
  assert.match(groupSource, /actions && data\.path !== undefined/);
});

test("matches the Figma node shell and shows description plus capability counts", () => {
  assert.match(
    source,
    /description: agent\.description\.trim\(\) \|\| "描述未配置"/,
  );
  assert.doesNotMatch(source, /instruction: agent\.instruction/);
  assert.match(
    source,
    /agent\.modelName\?\.trim\(\) \|\| agent\.model\?\.trim\(\) \|\| "模型未配置"/,
  );
  assert.match(source, /AgentToolCountIcon/);
  assert.match(source, /AgentSkillCountIcon/);
  assert.match(source, /className="abc-agent-card-identity"/);
  assert.match(source, /toolCount: uniqueCapabilityCount/);
  assert.match(source, /skillCount: uniqueCapabilityCount/);
  assert.match(
    cssSource,
    /\.abc-agent-card\s*\{[\s\S]*?--abc-agent-card-tone:\s*#e8ebf9;[\s\S]*?box-sizing:\s*border-box;[\s\S]*?width:\s*214px;[\s\S]*?height:\s*100%;[\s\S]*?padding:\s*8px;[\s\S]*?border:\s*0\.5px solid var\(--abc-agent-card-tone\);[\s\S]*?border-radius:\s*12px;[\s\S]*?background:\s*#fff;[\s\S]*?box-shadow:\s*none;[\s\S]*?text-align:\s*left;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-head\s*\{[\s\S]*?flex:\s*0 0 42px;[\s\S]*?border-radius:\s*6px;[\s\S]*?background:\s*var\(--abc-agent-card-tone\);/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-identity\s*\{[\s\S]*?gap:\s*3px;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-head strong\s*\{[\s\S]*?font-size:\s*12px;[\s\S]*?line-height:\s*16px;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-main p\s*\{[\s\S]*?font-size:\s*10\.5px;[\s\S]*?line-height:\s*15px;[\s\S]*?-webkit-line-clamp:\s*2;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-stats\s*\{[\s\S]*?gap:\s*6px;[\s\S]*?border-top:\s*1px solid #ececef;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-stats > span\s*\{[\s\S]*?border-radius:\s*6px;[\s\S]*?background:\s*#f5f5f5;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-main\s*\{[\s\S]*?flex:\s*0 0 80px;[\s\S]*?gap:\s*8px;[\s\S]*?padding:\s*8px 0;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-stats\s*\{[\s\S]*?flex:\s*0 0 29px;[\s\S]*?padding:\s*8px 0 0;[\s\S]*?border-top:\s*1px solid #ececef;/,
  );
  assert.match(
    cssSource,
    /\.abc-node\.is-selected > \.abc-agent-card\s*\{[\s\S]*?border-color:\s*var\(--abc-agent-card-tone\);[\s\S]*?outline:\s*0;[\s\S]*?box-shadow:\s*inset 0 0 0 0\.5px var\(--abc-agent-card-tone\);/,
  );
  assert.doesNotMatch(
    cssSource,
    /\.abc-(?:node|group)\.is-selected[^}]*outline-offset/,
  );
});

test("uses distinct canvas marks while preserving the Agent type controls", () => {
  assert.match(source, /loop:\s*\{[\s\S]*?label:\s*"循环执行"/);
  assert.match(source, /<CanvasAgentTypeIcon type=\{type\} \/>/);
  assert.match(capabilityIconsSource, /type === "sequential"/);
  assert.match(capabilityIconsSource, /type === "parallel"/);
  assert.match(capabilityIconsSource, /type === "loop"/);
  assert.match(customCreateSource, /<Section meta=\{metaOf\("type"\)\}>/);
  assert.match(
    customCreateSource,
    /<RadioGroup<AgentType>[\s\S]*?aria-label="Agent 类型"/,
  );
  assert.match(customCreateSource, /<RadioGroup\.Item/);
  assert.match(customCreateSource, /data-agent-type=\{t\.id\}/);
});

test("shows model and capability counts only for LLM Agents", () => {
  assert.match(source, /const COMPACT_NODE_HEIGHT = 138;/);
  assert.match(source, /const nodeHeight = \(type: AgentType, readOnly: boolean\): number/);
  assert.match(source, /showsModelCapabilities\(type\)[\s\S]*?NODE_HEIGHT[\s\S]*?COMPACT_NODE_HEIGHT/);
  assert.match(source, /\{showModelCapabilities && \([\s\S]*?abc-agent-card-model/);
  assert.match(source, /\{showModelCapabilities && \([\s\S]*?abc-agent-card-stats/);
  assert.match(groupSource, /\{showModelCapabilities && \([\s\S]*?<small title=\{data\.modelLabel\}>/);
  assert.match(groupSource, /\{showModelCapabilities && \([\s\S]*?abc-group-summary-stats/);
  assert.match(cssSource, /\.abc-node:not\(\.is-llm\)\s*\{[\s\S]*?height:\s*138px;/);
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

test("compacts read-only nodes after mutation actions are removed", () => {
  assert.match(source, /const READ_ONLY_NODE_HEIGHT = 133;/);
  assert.match(source, /const READ_ONLY_COMPACT_NODE_HEIGHT = 104;/);
  assert.match(source, /const READ_ONLY_GROUP_SUMMARY_HEIGHT = 84;/);
  assert.match(source, /const READ_ONLY_GROUP_COMPACT_SUMMARY_HEIGHT = 46;/);
  assert.match(source, /const nodeHeight = \(type: AgentType, readOnly: boolean\): number/);
  assert.match(source, /const groupSummaryHeight = \(type: AgentType, readOnly: boolean\): number/);
  assert.match(source, /function measureAgent\([\s\S]*?readOnly = false,[\s\S]*?nodeHeight\(type, readOnly\)/);
  assert.match(source, /measureAgent\(child, \[\.\.\.path, index\], direction, readOnly\)/);
  assert.match(source, /function buildCanvasGraph\([\s\S]*?readOnly = false,/);
  assert.match(source, /buildCanvasGraph\(draft, direction, readOnly\)/);
  assert.doesNotMatch(source, /nodeHeight\(type\);/);
  assert.match(
    cssSource,
    /\.abc-root\.is-readonly \.abc-group\.is-llm\s*\{[\s\S]*?--abc-group-summary-height:\s*84px;/,
  );
  assert.match(
    cssSource,
    /\.abc-root\.is-readonly \.abc-group:not\(\.is-llm\)\s*\{[\s\S]*?--abc-group-summary-height:\s*46px;/,
  );
  assert.match(
    cssSource,
    /\.abc-root\.is-readonly \.abc-agent-card-main\s*\{[\s\S]*?flex:\s*0 0 46px;/,
  );
  assert.match(cssSource, /\.abc-root\.is-readonly \.abc-node\.is-llm\s*\{[\s\S]*?height:\s*133px;/);
  assert.match(cssSource, /\.abc-root\.is-readonly \.abc-node:not\(\.is-llm\)\s*\{[\s\S]*?height:\s*104px;/);
});

test("keeps the parent identity compact while restoring its full summary", () => {
  assert.match(
    source,
    /const GROUP_HEADER_HEIGHT = 46;/,
  );
  assert.match(source, /const GROUP_SUMMARY_HEIGHT = 122;/);
  assert.match(
    source,
    /const GROUP_COMPACT_SUMMARY_HEIGHT = 84;/,
  );
  assert.match(source, /const showsModelCapabilities = \(type: AgentType\): boolean => type === "llm";/);
  assert.match(source, /const groupContentTop = \(type: AgentType, readOnly: boolean\): number/);
  assert.match(source, /childCount > 0 \? " has-children" : " is-empty"/);
  assert.match(groupSource, /className="abc-group-summary"/);
  assert.match(
    groupSource,
    /className="abc-group-description" title=\{data\.description\}>[\s\S]*?\{data\.description\}/,
  );
  assert.match(groupSource, /className="abc-group-summary-add nodrag nopan"/);
  assert.match(groupSource, /className="abc-group-summary-stats"/);
  assert.match(groupSource, /\{showModelCapabilities && \(/);
  assert.match(groupSource, /<AgentSkillCountIcon \/>[\s\S]*?data\.skillCount/);
  assert.match(groupSource, /<AgentToolCountIcon \/>[\s\S]*?data\.toolCount/);
  assert.doesNotMatch(groupSource, /<AgentCardContent/);
  assert.match(
    cssSource,
    /\.abc-group\s*\{[\s\S]*?display:\s*flow-root;/,
  );
  assert.match(
    cssSource,
    /\.abc-group-head\s*\{[\s\S]*?width:\s*calc\(100% - 16px\);[\s\S]*?height:\s*38px;[\s\S]*?background:\s*var\(--abc-group-tone\);[\s\S]*?text-align:\s*left;/,
  );
  assert.doesNotMatch(groupSource, /<em>\{childCount\}/);
  assert.match(
    cssSource,
    /\.abc-group-summary\s*\{[\s\S]*?height:\s*var\(--abc-group-summary-height\);[\s\S]*?padding:\s*8px 16px;[\s\S]*?text-align:\s*left;/,
  );
  assert.match(cssSource, /\.abc-group\s*\{[\s\S]*?--abc-group-summary-height:\s*84px;/);
  assert.match(cssSource, /\.abc-group\.is-llm\s*\{[\s\S]*?--abc-group-summary-height:\s*122px;/);
  assert.match(
    cssSource,
    /\.abc-group-summary-stats\s*\{[\s\S]*?margin-top:\s*8px;[\s\S]*?padding-top:\s*8px;/,
  );
  assert.doesNotMatch(cssSource, /\.abc-group-summary-stats\s*\{[\s\S]*?margin-top:\s*auto;/);
  assert.match(
    cssSource,
    /\.abc-group-description\s*\{[\s\S]*?-webkit-line-clamp:\s*2;/,
  );
});

test("measures empty and nested groups below the parent summary", () => {
  assert.match(
    source,
    /if \(sizes\.length === 0\) \{[\s\S]*?width: GROUP_MIN_WIDTH,[\s\S]*?height: contentTop/,
  );
  assert.match(
    source,
    /height:\s*contentTop \+[\s\S]*?sizes\.reduce/,
  );
  assert.match(
    source,
    /height:\s*contentTop \+[\s\S]*?tallestChild/,
  );
  assert.doesNotMatch(source, /GROUP_HEADER_HEIGHT \+\s*flowPadding/);
});

test("starts child nodes and parallel rails after the parent summary", () => {
  assert.match(
    source,
    /y:\s*contentTop \+[\s\S]*?type === "parallel" \? PARALLEL_RAIL_SPACE/,
  );
  assert.match(source, /y: contentTop \+ cursor/);
  assert.match(
    source,
    /const splitPosition =[\s\S]*?contentTop \+[\s\S]*?const mergePosition =[\s\S]*?contentTop \+/,
  );
  assert.doesNotMatch(cssSource, /\.abc-group-boundary-actions/);
});

test("keeps child Agents inside a visible parent body with semantic flow lines", () => {
  assert.match(source, /parentId,\s*extent: "parent"/);
  assert.match(source, /className="abc-group-body"/);
  assert.match(source, /aria-label=\{`\$\{data\.title\} 的子 Agent 容器`\}/);
  assert.match(
    cssSource,
    /\.abc-group-body\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?border:\s*1px solid var\(--abc-group-tone\);[\s\S]*?background:\s*rgb\(255 255 255 \/ 74%\);/,
  );

  assert.doesNotMatch(source, /sourceHandle:\s*"child-source"/);
  assert.doesNotMatch(source, /makeEdge\(id, childId, "调用"/);
  assert.doesNotMatch(source, /makeEdge\(id, childIds\[0\], "开始"/);
  assert.match(source, /makeEdge\(childIds\[index\], childIds\[index \+ 1\], "然后"/);
  assert.match(source, /"继续循环"/);

  assert.match(source, /junctionKind\?:\s*"split" \| "merge"/);
  assert.match(source, /addParallelJunction\(\s*"split"/);
  assert.match(source, /addParallelJunction\(\s*"merge"/);
  assert.doesNotMatch(source, /makeEdge\(id, splitId, "分发"/);
  assert.match(source, /makeEdge\(splitId, childId/);
  assert.match(source, /makeEdge\(childId, mergeId/);
  assert.match(source, /groupExitIds\.set\(id, \[id\]\)/);
  assert.match(source, /return groupExitIds\.get\(id\) \?\? \[id\]/);
  assert.match(source, /const topLevelId = \(nodeId: string\)/);
  assert.match(source, /if \(source !== target\) graph\.setEdge\(source, target\)/);
  assert.match(source, /function ParallelJunctionNode/);
  assert.match(cssSource, /\.abc-junction\.is-split \.abc-junction-mark/);
  assert.match(cssSource, /\.abc-junction\.is-merge \.abc-junction-mark/);
});

test("selection only strengthens the Agent card border without moving its content", () => {
  const selectionRule = cssSource.match(
    /\.abc-node\.is-selected > \.abc-agent-card\s*\{[^}]*\}/,
  )?.[0] ?? "";
  assert.match(selectionRule, /box-shadow:\s*inset 0 0 0 0\.5px/);
  assert.doesNotMatch(selectionRule, /transform|translate|margin|padding/);
  const groupSelectionRule = cssSource.match(
    /\.abc-group\.is-selected > \.abc-group-body\s*\{[^}]*\}/,
  )?.[0] ?? "";
  assert.match(groupSelectionRule, /inset 0 0 0 0\.5px/);
  assert.doesNotMatch(groupSelectionRule, /transform|translate|margin|padding/);
});

test("reuses the session canvas between the Figma chat and configuration panels", () => {
  assert.match(source, /direction\?: CanvasDirection/);
  assert.match(source, /direction = "vertical"/);
  assert.match(source, /rankdir: direction === "vertical" \? "TB" : "LR"/);
  assert.match(source, /direction === "vertical" \? Position\.Top : Position\.Left/);
  assert.match(source, /direction === "vertical" \? Position\.Bottom : Position\.Right/);
  assert.match(customCreateSource, /<AgentBuildCanvas[\s\S]*?direction="vertical"/);
  assert.match(agentWorkspaceSource, /<AgentBuildCanvas[\s\S]*?direction="horizontal"/);
  assert.match(projectPreviewSource, /<AgentBuildCanvas[\s\S]*?direction="horizontal"/);
  assert.match(
    customCreateSource,
    /<AgentBuilderChatPanel[\s\S]*?<AgentBuildCanvas[\s\S]*?key="builder-config"[\s\S]*?className=\{`cw-detail is-\$\{configTab\}`\}/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-editor > \.abc-root\s*\{[\s\S]*?flex:\s*1 1 auto;[\s\S]*?min-height:\s*0;[\s\S]*?border-radius:\s*0;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail\s*\{[\s\S]*?flex:\s*0 0 420px;[\s\S]*?width:\s*420px;[\s\S]*?max-width:\s*420px;/,
  );
  assert.match(builderChatSource, /<Textarea[\s\S]*?isImeCompositionEvent\(event\.nativeEvent\)/);
  assert.match(
    builderChatSource,
    /@openai\/apps-sdk-ui\/components\/Textarea/,
  );
  assert.match(builderChatSource, /import \{ Blocks \} from "\.\.\/ui\/Blocks"/);
  assert.match(
    builderChatSource,
    /messages\.map\(\(message\) =>[\s\S]*?<Blocks[\s\S]*?blocks=\{message\.blocks \?\? \[\]\}[\s\S]*?streaming=\{message\.streaming === true\}/,
  );
  assert.match(
    builderChatSource,
    /className=\{`turn turn--\$\{message\.role\} agent-builder-chat-turn`\}/,
  );
  assert.doesNotMatch(builderChatSource, /ConversationCopyButton|ConversationFeedbackButtons|ConversationFeedbackRating/);
  assert.doesNotMatch(builderChatSource, /lucide-react/);
  assert.match(builderChatSource, /<CreateBackIcon \/>/);
  assert.doesNotMatch(builderChatSource, /我现在正将所选的 2 个工具添加到此智能体中/);
  assert.match(
    builderChatStyles,
    /\.agent-builder-chat\s*\{[\s\S]*?width:\s*var\(--cw-builder-chat-width, 420px\);/,
  );
  assert.match(
    builderChatStyles,
    /\.agent-builder-chat-composer\s*\{[\s\S]*?margin:\s*0 20px[\s\S]*?var\(--cw-builder-chat-header-height, 58px\)[\s\S]*?var\(--cw-builder-chat-icon-size, 20px\)[\s\S]*?\/\s*2/,
  );
  assert.match(
    builderChatStyles,
    /\.agent-builder-chat-composer:focus-within\s*\{[\s\S]*?border-color:\s*#c9cdd4;[\s\S]*?box-shadow:\s*0 6px 18px rgb\(16 16 19 \/ 7%\);/,
  );
  assert.doesNotMatch(
    builderChatStyles,
    /\.agent-builder-chat-composer:focus-within\s*\{[\s\S]*?rgb\(16 16 19 \/ 30%\)/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-editor\s*\{[\s\S]*?--cw-builder-panel-inset:\s*8px;[\s\S]*?padding:\s*var\(--cw-builder-panel-inset\);/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-editor:has\(> \.cw-builder-chat-motion\)\s*\{[\s\S]*?padding:\s*var\(--cw-builder-panel-inset\);/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-open-chat-motion\s*\{[\s\S]*?top:\s*var\(--cw-builder-panel-inset\);[\s\S]*?left:\s*var\(--cw-builder-panel-inset\);[\s\S]*?width:\s*calc\([\s\S]*?var\(--cw-builder-chat-header-padding-inline\)[\s\S]*?var\(--cw-builder-chat-icon-size\)[\s\S]*?height:\s*var\(--cw-builder-chat-header-height\);[\s\S]*?align-items:\s*center;[\s\S]*?justify-content:\s*center;/,
  );
  assert.doesNotMatch(
    customCreateStyles,
    /\.(?:cw-builder-chat-motion|cw-detail)\s*\{[\s\S]*?margin-top:\s*calc\(-1\s*\*\s*var\(--cw-builder-header-edge-space\)\)/,
  );
  assert.match(
    builderChatStyles,
    /\.agent-builder-chat-header\s*\{[\s\S]*?height:\s*var\(--cw-builder-chat-header-height, 58px\);[\s\S]*?padding:\s*0 var\(--cw-builder-chat-header-padding-inline, 20px\);/,
  );
  assert.match(
    builderChatStyles,
    /\.agent-builder-chat-thread\s*\{[\s\S]*?padding:\s*16px 20px 20px;/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-detail-scroll\s*\{[\s\S]*?padding:\s*24px;/,
  );
  assert.match(customCreateSource, /setBuilderPanel\("config"\)/);
  assert.match(
    customCreateStyles,
    /@media \(max-width: 860px\)[\s\S]*?\.cw-detail\s*\{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*none;/,
  );
});

test("keeps edge anchors functional while using the borderless Figma card", () => {
  assert.match(source, /<Handle type="target"[\s\S]*?className="abc-handle"/);
  assert.match(source, /<Handle type="source"[\s\S]*?className="abc-handle"/);
  assert.match(
    cssSource,
    /\.abc-handle\s*\{[\s\S]*?opacity:\s*0\s*!important;[\s\S]*?pointer-events:\s*none;/,
  );
  assert.match(source, /groupHeaderAligned[\s\S]*?GROUP_HEADER_HEIGHT/);
  assert.match(cssSource, /\.abc-root\.is-horizontal \.abc-group > \.react-flow__handle-left/);
  assert.match(cssSource, /top:\s*32px\s*!important/);
  assert.match(
    cssSource,
    /\.abc-node\s*\{[\s\S]*?border:\s*0;[\s\S]*?box-shadow:\s*none;/,
  );
  assert.match(
    cssSource,
    /\.abc-group\s*\{[\s\S]*?border:\s*0;[\s\S]*?box-shadow:\s*none;/,
  );
  assert.match(
    cssSource,
    /\.abc-canvas \.react-flow__node-group\s*\{[\s\S]*?border:\s*0;[\s\S]*?box-shadow:\s*none;/,
  );
  assert.match(
    cssSource,
    /\.abc-terminal\s*\{[\s\S]*?border:\s*0;[\s\S]*?border-radius:\s*10px;/,
  );
});

test("balances the Figma request and reply styling with the Agent card", () => {
  assert.match(source, /const TERMINAL_WIDTH = 120;/);
  assert.match(source, /const TERMINAL_HEIGHT = 52;/);
  assert.match(source, /terminalKind: "input"/);
  assert.match(source, /terminalKind: "output"/);
  assert.match(source, /TerminalUserRequestIcon/);
  assert.match(source, /TerminalFinalReplyIcon/);
  assert.match(source, /figmaFlow\?: boolean/);
  assert.match(source, /options\?\.figmaFlow\s*\? "#C9CDD4"/);
  assert.match(source, /markerEnd: options\?\.figmaFlow\s*\? undefined/);
  assert.match(source, /getStraightPath\(\{ sourceX, sourceY, targetX, targetY \}\)/);
  assert.match(source, /const FIGMA_FLOW_LINE_LENGTH = 69;/);
  assert.match(source, /ranksep: FIGMA_FLOW_LINE_LENGTH \+ FLOW_HANDLE_SIZE/);
  assert.match(
    source,
    /makeEdge\(exitId, "terminal-output", undefined, \{ figmaFlow: true \}\)/,
  );
  assert.match(
    cssSource,
    /\.abc-terminal-mark\s*\{[\s\S]*?width:\s*32px;[\s\S]*?height:\s*32px;[\s\S]*?border-radius:\s*5px;/,
  );
  assert.match(cssSource, /\.abc-terminal\.is-input \.abc-terminal-mark\s*\{[\s\S]*?background:\s*#f9eea2;/);
  assert.match(cssSource, /\.abc-terminal\.is-output \.abc-terminal-mark\s*\{[\s\S]*?background:\s*#d2e6ff;/);
});

test("canvas retries fitting until it has dimensions", () => {
  assert.match(source, /container\.clientWidth === 0 \|\| container\.clientHeight === 0/);
  assert.match(source, /attempt < 8/);
  assert.match(source, /fitAfterLayout\(attempt \+ 1\)/);
  assert.match(source, /onInit=\{\(\) => fitAfterLayout\(\)\}/);
});

test("refits editable and read-only canvases as their available area resizes", () => {
  assert.match(source, /const fitFrameRef = useRef<number \| null>\(null\)/);
  assert.match(
    source,
    /cancelScheduledFit[\s\S]*?window\.cancelAnimationFrame\(fitFrameRef\.current\)/,
  );
  assert.match(
    source,
    /fitAfterLayout[\s\S]*?cancelScheduledFit\(\);[\s\S]*?fitFrameRef\.current = window\.requestAnimationFrame/,
  );
  assert.match(
    source,
    /const container = canvasRef\.current;[\s\S]*?const observer = new ResizeObserver\(\(\) => fitAfterLayout\(\)\);[\s\S]*?observer\.observe\(container\)/,
  );
  assert.doesNotMatch(
    source,
    /if \(!readOnly \|\| !canvasRef\.current\) return;/,
  );
  assert.match(
    source,
    /observer\.disconnect\(\);[\s\S]*?cancelScheduledFit\(\);/,
  );
});

test("uses concise labels for child agent basics", () => {
  assert.match(
    customCreateSource,
    /<label className="cw-label" htmlFor="cw-agent-name">\s*名称[\s\S]*?<Input[\s\S]*?id="cw-agent-name"/,
  );
  assert.match(customCreateSource, /\{isRootAgent \? "描述" : "智能体描述"\}/);
  assert.doesNotMatch(customCreateSource, /"步骤名称"|"任务说明"/);
});

test("hides capabilities for orchestration types and falls back to basics", () => {
  assert.match(
    customCreateSource,
    /useEffect\(\(\) => \{\s*if \(orchestrator && configTab === "capabilities"\) \{\s*setConfigTab\("basic"\);\s*\}\s*\}, \[configTab, orchestrator\]\);/,
  );
  assert.match(
    customCreateSource,
    /\{!orchestrator && \(\s*<button[\s\S]*?aria-selected=\{configTab === "capabilities"\}[\s\S]*?>能力扩展<\/button>\s*\)\}/,
  );
});

test("refits the graph after React Flow finishes measuring its nodes", () => {
  assert.match(source, /const nodesInitialized = useNodesInitialized\(\)/);
  assert.match(source, /if \(!nodesInitialized\) return;[\s\S]*?fitAfterLayout\(\)/);
});

test("preserves measured dimensions only while the graph structure is stable", () => {
  assert.match(
    source,
    /const currentNodes = new Map\([\s\S]*?current\.map\(\(node\) => \[node\.id, node\] as const\)/,
  );
  assert.match(
    source,
    /measured:\s*!structureChanged &&[\s\S]*?currentNode &&[\s\S]*?currentNode\.type === node\.type[\s\S]*?\? currentNode\.measured[\s\S]*?: undefined/,
  );
});
