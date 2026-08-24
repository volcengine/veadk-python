import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const navbarSource = readFileSync(
  new URL("../src/create/CreateNavbar.tsx", import.meta.url),
  "utf8",
);
const workspaceSource = readFileSync(
  new URL("../src/create/CreateWorkspace.tsx", import.meta.url),
  "utf8",
);
const workspaceStyles = readFileSync(
  new URL("../src/create/CreateWorkspace.css", import.meta.url),
  "utf8",
);
const flowCanvasSource = readFileSync(
  new URL("../src/create/CreationFlowCanvas.tsx", import.meta.url),
  "utf8",
);
const agentDraftWorkflowSource = readFileSync(
  new URL("../src/create/agentDraftWorkflow.ts", import.meta.url),
  "utf8",
);
const normalizeDraftSource = readFileSync(
  new URL("../src/create/normalizeDraft.ts", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const debugWorkspaceSource = readFileSync(
  new URL("../src/create/DebugWorkspace.tsx", import.meta.url),
  "utf8",
);
const debugWorkspaceStyles = readFileSync(
  new URL("../src/create/DebugWorkspace.css", import.meta.url),
  "utf8",
);
const debugConfigSource = readFileSync(
  new URL("../src/ui/AgentDebugConfigPanel.tsx", import.meta.url),
  "utf8",
);
const modelFieldsSource = readFileSync(
  new URL("../src/ui/AgentModelConfigFields.tsx", import.meta.url),
  "utf8",
);
const deploymentWorkspaceSource = readFileSync(
  new URL("../src/create/DeploymentWorkspace.tsx", import.meta.url),
  "utf8",
);
const creationFlowSource = readFileSync(
  new URL("../src/create/CreationFlowCanvas.tsx", import.meta.url),
  "utf8",
);
const flowCanvasStyles = readFileSync(
  new URL("../src/create/CreationFlowCanvas.css", import.meta.url),
  "utf8",
);
const deploymentStyles = readFileSync(
  new URL("../src/create/DeploymentWorkspace.css", import.meta.url),
  "utf8",
);
const createCanvasSource = readFileSync(
  new URL("../src/create/CreateCanvas.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);

test("the create landing page focuses its prompt and offers blank creation", () => {
  assert.match(createCanvasSource, /<textarea[\s\S]*?autoFocus/);
  assert.match(createCanvasSource, /title: "从空白创建"/);
  assert.match(createCanvasSource, /description: "手动配置智能体"/);
  assert.match(createCanvasSource, /onBlank: \(\) => void/);
  assert.doesNotMatch(createCanvasSource, /基于模板|选择模板进行创建|onTemplate/);
});

test("the agent creation shell has no template creation mode", () => {
  assert.match(appSource, /type CreateView = "custom" \| "package" \| "migration" \| null/);
  assert.match(appSource, /onBlank=\{\(\) => \{[\s\S]*?setCustomCreateMode\("custom"\)[\s\S]*?setCreateView\("custom"\)/);
  assert.doesNotMatch(appSource, /TemplateCreate|setCreateView\("template"\)|v === "template"/);
});

test("the create navbar exposes a working debug action", () => {
  assert.match(navbarSource, /onDebug\?: \(\) => void/);
  assert.match(
    navbarSource,
    /create-navbar__button--debug"\s+onClick=\{onDebug\}/,
  );
});

test("the intelligent workspace can enter and exit debug mode", () => {
  assert.match(
    workspaceSource,
    /useState<\s*"create" \| "debug" \| "deploy"\s*>\("create"\)/,
  );
  assert.match(
    workspaceSource,
    /<DebugWorkspace[\s\S]*?onExit=\{\(\) => setWorkspaceMode\("create"\)\}/,
  );
  assert.match(
    workspaceSource,
    /onDebug=\{\(\) => setWorkspaceMode\("debug"\)\}/,
  );
});

test("the create workspace opens and closes the Figma deployment workspace", () => {
  assert.match(navbarSource, /onDeploy\?: \(\) => void/);
  assert.match(
    navbarSource,
    /create-navbar__button--primary"\s+onClick=\{onDeploy\}/,
  );
  assert.match(
    workspaceSource,
    /workspaceMode === "deploy"[\s\S]*?<DeploymentWorkspace[\s\S]*?agentDraft=\{agentDraft\}[\s\S]*?onBack=\{\(\) => setWorkspaceMode\("create"\)\}/,
  );
  assert.match(workspaceSource, /onDeploy=\{\(\) => setWorkspaceMode\("deploy"\)\}/);
  assert.match(deploymentWorkspaceSource, /发布与集成/);
  assert.match(deploymentWorkspaceSource, /消息渠道/);
  assert.match(deploymentWorkspaceSource, /企业系统集成/);
  assert.match(deploymentWorkspaceSource, /调用地址/);
  assert.match(deploymentWorkspaceSource, /API Key/);
  assert.match(deploymentWorkspaceSource, /调用示例/);
});

test("debug and deployment workflows are centered in their visible canvases", () => {
  assert.match(debugWorkspaceSource, /<CreationFlowCanvas[\s\S]*?centerViewport/);
  assert.match(deploymentWorkspaceSource, /<CreationFlowCanvas[\s\S]*?centerViewport/);
  assert.match(creationFlowSource, /else if \(!centerViewport\)/);
  assert.match(
    deploymentStyles,
    /\.create-workspace--deployment \.creation-flow--config-open\s*\{[\s\S]*?right:\s*492px/,
  );
});

test("the create workspace sends messages to the stateful creation assistant", () => {
  assert.match(workspaceSource, /role: "user", content/);
  assert.match(workspaceSource, /chatWithGeneratedAgent\(/);
  assert.match(workspaceSource, /conversationSessionIdRef\.current/);
  assert.match(workspaceSource, /status: "processing"/);
  assert.match(workspaceSource, /status: "complete"/);
  assert.match(workspaceSource, /setPrompt\(""\)/);
  assert.match(workspaceSource, /event\.key === "Enter"/);
  assert.match(workspaceSource, /!event\.shiftKey/);
  assert.match(workspaceSource, /compositionRef\.current/);
  assert.match(clientSource, /"\/web\/generated-agent-conversations"/);
  assert.match(clientSource, /JSON\.stringify\(\{ sessionId, message, currentDraft \}\)/);
  assert.match(workspaceSource, /agentDraftForConversation\(agentDraft\)/);
});

test("agent names stay synchronized between canvas nodes and configuration", () => {
  assert.match(workspaceSource, /interface AgentConfigDraft/);
  assert.match(workspaceSource, /const \[agentConfigs, setAgentConfigs\] = useState/);
  assert.match(
    workspaceSource,
    /<AgentConfigPanel[\s\S]*?agentName=\{selectedAgentConfig\.agentName\}[\s\S]*?onAgentNameChange=/,
  );
  assert.match(
    workspaceSource,
    /<CreationFlowCanvas[\s\S]*?agentOverrides=\{agentOverrides\}/,
  );
  assert.match(
    workspaceSource,
    /setSelectedAgent\(\(currentAgent\)[\s\S]*?title: value/,
  );
  assert.match(workspaceSource, /updateAgentDraftAtNodeId\(/);
});

test("the assistant status shows elapsed time without a chevron icon", () => {
  assert.match(workspaceSource, /已处理 \$\{formatDuration/);
  assert.match(workspaceSource, /耗时 \$\{formatDuration/);
  assert.doesNotMatch(workspaceSource, /ProcessedChevronIcon/);
  assert.doesNotMatch(workspaceStyles, /assistant-status-icon/);
});

test("a generated draft replaces the canvas graph and hydrates agent fields", () => {
  assert.match(workspaceSource, /normalizeDraft\(\{ \.\.\.result\.draft, cloudProvider \}\)/);
  assert.match(workspaceSource, /sanitizeGeneratedDraftCapabilities/);
  assert.match(
    normalizeDraftSource,
    /const cloudProvider = inheritedCloudProvider;[\s\S]*?cloudProvider,[\s\S]*?sanitizeGeneratedDraftCapabilities\(child, cloudProvider\)/,
  );
  assert.match(workspaceSource, /setAgentDraft\(nextDraft\)/);
  assert.match(flowCanvasSource, /function graphFromDraft\(draft: AgentDraft\)/);
  assert.match(flowCanvasSource, /systemPrompt: agent\.instruction/);
  assert.match(flowCanvasSource, /function emptyGraph\(\): GraphState/);
  assert.match(
    flowCanvasSource,
    /agentDraft \? graphFromDraft\(agentDraft\) : showEmptyGraph \? emptyGraph\(\) : initialGraph\(\)/,
  );
});

test("sequential wrappers stay internal while their agents form one visible chain", () => {
  assert.match(
    agentDraftWorkflowSource,
    /draft\.agentType === "sequential"[\s\S]*?draft\.subAgents\.map/,
  );
  assert.match(flowCanvasSource, /const visibleAgents = visibleAgentDrafts\(draft\)/);
  assert.match(flowCanvasSource, /let previousId = "request"/);
  assert.match(flowCanvasSource, /edges\.push\(makeEdge\(previousId, id, "straight"\)\)/);
  assert.doesNotMatch(flowCanvasSource, /visit\(draft, \[\], "request", 1\)/);
});

test("configuration edits update the authoritative nested Agent draft", () => {
  assert.match(agentDraftWorkflowSource, /function updateAgentDraftAtNodeId/);
  assert.match(agentDraftWorkflowSource, /\^agent-root-\(\\d\+\)\$/);
  assert.match(workspaceSource, /updateDraftFromConfigField\(agent, field, value\)/);
  assert.match(workspaceSource, /updateDraftModelConfig\(agent, value\)/);
  assert.match(workspaceSource, /selectedTools=\{selectedAgentConfig\.selectedTools\}/);
  assert.match(workspaceSource, /selectedSkills: Array\.from/);
});

test("conversation context strips credentials before leaving the browser", () => {
  assert.match(agentDraftWorkflowSource, /authToken: _authToken/);
  assert.match(agentDraftWorkflowSource, /envValues: _envValues/);
  assert.match(agentDraftWorkflowSource, /localFiles: \[\]/);
});

test("the blank create canvas uses the Figma agent placeholder", () => {
  assert.match(flowCanvasSource, /type AgentPlaceholderFlowNode/);
  assert.match(flowCanvasSource, /id: "agent-placeholder"/);
  assert.match(flowCanvasSource, /makeEdge\("request", "agent-placeholder", "straight"\)/);
  assert.match(flowCanvasSource, /makeEdge\("agent-placeholder", "response", "straight"\)/);
  assert.match(
    flowCanvasStyles,
    /\.creation-flow__agent-placeholder\s*\{[\s\S]*?width: 214px;[\s\S]*?height: 137px;[\s\S]*?border: 1px dashed #c9cdd4;[\s\S]*?border-radius: 12px;/,
  );
  assert.match(
    flowCanvasStyles,
    /\.creation-flow__agent-placeholder-line\s*\{[\s\S]*?top: 23px;[\s\S]*?left: 41px;[\s\S]*?width: 91px;[\s\S]*?height: 6px;/,
  );
});

test("only top-level agent cards expose the direct sub-agent count", () => {
  assert.match(
    flowCanvasSource,
    /import \{ Members \} from "@openai\/apps-sdk-ui\/components\/Icon"/,
  );
  assert.match(flowCanvasSource, /subAgents: number/);
  assert.match(flowCanvasSource, /<Members aria-hidden="true" \/>/);
  assert.match(flowCanvasSource, /data\.subAgents/);
  assert.match(flowCanvasSource, /subAgents: agent\.subAgents\.length/);
  assert.match(flowCanvasSource, /canExpandSubAgents \? \([\s\S]*?<Members aria-hidden="true" \/>[\s\S]*?\) : null/);
});

test("direct sub-agents are always rendered as full cards with an add placeholder", () => {
  assert.match(flowCanvasSource, /function expandSubAgentGroups/);
  assert.match(flowCanvasSource, /childAgents: agent\.subAgents\.map/);
  assert.match(flowCanvasSource, /type: "subAgentPlaceholder"/);
  assert.match(flowCanvasSource, /label: "添加子智能体"/);
  assert.match(flowCanvasSource, /onSubAgentAdd\?\.\(parentAgentId\)/);
  assert.match(workspaceSource, /onSubAgentAdd=\{handleSubAgentAdd\}/);
  assert.match(
    flowCanvasSource,
    /const expandedSubAgentIds = useMemo\([\s\S]*?node\.data\.canExpandSubAgents === true[\s\S]*?map\(\(node\) => node\.id\)/,
  );
  assert.doesNotMatch(flowCanvasSource, /hoveredSubAgentIds/);
  assert.doesNotMatch(flowCanvasSource, /SUB_AGENT_CLOSE_DELAY/);
  assert.doesNotMatch(flowCanvasSource, /aria-haspopup="true"/);
});

test("expanded sub-agent groups use collision-aware centered orthogonal layout", () => {
  assert.match(flowCanvasSource, /SUB_AGENT_GROUP_GAP = 24/);
  assert.match(flowCanvasSource, /groupAnchorOffset/);
  assert.match(flowCanvasSource, /previousBottom \+ SUB_AGENT_GROUP_GAP/);
  assert.match(flowCanvasSource, /subAgentEdgeGeometry/);
  assert.match(flowCanvasSource, /expandableAgentOrder\.get\(parent\.id\)/);
  assert.match(flowCanvasSource, /sourceHandle: `sub-source-\$\{side\}`/);
  assert.match(flowCanvasSource, /targetHandle: `sub-target-\$\{oppositeSide\}`/);
  assert.match(
    flowCanvasStyles,
    /\.creation-flow__sub-edge-visible[\s\S]*?stroke-dasharray: 4 4/,
  );
  assert.match(
    flowCanvasStyles,
    /\.creation-flow__sub-agent-placeholder\s*\{[\s\S]*?width: 216px;[\s\S]*?height: 48px;[\s\S]*?border: 1px dashed #c9cdd4;/,
  );
});

test("the sequential workflow binds solid edges to dedicated center handles", () => {
  assert.match(flowCanvasSource, /const MAIN_TARGET_HANDLE_ID = "main-target"/);
  assert.match(flowCanvasSource, /const MAIN_SOURCE_HANDLE_ID = "main-source"/);
  assert.match(
    flowCanvasSource,
    /sourceHandle: MAIN_SOURCE_HANDLE_ID,[\s\S]*?targetHandle: MAIN_TARGET_HANDLE_ID/,
  );
  assert.match(
    flowCanvasSource,
    /id=\{MAIN_TARGET_HANDLE_ID\}[\s\S]*?position=\{Position\.Top\}/,
  );
  assert.match(
    flowCanvasSource,
    /id=\{MAIN_SOURCE_HANDLE_ID\}[\s\S]*?position=\{Position\.Bottom\}/,
  );
});

test("the create workspace messages retain the Figma message geometry", () => {
  assert.match(workspaceSource, /create-workspace__message--user/);
  assert.match(workspaceSource, /create-workspace__message--assistant/);
  assert.match(workspaceSource, /create-workspace__assistant-status/);
  assert.match(workspaceSource, /create-workspace__assistant-divider/);
  assert.match(workspaceStyles, /\.create-workspace__message--user[\s\S]*?padding: 10px 12px/);
  assert.match(workspaceStyles, /\.create-workspace__message--user[\s\S]*?border-radius: 8px/);
  assert.match(workspaceStyles, /\.create-workspace__message--user[\s\S]*?background: #f3f3f5/);
  assert.match(workspaceStyles, /\.create-workspace__message--assistant[\s\S]*?gap: 16px/);
  assert.match(workspaceStyles, /\.create-workspace__assistant-body[\s\S]*?line-height: 28px/);
});

test("the create chat panel collapses to the fixed Figma message control", () => {
  assert.match(workspaceSource, /const \[chatCollapsed, setChatCollapsed\] = useState\(false\)/);
  assert.match(workspaceSource, /aria-expanded=\{!chatCollapsed\}/);
  assert.match(workspaceSource, /onClick=\{\(\) => setChatCollapsed\(true\)\}/);
  assert.match(
    workspaceStyles,
    /\.create-workspace__chat-toggle\s*\{[\s\S]*?top: 71px;[\s\S]*?left: 21px;[\s\S]*?width: 48px;[\s\S]*?height: 48px;[\s\S]*?padding: 14px;/,
  );
  assert.match(
    flowCanvasStyles,
    /\.create-workspace--chat-collapsed \.creation-flow--create:not\(\.creation-flow--config-open\)\s*\{[\s\S]*?left: 69px;/,
  );
});

test("agent configuration and the expanded chat panel are mutually exclusive", () => {
  assert.match(
    workspaceSource,
    /function handleChatToggle\(\)[\s\S]*?setSelectedAgent\(null\)[\s\S]*?setChatCollapsed\(false\)/,
  );
  assert.match(
    workspaceSource,
    /function handleAgentSelect\([\s\S]*?setSelectedAgent\(agent\)[\s\S]*?if \(agent\) setChatCollapsed\(true\)/,
  );
  assert.match(
    workspaceSource,
    /className="create-workspace__chat-toggle"[\s\S]*?onClick=\{handleChatToggle\}/,
  );
  assert.doesNotMatch(workspaceSource, /\{!selectedAgent && \(/);
  assert.match(
    workspaceStyles,
    /@media \(max-width: 900px\)[\s\S]*?\.create-workspace__chat\s*\{[\s\S]*?right: 8px;[\s\S]*?left: 8px;[\s\S]*?width: auto;/,
  );
  assert.doesNotMatch(
    workspaceStyles,
    /@media \(max-width: 900px\)[\s\S]*?\.create-workspace__chat-toggle\s*\{[\s\S]*?display: none;/,
  );
});

test("the composer shows focus on its outer surface instead of outlining the textarea", () => {
  assert.match(
    workspaceStyles,
    /\.create-workspace__composer-input:focus-visible\s*\{\s*outline: none/,
  );
  assert.match(
    workspaceStyles,
    /\.create-workspace__composer:focus-within[\s\S]*?border-color:/,
  );
});

test("the debug workspace can open the Figma comparison layout", () => {
  assert.match(debugWorkspaceSource, /useState\(false\)/);
  assert.match(
    debugWorkspaceSource,
    /onAddComparison=\{\(\) => setComparisonOpen\(true\)\}/,
  );
  assert.match(debugWorkspaceSource, /debug-workspace__comparison-columns/);
  assert.match(debugWorkspaceSource, /基准组 A/);
  assert.match(debugWorkspaceSource, /对照组 B/);
  assert.match(debugWorkspaceSource, /提示词、模型 2 处改动/);
});

test("each comparison group owns an independent Figma debug configuration", () => {
  assert.match(
    debugWorkspaceSource,
    /groupStates\.baseline\.configOpen[\s\S]*?closeGroupConfig\("baseline"\)[\s\S]*?openGroupConfig\("baseline"\)/,
  );
  assert.match(
    debugWorkspaceSource,
    /groupStates\.comparison\.configOpen[\s\S]*?closeGroupConfig\("comparison"\)[\s\S]*?openGroupConfig\("comparison"\)/,
  );
  assert.match(debugWorkspaceSource, /interface DebugGroupState/);
  assert.match(debugWorkspaceSource, /Record<DebugGroup, DebugGroupState>/);
  assert.match(debugWorkspaceSource, /groupStates\.baseline\.configOpen/);
  assert.match(debugWorkspaceSource, /groupStates\.comparison\.configOpen/);
  assert.doesNotMatch(debugWorkspaceSource, /configuringGroup/);
  assert.doesNotMatch(debugWorkspaceSource, /const \[configDraft/);
});

test("debug configuration follows the selected canvas agent without sharing values", () => {
  assert.match(debugWorkspaceSource, /agentDraft\?: AgentDraft \| null/);
  assert.match(debugWorkspaceSource, /agentOverrides\?: CreationFlowAgentOverrides/);
  assert.match(debugWorkspaceSource, /const \[selectedAgent, setSelectedAgent\]/);
  assert.match(debugWorkspaceSource, /onAgentSelect=\{handleAgentSelect\}/);
  assert.match(debugWorkspaceSource, /agentConfigs: Record<string, DebugAgentConfigState>/);
  assert.match(debugWorkspaceSource, /current\[group\]\.agentConfigs\[selectedAgent\.id\]/);
  assert.match(
    workspaceSource,
    /<DebugWorkspace[\s\S]*?agentDraft=\{agentDraft\}[\s\S]*?agentOverrides=\{agentOverrides\}/,
  );
  assert.doesNotMatch(creationFlowSource, /if \(mode === "debug"\) return/);
  assert.match(creationFlowSource, /model: node\.data\.model/);
  assert.match(debugConfigSource, /agentName: string/);
  assert.match(debugConfigSource, /<h2>\{value\.agentName\}<\/h2>/);
});

test("each debug configuration closes from the settings-button position", () => {
  assert.match(debugWorkspaceSource, /function CloseConfigIcon/);
  assert.match(debugWorkspaceSource, /"关闭基准组 A 配置"/);
  assert.match(debugWorkspaceSource, /"关闭对照组 B 配置"/);
  assert.doesNotMatch(debugWorkspaceSource, /CollapsedChatIcon/);
  assert.doesNotMatch(debugWorkspaceSource, /debug-workspace__collapsed-chat/);
  assert.doesNotMatch(debugConfigSource, /AgentIdentityIcon/);
});

test("debug configuration reuses Apps SDK fields without optimization options", () => {
  assert.match(
    modelFieldsSource,
    /@openai\/apps-sdk-ui\/components\/Select/,
  );
  assert.match(
    debugConfigSource,
    /@openai\/apps-sdk-ui\/components\/Textarea/,
  );
  assert.match(debugConfigSource, />描述</);
  assert.match(debugConfigSource, />模型</);
  assert.match(debugConfigSource, />系统提示词</);
  assert.match(debugConfigSource, /id=\{`\$\{idPrefix\}-system-prompt`\}[\s\S]*?rows=\{11\}/);
  assert.match(debugConfigSource, /<AgentModelConfigFields[\s\S]*?idPrefix=\{idPrefix\}/);
  assert.doesNotMatch(debugConfigSource, /优化选项/);
});

test("debug runtime and conversation reuse the generated-agent test stream", () => {
  assert.match(debugWorkspaceSource, /createGeneratedAgentTestRun/);
  assert.match(debugWorkspaceSource, /createGeneratedAgentTestSession/);
  assert.match(debugWorkspaceSource, /runGeneratedAgentTestSSE/);
  assert.match(debugWorkspaceSource, /deleteGeneratedAgentTestRun/);
  assert.match(debugWorkspaceSource, /applyEvent\(acc, event\)/);
  assert.match(debugWorkspaceSource, /<Blocks/);
  assert.match(debugWorkspaceSource, /<ThinkingPlaceholder/);
  assert.match(debugWorkspaceSource, /<Markdown text=\{message\.content\}/);
  assert.match(
    debugWorkspaceStyles,
    /\.debug-workspace__conversation-error\s*\{[\s\S]*?color:\s*hsl\(var\(--destructive\)\)/,
  );
});

test("debug runtimes, sessions, and messages are isolated by group and agent", () => {
  assert.match(debugWorkspaceSource, /runtimeKey = \(group: DebugGroup, agentId: string\)/);
  assert.match(debugWorkspaceSource, /`\$\{group\}:\$\{agentId\}`/);
  assert.match(debugWorkspaceSource, /agentConfigs: Record<string, DebugAgentConfigState>/);
  assert.match(debugWorkspaceSource, /messages: DebugMessage\[\]/);
  assert.match(debugWorkspaceSource, /targets\.map\(async \(target\)/);
});

test("debug model configuration starts from the selected agent configuration", () => {
  assert.match(workspaceSource, /agentModelConfigs=\{agentModelConfigs\}/);
  assert.match(debugWorkspaceSource, /agentModelConfigs\?: Record<string, AgentModelConfigValue>/);
  assert.match(debugWorkspaceSource, /agentModelConfigs\[selectedAgent\.id\]/);
  assert.match(debugWorkspaceSource, /debugDraftForAgent/);
  assert.match(debugWorkspaceSource, /activeAgentModelName\(modelConfig\)/);
});
