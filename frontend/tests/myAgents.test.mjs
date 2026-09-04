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
const runtimeDiscoverySource = readFileSync(
  new URL("../src/adk/runtimeDiscovery.ts", import.meta.url),
  "utf8",
);
const resourceSource = readFileSync(
  new URL("../src/ui/ResourceCollection.tsx", import.meta.url),
  "utf8",
);
const resourceStyles = readFileSync(
  new URL("../src/ui/ResourceCollection.css", import.meta.url),
  "utf8",
);
const relativeTimeSource = readFileSync(
  new URL("../src/ui/relativeTime.ts", import.meta.url),
  "utf8",
);
const resourceMetadataSource = readFileSync(
  new URL("../src/ui/resourceMetadata.ts", import.meta.url),
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
const sandboxSource = readFileSync(new URL("../src/adk/sandbox.ts", import.meta.url), "utf8");
const sandboxServerSource = readFileSync(
  new URL("../../veadk/cli/frontend_sandbox.py", import.meta.url),
  "utf8",
);

test("shows only the Agent navigation in the sidebar", () => {
  assert.match(sidebarSource, /onMyAgents: \(\) => void/);
  assert.doesNotMatch(sidebarSource, /onManageAgents/);
  assert.doesNotMatch(sidebarSource, /aria-label="智能体库"/);
  assert.match(
    sidebarSource,
    /onClick=\{onMyAgents\}[\s\S]*?aria-label="智能体"[\s\S]*?<SidebarAgentIcon className="icon" \/>/,
  );
  assert.match(appSource, /const openMyAgentsPage = \(\) => \{/);
  assert.match(
    appSource,
    /<Sidebar[\s\S]*?onMyAgents=\{\(\) => requestIntelligentNavigation\(openMyAgentsPage\)\}/,
  );
  assert.match(appSource, /myAgents && !showManageAgents \? \([\s\S]*?<MyAgents/);
});

test("keeps Agent creation out of the sidebar navigation", () => {
  assert.doesNotMatch(sidebarSource, /new-chat--add-agent/);
  assert.doesNotMatch(sidebarSource, /aria-label="添加智能体"/);
});

test("shows the requested title and Figma-aligned Agent toolbar", () => {
  assert.match(pageSource, /<ResourcePageHeader title="智能体"/);
  assert.doesNotMatch(pageSource, /在此处浏览(?:所有|您的所有)智能体/);
  assert.match(pageSource, /className="my-agent-toolbar"/);
  assert.match(pageSource, /placeholder="搜索"/);
  assert.match(pageSource, /aria-label="搜索智能体"/);
  assert.match(resourceSource, /function ResourceSearchIcon[\s\S]*?viewBox="0 0 14 14"[\s\S]*?translate\(0\.875 0\.875\)/);
  assert.match(resourceSource, /@openai\/apps-sdk-ui\/components\/Select/);
  for (const title of [
    "通用智能体",
    "Codex",
    "DeepSeek",
    "OpenClaw",
    "Hermes",
  ]) {
    assert.match(pageSource, new RegExp(`label: "${title}"`));
  }
  assert.match(
    pageSource,
    /<ResourceTabs[\s\S]*?idPrefix="my-agent-ownership"[\s\S]*?<div className="resource-toolbar__actions">/,
  );
  assert.match(
    pageSource,
    /<ResourceFilterSelect[\s\S]*?id="my-agent-type-filter"[\s\S]*?value=\{activeType\}[\s\S]*?options=\{AGENT_TYPE_OPTIONS\}[\s\S]*?onChange=\{selectAgentType\}/,
  );
  assert.match(
    pageSource,
    /id="my-agent-type-filter"[\s\S]*?id="my-agent-region-filter"[\s\S]*?className="my-agent-search"/,
  );
  assert.doesNotMatch(pageSource, /my-agent-type-tabs|my-agent-type-tab/);
  assert.match(resourceStyles, /\.resource-page__header h1\s*\{[\s\S]*?font-size: 24px;[\s\S]*?line-height: normal;/);
  assert.match(resourceStyles, /\.resource-toolbar\s*\{[\s\S]*?gap: 12px;[\s\S]*?margin-top: 20px;/);
  assert.match(
    resourceStyles,
    /\.resource-search\s*\{[\s\S]*?width: 248px;[\s\S]*?height: 32px;[\s\S]*?gap: 4px;[\s\S]*?padding: 0 8px;[\s\S]*?border: 0\.5px solid #b8b7c3;[\s\S]*?border-radius: 8px;/,
  );
  assert.match(
    resourceStyles,
    /\.resource-search input\s*\{[\s\S]*?font-size: 13px;[\s\S]*?line-height: 22px;[\s\S]*?letter-spacing: 0\.039px;/,
  );
  assert.match(
    resourceStyles,
    /\.resource-filter-select\s*\{[\s\S]*?width: fit-content;/,
  );
  assert.match(
    resourceStyles,
    /\.resource-filter-select__trigger\s*\{[\s\S]*?--select-control-font-size: 14px;[\s\S]*?--select-control-font-weight: 400;[\s\S]*?--select-control-gutter: 8px;[\s\S]*?font-family: inherit;/,
  );
  assert.match(
    resourceStyles,
    /\.resource-results\s*\{[\s\S]*?margin: 4px -8px 0;[\s\S]*?padding: 8px 8px 56px;/,
  );
});

test("resets runtime pagination before changing ownership or region filters", () => {
  assert.match(
    pageSource,
    /function resetRuntimePagination\(\)[\s\S]*?runtimeRequestRef\.current \+= 1[\s\S]*?setRuntimeAgents\(\[\]\)[\s\S]*?setRuntimeNextToken\(""\)[\s\S]*?setRuntimeError\(""\)/,
  );
  assert.match(
    pageSource,
    /function selectOwnership\(nextOwnership: RuntimeScope\)[\s\S]*?resetRuntimePagination\(\)[\s\S]*?setOwnership\(nextOwnership\)/,
  );
  assert.match(
    pageSource,
    /function selectRegion\(nextRegion: string\)[\s\S]*?resetRuntimePagination\(\)[\s\S]*?setRegion\(nextRegion\)/,
  );
});

test("uses the Studio-delivered private region instead of a public-cloud fallback", () => {
  assert.match(
    pageSource,
    /return studioRegion\.trim\(\) \|\| defaultCloudRegion\(cloudProvider\)/,
  );
  assert.match(
    pageSource,
    /providerOptions\.some\(\(option\) => option\.value === configuredRegion\)[\s\S]*?value: configuredRegion, label: configuredRegion/,
  );
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

test("renders Agent creation as the first dashed card instead of a toolbar button", () => {
  assert.match(pageSource, /canCreateRuntimeAgents: boolean/);
  assert.match(pageSource, /canCreatePersonalAgents: boolean/);
  assert.match(pageSource, /cloudProvider: CloudProvider/);
  assert.match(pageSource, /activeType === "general"[\s\S]*?onCreateAgent\(region\)[\s\S]*?onCreateSandboxAgent\(activeType\)/);
  assert.match(pageSource, /onCreateSandboxAgent: \(kind: "codex" \| SandboxAgentKind\) => void/);
  assert.match(pageSource, /<ResourceGrid className="my-agent-grid">[\s\S]*?createAgent \? \([\s\S]*?<ResourceCreateCard[\s\S]*?className="my-agent-create-card"[\s\S]*?创建智能体[\s\S]*?visibleAgents\.map/);
  assert.doesNotMatch(pageSource, /my-agent-create-primary/);
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
    /\.my-agent-create-secondary svg\s*\{[\s\S]*?width: 14px;[\s\S]*?height: 14px;/,
  );
  assert.doesNotMatch(pageSource, /本地迁移/);
  assert.match(resourceStyles, /\.resource-create-card\s*\{[\s\S]*?height: 152px;[\s\S]*?border: 1px dashed #d2d1e0[\s\S]*?border-radius: 16px/);
  assert.match(resourceStyles, /\.resource-create-card:hover:not\(:disabled\)\s*\{/);
});

test("agent cards reproduce the compact Figma hierarchy with card details and one chat action", () => {
  assert.match(pageSource, /<ResourceIdentityMark seed=\{agent\.name\} \/>/);
  assert.match(pageSource, /<ResourceCardHeader[\s\S]*?title=\{agent\.name\}/);
  assert.match(pageSource, /formatCardUpdateLabel\(agent\.createdAt, nowMs\)/);
  assert.match(pageSource, /label: agent\.specificationLabel,[\s\S]*?value: agent\.specification,[\s\S]*?hideLabel: true/);
  assert.match(pageSource, /const sandboxResourceId = agent\.sandbox\?\.resourceType === "snapshot"[\s\S]*?agent\.sandbox\.sourceSessionId \|\| agent\.sandbox\.snapshotId[\s\S]*?: agent\.sandbox\?\.id/);
  assert.match(pageSource, /className="my-agent-session-id"[\s\S]*?\{sandboxResourceId\}/);
  assert.doesNotMatch(pageSource, /Session ID：/);
  assert.match(pageSource, /className="my-agent-status-label"[\s\S]*?\{agent\.description\}/);
  assert.doesNotMatch(pageSource, /<dt>工具<\/dt>|<dt>技能<\/dt>/);
  assert.match(pageSource, /<ResourceCardDescription>\{agent\.description\}<\/ResourceCardDescription>/);
  assert.match(pageSource, /actions=\{agent\.draft \? \(/);
  assert.match(pageSource, /activateLabel=\{cardTargetEnabled \? cardTargetLabel : undefined\}[\s\S]*?onActivate=\{cardTargetEnabled \? openCard : undefined\}/);
  assert.match(pageSource, /else onViewDetails\?\.\(agent\)/);
  assert.match(pageSource, /label=\{connected[\s\S]*?\? `\$\{agent\.name\} 已连接`[\s\S]*?: wakeable[\s\S]*?\? `唤醒 \$\{agent\.name\} 并开始对话`[\s\S]*?: `与 \$\{agent\.name\} 对话`\}/);
  assert.doesNotMatch(pageSource, /function AgentDetailsIcon/);
  assert.match(pageSource, /<AgentUseIcon \/>/);
  assert.doesNotMatch(pageSource, /<small|<code/);
  assert.match(
    resourceStyles,
    /\.resource-page\s*\{[\s\S]*?background: hsl\(var\(--panel\)\);[\s\S]*?font-family: "PingFang SC"/,
  );
  assert.match(
    resourceStyles,
    /\.resource-page__header h1\s*\{[\s\S]*?color: #0c0d0e;[\s\S]*?font-size: 24px;[\s\S]*?font-weight: 500;[\s\S]*?line-height: normal;/,
  );
  assert.match(resourceStyles, /\.resource-grid\s*\{[\s\S]*?gap: 16px;/);
  assert.match(resourceStyles, /\.resource-card\s*\{[\s\S]*?height: 152px;[\s\S]*?border-radius: 16px;/);
  assert.match(resourceStyles, /\.resource-card\s*\{[\s\S]*?gap: 16px;[\s\S]*?padding: 18px 20px;/);
  assert.match(resourceStyles, /\.resource-card__identity-mark\s*\{[\s\S]*?width: 20px;[\s\S]*?height: 20px;[\s\S]*?border-radius: 50%;/);
  assert.match(resourceStyles, /\.resource-card__identity-mark\s*\{[\s\S]*?--resource-identity-glow[\s\S]*?--resource-identity-accent[\s\S]*?linear-gradient\(/);
  assert.match(resourceStyles, /\.resource-card__actions\s*\{[\s\S]*?opacity: 0;[\s\S]*?pointer-events: none;/);
  assert.match(resourceStyles, /\.resource-card__target\s*\{[\s\S]*?position: absolute;[\s\S]*?inset: 0;[\s\S]*?z-index: 1;/);
  assert.match(resourceStyles, /@media \(hover: none\), \(pointer: coarse\)[\s\S]*?\.resource-card__actions\s*\{[\s\S]*?opacity: 1;/);
});

test("shows browser-local drafts with edit and confirmed delete actions", () => {
  assert.match(pageSource, /drafts\?: WorkspaceAgentDraft\[\]/);
  assert.match(pageSource, /function draftToAgent\(item: WorkspaceAgentDraft\)/);
  assert.match(pageSource, /specification: "当前浏览器"/);
  assert.match(pageSource, /\? \[\.\.\.draftAgents, \.\.\.runtimeAgents\]/);
  assert.match(pageSource, /className="my-agent-draft-badge">草稿<\/span>/);
  assert.match(pageSource, /deploymentTask \? \([\s\S]*?className="my-agent-deploying-badge">部署中<\/span>/);
  assert.match(pageSource, /: `编辑草稿 \$\{agent\.name\}`/);
  assert.match(pageSource, /aria-label=\{`删除草稿 \$\{agent\.name\}`\}/);
  assert.match(pageSource, /title="删除草稿？"[\s\S]*?confirmLabel="删除草稿"/);
  assert.match(appSource, /<MyAgents[\s\S]*?drafts=\{savedAgentDrafts\}/);
  assert.match(appSource, /onDeleteDraft=\{\(item\) => deleteWorkspaceDrafts\(\[item\]\)\}/);
  assert.match(
    pageStyles,
    /\.my-agent-draft-badge\s*\{[\s\S]*?color: #dd6800;[\s\S]*?font-size: 12px;[\s\S]*?font-weight: 400;[\s\S]*?line-height: 18px;/,
  );
  assert.doesNotMatch(
    pageStyles.match(/\.my-agent-draft-badge\s*\{[\s\S]*?\n\}/)?.[0] ?? "",
    /background:|border:/,
  );
  assert.match(pageSource, /<ResourceCardAction[\s\S]*?tone="danger"[\s\S]*?删除/);
});

test("reopens running deployment progress from draft and Runtime cards", () => {
  assert.match(pageSource, /deploymentTasks\?: DeploymentTaskUpdate\[\]/);
  assert.match(pageSource, /draftDeploymentTaskIds\?: Readonly<Record<string, string>>/);
  assert.match(pageSource, /task\.status !== "running"/);
  assert.match(pageSource, /byDraftId\.set\(task\.draftId, task\)/);
  assert.match(pageSource, /activeDeploymentTasks\.byDraftId\.get\(agent\.draft\.id\)/);
  assert.match(pageSource, /draftDeploymentTaskIds\[agent\.draft\.id\]/);
  assert.match(pageSource, /activeDeploymentTasks\.byRuntimeId\.get\(runtimeId\)/);
  assert.match(pageSource, /className="my-agent-draft-badge">草稿<\/span>/);
  assert.match(pageSource, /deploymentTask \? "查看进度" : "编辑"/);
  assert.match(pageSource, /\? `查看 \$\{agent\.name\} 部署进度`[\s\S]*?: `查看 \$\{agent\.name\} Runtime 详情`/);
  assert.match(pageSource, /function runtimeDetailTargetForCard\(/);
  assert.match(pageSource, /const target = agent\.draft\.deploymentTarget;[\s\S]*?if \(!target\) return null/);
  assert.match(pageSource, /runtimeAgent\.runtime\?\.runtimeId === target\.runtimeId/);
  assert.match(pageSource, /if \(agent\.draft\) \{[\s\S]*?else onViewDetails\?\.\(agent\)/);
  assert.doesNotMatch(
    pageSource,
    /if \(agent\.draft\) \{[\s\S]*?else onEditDraft\?\.\(agent\.draft\)/,
  );
  assert.match(appSource, /const \[draftDeploymentTaskIds, setDraftDeploymentTaskIds\]/);
  assert.match(appSource, /\[editingDraftId\]: task\.id/);
  assert.match(appSource, /deploymentTasks=\{deploymentTasks\}/);
  assert.match(appSource, /onViewDeploymentTask=\{openDeploymentDetail\}/);
});

test("uses a responsive four-column card layout without an empty fixed-height gap", () => {
  assert.match(
    resourceStyles,
    /\.resource-grid\s*\{[\s\S]*?grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);[\s\S]*?align-items: start;[\s\S]*?gap: 16px;/,
  );
  assert.match(resourceStyles, /@media \(min-width: 1181px\) and \(max-width: 1599px\)[\s\S]*?grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/);
  assert.match(resourceStyles, /@media \(min-width: 721px\) and \(max-width: 1180px\)[\s\S]*?grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(resourceStyles, /@media \(max-width: 720px\)[\s\S]*?grid-template-columns: 1fr/);
  assert.match(
    resourceStyles,
    /\.resource-card\s*\{[\s\S]*?height: 152px;[\s\S]*?border: 1px solid rgba\(229, 230, 235, 0\.7\);[\s\S]*?background: #fff/,
  );
  assert.doesNotMatch(
    pageStyles,
    /\.my-agent-card-content\s*\{[^}]*box-shadow:/,
  );
  assert.doesNotMatch(pageStyles, /\.my-agent-card:hover \.my-agent-card-content/);
  assert.match(resourceStyles, /\.resource-card__description\s*\{[\s\S]*?-webkit-line-clamp: 2/);
  assert.match(resourceStyles, /\.resource-card__footer\s*\{[\s\S]*?height: 28px;[\s\S]*?justify-content: space-between/);
  assert.match(resourceStyles, /\.resource-card__action\.is-icon-only\s*\{[\s\S]*?width: 28px;[\s\S]*?border-radius: 50%/);
  assert.match(resourceStyles, /\.resource-card__actions\s*\{[\s\S]*?gap: 8px/);
  assert.match(resourceStyles, /\.resource-card:hover,[\s\S]*?box-shadow: 0 0 0 4px rgba\(229, 230, 235, 0\.6\)/);
});

test("aligns sandbox names with status and formats card time relatively", async () => {
  assert.match(resourceStyles, /\.resource-card__header\s*\{[\s\S]*?justify-content: space-between/);
  assert.match(pageStyles, /\.my-agent-session-id\s*\{/);
  assert.match(pageSource, /return formatRelativeTimeLabel\(value, nowMs\)/);
  const { outputText } = ts.transpileModule(relativeTimeSource, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
  const { formatRelativeTimeLabel } = await import(moduleUrl);
  const now = Date.parse("2026-08-11T03:00:00.000Z");
  assert.equal(formatRelativeTimeLabel("2026-08-11T02:59:40.000Z", now), "20 秒前");
  assert.equal(formatRelativeTimeLabel("2026-08-11T02:57:00.000Z", now), "3 分钟前");
  assert.equal(formatRelativeTimeLabel("2026-08-11T01:00:00.000Z", now), "2 小时前");
  assert.equal(formatRelativeTimeLabel("2026-08-07T03:00:00.000Z", now), "4 天前");
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
    /label: "剩余时间",[\s\S]*?agent\.sandbox\.persistent[\s\S]*?"永不过期"[\s\S]*?agent\.sandbox\.expireAt[\s\S]*?className: `my-agent-expiry/,
  );
  assert.doesNotMatch(
    pageSource,
    /<span className="my-agent-expiry"/,
  );
  assert.match(pageSource, /window\.setInterval\([\s\S]*?1_000/);
  assert.match(pageSource, /return \(\) => window\.clearInterval\(timer\)/);
  assert.match(pageStyles, /\.my-agent-expiry\.is-expiring dd\s*\{[\s\S]*?color: hsl\(38 78% 36%\)/);
});

test("metadata stays compact without expanding every card into Agent metadata", () => {
  assert.doesNotMatch(pageStyles, /\.my-agent-label/);
  assert.match(pageSource, /label: agent\.specificationLabel,[\s\S]*?hideLabel: true/);
  assert.match(pageSource, /label: "时间",[\s\S]*?hideLabel: true/);
  assert.doesNotMatch(pageSource, /label: "更新时间"/);
  assert.match(relativeTimeSource, /return `\$\{elapsedSeconds\} 秒前`/);
  assert.match(relativeTimeSource, /return `\$\{elapsedMinutes\} 分钟前`/);
  assert.match(relativeTimeSource, /return `\$\{elapsedHours\} 小时前`/);
  assert.match(relativeTimeSource, /return `\$\{elapsedDays\} 天前`/);
  assert.doesNotMatch(pageSource, /\$\{match\[1\]\}-\$\{match\[2\]\} 更新/);
  assert.match(resourceStyles, /\.resource-card__metadata dd\s*\{[\s\S]*?color: #7a7880/);
  assert.match(resourceStyles, /\.resource-card__metadata > div \+ div::before\s*\{[\s\S]*?height: 12px/);
  assert.doesNotMatch(pageSource, /getRuntimeAgentInfo/);
  assert.doesNotMatch(pageSource, /Promise\.all\([\s\S]*?page\.runtimes\.map/);
  assert.doesNotMatch(pageSource, /appName: info\.appName/);
});

test("loads Runtime pages by the selected ownership and region", () => {
  assert.match(pageSource, /getRuntimes/);
  assert.match(pageSource, /runtimeScope: RuntimeScope/);
  assert.match(pageSource, /studioRegion: string/);
  assert.match(pageSource, /const \[ownership, setOwnership\] = useState<RuntimeScope>/);
  assert.match(pageSource, /const \[region, setRegion\] = useState\(configuredRegion\)/);
  assert.match(pageSource, /function resolveAgentRegion\([\s\S]*?studioRegion\.trim\(\) \|\| defaultCloudRegion\(cloudProvider\)/);
  assert.doesNotMatch(pageSource, /label: "全部区域"/);
  assert.match(pageSource, /scope: runtimeScope,[\s\S]*?region,[\s\S]*?pageSize: RUNTIME_PAGE_SIZE/);
  assert.match(pageSource, /ariaLabel="创建人筛选"/);
  assert.match(pageSource, /id="my-agent-region-filter"[\s\S]*?ariaLabel="区域"[\s\S]*?onChange=\{selectRegion\}/);
  assert.match(pageSource, /cloudRegionOptions\(cloudProvider\)/);
  assert.match(pageSource, /id: runtime\.runtimeId/);
  assert.match(pageSource, /name: runtime\.name/);
  assert.match(pageSource, /description: runtime\.description\?\.trim\(\) \|\| "暂无描述"/);
  assert.match(pageSource, /specificationLabel: "创建人"/);
  assert.match(pageSource, /specification: formatResourceCreator\(runtime\.author\)/);
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
  assert.match(appSource, /<MyAgents[\s\S]*?studioRegion=\{agentsSource === "local" \? "cn-beijing" : studioRegion\}[\s\S]*?runtimeScope=\{access\.capabilities\.runtimeScope\}/);
  assert.match(appSource, /const grantedRuntimeScope = access\?\.capabilities\.runtimeScope \?\? "mine"/);
  assert.match(appSource, /const refreshAgentLibrary[\s\S]*?scope: grantedRuntimeScope/);
});

test("uses semantic fallbacks for missing resource sources and creators", async () => {
  const { outputText } = ts.transpileModule(resourceMetadataSource, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
  const { formatResourceCreator, formatResourceSource } = await import(moduleUrl);
  assert.equal(formatResourceSource(undefined), "未知来源");
  assert.equal(formatResourceSource(null), "未知来源");
  assert.equal(formatResourceSource("   "), "未知来源");
  assert.equal(formatResourceSource(" Alice "), "Alice");
  assert.equal(formatResourceCreator(undefined), "未知创建者");
  assert.equal(formatResourceCreator(null), "未知创建者");
  assert.equal(formatResourceCreator("   "), "未知创建者");
  assert.equal(formatResourceCreator(" Alice "), "Alice");
  assert.match(pageSource, /specification: formatResourceCreator\(session\.createdBy\)/);
});

test("uses authoritative Sandbox ownership and region metadata for shared filters", () => {
  assert.match(sandboxSource, /region: string;/);
  assert.match(sandboxSource, /isMine: boolean;/);
  assert.match(sandboxSource, /region: data\.region \?\? ""/);
  assert.match(sandboxSource, /isMine: data\.isMine === true/);
  assert.match(sandboxServerSource, /"region": session\.region/);
  assert.match(sandboxServerSource, /"isMine": bool\(owner_id and session\.created_by == owner_id\)/);
  assert.match(pageSource, /isMine: session\.isMine/);
  assert.match(pageSource, /region: session\.region/);
});

test("keeps ownership filtering in the toolbar without duplicating it on cards", () => {
  assert.match(pageSource, /isMine\?: boolean/);
  assert.match(pageSource, /isMine: runtime\.isMine/);
  assert.doesNotMatch(pageSource, /showOwnership=\{runtimeScope === "all"\}/);
  assert.doesNotMatch(pageSource, /className="runtime-owner-badge"/);
  assert.match(appSource, /canCreateRuntimeAgents=\{canCreateRuntimeAgents\}/);
  assert.match(appSource, /canCreatePersonalAgents=\{canCreatePersonalAgents\}/);
});

test("keeps Runtime title rows clear of redundant region badges", () => {
  assert.doesNotMatch(pageSource, /formatCloudRegion\(agent\.runtime\.region, cloudProvider\)/);
  assert.doesNotMatch(pageSource, /className="my-agent-region-badge"/);
  assert.doesNotMatch(pageStyles, /\.my-agent-region-badge\s*\{/);
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
  assert.match(resourceStyles, /@keyframes resource-card-enter/);
  assert.match(resourceStyles, /\.resource-card\s*\{[\s\S]*?animation: resource-card-enter/);
  assert.match(pageStyles, /\.my-agent-load-more\s*\{[\s\S]*?min-height: 54px/);
  assert.doesNotMatch(pageStyles, /\.my-agent-pagination/);
  assert.match(pageStyles, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?animation: none/);
});

test("keeps the page controls fixed while only the Agent results scroll", () => {
  assert.match(pageSource, /const resultsRef = useRef<HTMLElement>\(null\)/);
  assert.match(pageSource, /<ResourceResults[\s\S]*?className="my-agent-results"[\s\S]*?ref=\{resultsRef\}/);
  assert.match(resourceStyles, /\.resource-page\s*\{[\s\S]*?overflow: hidden/);
  assert.match(
    resourceStyles,
    /\.resource-page\s*\{[\s\S]*?padding: 80px 80px 0;/,
  );
  assert.match(
    resourceStyles,
    /\.resource-results\s*\{[\s\S]*?flex: 1;[\s\S]*?min-height: 0;[\s\S]*?overflow-y: auto/,
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

test("defers conversation and session requests while update preparation stays bounded", () => {
  assert.match(
    appSource,
    /if \(authStatus !== "authenticated"\) return;[\s\S]*?if \(agentsSource === "cloud"\) \{[\s\S]*?return;[\s\S]*?listApps\(\)/,
  );
  assert.match(
    appSource,
    /authStatus !== "authenticated" \|\|[\s\S]*?myAgents \|\|[\s\S]*?agentDetailTarget \|\|[\s\S]*?!studioToolRuntime[\s\S]*?getRuntimeStudioToolCapabilities/,
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
  assert.match(pageSource, /onActivate=\{cardTargetEnabled \? openCard : undefined\}/);
  assert.match(pageSource, /else onViewDetails\?\.\(agent\)/);
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
  assert.match(pageSource, /label: "Codex"/);
  assert.match(pageSource, /label: "DeepSeek"/);
  assert.match(pageSource, /label: "OpenClaw"/);
  assert.match(pageSource, /label: "Hermes"/);
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
  assert.match(pageSource, /: \(\) => onCreateSandboxAgent\(activeType\)/);
});

test("uses the official EmptyMessage when creation is unavailable", () => {
  assert.match(
    pageSource,
    /from "@openai\/apps-sdk-ui\/components\/EmptyMessage"/,
  );
  assert.match(pageSource, /from "@openai\/apps-sdk-ui\/components\/Icon"/);
  assert.match(
    pageSource,
    /<EmptyMessage\.Title>暂无通用智能体<\/EmptyMessage\.Title>/,
  );
  assert.doesNotMatch(pageSource, /<EmptyMessage\.ActionRow>/);
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
    pageSource.indexOf(": showEmpty && !createAgent ?"),
  );
  assert.doesNotMatch(errorBranch, /<EmptyMessage/);
  assert.match(errorBranch, /fetchSandboxAgents\(activeType\)/);
  assert.match(pageSource, /formatRequestError\(cause, "加载通用智能体", "GET \/web\/runtimes"\)/);
  assert.match(pageSource, /formatRequestError\([\s\S]*?`加载 \$\{AGENT_TYPES\.find/);
  assert.match(pageSource, /`GET \/web\/\$\{type === "codex" \? "sandbox" : type\}\/sessions`/);
  assert.match(pageStyles, /\.my-agent-empty p\s*\{[\s\S]*?white-space: pre-wrap;[\s\S]*?overflow-wrap: anywhere;/);
});

test("retries the Runtime list once after a timeout without leaving the loading state", () => {
  assert.match(runtimeDiscoverySource, /const RUNTIME_LIST_RETRY_DELAY_MS = 5_000/);
  assert.match(
    runtimeDiscoverySource,
    /function isTimeoutError\(error: unknown\)[\s\S]*?error instanceof Error && error\.name === "TimeoutError"/,
  );
  assert.match(
    runtimeDiscoverySource,
    /async function getRuntimesWithTimeoutRetry[\s\S]*?await request\(options\)[\s\S]*?if \(!shouldRetryRuntimeList\(error\)\) throw error;[\s\S]*?RUNTIME_LIST_RETRY_DELAY_MS[\s\S]*?return request\(options\)/,
  );
  assert.match(pageSource, /request = getRuntimesWithTimeoutRetry\(\{/);
  assert.match(
    pageSource,
    /setLoadingRuntimes\(true\)[\s\S]*?loadRuntimeAgents[\s\S]*?\.finally\(\(\) => \{[\s\S]*?setLoadingRuntimes\(false\)/,
  );
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
  assert.match(pageSource, /<span className="sr-only">\{wakeable \? "唤醒中" : "连接中"\}<\/span>/);
  assert.doesNotMatch(pageSource, /ConnectIcon/);
  assert.match(pageSource, /const actionable = Boolean\([\s\S]*?agent\.runtime \|\| sandboxStatus === "ready" \|\| sandboxStatus === "wakeable"/);
  assert.match(
    pageSource,
    /disabled=\{!actionable \|\| checkingCompatibility \|\| incompatible \|\| connecting \|\| connected\}/,
  );
  assert.match(appSource, /connectedRuntimeId=\{connectedRuntimeId\}/);
  assert.match(pageStyles, /\.my-agent-loading-mark[\s\S]*?border-right-color: transparent/);
  assert.match(
    pageStyles,
    /\.resource-card__action\.my-agent-use\.is-connected,[\s\S]*?background: transparent[\s\S]*?color: hsl\(142 62% 30%\)/,
  );
  assert.match(
    pageSource,
    /className=\{connecting \? "my-agent-card is-connecting" : "my-agent-card"\}/,
  );
  assert.match(
    pageStyles,
    /\.my-agent-card\.is-connecting \.resource-card__actions\s*\{[\s\S]*?opacity: 1;[\s\S]*?pointer-events: auto;/,
  );
});

test("checks Runtime chat compatibility before enabling the connect action", () => {
  assert.match(pageSource, /probeRuntimeApps/);
  assert.match(runtimeDiscoverySource, /const RUNTIME_COMPATIBILITY_CONCURRENCY = 4/);
  assert.match(pageSource, /const RUNTIME_COMPATIBILITY_TIMEOUT_MS = 7_000/);
  assert.match(pageSource, /const RUNTIME_COMPATIBILITY_RETRY_TIMEOUT_MS = 20_000/);
  assert.match(
    pageSource,
    /type RuntimeCompatibilityStatus = "checking" \| "compatible" \| "unsupported" \| "error"/,
  );
  assert.match(pageSource, /runRuntimeCompatibilityChecks/);
  assert.match(pageSource, /signal: controller\.signal/);
  assert.match(pageSource, /const checkingCompatibility = compatibility\?\.status === "checking"/);
  assert.match(pageSource, /const incompatible = compatibility\?\.status === "unsupported"/);
  assert.match(pageSource, /const compatibilityFailed = compatibility\?\.status === "error"/);
  assert.match(pageSource, /disabled=\{!actionable \|\| checkingCompatibility \|\| incompatible \|\| connecting \|\| connected\}/);
  assert.match(pageSource, />检测中<\/span>/);
  assert.match(pageSource, /onRetryCompatibility\?\.\(agent\)/);
  assert.match(pageSource, /<Button[\s\S]*?color="primary"[\s\S]*?<ArrowRotateCw \/>[\s\S]*?重试[\s\S]*?<\/Button>/);
  assert.match(pageSource, /import \{ Badge \} from "@openai\/apps-sdk-ui\/components\/Badge"/);
  assert.match(pageSource, /import \{ Tooltip \} from "@openai\/apps-sdk-ui\/components\/Tooltip"/);
  assert.match(pageSource, /content=\{compatibility\?\.message\}/);
  assert.match(pageSource, /contentClassName="my-agent-compatibility-tooltip"/);
  assert.match(pageSource, /color="warning"[\s\S]*?>[\s\S]*?不支持对话[\s\S]*?<\/Badge>/);
  assert.match(pageSource, /color="danger"[\s\S]*?>[\s\S]*?检测失败[\s\S]*?<\/Badge>/);
});

test("prepares Runtime update capability before opening details without unbounded work", () => {
  assert.match(pageSource, /prefetchRuntimeUpdateCapability/);
  assert.match(pageSource, /invalidateRuntimeUpdateCapabilityCache/);
  assert.match(pageSource, /const UPDATE_CAPABILITY_PREFETCH_LIMIT = 6/);
  assert.match(pageSource, /const UPDATE_CAPABILITY_PREFETCH_CONCURRENCY = 2/);
  assert.match(
    pageSource,
    /visibleAgents[\s\S]*?\.filter\(\(agent\) => Boolean\(agent\.runtime\)\)[\s\S]*?\.slice\(0, UPDATE_CAPABILITY_PREFETCH_LIMIT\)/,
  );
  assert.match(pageSource, /for \(let index = 0; index < UPDATE_CAPABILITY_PREFETCH_CONCURRENCY; index \+= 1\)/);
  assert.match(pageSource, /if \(cancelled\) return/);
  assert.match(pageSource, /onPointerEnter=\{\(\) => onPrepareUpdate\?\.\(agent\)\}/);
  assert.match(pageSource, /onFocusCapture=\{\(\) => onPrepareUpdate\?\.\(agent\)\}/);
  assert.match(pageSource, /canUpdate: boolean/);
  assert.match(appSource, /<MyAgents[\s\S]*?canUpdate=\{canCreateRuntimeAgents \|\| canManageAgents\}/);
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
