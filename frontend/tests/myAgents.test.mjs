import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

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
  assert.match(
    appSource,
    /<Sidebar[\s\S]*?onMyAgents=\{\(\) => requestIntelligentNavigation\(openMyAgentsPage\)\}/,
  );
  assert.match(appSource, /myAgents && !showManageAgents \? \([\s\S]*?<MyAgents/);
});

test("shows the requested title, search, and agent type pills", () => {
  assert.match(pageSource, /<h1>智能体<\/h1>/);
  assert.doesNotMatch(pageSource, /Runtime 地域|regionMenuOpen/);
  assert.doesNotMatch(pageStyles, /\.my-agents-region/);
  assert.match(pageSource, /在此处浏览您的所有智能体/);
  assert.match(pageSource, /placeholder="搜索所有类型智能体名称"/);
  assert.match(pageSource, /aria-label="搜索智能体"/);
  assert.doesNotMatch(pageSource, /<span className="sr-only">搜索智能体<\/span>/);
  for (const title of [
    "通用智能体",
    "Codex 智能体",
    "DeepSeek Harness",
    "OpenClaw 智能体",
    "Hermes 智能体",
  ]) {
    assert.match(pageSource, new RegExp(`label: "${title}"`));
  }
  assert.match(pageSource, /className="my-agent-type-pill/);
  assert.match(pageSource, /aria-pressed=\{activeType === type\.id\}/);
  assert.match(pageSource, /onClick=\{\(\) => selectAgentType\(type\.id\)\}/);
});

test("preserves the selected sandbox type across details and refreshes it after deletion", () => {
  assert.match(pageSource, /activeType: AgentType/);
  assert.match(pageSource, /onActiveTypeChange: \(type: AgentType\) => void/);
  assert.doesNotMatch(pageSource, /useState<AgentType>\("general"\)/);
  assert.match(
    appSource,
    /const \[myAgentsActiveType, setMyAgentsActiveType\] = useState<AgentType>\("general"\)/,
  );
  assert.match(
    appSource,
    /function openSandboxAgentDetails\(session: SandboxAgentResource\)[\s\S]*?setMyAgentsActiveType\(session\.toolName\)/,
  );
  assert.match(
    appSource,
    /async function deleteSandboxAgent\(session: SandboxAgentResource\)[\s\S]*?setMyAgentsActiveType\(session\.toolName\)[\s\S]*?setSandboxAgentRefreshKey\(\(current\) => current \+ 1\)[\s\S]*?setMyAgents\(true\)/,
  );
  assert.match(
    appSource,
    /<MyAgents[\s\S]*?activeType=\{myAgentsActiveType\}[\s\S]*?onActiveTypeChange=\{setMyAgentsActiveType\}[\s\S]*?sandboxRefreshKey=\{sandboxAgentRefreshKey\}/,
  );
  assert.match(
    pageSource,
    /fetchSandboxAgents\(activeType\)[\s\S]*?\[activeType, fetchSandboxAgents, sandboxRefreshKey\]/,
  );
});

test("clears stale sandbox cards as soon as the Agent type changes", () => {
  assert.match(
    pageSource,
    /function selectAgentType\(type: AgentType\)[\s\S]*?sandboxAbortRef\.current\?\.abort\(\)[\s\S]*?sandboxRequestRef\.current \+= 1[\s\S]*?setSandboxAgents\(\[\]\)[\s\S]*?setLoadingSandboxAgents\(true\)[\s\S]*?onActiveTypeChange\(type\)/,
  );
  assert.match(
    pageSource,
    /const fetchSandboxAgents[\s\S]*?setLoadingSandboxAgents\(true\)[\s\S]*?setSandboxAgents\(\[\]\)[\s\S]*?await sandboxClient/,
  );
  assert.match(
    pageSource,
    /type === "general"[\s\S]*?runtimeRequestRef\.current \+= 1[\s\S]*?setRuntimeAgents\(\[\]\)[\s\S]*?setLoadingRuntimes\(true\)/,
  );
  assert.match(
    pageSource,
    /useEffect\(\(\) => \{[\s\S]*?activeType !== "general"[\s\S]*?fetchRuntimePage\("", true\)[\s\S]*?\[activeType, fetchRuntimePage\]/,
  );
});

test("renders only account-backed Runtime and Sandbox agents", () => {
  assert.doesNotMatch(pageSource, /STATIC_SECTIONS/);
  assert.doesNotMatch(
    pageSource,
    /codex-code-review|codex-test-coverage|openclaw-research|hermes-data-analysis/,
  );
  assert.match(
    pageSource,
    /sandboxClient\.listSessions\(\{[\s\S]*?signal: controller\.signal,[\s\S]*?autoResumeSnapshots: true,[\s\S]*?\}\)/,
  );
  assert.match(
    pageSource,
    /sandboxClient\.listAgentSessions\(type, \{[\s\S]*?signal: controller\.signal,[\s\S]*?autoResumeSnapshots: true,[\s\S]*?\}\)/,
  );
  assert.match(pageSource, /sessions\.map\(sandboxToAgent\)/);
});

test("keeps a primary create action visible above the scrolling results", () => {
  assert.match(pageSource, /canCreate: boolean/);
  assert.match(pageSource, /cloudProvider: CloudProvider/);
  assert.match(pageSource, /activeType === "general"[\s\S]*?onCreateAgent\(defaultCloudRegion\(cloudProvider\)\)[\s\S]*?onCreateSandboxAgent\(activeType\)/);
  assert.match(pageSource, /onCreateAgent\(defaultCloudRegion\(cloudProvider\)\)/);
  assert.match(pageSource, /onCreateSandboxAgent: \(kind: "codex" \| SandboxAgentKind\) => void/);
  assert.match(pageSource, /className="my-agent-create-primary"[\s\S]*?disabled=\{!createAgent\}[\s\S]*?<span>创建智能体<\/span>/);
  assert.match(
    pageSource,
    /className="my-agent-create-secondary"[\s\S]*?<HandoffIcon \/>[\s\S]*?<span>接力<\/span>/,
  );
  assert.doesNotMatch(pageSource, /className="my-agent-handoff-button"/);
  assert.match(
    pageStyles,
    /\.my-agent-create-secondary\s*\{[\s\S]*?height: 32px;[\s\S]*?gap: 6px;[\s\S]*?font-size: 12\.5px;/,
  );
  assert.match(
    pageStyles,
    /\.my-agent-create-secondary\s*\{[\s\S]*?background-image: linear-gradient\([\s\S]*?var\(--blue-500\)[\s\S]*?var\(--purple-500\)[\s\S]*?var\(--purple-400\)[\s\S]*?color: var\(--white\)/,
  );
  assert.match(
    pageStyles,
    /\.my-agent-create-secondary:hover:not\(:disabled\)\s*\{[\s\S]*?background-position: 68% 50%/,
  );
  assert.match(
    pageStyles,
    /\.my-agent-create-secondary svg,[\s\S]*?\.my-agent-create-primary svg\s*\{[\s\S]*?width: 14px;[\s\S]*?height: 14px;/,
  );
  assert.doesNotMatch(pageSource, /本地迁移/);
  assert.ok(pageSource.indexOf('className="my-agent-create-primary"') < pageSource.indexOf('className="my-agent-results"'));
  assert.match(pageSource, /当前账号没有创建智能体权限/);
  assert.match(pageStyles, /\.my-agent-create-primary\s*\{[\s\S]*?background: hsl\(var\(--foreground\)\);[\s\S]*?color: hsl\(var\(--background\)\)/);
  assert.match(pageStyles, /\.my-agent-create-primary:disabled\s*\{[\s\S]*?cursor: not-allowed/);
});

test("agent cards show the archived metadata hierarchy and two-action footer", () => {
  assert.match(pageSource, /<h3>\{agent\.name\}<\/h3>/);
  assert.match(pageSource, /<dt>\{agent\.draft \? "更新时间" : "创建时间"\}<\/dt>/);
  assert.match(pageSource, /<dt>\{agent\.specificationLabel\}<\/dt>[\s\S]*?<dd>\{agent\.specification\}<\/dd>/);
  assert.match(pageSource, /const sandboxResourceId = agent\.sandbox\?\.resourceType === "snapshot"[\s\S]*?agent\.sandbox\.sourceSessionId \|\| agent\.sandbox\.snapshotId[\s\S]*?: agent\.sandbox\?\.id/);
  assert.match(pageSource, /className="my-agent-session-id"[\s\S]*?\{sandboxResourceId\}/);
  assert.doesNotMatch(pageSource, /Session ID：/);
  assert.match(pageSource, /className="my-agent-status-label"[\s\S]*?\{agent\.description\}/);
  assert.doesNotMatch(pageSource, /<dt>工具<\/dt>|<dt>技能<\/dt>/);
  assert.match(pageSource, /className="my-agent-description">\{agent\.description\}/);
  assert.match(pageSource, /className="my-agent-actions"/);
  assert.match(pageSource, /aria-label=\{connected[\s\S]*?\? `\$\{agent\.name\} 已连接`[\s\S]*?: wakeable[\s\S]*?\? `唤醒 \$\{agent\.name\}`[\s\S]*?: `使用 \$\{agent\.name\}`\}/);
  assert.match(pageSource, /: onViewDetails\?\.\(agent\)/);
  assert.match(pageSource, /deploymentTask \? "查看进度" : "查看详情"/);
  assert.match(pageSource, /connected \? "已连接" : wakeable \? "唤醒" : "使用"/);
  assert.ok(pageSource.indexOf("my-agent-details") < pageSource.indexOf("my-agent-use"));
  assert.doesNotMatch(pageSource, /<small|<code/);
  assert.doesNotMatch(pageStyles, /font-family/);
});

test("shows browser-local drafts with edit and confirmed delete actions", () => {
  assert.match(pageSource, /drafts\?: WorkspaceAgentDraft\[\]/);
  assert.match(pageSource, /function draftToAgent\(item: WorkspaceAgentDraft\)/);
  assert.match(pageSource, /specification: "当前浏览器"/);
  assert.match(pageSource, /\? \[\.\.\.draftAgents, \.\.\.runtimeAgents\]/);
  assert.match(
    pageSource,
    /className="my-agent-draft-badge">[\s\S]*?deploymentTask \? "部署中" : "草稿"/,
  );
  assert.match(pageSource, /: `编辑草稿 \$\{agent\.name\}`/);
  assert.match(pageSource, /aria-label=\{`删除草稿 \$\{agent\.name\}`\}/);
  assert.match(pageSource, /title="删除草稿？"[\s\S]*?confirmLabel="删除草稿"/);
  assert.match(appSource, /<MyAgents[\s\S]*?drafts=\{savedAgentDrafts\}/);
  assert.match(appSource, /onDeleteDraft=\{\(item\) => deleteWorkspaceDrafts\(\[item\]\)\}/);
  assert.match(pageStyles, /\.my-agent-draft-badge,[\s\S]*?\.my-agent-deploying-badge\s*\{/);
  assert.match(pageStyles, /\.my-agent-actions \.my-agent-delete\s*\{/);
});

test("reopens running deployment progress from draft and Runtime cards", () => {
  assert.match(pageSource, /deploymentTasks\?: DeploymentTaskUpdate\[\]/);
  assert.match(pageSource, /draftDeploymentTaskIds\?: Readonly<Record<string, string>>/);
  assert.match(pageSource, /task\.status !== "running"/);
  assert.match(pageSource, /draftDeploymentTaskIds\[agent\.draft\.id\]/);
  assert.match(pageSource, /activeDeploymentTasks\.byRuntimeId\.get\(runtimeId\)/);
  assert.match(pageSource, /\{deploymentTask \? "部署中" : "草稿"\}/);
  assert.match(pageSource, /deploymentTask \? "查看进度" : "编辑"/);
  assert.match(pageSource, /deploymentTask \? "查看进度" : "查看详情"/);
  assert.match(appSource, /const \[draftDeploymentTaskIds, setDraftDeploymentTaskIds\]/);
  assert.match(appSource, /\[editingDraftId\]: task\.id/);
  assert.match(appSource, /deploymentTasks=\{deploymentTasks\}/);
  assert.match(appSource, /onViewDeploymentTask=\{openDeploymentDetail\}/);
});

test("uses a responsive two-layer card layout without an empty fixed-height gap", () => {
  assert.match(
    pageStyles,
    /\.my-agent-grid\s*\{[\s\S]*?grid-template-columns: repeat\(auto-fill, minmax\(min\(280px, 100%\), 1fr\)\);[\s\S]*?align-items: start;[\s\S]*?gap: 12px;/,
  );
  assert.match(
    pageStyles,
    /\.my-agent-card\s*\{[\s\S]*?height: auto;[\s\S]*?background: hsl\(var\(--secondary\) \/ 0\.82\)/,
  );
  assert.match(pageStyles, /\.my-agent-card-content\s*\{[\s\S]*?background: hsl\(var\(--panel\)\);/);
  assert.doesNotMatch(
    pageStyles,
    /\.my-agent-card-content\s*\{[^}]*box-shadow:/,
  );
  assert.doesNotMatch(pageStyles, /\.my-agent-card:hover \.my-agent-card-content/);
  assert.match(pageStyles, /\.my-agent-description\s*\{[\s\S]*?-webkit-line-clamp: 2/);
  assert.match(pageStyles, /\.my-agent-actions\s*\{[\s\S]*?gap: 8px;[\s\S]*?padding: 6px 8px 7px;[\s\S]*?background: hsl\(var\(--secondary\) \/ 0\.82\)/);
  assert.match(pageStyles, /\.my-agent-actions button\s*\{[\s\S]*?background: transparent/);
});

test("aligns sandbox names with status and formats creation time to seconds", () => {
  assert.match(pageStyles, /\.my-agent-card-title\s*\{[\s\S]*?justify-content: space-between/);
  assert.match(pageStyles, /\.my-agent-session-id\s*\{/);
  assert.match(pageSource, /hour: "2-digit"[\s\S]*?minute: "2-digit"[\s\S]*?second: "2-digit"/);
  assert.match(pageSource, /agent\.sandbox \? \([\s\S]*?\{sandboxResourceId\}/);
});

test("shows aligned lifetime metadata for persistent and non-persistent Sandbox agents", async () => {
  const formatterSource = pageSource.match(
    /export function formatSandboxRemainingTime\([\s\S]*?\n\}/,
  )?.[0];
  assert.ok(formatterSource);
  const { outputText } = ts.transpileModule(formatterSource, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
  const { formatSandboxRemainingTime } = await import(moduleUrl);
  const now = Date.parse("2026-08-11T00:00:00.000Z");

  assert.equal(
    formatSandboxRemainingTime("2026-08-11T02:30:00.000Z", now),
    "2 小时 30 分钟",
  );
  assert.equal(
    formatSandboxRemainingTime("2026-08-11T00:00:30.000Z", now),
    "即将清空",
  );
  assert.equal(formatSandboxRemainingTime("2026-08-10T23:59:59.000Z", now), "即将清空");
  assert.equal(formatSandboxRemainingTime("invalid", now), "即将清空");

  assert.match(
    pageSource,
    /className=\{`my-agent-expiry\$\{[\s\S]*?agent\.sandbox\.persistent[\s\S]*?`\}[\s\S]*?<dt>剩余时间<\/dt>[\s\S]*?agent\.sandbox\.persistent[\s\S]*?"永不过期"[\s\S]*?agent\.sandbox\.expireAt/,
  );
  assert.doesNotMatch(
    pageSource,
    /<span className="my-agent-expiry"/,
  );
  assert.match(pageSource, /window\.setInterval\([\s\S]*?60_000/);
  assert.match(pageSource, /return \(\) => window\.clearInterval\(timer\)/);
  assert.match(pageStyles, /\.my-agent-expiry\.is-expiring dd\s*\{[\s\S]*?color: hsl\(38 78% 36%\)/);
});

test("metadata remains compact without adding data-plane requests", () => {
  assert.doesNotMatch(pageStyles, /\.my-agent-label/);
  assert.match(pageStyles, /\.my-agent-created-at dt,[\s\S]*?\.my-agent-region dt,[\s\S]*?\.my-agent-expiry dt\s*\{[\s\S]*?font-weight: 600/);
  assert.match(pageStyles, /\.my-agent-created-at dd,[\s\S]*?\.my-agent-region dd,[\s\S]*?\.my-agent-expiry dd\s*\{[\s\S]*?color: hsl\(var\(--muted-foreground\)\)/);
  assert.doesNotMatch(pageSource, /getRuntimeAgentInfo/);
  assert.doesNotMatch(pageSource, /Promise\.all\([\s\S]*?page\.runtimes\.map/);
  assert.doesNotMatch(pageSource, /appName: info\.appName/);
});

test("loads all Runtime regions and shows the creator in card metadata", () => {
  assert.match(pageSource, /getRuntimes/);
  assert.match(pageSource, /runtimeScope: RuntimeScope/);
  assert.match(pageSource, /scope: runtimeScope/);
  assert.doesNotMatch(pageSource, /const \[region, setRegion\]/);
  assert.match(pageSource, /region: "all",\s*pageSize: RUNTIME_PAGE_SIZE/);
  assert.match(pageSource, /id: runtime\.runtimeId/);
  assert.match(pageSource, /name: runtime\.name/);
  assert.match(pageSource, /description: runtime\.description\?\.trim\(\) \|\| "暂无描述"/);
  assert.match(pageSource, /specificationLabel: "创建人"/);
  assert.match(pageSource, /specification: runtime\.author \|\| "—"/);
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

test("shows the Runtime region before the ownership badge in the card title", () => {
  assert.match(
    pageSource,
    /formatCloudRegion\(agent\.runtime\.region, cloudProvider\)/,
  );
  assert.match(
    pageSource,
    /className="my-agent-card-badges"[\s\S]*?className="my-agent-region-badge"[\s\S]*?formatCloudRegion\(agent\.runtime\.region, cloudProvider\)[\s\S]*?className="runtime-owner-badge"[\s\S]*?>我创建的</,
  );
  assert.match(
    pageStyles,
    /\.my-agent-card-badges\s*\{[\s\S]*?display: flex;[\s\S]*?gap: 6px/,
  );
  assert.match(
    pageStyles,
    /\.my-agent-region-badge\s*\{[\s\S]*?display: inline-flex;[\s\S]*?border-radius: 999px/,
  );
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
  assert.match(pageSource, /: onViewDetails\?\.\(agent\)/);
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
  assert.match(pageSource, /onCreateSandboxAgent/);
  assert.match(appSource, /onCreateSandboxAgent=\{openSandboxAgentCreate\}/);
  assert.match(pageSource, /AGENT_TYPES\.map/);
  assert.match(pageSource, /label: "Codex 智能体"/);
  assert.match(pageSource, /label: "DeepSeek Harness"/);
  assert.match(pageSource, /label: "OpenClaw 智能体"/);
  assert.match(pageSource, /label: "Hermes 智能体"/);
  assert.doesNotMatch(pageSource, /AgentSection|my-agents-section|comingSoon/);
  assert.match(pageSource, /<EmptyMessage\.Title className="my-agent-sandbox-empty-title">[\s\S]*?暂无 \{activeLabel\}[\s\S]*?<\/EmptyMessage\.Title>/);
  assert.match(pageStyles, /\.my-agent-sandbox-empty-title\s*\{[\s\S]*?max-width: none;[\s\S]*?white-space: nowrap;[\s\S]*?text-wrap: nowrap;/);
  assert.match(pageSource, /activeType === "general"[\s\S]*?没有匹配的智能体/);
  assert.doesNotMatch(pageStyles, /\.my-agent-empty\s*\{[^}]*border:/);
  assert.doesNotMatch(pageStyles, /\.my-agent-empty\s*\{[^}]*background:/);
  assert.match(pageSource, /<EmptyMessage[\s\S]*?<EmptyMessage\.Icon/);
  assert.match(pageSource, /<AgentTypeIcon type=\{activeType\} \/>/);
  assert.match(pageSource, /type === "general"\) return <AgentFaceIcon \/>/);
  assert.match(pageSource, /return <SandboxAgentIcon kind=\{type\} \/>/);
  assert.doesNotMatch(pageSource, /开始使用 AgentKit Session/);
  assert.match(pageSource, /onClick=\{\(\) => onCreateSandboxAgent\(activeType\)\}/);
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
    /canCreate \? \([\s\S]*?<EmptyMessage\.ActionRow>[\s\S]*?<Button[\s\S]*?color="primary"[\s\S]*?onClick=\{\(\) => onCreateAgent\(defaultCloudRegion\(cloudProvider\)\)\}[\s\S]*?创建智能体/,
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
  assert.match(pageSource, /activeType === "general" \? runtimeError : sandboxError/);
  assert.match(pageSource, /className="my-agent-empty" role="alert"/);
  assert.match(pageSource, />\s*重新加载\s*<\/button>/);
  const errorBranch = pageSource.slice(
    pageSource.indexOf('(activeType === "general" ? runtimeError : sandboxError)'),
    pageSource.indexOf(": showEmpty ?"),
  );
  assert.doesNotMatch(errorBranch, /<EmptyMessage/);
  assert.match(errorBranch, /fetchSandboxAgents\(activeType\)/);
  assert.match(pageSource, /formatRequestError\(cause, "加载通用智能体", "GET \/web\/runtimes"\)/);
  assert.match(pageSource, /formatRequestError\([\s\S]*?`加载 \$\{AGENT_TYPES\.find/);
  assert.match(pageSource, /`GET \/web\/\$\{type === "codex" \? "sandbox" : type\}\/sessions`/);
  assert.match(pageStyles, /\.my-agent-empty p\s*\{[\s\S]*?white-space: pre-wrap;[\s\S]*?overflow-wrap: anywhere;/);
});

test("shows connecting progress and preserves the connected Runtime state", () => {
  assert.match(pageSource, /const \[connectingAgentId, setConnectingAgentId\] = useState\(""\)/);
  assert.match(
    pageSource,
    /setConnectingAgentId\(agent\.id\)[\s\S]*?requestAnimationFrame[\s\S]*?await onUseAgent\(agent\)[\s\S]*?setConnectingAgentId\(""\)/,
  );
  assert.match(pageSource, /aria-busy=\{connecting \|\| undefined\}/);
  assert.match(pageSource, /my-agent-use-spinner/);
  assert.match(pageSource, /const wakeable = agent\.sandbox\?\.resourceType === "snapshot"/);
  assert.match(pageSource, /<span>\{wakeable \? "唤醒中" : "连接中"\}<\/span>/);
  assert.doesNotMatch(pageSource, /ConnectIcon/);
  assert.match(pageSource, /const actionable = Boolean\([\s\S]*?agent\.runtime \|\| sandboxStatus === "ready" \|\| sandboxStatus === "wakeable"/);
  assert.match(pageSource, /disabled=\{!actionable \|\| connecting \|\| connected\}/);
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
