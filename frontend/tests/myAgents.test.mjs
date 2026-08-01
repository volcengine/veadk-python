import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pageSource = readFileSync(
  new URL("../src/ui/MyAgents.tsx", import.meta.url),
  "utf8",
);
const pageStyles = readFileSync(
  new URL("../src/ui/MyAgents.css", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const authSource = readFileSync(new URL("../src/adk/auth.ts", import.meta.url), "utf8");

test("shows only the Agent navigation in the sidebar", () => {
  assert.match(sidebarSource, /onMyAgents: \(\) => void/);
  assert.doesNotMatch(sidebarSource, /onManageAgents/);
  assert.doesNotMatch(sidebarSource, /aria-label="智能体库"/);
  assert.match(
    sidebarSource,
    /onClick=\{onMyAgents\}[\s\S]*?aria-label="智能体"[\s\S]*?<ManageAgentsIcon \/>/,
  );
  assert.match(appSource, /const openMyAgentsPage = \(\) => \{/);
  assert.match(appSource, /<Sidebar[\s\S]*?onMyAgents=\{openMyAgentsPage\}/);
  assert.match(appSource, /myAgents \? \([\s\S]*?<MyAgents/);
});

test("shows the requested title, search, and agent type pills", () => {
  assert.match(pageSource, /<h1>智能体<\/h1>/);
  assert.match(pageSource, /aria-label="Runtime 地域"/);
  assert.doesNotMatch(pageSource, />Runtime 地域<\/span>/);
  assert.match(pageSource, /className="my-agents-region"/);
  assert.match(pageSource, /aria-haspopup="listbox"/);
  assert.match(pageSource, /className="my-agents-region-menu" role="listbox"/);
  assert.match(pageSource, /\{ value: "cn-beijing", label: "北京" \}/);
  assert.match(pageSource, /\{ value: "cn-shanghai", label: "上海" \}/);
  assert.doesNotMatch(pageSource, /<select/);
  assert.match(pageStyles, /\.my-agents-region\s*\{[\s\S]*?gap:\s*4px;[\s\S]*?height:\s*24px;[\s\S]*?border:\s*0;[\s\S]*?background:\s*transparent;[\s\S]*?font-size:\s*13px;/);
  assert.match(pageStyles, /\.my-agents-region-chevron\s*\{[\s\S]*?width:\s*12px;[\s\S]*?height:\s*12px;/);
  assert.match(pageStyles, /\.my-agents-region-menu\s*\{[\s\S]*?position:\s*absolute;/);
  assert.match(pageSource, /在此处浏览您的所有智能体/);
  assert.match(pageSource, /placeholder="搜索所有类型智能体名称"/);
  assert.match(pageSource, /aria-label="搜索智能体"/);
  assert.doesNotMatch(pageSource, /<span className="sr-only">搜索智能体<\/span>/);
  for (const title of ["通用智能体", "Codex 智能体", "OpenClaw 智能体", "Hermes 智能体"]) {
    assert.match(pageSource, new RegExp(`label: "${title}"`));
  }
  assert.match(pageSource, /className="my-agent-type-pill/);
  assert.match(pageSource, /aria-pressed=\{activeType === type\.id\}/);
});

test("renders only account-backed agents and never ships placeholder cards", () => {
  assert.doesNotMatch(pageSource, /STATIC_SECTIONS/);
  assert.doesNotMatch(
    pageSource,
    /codex-code-review|codex-test-coverage|openclaw-research|hermes-data-analysis/,
  );
  assert.match(pageSource, /if \(activeType !== "general"\) return \[\]/);
});

test("offers the existing create action for the active agent type", () => {
  assert.match(pageSource, /canCreate: boolean/);
  assert.match(pageSource, /\{canCreate && \(/);
  assert.match(pageSource, /activeType === "general"[\s\S]*?onCreateAgent/);
  assert.match(pageSource, /onCreateSandboxAgent\(activeType\)/);
  assert.match(pageSource, /className="my-agent-add"/);
  assert.match(pageSource, /createLabel: "添加通用智能体"/);
  assert.match(pageSource, /createLabel: "添加 Codex 智能体"/);
  assert.match(pageSource, /<AddIcon \/>[\s\S]*?\{createLabel\}/);
  assert.match(pageSource, /disabled=\{!createAgent\}/);
  assert.match(pageStyles, /\.my-agent-type-bar\s*\{[\s\S]*?justify-content: space-between/);
  assert.match(pageStyles, /\.my-agent-add\s*\{[\s\S]*?background: hsl\(var\(--foreground\)\)[\s\S]*?color: hsl\(var\(--background\)\)/);
  assert.match(pageStyles, /@media \(max-width: 720px\)[\s\S]*?\.my-agent-add\s*\{[\s\S]*?align-self: flex-end/);
});

test("agent cards show only Runtime name, creation time, and connect action", () => {
  assert.match(pageSource, /<h3>\{agent\.name\}<\/h3>/);
  assert.match(pageSource, /<dt>创建时间<\/dt>/);
  assert.doesNotMatch(pageSource, /<dt>工具<\/dt>|<dt>技能<\/dt>/);
  assert.doesNotMatch(pageSource, /toolCount|skillCount|agent\.description/);
  assert.match(pageSource, /aria-label=\{connected \? `\$\{agent\.name\} 已连接` : `连接 \$\{agent\.name\}`\}/);
  assert.match(pageSource, /onClick=\{\(\) => onViewDetails\?\.\(agent\)\}/);
  assert.doesNotMatch(pageSource, />\s*查看详情\s*<\/button>/);
  assert.doesNotMatch(pageSource, /<small|<code/);
  assert.doesNotMatch(pageStyles, /font-family/);
});

test("uses a compact three-column directory grid", () => {
  assert.match(
    pageStyles,
    /\.my-agent-grid\s*\{[\s\S]*?grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/,
  );
  assert.match(pageStyles, /@media \(max-width: 980px\)[\s\S]*?repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(pageStyles, /@media \(max-width: 640px\)[\s\S]*?grid-template-columns: 1fr/);
});

test("creation time remains compact without data-plane metadata", () => {
  assert.doesNotMatch(pageStyles, /\.my-agent-label/);
  assert.match(pageStyles, /\.my-agent-created-at dd\s*\{[\s\S]*?font-weight: 400/);
  assert.doesNotMatch(pageSource, /getRuntimeAgentInfo/);
  assert.doesNotMatch(pageSource, /Promise\.all\([\s\S]*?page\.runtimes\.map/);
  assert.doesNotMatch(pageSource, /appName: info\.appName/);
});

test("loads the runtime scope granted to the current role", () => {
  assert.match(pageSource, /getRuntimes/);
  assert.match(pageSource, /runtimeScope: RuntimeScope/);
  assert.match(pageSource, /scope: runtimeScope/);
  assert.match(pageSource, /const \[region, setRegion\] = useState<RuntimeRegion>\("cn-beijing"\)/);
  assert.match(pageSource, /region,\s*pageSize: RUNTIME_PAGE_SIZE/);
  assert.doesNotMatch(pageSource, /region: "all"/);
  assert.match(pageSource, /id: runtime\.runtimeId/);
  assert.match(pageSource, /name: runtime\.name/);
  assert.match(pageSource, /description: runtime\.name/);
  assert.match(pageSource, /runtimeId: runtime\.runtimeId/);
  assert.match(pageSource, /region: runtime\.region/);
  assert.match(pageSource, /<AgentCard[\s\S]*?key=\{agent\.id\}/);
  assert.match(pageSource, /const RUNTIME_PAGE_SIZE = 24/);
  assert.match(pageSource, /onList\(page\.runtimes\.map\(runtimeToAgent\)\)/);
  assert.match(pageSource, /runtimeRequestRef\.current !== requestId/);
  assert.match(pageSource, /const runtimePageRequests = new Map/);
  assert.match(pageSource, /const requestKey = `\$\{runtimeScope\}:\$\{region\}:\$\{nextToken\}`/);
  assert.match(pageSource, /runtimePageRequests\.get\(requestKey\)/);
  assert.match(pageSource, /runtimePageRequests\.set\(requestKey, request\)/);
  assert.match(pageSource, /const RUNTIME_PAGE_CACHE_TTL_MS = 30_000/);
  assert.match(pageSource, /runtimePageCache\.get\(requestKey\)/);
  assert.match(pageSource, /runtimePageCache\.set\(requestKey/);
  assert.match(pageSource, /setRuntimeAgents\(\(current\) => reset \? agents : \[\.\.\.current, \.\.\.agents\]\)/);
  assert.match(appSource, /<MyAgents[\s\S]*?runtimeScope=\{access\.capabilities\.runtimeScope\}/);
  assert.match(appSource, /const grantedRuntimeScope = access\?\.capabilities\.runtimeScope \?\? "mine"/);
  assert.match(appSource, /const refreshAgentLibrary[\s\S]*?scope: grantedRuntimeScope/);
});

test("marks runtimes created by the administrator", () => {
  assert.match(pageSource, /isMine\?: boolean/);
  assert.match(pageSource, /isMine: runtime\.isMine/);
  assert.match(pageSource, /showOwnership=\{runtimeScope === "all"\}/);
  assert.match(pageSource, /showOwnership && agent\.isMine/);
  assert.match(pageSource, /className="runtime-owner-badge"[\s\S]*?>我创建的</);
  assert.match(appSource, /canCreate=\{canCreateAgents\}/);
});

test("hides deleted Runtime cards and invalidates stale Runtime pages", () => {
  assert.match(pageSource, /export function invalidateRuntimeAgentCache/);
  assert.match(pageSource, /runtimePageRequests\.clear\(\)/);
  assert.match(pageSource, /runtimePageCache\.clear\(\)/);
  assert.match(pageSource, /runtimePageCache\.delete\(key\)/);
  assert.match(pageSource, /hiddenRuntimeIds\?: ReadonlySet<string>/);
  assert.match(
    pageSource,
    /!agent\.runtime \|\| !hiddenRuntimeIds\.has\(agent\.runtime\.runtimeId\)/,
  );
  assert.match(appSource, /const \[hiddenRuntimeIds, setHiddenRuntimeIds\] = useState<Set<string>>/);
  assert.match(appSource, /invalidateRuntimeAgentCache\(pendingRuntimeIds\)/);
  assert.match(appSource, /invalidateRuntimeAgentCache\(deletedRuntimeIds\)/);
  assert.match(appSource, /const selectedRuntimeId = runtimeIdForSelection\(connections, appName\)/);
  assert.match(appSource, /deletedCurrentSelection[\s\S]*?deletedRuntimeIds\.has\(selectedRuntimeId\)/);
  assert.match(appSource, /clearSelectedAgentAfterRemoval\(\)/);
  assert.match(appSource, /agentSelectionClearedRef\.current = true/);
  assert.match(appSource, /hiddenRuntimeIds=\{hiddenRuntimeIds\}/);
});

test("loads configured Codex Sessions as reusable agents", () => {
  assert.match(
    pageSource,
    /sandboxClient,[\s\S]*?type SandboxAgentKind,[\s\S]*?type SandboxSession/,
  );
  assert.match(pageSource, /sandboxClient\s*\.listSessions/);
  assert.match(pageSource, /activeType !== "codex"/);
  assert.match(pageSource, /codexRefreshKey/);
  assert.match(pageSource, /function CodexSessionCard/);
  assert.match(
    pageSource,
    /session\.displayName\s*\|\|\s*session\.userSessionId/,
  );
  assert.match(
    pageSource,
    /session\.displayName && session\.userSessionId[\s\S]*codex-session-user-id/,
  );
  assert.match(pageSource, /User Session · \{userSessionSubtitle\}/);
  assert.doesNotMatch(pageSource, /Session \{session\.id\}/);
  assert.doesNotMatch(pageSource, /session\.id\.slice/);
  assert.match(pageSource, /session\.status\.toLowerCase\(\) === "ready"/);
  assert.match(pageSource, /<dt>到期时间<\/dt>/);
  assert.match(pageSource, /进入对话/);
  assert.match(pageSource, /await onOpenCodexSession\(session\)/);
  assert.match(pageSource, /重新加载/);
  assert.match(pageSource, /`正在加载 \$\{activeLabel\}`/);
  assert.match(
    pageSource,
    /\[session\.displayName, session\.userSessionId, session\.status\]/,
  );
});

test("keeps the Codex filter selected across conversation navigation", () => {
  assert.match(pageSource, /activeType: AgentType/);
  assert.match(pageSource, /onActiveTypeChange: \(type: AgentType\) => void/);
  assert.match(
    pageSource,
    /aria-pressed=\{activeType === type\.id\}[\s\S]*?onClick=\{\(\) => onActiveTypeChange\(type\.id\)\}/,
  );
  assert.match(appSource, /const \[agentDirectoryType, setAgentDirectoryType\]/);
  assert.match(
    appSource,
    /<MyAgents[\s\S]*?activeType=\{agentDirectoryType\}[\s\S]*?onActiveTypeChange=\{setAgentDirectoryType\}/,
  );
});

test("loads more Runtime cards at the scroll sentinel with accessible animation", () => {
  assert.match(pageSource, /new IntersectionObserver/);
  assert.match(pageSource, /loadMoreRef/);
  assert.match(pageSource, /void fetchRuntimePage\(runtimeNextToken, false\)/);
  assert.match(pageSource, /className="my-agent-load-more"/);
  assert.match(pageStyles, /@keyframes my-agent-card-enter/);
  assert.match(pageStyles, /\.my-agent-card\s*\{[\s\S]*?animation: my-agent-card-enter/);
  assert.match(pageStyles, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?animation: none/);
});

test("keeps the page controls fixed while only the Agent results scroll", () => {
  assert.match(pageSource, /const resultsRef = useRef<HTMLElement>\(null\)/);
  assert.match(pageSource, /const root = resultsRef\.current/);
  assert.match(pageSource, /className="my-agent-results"[\s\S]*?ref=\{resultsRef\}/);
  assert.match(pageStyles, /\.my-agents-page\s*\{[\s\S]*?overflow: hidden/);
  assert.match(
    pageStyles,
    /\.my-agent-results\s*\{[\s\S]*?flex: 1;[\s\S]*?min-height: 0;[\s\S]*?overflow-y: auto/,
  );
});

test("does not ship development-only Runtime fixtures", () => {
  assert.doesNotMatch(pageSource, /mockAgents|MOCK_RUNTIME|mockRuntimePage|演示智能体/);
  assert.doesNotMatch(authSource, /mockAgents/);
});

test("refreshes Runtime permissions without connecting to the data plane", () => {
  const refreshStart = appSource.indexOf("const refreshAgentLibrary");
  const refreshEnd = appSource.indexOf("\n  // Placeholder", refreshStart);
  assert.ok(refreshStart >= 0 && refreshEnd > refreshStart);
  const refreshSource = appSource.slice(refreshStart, refreshEnd);
  assert.match(refreshSource, /getRuntimes/);
  assert.match(refreshSource, /setLibraryRuntimeIds/);
  assert.match(refreshSource, /setLibraryRuntimePermissions/);
  assert.doesNotMatch(refreshSource, /connectRuntime|loadConnections/);
  assert.match(
    appSource,
    /if \([\s\S]*?!manageAgents[\s\S]*?\) \{[\s\S]*?return;[\s\S]*?void refreshAgentLibrary\(\)/,
  );
});

test("defers conversation data-plane requests until leaving the Agent list", () => {
  assert.match(
    appSource,
    /if \(authStatus !== "authenticated"\) return;[\s\S]*?if \(agentsSource === "cloud"\) \{[\s\S]*?return;[\s\S]*?listApps\(\)/,
  );
  assert.match(
    appSource,
    /myAgents \|\|[\s\S]*?sandboxAgentWorkspace \|\|[\s\S]*?agentDetailTarget \|\|[\s\S]*?!sessionId[\s\S]*?getSessionCapabilities/,
  );
  assert.match(
    appSource,
    /if \([\s\S]*?authStatus !== "authenticated"[\s\S]*?myAgents[\s\S]*?!appName[\s\S]*?\)[\s\S]*?getAgentInfo/,
  );
  assert.match(
    appSource,
    /myAgents \|\|[\s\S]*?sandboxAgentWorkspace \|\|[\s\S]*?agentDetailTarget \|\|[\s\S]*?sandboxSession[\s\S]*?return;[\s\S]*?refreshSessions/,
  );
  assert.match(
    appSource,
    /!manageAgents \|\|[\s\S]*?agentDetailTarget[\s\S]*?void refreshAgentLibrary\(\)/,
  );
});

test("wires card details and connect actions into App navigation", () => {
  assert.match(pageSource, /onClick=\{\(\) => void onUse\?\.\(agent\)\}/);
  assert.match(pageSource, /onClick=\{\(\) => onViewDetails\?\.\(agent\)\}/);
  assert.match(appSource, /const connectMyAgent[\s\S]*?connectRuntime[\s\S]*?startNewChat\(\)[\s\S]*?setAppName\(agentId\)/);
  assert.match(appSource, /const openMyAgentDetails[\s\S]*?setAgentDetailTarget\(agent\)[\s\S]*?setManageAgents\(true\)/);
  const detailHandler = appSource.slice(
    appSource.indexOf("const openMyAgentDetails"),
    appSource.indexOf("const openMyAgentsPage"),
  );
  assert.doesNotMatch(detailHandler, /connectRuntime\(/);
  assert.match(appSource, /const detailAgentEntry:[\s\S]*?id: `detail:\$\{agentDetailTarget\.runtime\.runtimeId\}`/);
  assert.match(appSource, /app: agentDetailTarget\.appName \?\? agentDetailTarget\.name/);
  assert.match(pageSource, /appName\?: string/);
  assert.doesNotMatch(pageSource, /appName: info\.appName/);
  assert.match(appSource, /<MyAgents[\s\S]*?onCreateAgent=\{openAgentCreateFromMyAgents\}[\s\S]*?onUseAgent=/);
  assert.match(appSource, /const openAgentCreateFromMyAgents = \(region: string\)[\s\S]*?setNewRuntimeRegion\(region\)/);
  assert.match(appSource, /<CustomCreate[\s\S]*?initialDeployRegion=\{newRuntimeRegion\}/);
  assert.match(appSource, /<CodePackageCreate[\s\S]*?initialDeployRegion=\{newRuntimeRegion\}/);
});

test("keeps all requested type filters without nested category sections", () => {
  assert.match(pageSource, /onCreateSandboxAgent: \(type: "codex" \| SandboxAgentKind\) => void/);
  assert.match(pageSource, /AGENT_TYPES\.map/);
  assert.match(pageSource, /label: "Codex 智能体"/);
  assert.match(pageSource, /label: "OpenClaw 智能体"/);
  assert.match(pageSource, /label: "Hermes 智能体"/);
  assert.doesNotMatch(pageSource, /AgentSection|my-agents-section|comingSoon/);
  assert.match(pageSource, /\$\{activeLabel\}暂无内容/);
  assert.match(pageSource, /listAgentSessions\(kind/);
  assert.match(pageSource, /agentType=\{activeType\}/);
  assert.doesNotMatch(pageSource, /暂未开放/);
  assert.doesNotMatch(pageStyles, /\.my-agent-empty\s*\{[^}]*border:/);
  assert.doesNotMatch(pageStyles, /\.my-agent-empty\s*\{[^}]*background:/);
  assert.match(
    pageStyles,
    /\.my-agent-initial-loading,[\s\S]*?\.my-agent-empty\s*\{[\s\S]*?font-size: 12\.5px/,
  );
  assert.match(pageStyles, /\.my-agent-empty p\s*\{[\s\S]*?color: inherit;[\s\S]*?font-size: inherit/);
  assert.match(pageStyles, /\.my-agent-empty p\s*\{[\s\S]*?font-weight: 400/);
});

test("offers a link-styled create action when the Runtime list is empty", () => {
  assert.match(
    pageSource,
    /!query\.trim\(\) && activeType === "general"[\s\S]*?暂无智能体，[\s\S]*?className="my-agent-empty-create"[\s\S]*?onClick=\{\(\) => onCreateAgent\(region\)\}[\s\S]*?点此创建/,
  );
  assert.match(
    pageStyles,
    /\.my-agent-empty \.my-agent-empty-create\s*\{[\s\S]*?border: 0;[\s\S]*?background: transparent;[\s\S]*?text-decoration: underline/,
  );
});

test("shows connecting progress and preserves the connected Runtime state", () => {
  assert.match(pageSource, /const \[connectingAgentId, setConnectingAgentId\] = useState\(""\)/);
  assert.match(
    pageSource,
    /setConnectingAgentId\(agent\.id\)[\s\S]*?requestAnimationFrame[\s\S]*?await onUseAgent\(agent\)[\s\S]*?setConnectingAgentId\(""\)/,
  );
  assert.match(pageSource, /aria-busy=\{connecting \|\| undefined\}/);
  assert.match(pageSource, /connecting \? "连接中" : connected \? "已连接" : "连接"/);
  assert.doesNotMatch(pageSource, /ConnectIcon|my-agent-use-spinner/);
  assert.match(pageSource, /disabled=\{!agent\.runtime \|\| connecting \|\| connected\}/);
  assert.match(appSource, /connectedRuntimeId=\{connectedRuntimeId\}/);
  assert.match(pageStyles, /\.my-agent-loading-mark[\s\S]*?border-right-color: transparent/);
  assert.match(
    pageStyles,
    /\.my-agent-connect\.is-connected,[\s\S]*?background: hsl\(142 55% 94%\)[\s\S]*?color: hsl\(142 62% 30%\)/,
  );
});

test("uses connected Runtime state only for the card action", () => {
  assert.doesNotMatch(pageSource, /my-agents-connect-banner|请选择一个智能体以对话/);
  assert.match(pageSource, /agent\.runtime\?\.runtimeId === connectedRuntimeId/);
  assert.match(pageSource, /const connectedIndex = availableAgents\.findIndex/);
  assert.match(pageSource, /availableAgents\[connectedIndex\][\s\S]*?availableAgents\.slice\(0, connectedIndex\)/);
  assert.match(appSource, /const connectedRuntimeId =[\s\S]*?currentRuntime\?\.runtimeId \?\?[\s\S]*?connections\.reduce/);
  assert.match(appSource, /connectedRuntimeId=\{connectedRuntimeId\}/);
});

test("authenticated users land on the Agent page by default", () => {
  assert.match(appSource, /if \(id\.status === "authenticated"\)[\s\S]*?setMyAgents\(true\)/);
  assert.match(appSource, /function onUsername[\s\S]*?startNewChat\(\);[\s\S]*?setMyAgents\(true\)/);
  assert.match(appSource, /defaultViewAppliedRef\.current \|\| myAgents/);
});

test("removes numbered pagination in favor of continuous loading", () => {
  assert.doesNotMatch(pageSource, /MAX_ROWS|my-agent-pagination|上一页|下一页/);
  assert.doesNotMatch(pageStyles, /\.my-agent-pagination/);
});
