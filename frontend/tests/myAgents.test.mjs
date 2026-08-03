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
const globalStyles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const packageJson = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
);
const viteConfig = readFileSync(
  new URL("../vite.config.ts", import.meta.url),
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
    /onClick=\{onMyAgents\}[\s\S]*?aria-label="智能体"[\s\S]*?<AgentFaceIcon \/>/,
  );
  assert.match(appSource, /const openMyAgentsPage = \(\) => \{/);
  assert.match(appSource, /<Sidebar[\s\S]*?onMyAgents=\{openMyAgentsPage\}/);
  assert.match(appSource, /myAgents \? \([\s\S]*?<MyAgents/);
});

test("shows the requested title, search, and agent type pills", () => {
  assert.match(pageSource, /<h1>智能体<\/h1>/);
  assert.doesNotMatch(pageSource, /Runtime 地域|regionMenuOpen/);
  assert.doesNotMatch(pageStyles, /\.my-agents-region/);
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

test("keeps a primary create action visible above the scrolling results", () => {
  assert.match(pageSource, /canCreate: boolean/);
  assert.match(pageSource, /canCreate && activeType === "general"/);
  assert.match(pageSource, /onCreateAgent\(DEFAULT_CREATE_REGION\)/);
  assert.doesNotMatch(pageSource, /activeType === "codex" \? onCreateCodexAgent/);
  assert.match(pageSource, /className="my-agent-create-primary"[\s\S]*?disabled=\{!createAgent\}[\s\S]*?<span>创建智能体<\/span>/);
  assert.ok(pageSource.indexOf('className="my-agent-create-primary"') < pageSource.indexOf('className="my-agent-results"'));
  assert.match(pageSource, /当前账号没有创建智能体权限/);
  assert.match(pageSource, /activeType !== "general" \? `\$\{activeLabel\}暂未开放`/);
  assert.match(pageStyles, /\.my-agent-create-primary\s*\{[\s\S]*?background: hsl\(var\(--foreground\)\);[\s\S]*?color: hsl\(var\(--background\)\)/);
  assert.match(pageStyles, /\.my-agent-create-primary:disabled\s*\{[\s\S]*?cursor: not-allowed/);
});

test("agent cards show the archived metadata hierarchy and two-action footer", () => {
  assert.match(pageSource, /<h3>\{agent\.name\}<\/h3>/);
  assert.match(pageSource, /<dt>创建时间<\/dt>/);
  assert.match(pageSource, /<dt>地域<\/dt>[\s\S]*?<dd>\{agent\.specification\}<\/dd>/);
  assert.doesNotMatch(pageSource, /<dt>工具<\/dt>|<dt>技能<\/dt>/);
  assert.match(pageSource, /className="my-agent-description">\{agent\.description\}/);
  assert.match(pageSource, /className="my-agent-actions"/);
  assert.match(pageSource, /aria-label=\{connected \? `\$\{agent\.name\} 已连接` : `使用 \$\{agent\.name\}`\}/);
  assert.match(pageSource, /onClick=\{\(\) => onViewDetails\?\.\(agent\)\}/);
  assert.match(pageSource, />\s*查看详情\s*<\/button>/);
  assert.match(pageSource, /connected \? "已连接" : "使用"/);
  assert.ok(pageSource.indexOf("my-agent-details") < pageSource.indexOf("my-agent-use"));
  assert.doesNotMatch(pageSource, /<small|<code/);
  assert.doesNotMatch(pageStyles, /font-family/);
});

test("uses the archived two-layer card layout", () => {
  assert.match(
    pageStyles,
    /\.my-agent-grid\s*\{[\s\S]*?grid-template-columns: repeat\(auto-fit, minmax\(min\(204px, 100%\), 1fr\)\);[\s\S]*?gap: 12px;/,
  );
  assert.match(
    pageStyles,
    /\.my-agent-card\s*\{[\s\S]*?height: 204px;[\s\S]*?background: transparent;/,
  );
  assert.match(pageStyles, /\.my-agent-card-content\s*\{[\s\S]*?background: hsl\(var\(--panel\)\);/);
  assert.match(pageStyles, /\.my-agent-description\s*\{[\s\S]*?-webkit-line-clamp: 2/);
  assert.match(pageStyles, /\.my-agent-actions\s*\{[\s\S]*?gap: 8px;[\s\S]*?padding: 6px 8px 7px;[\s\S]*?background: hsl\(var\(--secondary\) \/ 0\.82\)/);
  assert.match(pageStyles, /\.my-agent-actions button\s*\{[\s\S]*?background: transparent/);
});

test("metadata remains compact without adding data-plane requests", () => {
  assert.doesNotMatch(pageStyles, /\.my-agent-label/);
  assert.match(pageStyles, /\.my-agent-created-at dt,[\s\S]*?\.my-agent-region dt\s*\{[\s\S]*?font-weight: 600/);
  assert.match(pageStyles, /\.my-agent-created-at dd,[\s\S]*?\.my-agent-region dd\s*\{[\s\S]*?color: hsl\(var\(--muted-foreground\)\)/);
  assert.doesNotMatch(pageSource, /getRuntimeAgentInfo/);
  assert.doesNotMatch(pageSource, /Promise\.all\([\s\S]*?page\.runtimes\.map/);
  assert.doesNotMatch(pageSource, /appName: info\.appName/);
});

test("loads both Runtime regions through the merged all-regions endpoint", () => {
  assert.match(pageSource, /getRuntimes/);
  assert.match(pageSource, /runtimeScope: RuntimeScope/);
  assert.match(pageSource, /scope: runtimeScope/);
  assert.doesNotMatch(pageSource, /const \[region, setRegion\]/);
  assert.match(pageSource, /region: "all",\s*pageSize: RUNTIME_PAGE_SIZE/);
  assert.match(pageSource, /id: runtime\.runtimeId/);
  assert.match(pageSource, /name: runtime\.name/);
  assert.match(pageSource, /description: runtime\.description\?\.trim\(\) \|\| "暂无描述"/);
  assert.match(pageSource, /formatRuntimeRegion\(runtime\.region\)/);
  assert.match(pageSource, /region === "cn-shanghai"[\s\S]*?"上海"[\s\S]*?region === "cn-beijing"[\s\S]*?"北京"/);
  assert.match(pageSource, /runtimeId: runtime\.runtimeId/);
  assert.match(pageSource, /region: runtime\.region/);
  assert.match(pageSource, /<AgentCard[\s\S]*?key=\{agent\.id\}/);
  assert.match(pageSource, /const RUNTIME_PAGE_SIZE = 24/);
  assert.match(pageSource, /onList\(page\.runtimes\.map\(runtimeToAgent\)\)/);
  assert.match(pageSource, /runtimeRequestRef\.current !== requestId/);
  assert.match(pageSource, /const runtimePageRequests = new Map/);
  assert.match(pageSource, /const requestKey = `\$\{runtimeScope\}:all:\$\{nextToken\}`/);
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

test("loads subsequent Runtime pages as the results are scrolled", () => {
  assert.match(pageSource, /const loadMoreRef = useRef<HTMLDivElement>\(null\)/);
  assert.match(pageSource, /const root = resultsRef\.current/);
  assert.match(pageSource, /new IntersectionObserver/);
  assert.match(pageSource, /void fetchRuntimePage\(runtimeNextToken, false\)/);
  assert.match(pageSource, /rootMargin: "240px 0px"/);
  assert.match(pageSource, /className="my-agent-load-more" ref=\{loadMoreRef\}/);
  assert.match(pageSource, /visibleAgents\.length > 0 \|\| Boolean\(runtimeNextToken\)/);
  assert.doesNotMatch(pageSource, /my-agent-pagination|PageChevronIcon|ResizeObserver|MAX_CARD_ROWS/);
  assert.match(pageStyles, /@keyframes my-agent-card-enter/);
  assert.match(pageStyles, /\.my-agent-card\s*\{[\s\S]*?animation: my-agent-card-enter/);
  assert.match(pageStyles, /\.my-agent-load-more\s*\{[\s\S]*?min-height: 54px/);
  assert.doesNotMatch(pageStyles, /\.my-agent-pagination/);
  assert.match(pageStyles, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?animation: none/);
});

test("keeps the page controls fixed while only the Agent results scroll", () => {
  assert.match(pageSource, /const resultsRef = useRef<HTMLElement>\(null\)/);
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
    /if \(myAgents \|\| agentDetailTarget \|\| !appName \|\| !userId \|\| !sessionId\)[\s\S]*?getSessionCapabilities/,
  );
  assert.match(
    appSource,
    /if \([\s\S]*?authStatus !== "authenticated"[\s\S]*?myAgents[\s\S]*?!appName[\s\S]*?\)[\s\S]*?getAgentInfo/,
  );
  assert.match(
    appSource,
    /if \(myAgents \|\| agentDetailTarget \|\| sandboxSession \|\| !appName \|\| !userId\)[\s\S]*?return;[\s\S]*?refreshSessions/,
  );
  assert.match(
    appSource,
    /!manageAgents \|\|[\s\S]*?agentDetailTarget[\s\S]*?void refreshAgentLibrary\(\)/,
  );
});

test("wires card details and connect actions into App navigation", () => {
  assert.match(pageSource, /onClick=\{\(\) => void onUse\?\.\(agent\)\}/);
  assert.match(pageSource, /onClick=\{\(\) => onViewDetails\?\.\(agent\)\}/);
  assert.match(
    appSource,
    /const connectMyAgent[\s\S]*?connectRuntime[\s\S]*?await refreshCurrentAgentAndStartNewChat\(agentId\)/,
  );
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
  assert.doesNotMatch(pageSource, /onCreateCodexAgent/);
  assert.doesNotMatch(appSource, /onCreateCodexAgent=/);
  assert.match(pageSource, /AGENT_TYPES\.map/);
  assert.match(pageSource, /label: "Codex 智能体"/);
  assert.match(pageSource, /label: "OpenClaw 智能体"/);
  assert.match(pageSource, /label: "Hermes 智能体"/);
  assert.doesNotMatch(pageSource, /AgentSection|my-agents-section|comingSoon/);
  assert.match(pageSource, /<EmptyMessage\.Title>\{activeLabel\}暂未开放<\/EmptyMessage\.Title>/);
  assert.match(pageSource, /activeType === "general"[\s\S]*?没有匹配的智能体/);
  assert.doesNotMatch(pageStyles, /\.my-agent-empty\s*\{[^}]*border:/);
  assert.doesNotMatch(pageStyles, /\.my-agent-empty\s*\{[^}]*background:/);
  assert.match(pageSource, /<EmptyMessage[\s\S]*?<EmptyMessage\.Icon/);
  assert.match(pageSource, /<AgentTypeIcon type=\{activeType\} \/>/);
  assert.match(pageSource, /type === "codex"[\s\S]*?type === "openclaw"/);
  assert.match(pageSource, /type === "general"\) return <AgentFaceIcon \/>/);
  assert.match(pageSource, /<EmptyMessage\.Title>\{activeLabel\}暂未开放<\/EmptyMessage\.Title>/);
  assert.match(pageSource, /<EmptyMessage\.Description>敬请期待<\/EmptyMessage\.Description>/);
});

test("uses the official EmptyMessage and offers a real create action for an empty Runtime list", () => {
  assert.match(
    pageSource,
    /from "@openai\/apps-sdk-ui\/components\/EmptyMessage"/,
  );
  assert.match(pageSource, /from "@openai\/apps-sdk-ui\/components\/Button"/);
  assert.match(pageSource, /from "@openai\/apps-sdk-ui\/components\/Icon"/);
  assert.match(
    pageSource,
    /<EmptyMessage\.Title>暂无通用智能体<\/EmptyMessage\.Title>/,
  );
  assert.match(
    pageSource,
    /canCreate \? \([\s\S]*?<EmptyMessage\.ActionRow>[\s\S]*?<Button[\s\S]*?color="primary"[\s\S]*?onClick=\{\(\) => onCreateAgent\(DEFAULT_CREATE_REGION\)\}[\s\S]*?创建智能体/,
  );
  assert.match(pageSource, /query\.trim\(\)[\s\S]*?<EmptyMessage\.Title>没有匹配的智能体<\/EmptyMessage\.Title>/);
  assert.match(pageSource, /className="my-agent-empty-message"[\s\S]*?<EmptyMessage fill="none">/);
  assert.doesNotMatch(pageSource, /<EmptyMessage fill="static">/);
  assert.match(pageStyles, /\.my-agent-empty-message\s*\{[\s\S]*?height: 100%;[\s\S]*?min-height: 220px;[\s\S]*?place-items: center/);
  assert.doesNotMatch(pageStyles, /\.my-agent-empty-message\s+(?:button|svg|\[)/);
});

test("integrates Tailwind 4 and the Apps SDK UI foundation styles", () => {
  assert.equal(packageJson.dependencies["@openai/apps-sdk-ui"], "^0.2.2");
  assert.equal(packageJson.devDependencies.tailwindcss, "^4.3.3");
  assert.equal(packageJson.devDependencies["@tailwindcss/vite"], "^4.3.3");
  assert.match(globalStyles, /@import "tailwindcss";/);
  assert.match(globalStyles, /@import "@openai\/apps-sdk-ui\/css";/);
  assert.match(globalStyles, /@source "\.\.\/node_modules\/@openai\/apps-sdk-ui";/);
  assert.match(viteConfig, /import tailwindcss from "@tailwindcss\/vite"/);
  assert.match(viteConfig, /plugins: \[react\(\), tailwindcss\(\)\]/);
});

test("keeps Runtime failures distinct from successful empty states", () => {
  assert.match(pageSource, /runtimeError && activeType === "general"/);
  assert.match(pageSource, /className="my-agent-empty" role="alert"/);
  assert.match(pageSource, />重新加载<\/button>/);
  const errorBranch = pageSource.slice(
    pageSource.indexOf('runtimeError && activeType === "general"'),
    pageSource.indexOf(": showEmpty ?"),
  );
  assert.doesNotMatch(errorBranch, /<EmptyMessage/);
});

test("shows connecting progress and preserves the connected Runtime state", () => {
  assert.match(pageSource, /const \[connectingAgentId, setConnectingAgentId\] = useState\(""\)/);
  assert.match(
    pageSource,
    /setConnectingAgentId\(agent\.id\)[\s\S]*?requestAnimationFrame[\s\S]*?await onUseAgent\(agent\)[\s\S]*?setConnectingAgentId\(""\)/,
  );
  assert.match(pageSource, /aria-busy=\{connecting \|\| undefined\}/);
  assert.match(pageSource, /my-agent-use-spinner/);
  assert.match(pageSource, /<span>连接中<\/span>/);
  assert.doesNotMatch(pageSource, /ConnectIcon/);
  assert.match(pageSource, /disabled=\{!agent\.runtime \|\| connecting \|\| connected\}/);
  assert.match(appSource, /connectedRuntimeId=\{connectedRuntimeId\}/);
  assert.match(pageStyles, /\.my-agent-loading-mark[\s\S]*?border-right-color: transparent/);
  assert.match(
    pageStyles,
    /\.my-agent-actions \.my-agent-use\.is-connected,[\s\S]*?background: transparent[\s\S]*?color: hsl\(142 62% 30%\)/,
  );
});

test("uses connected Runtime state only for the card action", () => {
  assert.doesNotMatch(pageSource, /my-agents-connect-banner|请选择一个智能体以对话/);
  assert.match(pageSource, /agent\.runtime\?\.runtimeId === connectedRuntimeId/);
  assert.match(pageSource, /const connectedIndex = availableAgents\.findIndex/);
  assert.match(pageSource, /availableAgents\[connectedIndex\][\s\S]*?availableAgents\.slice\(0, connectedIndex\)/);
  assert.match(appSource, /const connectedRuntimeId = currentRuntime\?\.runtimeId \?\? ""/);
  assert.doesNotMatch(
    appSource,
    /const connectedRuntimeId =[\s\S]*?connections\.reduce/,
  );
  assert.match(appSource, /connectedRuntimeId=\{connectedRuntimeId\}/);
});

test("authenticated users land on a new chat without a selected Agent", () => {
  assert.match(
    appSource,
    /if \(id\.status === "authenticated"\)[\s\S]*?setAppName\(""\)[\s\S]*?setMyAgents\(false\)/,
  );
  assert.match(
    appSource,
    /function onUsername[\s\S]*?startNewChat\(\);[\s\S]*?setAppName\(""\)[\s\S]*?setMyAgents\(false\)/,
  );
  assert.doesNotMatch(appSource, /defaultViewAppliedRef/);
});
