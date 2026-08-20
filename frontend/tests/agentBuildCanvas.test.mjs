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
const packageSource = readFileSync(
  new URL("../package.json", import.meta.url),
  "utf8",
);
const mainSource = readFileSync(
  new URL("../src/main.tsx", import.meta.url),
  "utf8",
);

test("uses FlowGram as the Agent builder canvas engine", () => {
  assert.match(source, /@flowgram\.ai\/free-layout-editor/);
  assert.match(source, /FreeLayoutEditorProvider/);
  assert.match(source, /<EditorRenderer className="abc-flowgram-editor"/);
  assert.match(source, /@flowgram\.ai\/free-layout-editor\/index\.css/);
  assert.match(packageSource, /"@flowgram\.ai\/free-layout-editor"/);
  assert.doesNotMatch(source, /@xyflow\/react|ReactFlowProvider|<ReactFlow/);
  assert.doesNotMatch(mainSource, /React\.StrictMode|<StrictMode/);
});

test("flattens every Agent into an independent workflow node", () => {
  assert.match(source, /function flattenAgentNodes/);
  assert.match(source, /agent\.subAgents\.forEach\(\(child, index\) =>/);
  assert.match(source, /flattenAgentNodes\(child, \[\.\.\.path, index\]/);
  assert.match(source, /type: "agent"/);
  assert.doesNotMatch(source, /parentId|extent: "parent"|abc-group-body/);
  assert.doesNotMatch(source, /AgentGroupNode|ParallelJunctionNode/);
});

test("removes every in-node child Agent action", () => {
  assert.doesNotMatch(source, /添加子 Agent/);
  assert.doesNotMatch(source, /abc-agent-card-add|abc-group-summary-add/);
  assert.doesNotMatch(cssSource, /\.abc-agent-card-add|\.abc-group-summary-add/);
});

test("adds nodes from a canvas-level Apps SDK UI action", () => {
  assert.match(source, /@openai\/apps-sdk-ui\/components\/Button/);
  assert.match(source, /className="abc-add-node"/);
  assert.match(source, />\s*添加节点\s*</);
  assert.match(source, /onClick=\{\(\) => onAdd\(\[\]\)\}/);
  assert.match(cssSource, /\.abc-add-node\s*\{/);
});

test("enables native FlowGram node, edge, and history interactions", () => {
  assert.match(source, /canAddLine:/);
  assert.match(source, /canDeleteLine:/);
  assert.match(source, /canDeleteNode:/);
  assert.match(source, /history:\s*\{[\s\S]*?enable:\s*true/);
  assert.match(source, /twoWayConnection:\s*false/);
  assert.match(source, /onContentChange\(ctx/);
  assert.match(source, /ctx\.document\.toJSON\(\)/);
  assert.match(source, /!structureChanged && !directionChanged/);
  assert.match(
    source,
    /key=\{`\$\{direction\}-\$\{readOnly \? "readonly" : "editable"\}`\}/,
  );
});

test("keeps vertical and horizontal ports aligned with the requested layout", () => {
  assert.match(source, /direction === "vertical" \? "top" : "left"/);
  assert.match(source, /direction === "vertical" \? "bottom" : "right"/);
  assert.match(source, /defaultPorts:/);
  assert.match(source, /type: "input"/);
  assert.match(source, /type: "output"/);
});

test("keeps the Figma Agent card DOM and visual dimensions", () => {
  assert.match(source, /function AgentCardContent/);
  assert.match(source, /className=\{`abc-agent-card is-\$\{type\}`\}/);
  assert.match(source, /className="abc-agent-card-head"/);
  assert.match(source, /className="abc-agent-card-main"/);
  assert.match(source, /className="abc-agent-card-stats"/);
  assert.match(
    cssSource,
    /\.abc-agent-card\s*\{[\s\S]*?--abc-agent-card-tone:\s*#e8ebf9;[\s\S]*?width:\s*214px;[\s\S]*?height:\s*100%;[\s\S]*?padding:\s*8px;[\s\S]*?border:\s*0\.5px solid var\(--abc-agent-card-tone\);[\s\S]*?border-radius:\s*12px;[\s\S]*?background:\s*#fff;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-head\s*\{[\s\S]*?flex:\s*0 0 42px;[\s\S]*?border-radius:\s*6px;[\s\S]*?background:\s*var\(--abc-agent-card-tone\);/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-head strong\s*\{[\s\S]*?font-size:\s*12px;[\s\S]*?line-height:\s*16px;/,
  );
  assert.match(
    cssSource,
    /\.abc-agent-card-main p\s*\{[\s\S]*?font-size:\s*10\.5px;[\s\S]*?line-height:\s*15px;[\s\S]*?-webkit-line-clamp:\s*2;/,
  );
});

test("keeps selected nodes stable without changing their geometry", () => {
  assert.match(source, /selected \? " is-selected" : ""/);
  const selectionRule = cssSource.match(
    /\.abc-node\.is-selected > \.abc-agent-card\s*\{[^}]*\}/,
  )?.[0] ?? "";
  assert.match(selectionRule, /box-shadow:\s*inset 0 0 0 0\.5px/);
  assert.doesNotMatch(selectionRule, /transform|translate|margin|padding/);
});

test("shows description and LLM capability counts without system prompts", () => {
  assert.match(source, /description: agent\.description\.trim\(\) \|\| "描述未配置"/);
  assert.doesNotMatch(source, /instruction: agent\.instruction/);
  assert.match(source, /AgentToolCountIcon/);
  assert.match(source, /AgentSkillCountIcon/);
  assert.match(source, /const showsModelCapabilities = \(type: AgentType\): boolean => type === "llm"/);
  assert.match(source, /\{showModelCapabilities && \([\s\S]*?abc-agent-card-model/);
  assert.match(source, /\{showModelCapabilities && \([\s\S]*?abc-agent-card-stats/);
});

test("shows missing Agent names in red on canvas and configuration", () => {
  assert.match(source, /return agent\.name\.trim\(\) \|\| "名称未配置"/);
  assert.match(source, /nameMissing: type !== "a2a" && agent\.name\.trim\(\)\.length === 0/);
  assert.match(source, /className=\{data\.nameMissing \? "is-name-missing" : undefined\}/);
  assert.match(cssSource, /\.abc-agent-card-head strong\.is-name-missing\s*\{[\s\S]*?color: hsl\(var\(--destructive\)\);/);
  assert.match(customCreateSource, /node\.name\.trim\(\) \|\| "名称未配置"/);
});

test("keeps the request and reply terminal cards", () => {
  assert.match(source, /terminalKind: "input"/);
  assert.match(source, /terminalKind: "output"/);
  assert.match(source, /TerminalUserRequestIcon/);
  assert.match(source, /TerminalFinalReplyIcon/);
  assert.match(cssSource, /\.abc-terminal\s*\{[\s\S]*?width:\s*120px;[\s\S]*?height:\s*52px;[\s\S]*?border-radius:\s*10px;[\s\S]*?background:\s*#fff;/);
  assert.match(cssSource, /\.abc-terminal\.is-input \.abc-terminal-mark\s*\{[\s\S]*?background:\s*#f9eea2;/);
  assert.match(cssSource, /\.abc-terminal\.is-output \.abc-terminal-mark\s*\{[\s\S]*?background:\s*#d2e6ff;/);
});

test("preserves read-only preview pan and zoom without mutation actions", () => {
  assert.match(source, /readOnly\?: boolean/);
  assert.match(source, /interactivePreview\?: boolean/);
  assert.match(source, /readonly:\s*readOnly/);
  assert.match(source, /enableReadonlyNodeDragging:\s*false/);
  assert.match(source, /canAddLine:[\s\S]*?!readOnly/);
  assert.match(source, /canDeleteLine:[\s\S]*?!readOnly/);
  assert.match(source, /\{!readOnly && \([\s\S]*?abc-add-node/);
});

test("uses the existing Figma canvas surface and FlowGram editor", () => {
  const rootRule = cssSource.match(/\.abc-root\s*\{[^}]*\}/)?.[0] ?? "";
  const canvasRule = cssSource.match(/\.abc-canvas\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(rootRule, /background:\s*#f0f0f0;/);
  assert.match(canvasRule, /background-color:\s*#f0f0f0;/);
  assert.match(canvasRule, /radial-gradient/);
  assert.match(source, /background:\s*false/);
  assert.match(source, /context\.tools\.fitView\(false\)/);
});

test("reuses canvas across builder, workspace, and preview surfaces", () => {
  assert.match(source, /direction\?: CanvasDirection/);
  assert.match(source, /direction = "vertical"/);
  assert.match(customCreateSource, /<AgentBuildCanvas[\s\S]*?direction="vertical"/);
  assert.match(agentWorkspaceSource, /<AgentBuildCanvas[\s\S]*?direction="horizontal"/);
  assert.match(projectPreviewSource, /<AgentBuildCanvas[\s\S]*?direction="horizontal"/);
  assert.match(customCreateSource, /<AgentBuilderChatPanel[\s\S]*?<AgentBuildCanvas[\s\S]*?key="builder-config"/);
  assert.match(customCreateStyles, /\.cw-editor > \.abc-root\s*\{[\s\S]*?flex:\s*1 1 auto;[\s\S]*?min-height:\s*0;/);
});

test("keeps existing chat and configuration panel contracts", () => {
  assert.match(builderChatSource, /@openai\/apps-sdk-ui\/components\/Textarea/);
  assert.match(builderChatSource, /isImeCompositionEvent\(event\.nativeEvent\)/);
  assert.match(builderChatSource, /import \{ Blocks \} from "\.\.\/ui\/Blocks"/);
  assert.doesNotMatch(builderChatSource, /ConversationCopyButton|ConversationFeedbackButtons/);
  assert.match(builderChatStyles, /\.agent-builder-chat\s*\{[\s\S]*?width:\s*var\(--cw-builder-chat-width, 420px\);/);
  assert.match(customCreateStyles, /\.cw-detail\s*\{[\s\S]*?width:\s*420px;[\s\S]*?max-width:\s*420px;/);
  assert.match(customCreateStyles, /\.cw-detail-scroll\s*\{[\s\S]*?padding:\s*24px;/);
});

test("keeps concise labels and capability visibility in selected-node form", () => {
  assert.match(customCreateSource, /<label className="cw-label" htmlFor="cw-agent-name">\s*名称/);
  assert.match(customCreateSource, /\{isRootAgent \? "描述" : "智能体描述"\}/);
  assert.doesNotMatch(customCreateSource, /"步骤名称"|"任务说明"/);
  assert.match(customCreateSource, /if \(orchestrator && configTab === "capabilities"\)/);
  assert.match(customCreateSource, /\{!orchestrator && \([\s\S]*?>能力扩展<\/button>/);
});
