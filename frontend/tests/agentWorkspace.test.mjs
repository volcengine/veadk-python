import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const workspaceSource = readFileSync(
  new URL("../src/ui/AgentWorkspace.tsx", import.meta.url),
  "utf8",
);
const workspaceStyles = readFileSync(
  new URL("../src/ui/AgentWorkspace.css", import.meta.url),
  "utf8",
);
const appStyles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const studioConfirmSource = readFileSync(
  new URL("../src/ui/StudioConfirmDialog.tsx", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const connectionsSource = readFileSync(
  new URL("../src/adk/connections.ts", import.meta.url),
  "utf8",
);
const skillSourcePickerSource = readFileSync(
  new URL("../src/ui/SkillSourcePicker.tsx", import.meta.url),
  "utf8",
);
const enUiCatalog = JSON.parse(
  readFileSync(new URL("../src/i18n/resources/en-US/ui.json", import.meta.url), "utf8"),
);
const zhUiCatalog = JSON.parse(
  readFileSync(new URL("../src/i18n/resources/zh-CN/ui.json", import.meta.url), "utf8"),
);

test("Agent navigation uses the card page and keeps only detail workspace routes", () => {
  assert.match(appSource, /import \{[\s\S]*?AgentWorkspace[\s\S]*?\} from "\.\/ui\/AgentWorkspace"/);
  assert.match(
    appSource,
    /<AgentWorkspace[\s\S]*?agents=\{detailAgentEntry \? \[detailAgentEntry\] : orderedWorkspaceAgentEntries\}/,
  );
  assert.doesNotMatch(appSource, /<Navbar\b/);
  assert.doesNotMatch(appSource, /showManageAgents\s*\?\s*"智能体"/);
  assert.match(appSource, /myAgents && !showManageAgents \? \([\s\S]*?<MyAgents/);
  assert.match(
    appSource,
    /const showManageAgents = manageAgents && Boolean\([\s\S]*?agentDetailTarget \|\| focusedDeploymentTaskId \|\| focusedWorkspaceAgentId/,
  );
});

test("workspace drafts stay wired to custom Agent creation", () => {
  assert.match(appSource, /loadWorkspaceDrafts,[\s\S]*?from "\.\/create\/agentDraftStorage"/);
  assert.match(appSource, /saveWorkspaceDraft/);
  assert.match(appSource, /DRAFT_AUTOSAVE_DELAY_MS = 600/);
  assert.match(appSource, /window\.addEventListener\("pagehide", flushPendingWorkspaceDraft\)/);
  assert.match(appSource, /draftStorageError/);
  assert.match(appSource, /onDraftChange=\{\(draft, dirty\) =>/);
  assert.match(appSource, /deploymentTarget=\{runtimeUpdateTarget \?\? undefined\}/);
  assert.match(appSource, /workspaceDraftId=\{editingDraftId \|\| undefined\}/);
  assert.match(
    appSource,
    /if \(dirty\)[\s\S]*?saveWorkspaceDraft[\s\S]*?else[\s\S]*?restoreWorkspaceDraftBaseline\(editingDraftId\)/,
  );
  assert.match(
    appSource,
    /onDiscard=\{editingDraftId \? \(\) => \{[\s\S]*?restoreWorkspaceDraftBaseline\(editingDraftId\)[\s\S]*?setFocusedWorkspaceAgentId\(appName\)/,
  );
});

test("every continue-edit entry routes persisted quick drafts back to quick creation", () => {
  assert.match(
    appSource,
    /const activeDraft = nextDrafts\.find[\s\S]*?setImportedDraft\(activeDraft\.draft\);[\s\S]*?setCustomCreationSurface\([\s\S]*?workspaceAgentCreationMode\(activeDraft\) === "quick"[\s\S]*?\? "vulcan"[\s\S]*?: "traditional"/,
  );

  const editHandlers = [
    ...appSource.matchAll(/onEditDraft=\{\(item\) => \{([\s\S]*?)\n\s*\}\}/g),
  ];
  assert.ok(editHandlers.length >= 2);
  for (const [, handler] of editHandlers) {
    assert.match(handler, /setImportedDraft\(item\.draft\)/);
    assert.match(
      handler,
      /setCustomCreationSurface\([\s\S]*?workspaceAgentCreationMode\(item\) === "quick"[\s\S]*?\? "vulcan"[\s\S]*?: "traditional"/,
    );
    assert.match(handler, /setRuntimeUpdateTarget\(item\.deploymentTarget \?\? null\)/);
  }
});

test("running deployments match drafts by stable draft id before names", () => {
  assert.match(
    workspaceSource,
    /task\.draftId === selectedDraft\.id[\s\S]*?task\.agentDraft\?\.name === selectedDraft\.draft\.name/,
  );
});

test("legacy workspace library chrome is unreachable from App", () => {
  assert.match(workspaceStyles, /\.aw-view-tabs/);
  assert.match(workspaceStyles, /\.aw-view-tabs button\s*\{[\s\S]*?font-size:\s*14px;/);
  assert.match(workspaceStyles, /\.aw-workspace-frame/);
  assert.match(workspaceStyles, /\.aw-sidebar/);
  assert.doesNotMatch(workspaceSource, /只读预览，可拖动与缩放/);
  assert.match(workspaceStyles, /\.aw-canvas\s*\{[\s\S]*?height:\s*220px;/);
  assert.doesNotMatch(workspaceStyles, /\.aw-canvas-card\s*\{[^}]*min-height:\s*330px/);
  assert.match(appSource, /<AgentWorkspace[\s\S]*?detailOnly\s+[\s\S]*?onRetryAgents=/);
});

test("focused agent details can render without the workspace tabs or list sidebar", () => {
  assert.match(workspaceSource, /detailOnly\?: boolean/);
  assert.match(workspaceSource, /aw-root\$\{detailOnly \? " is-detail-only" : ""\}/);
  assert.match(workspaceStyles, /\.aw-root\.is-detail-only \.aw-view-tabs,[\s\S]*?\.aw-root\.is-detail-only \.aw-sidebar[\s\S]*?display: none/);
  assert.match(workspaceStyles, /\.aw-root\.is-detail-only \.aw-workspace\s*\{[\s\S]*?grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(
    appSource,
    /focusedAgentId=\{detailAgentEntry\?\.id \?\? focusedWorkspaceAgentId\}[\s\S]*?detailOnly/,
  );
  assert.match(appSource, /runtimeApp: detailConnection\?\.apps\[0\]/);
  assert.match(workspaceSource, /const knownApp = selectedAgent\?\.runtimeApp \?\? ""[\s\S]*?getRuntimeAgentInfo\([\s\S]*?knownApp/);
  assert.match(clientSource, /loadDraft = true/);
  assert.match(clientSource, /return fetchAgentInfo\(app, ep, false\)/);
});

test("focused agent details use the shared resource detail header", () => {
  assert.match(workspaceSource, /onBack\?: \(\) => void/);
  assert.match(
    workspaceSource,
    /<ResourceDetailLayout[\s\S]*?title=\{selectedName\}[\s\S]*?identitySeed=\{selectedName\}[\s\S]*?backLabel=\{t\("agentWorkspace\.backToAgentList"\)\}[\s\S]*?onBack=\{detailOnly \? onBack : undefined\}/,
  );
  assert.doesNotMatch(workspaceSource, /import \{ PageBackButton \}/);
  assert.match(appSource, /<AgentWorkspace[\s\S]*?detailOnly[\s\S]*?onBack=\{closeAgentDetailPage\}/);
});

test("agent detail navigation delegates responsive layout to the shared resource shell", () => {
  const detailLayoutStart = workspaceSource.indexOf("<ResourceDetailLayout");
  const detailLayoutContractEnd = workspaceSource.indexOf("activeSectionKey={section}", detailLayoutStart);
  assert.ok(detailLayoutStart >= 0 && detailLayoutContractEnd > detailLayoutStart);
  const detailLayoutContract = workspaceSource.slice(detailLayoutStart, detailLayoutContractEnd);
  assert.match(detailLayoutContract, /sections=\{visibleAgentSections\.map/);
  assert.doesNotMatch(detailLayoutContract, /className="aw-agent-tabs"/);
  assert.match(workspaceSource, /activeSectionKey=\{section\}/);
  assert.match(workspaceSource, /onSectionChange=\{setSection\}/);
  assert.match(
    workspaceStyles,
    /@media \(max-width: 720px\)[\s\S]*?\.aw-version-row\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\)/,
  );
  assert.match(
    workspaceStyles,
    /@media \(max-width: 720px\)[\s\S]*?\.aw-version-row p\s*\{[\s\S]*?overflow-wrap:\s*anywhere/,
  );
});

test("runtime detail failures remain visible and retryable", () => {
  assert.match(workspaceSource, /const \[detailAgentInfoError, setDetailAgentInfoError\] = useState\(""\)/);
  assert.match(workspaceSource, /const \[detailAgentInfoUnsupported, setDetailAgentInfoUnsupported\] = useState\(false\)/);
  assert.match(workspaceSource, /const \[runtimeDetailError, setRuntimeDetailError\] = useState\(""\)/);
  assert.match(
    workspaceSource,
    /getRuntimeAgentInfo[\s\S]*?\.catch\(\(error: unknown\)[\s\S]*?setDetailAgentInfoError/,
  );
  assert.match(
    workspaceSource,
    /getRuntimeDetail[\s\S]*?\.catch\(\(error: unknown\)[\s\S]*?setRuntimeDetailError/,
  );
  assert.match(workspaceSource, /title=\{t\("agentWorkspace\.partialInfoUnavailable"\)\}/);
  assert.match(workspaceSource, /description=\{t\("agentWorkspace\.upgradeRuntimeForDetails"\)\}/);
  assert.match(workspaceSource, /title=\{t\("agentWorkspace\.detailLoadFailed"\)\}/);
  assert.doesNotMatch(workspaceSource, /className="aw-usage-state aw-detail-fetch-error is-error"/);
  assert.doesNotMatch(workspaceSource, /<DeploymentErrorMessage/);
  assert.match(workspaceSource, /setDetailReloadToken\(\(value\) => value \+ 1\)/);
});

test("agent details show capability badges and deployment state before the flow", () => {
  assert.match(workspaceSource, /const toolNames = useMemo/);
  assert.match(workspaceSource, /const skillNames = useMemo/);
  assert.match(workspaceSource, /<dt>\{t\("agentSelector\.tools"\)\}<\/dt>[\s\S]*?className="aw-fact-badges"[\s\S]*?toolNames\.map/);
  assert.match(workspaceSource, /<dt>\{t\("agentSelector\.skills"\)\}<\/dt>[\s\S]*?className="aw-fact-badges"[\s\S]*?skillNames\.map/);
  assert.match(workspaceStyles, /\.aw-fact-badges span\s*\{[\s\S]*?border-radius:\s*999px;/);
  assert.ok(
    workspaceSource.indexOf('t("agentWorkspace.deploymentConfig")') < workspaceSource.indexOf('t("agentWorkspace.executionFlow")'),
  );
  assert.ok(
    workspaceSource.indexOf('t("agentWorkspace.executionFlow")') < workspaceSource.indexOf('t("agentWorkspace.details")'),
  );
  assert.ok(
    workspaceSource.indexOf('t("agentWorkspace.details")') < workspaceSource.indexOf('t("agentWorkspace.selectedOptimizations")'),
  );
  assert.match(
    workspaceSource,
    /const publishedHarnessSidecar =[\s\S]*?selectedAgentInfo\?\.draft\?\.harnessSidecar \?\?[\s\S]*?harnessIntentFromRuntimeEnvs\(runtimeDetail\?\.envs\)/,
  );
  assert.match(workspaceSource, /aria-label=\{t\("agentWorkspace\.selectedOptimizations"\)\}/);
  assert.doesNotMatch(workspaceSource, /<h3>Harness Sidecar<\/h3>/);
  assert.match(workspaceSource, /<dt>\{t\("agentWorkspace\.configurationStatus"\)\}<\/dt>[\s\S]*?t\("skillCenter\.status\.enabled"\)[\s\S]*?t\("skillCenter\.status\.inactive"\)[\s\S]*?t\("agentWorkspace\.notRecorded"\)/);
  assert.match(workspaceSource, /<dt>\{t\("agentWorkspace\.optimizationProfile"\)\}<\/dt>[\s\S]*?harnessSidecarProfileLabel/);
  assert.match(workspaceSource, /<dt>\{t\("agentWorkspace\.selectedOptimizations"\)\}<\/dt>[\s\S]*?publishedHarnessOptimizations\.map/);
  assert.match(workspaceSource, /t\("agentWorkspace\.selectedOptimizationsDescription"\)/);
  assert.doesNotMatch(workspaceSource, /发布时选择的智能体优化项，只读展示。/);
  assert.match(workspaceSource, /status\.toLowerCase\(\) === "ready"[\s\S]*?className="aw-status-dot"/);
  assert.match(workspaceStyles, /\.aw-readonly-config dd\.is-ready\s*\{[\s\S]*?color:\s*hsl\(142 62% 30%\)/);
  assert.match(workspaceSource, /const executionFlowKey = selectedAgentInfo/);
  assert.match(workspaceSource, /const draftFlowKey = useMemo\(\(\) => canvasDraftKey\(draft\), \[draft\]\)/);
  assert.match(workspaceSource, /const displayCurrentVersion =[\s\S]*?selectedAgent\?\.currentVersion \?\? runtimeDetail\?\.currentVersion \?\? null/);
  assert.match(workspaceSource, /const runtimeVersionKey =[\s\S]*?displayCurrentVersion \?\? selectedPendingTask\?\.startedAt/);
  assert.match(workspaceSource, /className="aw-agent-meta">v\{displayCurrentVersion\}<\/span>/);
  assert.match(workspaceSource, /\? `v\$\{displayCurrentVersion\}`[\s\S]*?: t\("agentWorkspace\.notAvailable"\)/);
  assert.match(
    workspaceSource,
    /className="aw-canvas"[\s\S]*?<AgentBuildCanvas[\s\S]*?key=\{executionFlowKey\}/,
  );
  assert.doesNotMatch(workspaceSource, /loadingExecutionFlow/);
  assert.match(
    workspaceSource,
    /`runtime:\$\{selectedAgent\?\.runtimeId \?\? selectedAgentInfo\.name\}:v\$\{runtimeVersionKey\}:\$\{draftFlowKey\}`/,
  );
  assert.match(
    workspaceSource,
    /selectedAgent\?\.currentVersion,[\s\S]*?selectedAgent\?\.region,[\s\S]*?selectedAgent\?\.runtimeId/,
  );
  assert.match(workspaceStyles, /\.aw-canvas-loading\s*\{[\s\S]*?align-items:\s*center;/);
});

test("agent details expose detected integration methods without inventing unavailable endpoints", () => {
  assert.match(
    workspaceSource,
    /type AgentSection = "basic" \| "usage" \| "evaluations" \| "optimizations" \| "integrations" \| "versions"/,
  );
  assert.match(
    workspaceSource,
    /const AGENT_SECTIONS: AgentSection\[\] = \[[\s\S]*?"basic",[\s\S]*?"usage",[\s\S]*?"evaluations",[\s\S]*?"optimizations",[\s\S]*?"integrations",[\s\S]*?"versions",[\s\S]*?\]/,
  );
  assert.match(workspaceSource, /role="tablist"/);
  assert.match(workspaceSource, /role="tab"/);
  assert.match(workspaceSource, /role="tabpanel"/);
  assert.match(workspaceSource, /section !== "integrations"/);
  assert.match(workspaceSource, /probeRuntimeApps/);
  assert.match(workspaceSource, /probeRuntimeA2a/);
  assert.match(workspaceSource, /type IntegrationProtocol = "api-server" \| "a2a"/);
  assert.match(workspaceSource, /aria-label=\{t\("agentWorkspace\.integrationProtocol"\)\}/);
  assert.match(workspaceSource, /role="tab"/);
  assert.match(workspaceSource, /aria-controls=\{`integration-\$\{protocol\.id\}-panel`\}/);
  assert.match(workspaceSource, /setIntegrationProtocol/);
  assert.match(workspaceSource, /API Server/);
  assert.match(workspaceSource, /A2A/);
  assert.match(workspaceSource, /\/list-apps/);
  assert.match(workspaceSource, /\/run_sse/);
  assert.match(workspaceSource, /\.well-known\/agent-card\.json/);
  assert.match(workspaceSource, /message\/send/);
  assert.match(workspaceSource, /function apiServerPythonExample/);
  assert.match(workspaceSource, /function a2aPythonExample/);
  assert.match(workspaceSource, /function normalizeRuntimeA2aEndpoint/);
  assert.match(workspaceSource, /\["localhost", "127\.0\.0\.1", "::1"\]/);
  assert.match(workspaceSource, /agentUrl\.port = publicUrl\.port/);
  assert.match(workspaceSource, /const a2aEndpoint = normalizeRuntimeA2aEndpoint/);
  assert.match(workspaceSource, /<Markdown/);
  assert.match(workspaceSource, /<API_KEY>/);
  assert.match(workspaceSource, /revealRuntimeApiKey/);
  assert.match(workspaceSource, /aria-label=\{visible \? t\("agentWorkspace\.hideApiKey"\) : t\("agentWorkspace\.showApiKey"\)\}/);
  assert.match(workspaceSource, /visible && value \? value : "\*\*\*\*"/);
  assert.match(workspaceSource, /t\("agentWorkspace\.notAvailable"\)/);
  assert.match(
    workspaceSource,
    /section === "integrations" && integrationLoading[\s\S]*?className="aw-detail-loading"/,
  );
  assert.doesNotMatch(workspaceSource, /className="aw-integration-loading"/);
  assert.doesNotMatch(workspaceSource, /className=\{available \? "is-available" : ""\}/);
  assert.match(clientSource, /export interface RuntimeA2aIntegration/);
  assert.match(clientSource, /export async function probeRuntimeA2a/);
  assert.match(clientSource, /export async function revealRuntimeApiKey/);
  assert.match(clientSource, /method: "POST"/);
  assert.match(clientSource, /cache: "no-store"/);
  assert.match(clientSource, /\.well-known\/agent-card\.json/);
  assert.match(clientSource, /endpoint: string/);
  assert.match(clientSource, /authType: "none" \| "key_auth" \| "custom_jwt" \| "unknown"/);
  assert.match(workspaceStyles, /\.aw-integration-protocol-tabs/);
  assert.match(workspaceStyles, /\.aw-integration-protocol-slider/);
  assert.match(
    workspaceStyles,
    /\.aw-integration-protocol-tabs\s*\{[\s\S]*?width:\s*min\(240px, 100%\);[\s\S]*?height:\s*36px;/,
  );
  assert.match(
    workspaceStyles,
    /\.aw-integration-protocol-tabs button\s*\{[\s\S]*?min-height:\s*28px;[\s\S]*?font-size:\s*12px;/,
  );
  assert.doesNotMatch(workspaceStyles, /\.aw-integration-panel header > span\.is-available/);
  assert.match(workspaceStyles, /\.aw-integration-secret-toggle/);
  assert.match(workspaceStyles, /\.aw-integration-example/);
  assert.match(
    workspaceStyles,
    /\.aw-integration-panel\.has-example\s*\{[\s\S]*?display:\s*flex;[\s\S]*?flex-direction:\s*column;/,
  );
  const integrationPanelLayout = workspaceStyles.match(
    /\.aw-integration-panel\.has-example\s*\{([^}]*)\}/,
  )?.[1] ?? "";
  assert.doesNotMatch(integrationPanelLayout, /grid-template-columns:/);
  assert.match(workspaceStyles, /prefers-reduced-motion:\s*reduce/);
});

test("runtime-backed Agent details load and paginate usage without stale responses", () => {
  assert.match(clientSource, /agentUsage: boolean/);
  assert.match(clientSource, /agentUsage: false/);
  assert.match(clientSource, /export interface AgentUsageUser/);
  assert.match(clientSource, /export interface AgentUsageResponse/);
  assert.match(clientSource, /export async function getAgentUsage/);
  assert.match(
    clientSource,
    /new URLSearchParams\(\{[\s\S]*?runtimeId,[\s\S]*?region,[\s\S]*?appName,[\s\S]*?page: String\(page\),[\s\S]*?pageSize: String\(pageSize\)/,
  );
  assert.match(clientSource, /`\/web\/agent-usage\?\$\{params\.toString\(\)\}`/);
  assert.match(clientSource, /httpErrorMessage\(res, adkT\("client\.loadAgentUsageFailed"\)\)/);
  assert.match(clientSource, /adkT\("client\.agentUsageNonJson"/);
  assert.match(clientSource, /Content-Type/);
  assert.match(clientSource, /adkT\("client\.checkStudioGateway"\)/);

  assert.match(
    workspaceSource,
    /canViewUsage && selectedAgent\?\.runtimeId\s*\? AGENT_SECTIONS\s*:\s*AGENT_SECTIONS\.filter\(\(item\) => item !== "usage"\)/,
  );
  assert.match(workspaceSource, /canViewUsage\?: boolean/);
  assert.match(workspaceSource, /section === "usage" && !canViewUsage[\s\S]*?setSection\("basic"\)/);
  assert.match(workspaceSource, /section !== "usage" \|\| !runtimeId/);
  assert.match(
    workspaceSource,
    /getAgentUsage\(\{[\s\S]*?page: agentUsagePage,[\s\S]*?pageSize: AGENT_USAGE_PAGE_SIZE,[\s\S]*?signal: controller\.signal/,
  );
  assert.match(workspaceSource, /const requestId = agentUsageRequestRef\.current \+ 1/);
  assert.match(workspaceSource, /requestId !== agentUsageRequestRef\.current/);
  assert.match(workspaceSource, /controller\.abort\(\)/);
  assert.match(workspaceSource, /response\.runtimeId !== runtimeId/);
  assert.match(workspaceSource, /response\.appName !== appName/);

  assert.match(workspaceSource, /<h3>\{t\("agentWorkspace\.usageOverview"\)\}<\/h3>/);
  assert.match(workspaceSource, /<dt>\{t\("agentWorkspace\.totalCalls"\)\}<\/dt>/);
  assert.match(workspaceSource, /<dt>\{t\("agentWorkspace\.userCount"\)\}<\/dt>/);
  assert.match(workspaceSource, /<th scope="col">\{t\("agentWorkspace\.user"\)\}<\/th>/);
  assert.match(workspaceSource, /<th scope="col">\{t\("agentWorkspace\.callCount"\)\}<\/th>/);
  assert.match(workspaceSource, /<th scope="col">\{t\("agentWorkspace\.lastUsed"\)\}<\/th>/);
  assert.match(workspaceSource, /t\("agentWorkspace\.loadingUsage"\)/);
  assert.match(workspaceSource, /t\("agentWorkspace\.noUsage"\)/);
  assert.match(workspaceSource, /className="aw-usage-state is-error" role="alert"/);
  assert.match(workspaceSource, /setAgentUsageReloadToken/);
  assert.match(workspaceSource, /aria-label=\{t\("agentWorkspace\.usagePagination"\)\}/);
  assert.match(workspaceSource, /setAgentUsagePage\(\(page\) => Math\.max\(1, page - 1\)\)/);
  assert.match(workspaceSource, /setAgentUsagePage\(\(page\) => page \+ 1\)/);
  assert.match(workspaceStyles, /\.aw-usage-summary/);
  assert.match(
    workspaceStyles,
    /\.aw-usage-table-wrap\s*\{[\s\S]*?overflow-x:\s*auto/,
  );
  assert.match(workspaceStyles, /\.aw-usage-state\.is-error/);
  assert.match(workspaceStyles, /\.aw-usage-pagination button:disabled/);
});

test("agent details show GitHub delivery versions and rollback actions", () => {
  assert.match(clientSource, /export interface GithubDeliveryVersion/);
  assert.match(clientSource, /export async function getGithubDeliveryVersions/);
  assert.match(clientSource, /export async function createGithubDeliveryRollbackPr/);
  assert.match(workspaceSource, /getGithubDeliveryVersions/);
  assert.match(workspaceSource, /createGithubDeliveryRollbackPr/);
  assert.match(workspaceSource, /const \[githubVersions, setGithubVersions\]/);
  assert.match(workspaceSource, /section === "versions"/);
  assert.match(workspaceSource, /t\("agentWorkspace\.githubVersions"\)/);
  assert.match(workspaceSource, /t\("agentWorkspace\.sourceMergedRuntimeStill"\)/);
  assert.match(workspaceSource, /t\("agentWorkspace\.prLink"\)/);
  assert.match(workspaceSource, /t\("agentWorkspace\.author"\)/);
  assert.match(workspaceSource, /t\("agentWorkspace\.publishStatus"\)/);
  assert.match(workspaceSource, /t\("agentWorkspace\.rollbackEvent"\)/);
  assert.match(workspaceSource, /t\("agentWorkspace\.rollbackToVersion"\)/);
  assert.match(workspaceSource, /t\("agentWorkspace\.currentVersionOnly"\)/);
  assert.match(workspaceStyles, /\.aw-version-list/);
  assert.match(workspaceStyles, /\.aw-version-actions/);
});

test("workspace uses cached runtime data and prefetches likely next views", () => {
  assert.match(clientSource, /const RUNTIME_METADATA_CACHE_TTL_MS = 5 \* 60 \* 1000/);
  assert.match(clientSource, /const FEEDBACK_CASES_CACHE_TTL_MS = 60 \* 1000/);
  assert.match(clientSource, /export function getCachedRuntimeAgentInfo/);
  assert.match(clientSource, /export function getCachedRuntimeDetail/);
  assert.match(clientSource, /export function getCachedAgentFeedbackCases/);
  assert.match(clientSource, /export function prefetchRuntimeAgentInfo/);
  assert.match(clientSource, /export function prefetchRuntimeDetail/);
  assert.match(clientSource, /export function getCachedRuntimeUpdateCapability/);
  assert.match(clientSource, /export function prefetchRuntimeUpdateCapability/);
  assert.match(clientSource, /export function invalidateRuntimeUpdateCapabilityCache/);
  assert.match(clientSource, /export function prefetchAgentFeedbackCases/);
  assert.match(clientSource, /export function refreshAgentFeedbackCases/);
  assert.match(clientSource, /export function upsertCachedAgentFeedbackCase/);
  assert.match(clientSource, /const withoutCurrent = value\.items\.filter/);
  assert.match(clientSource, /sets: feedbackSetsWithCounts\(value\.sets, items\)/);
  assert.match(clientSource, /getAgentFeedbackCases\(args, \{ force: true \}\)/);
  assert.match(workspaceSource, /getCachedRuntimeAgentInfo\(runtimeId, region, knownApp\)/);
  assert.match(workspaceSource, /getRuntimeAgentInfo\([\s\S]*?\{ force: true \}/);
  assert.match(workspaceSource, /getCachedRuntimeDetail\(runtimeId, region\)/);
  assert.match(workspaceSource, /getRuntimeDetail\([\s\S]*?\{ force: true \}/);
  assert.match(workspaceSource, /getCachedAgentFeedbackCases\(\{/);
  assert.match(workspaceSource, /getAgentFeedbackCases\(\{[\s\S]*?\}, \{ force: true \}\)/);
  assert.match(workspaceSource, /item\.id !== previewCase\.id/);
  assert.match(workspaceSource, /item\.messageId !== previewCase\.messageId/);
  assert.match(workspaceSource, /for \(const agent of listedAgents\.slice\(0, 8\)\)/);
  assert.match(workspaceSource, /prefetchRuntimeDetail\(agent\.runtimeId, region\)/);
  assert.match(workspaceSource, /prefetchRuntimeAgentInfo\(agent\.runtimeId, region, agent\.runtimeApp \?\? ""\)/);
  assert.doesNotMatch(workspaceSource, /prefetchAgentFeedbackCases\(\{/);
});

test("workspace publish flow restores PR 748 deployment lifecycle hooks", () => {
  assert.match(appSource, /const openDeploymentDetail = useCallback/);
  assert.match(appSource, /const startDeployment = useCallback/);
  assert.match(appSource, /setMyAgents\(false\)[\s\S]*?setFocusedDeploymentTaskId\(task\.id\)/);
  assert.match(appSource, /setFocusedDeploymentTaskId\(task\.id\)/);
  assert.match(appSource, /setAgentDetailTarget\(null\)[\s\S]*?setFocusedDeploymentTaskId\(task\.id\)/);
  assert.match(appSource, /const finishDeployment = useCallback/);
  assert.match(appSource, /await connectRuntime\([\s\S]*?result\.runtimeId[\s\S]*?result\.version/);
  assert.match(appSource, /const \[agentInfoRefreshKey, setAgentInfoRefreshKey\] = useState\(0\)/);
  assert.match(appSource, /}, \[agentDetailTarget, appName, agentInfoRefreshKey, authStatus, myAgents\]\);/);
  assert.match(
    appSource,
    /const finishDeployment = useCallback[\s\S]*?setConnections\(loadConnections\(\)\);[\s\S]*?setAgentInfoRefreshKey\(\(key\) => key \+ 1\)/,
  );
  assert.match(
    appSource,
    /const finishDeployment = useCallback[\s\S]*?removeWorkspaceDraft\(completedDraftId\)[\s\S]*?setFocusedWorkspaceAgentId\(agentId\)[\s\S]*?setFocusedDeploymentTaskId\(""\)[\s\S]*?setManageAgents\(true\)/,
  );
  assert.match(appSource, /onDeploymentStarted=\{startDeployment\}/);
  assert.match(appSource, /onDeploymentComplete=\{finishDeployment\}/);

  assert.match(customCreateSource, /onDeploymentComplete\?: \(result: DeployResult\)/);
  assert.match(customCreateSource, /onDeploymentStarted\?: \(task: DeploymentTaskUpdate\)/);
  assert.match(customCreateSource, /<ProjectPreview[\s\S]*?embedded[\s\S]*?project=\{project\}/);
  assert.match(
    customCreateSource,
    /deploymentActionLabel=\{[\s\S]*?deploymentTarget[\s\S]*?t\("traditional\.deployment\.updateAndPublish"\)[\s\S]*?t\("common\.deploy"\)[\s\S]*?\}/,
  );
  assert.match(customCreateSource, /deploymentRuntimeId=\{deploymentTarget\?\.runtimeId\}/);
  assert.match(customCreateSource, /onDeploymentStarted=\{onDeploymentStarted\}/);
  assert.match(customCreateSource, /onDeploymentComplete=\{onDeploymentComplete\}/);

  assert.match(projectPreviewSource, /deploymentRuntimeId\?: string/);
  assert.match(projectPreviewSource, /onDeploymentStarted\?: \(task: DeploymentTaskUpdate\)/);
  assert.match(projectPreviewSource, /onDeploymentComplete\?: \(result: DeployResult\)/);
  assert.match(projectPreviewSource, /draftId\?: string/);
  assert.match(projectPreviewSource, /agentName: string/);
  assert.match(projectPreviewSource, /deploymentRuntimeName\?: string/);
  assert.match(
    projectPreviewSource,
    /const taskAgentName = agentName\?\.trim\(\) \|\| agentDraft\?\.name \|\| project\.name/,
  );
  assert.match(
    projectPreviewSource,
    /const requestedRuntimeName = effectiveRuntimeName\.trim\(\)/,
  );
  assert.match(
    customCreateSource,
    /deploymentRuntimeName=\{deploymentRuntimeName\}/,
  );
  assert.match(projectPreviewSource, /const isRuntimeUpdate = Boolean\(deploymentRuntimeId\)/);
  assert.match(customCreateSource, /resolveRuntimeName\([\s\S]*?draft\.name,[\s\S]*?configuredRuntimeName,[\s\S]*?runtimeNameCustomized/);
  assert.match(
    projectPreviewSource,
    /aria-describedby=\{isRuntimeUpdate \? deploymentRegionHelpId : undefined\}/,
  );
  assert.match(
    projectPreviewSource,
    /t\("projectPreview\.regionPreserved"\)/,
  );
  assert.match(projectPreviewSource, /onDeploymentStarted\?\.\(initialTask\)/);
  assert.match(projectPreviewSource, /RuntimeProbeError/);
  assert.match(projectPreviewSource, /import \{ mergeDeployBuildLog \} from "\.\/deployBuildLog"/);
  assert.match(projectPreviewSource, /latestBuildLog = mergeDeployBuildLog\(latestBuildLog, s\.buildLog\)/);
  assert.match(projectPreviewSource, /const pendingBuildLog = \(\): DeployBuildLogSnapshot/);
  assert.match(projectPreviewSource, /s\.phase === "build" && !latestBuildLog[\s\S]*?latestBuildLog = pendingBuildLog\(\)/);
  assert.match(projectPreviewSource, /let latestPhase = initialTask\.phase \?\? "prepare"/);
  assert.match(projectPreviewSource, /function advanceDeploymentPhase\(\s*current: string \| undefined,\s*next: string \| undefined,\s*\): string/);
  assert.match(projectPreviewSource, /const nextPhase = advanceDeploymentPhase\(latestPhase, s\.phase\)/);
  assert.match(projectPreviewSource, /const finalizeBuildFailureLog = \(\): DeployBuildLogSnapshot \| undefined =>/);
  assert.match(projectPreviewSource, /latestPhase !== "build" \|\| !latestBuildLog\?\.text/);
  assert.doesNotMatch(projectPreviewSource, /"----- 构建失败 -----"/);
  assert.match(projectPreviewSource, /const telemetryErrorMessage = \(error: unknown\): string \| undefined =>/);
  assert.match(projectPreviewSource, /latestPhase === "build" && latestBuildLog\?\.text[\s\S]*?safeTelemetryErrorMessage\(latestBuildLog\.text, \{ preserveEnd: true \}\)/);
  assert.match(projectPreviewSource, /errorMessage: telemetryErrorMessage\(err\)/);
  assert.doesNotMatch(projectPreviewSource, /latestPhase = s\.phase/);
  assert.match(projectPreviewSource, /setActivePhase\(latestPhase\)/);
  assert.match(
    projectPreviewSource,
    /label: buildStatusUnconfirmed[\s\S]*?t\("projectPreview\.task\.buildStatusUnconfirmed"\)[\s\S]*?t\("projectPreview\.task\.deploymentFailed"\)[\s\S]*?message: buildStatusUnconfirmed[\s\S]*?failedInBuild[\s\S]*?\.\.\.\(buildLog/,
  );
  assert.match(projectPreviewSource, /const failedInGithub = latestPhase === "github" && Boolean\(latestGithubLog\)/);
  assert.match(projectPreviewSource, /failedInBuild[\s\S]*?t\("projectPreview\.task\.buildFailedHint"\)[\s\S]*?failedInGithub[\s\S]*?t\("projectPreview\.task\.githubMountFailedHint"\)/);
  assert.match(
    projectPreviewSource,
    /await onDeploymentComplete\?\.\(result\)[\s\S]*?catch \(error\)[\s\S]*?error instanceof RuntimeProbeError[\s\S]*?status: "success"[\s\S]*?label: t\("projectPreview\.task\.deployedNotConnected"\)[\s\S]*?message: error\.message/,
  );
  assert.match(
    appSource,
    /const startDeployment = useCallback[\s\S]*?flushPendingWorkspaceDraft\(\)[\s\S]*?draftId: editingDraftId[\s\S]*?updateDeploymentTask\(linkedTask\)[\s\S]*?openDeploymentDetail\(linkedTask\)/,
  );
  assert.doesNotMatch(workspaceSource, /aw-deployment-focus/);
  assert.match(
    workspaceSource,
    /const focusedDeploymentTaskActive = Boolean\([\s\S]*?focusedDeploymentTaskId[\s\S]*?deploymentTask\.id === focusedDeploymentTaskId/,
  );
  assert.match(
    workspaceSource,
    /const selectedPendingTask = focusedDeploymentTaskId[\s\S]*?deploymentTasks\.find\(\(task\) => task\.id === focusedDeploymentTaskId\)[\s\S]*?: undefined/,
  );
  assert.match(
    workspaceSource,
    /const shouldShowDeploymentTask = Boolean\([\s\S]*?deploymentTask\.status !== "success"[\s\S]*?focusedDeploymentTaskActive/,
  );
  assert.match(
    workspaceSource,
    /const deploymentInProgress = deploymentTask\?\.status === "running"/,
  );
  assert.match(workspaceSource, /if \(!focusedDeploymentTaskId\) return;/);
  assert.doesNotMatch(workspaceSource, /activeDeploymentTaskId/);
  assert.match(workspaceSource, /<ResourceDetailLayout[\s\S]*?sections=\{visibleAgentSections\.map\(\(item\) => \(\{[\s\S]*?key: item\.id,[\s\S]*?label: item\.label,[\s\S]*?content: item\.id === section/);
  assert.match(workspaceSource, /activeSectionKey=\{section\}[\s\S]*?navigationLabel=\{t\("agentWorkspace\.agentDetails"\)\}[\s\S]*?onSectionChange=\{setSection\}/);
  assert.match(workspaceSource, /className=\{`aw-detail-deployment\$\{deploymentInProgress \? " is-running" : ""\}`\}[\s\S]*?<DeploymentProgressCard[\s\S]*?task=\{deploymentTask\}/);
  assert.match(
    workspaceSource,
    /const deploymentDraft = deploymentTask\?\.draftId[\s\S]*?drafts\.find\(\(item\) => item\.id === deploymentTask\.draftId\)[\s\S]*?deploymentTask\.agentDraft/,
  );
  assert.match(
    workspaceSource,
    /task\.status === "error" \|\| task\.status === "cancelled"[\s\S]*?onReturnToEdit[\s\S]*?>\{t\("agentWorkspace\.returnToEdit"\)\}<\/button>/,
  );
  assert.match(
    workspaceSource,
    /<DeploymentProgressCard[\s\S]*?task=\{deploymentTask\}[\s\S]*?onReturnToEdit=\{deploymentDraft[\s\S]*?onEditDraft\(deploymentDraft\)/,
  );
  assert.match(workspaceStyles, /\.aw-deploy-progress-actions\s*\{/);
  assert.match(workspaceSource, /const baseSteps = baseDeploymentSteps\(t\)/);
  assert.match(workspaceSource, /task\.githubDelivery[\s\S]*?steps\.push\(\{ phase: "github"/);
  assert.match(workspaceSource, /steps\.push\(baseSteps\[baseSteps\.length - 1\]\)/);
  assert.match(workspaceSource, /phase:\s*"github"[\s\S]*?label:\s*t\("agentWorkspace\.deploymentSteps\.github\.label"\)/);
  assert.match(workspaceSource, /autoExpand=\{Boolean\([\s\S]*?deploymentStepIndex\(task, t\) === 1/);
  assert.match(workspaceSource, /useState\(shouldAutoExpand\)/);
  assert.match(workspaceSource, /setExpanded\(shouldAutoExpand\)/);
  assert.match(workspaceSource, /const logTextRef = useRef<HTMLPreElement \| null>\(null\)/);
  assert.match(workspaceSource, /node\.scrollTop = node\.scrollHeight/);
  assert.match(workspaceSource, /log\.omittedEarly[\s\S]*?t\("agentWorkspace\.logStatus\.earlyOmitted"\)[\s\S]*?log\.snapshotTruncated[\s\S]*?t\("agentWorkspace\.logStatus\.recentOnly"\)/);
  assert.match(workspaceSource, /log\.pendingMessage/);
  assert.match(workspaceSource, /className="aw-deploy-log-empty">\{pendingMessage\}/);
  assert.match(workspaceSource, /hasLogText[\s\S]*?\? <pre ref=\{logTextRef\}>\{visibleText\}<\/pre>[\s\S]*?: <div className="aw-deploy-log-empty">\{pendingMessage\}<\/div>/);
  assert.match(workspaceSource, /step\.phase === "build" && task\.buildLog[\s\S]*?className="aw-deploy-step-log"[\s\S]*?<DeploymentBuildLog task=\{task\} \/>/);
  assert.match(workspaceSource, /step\.phase === "github" && task\.githubLog[\s\S]*?className="aw-deploy-step-log"[\s\S]*?<DeploymentGithubLog task=\{task\} \/>/);
  assert.doesNotMatch(workspaceSource, /<\/ol>\s*<DeploymentBuildLog task=\{task\} \/>/);
  assert.match(workspaceStyles, /\.aw-deploy-step-log\s*\{[\s\S]*?margin-top:\s*10px;/);
  assert.match(workspaceStyles, /\.aw-deploy-log-empty\s*\{/);
  assert.match(workspaceStyles, /\.aw-deploy-log\.is-collapsed header\s*\{[\s\S]*?border-bottom:\s*0;/);
  assert.doesNotMatch(
    workspaceSource,
    /className="aw-basic-stack">\s*\{deploymentTask && <DeploymentProgressCard/,
  );
  assert.match(workspaceStyles, /\.aw-detail-deployment\s*\{[\s\S]*?padding:\s*0 24px 16px;/);
  assert.match(
    workspaceStyles,
    /\.aw-detail-deployment\.is-running\s*\{[\s\S]*?flex:\s*1 1 auto;[\s\S]*?min-height:\s*0;[\s\S]*?overflow-y:\s*auto;[\s\S]*?overscroll-behavior:\s*contain;/,
  );
  assert.match(
    workspaceStyles,
    /\.aw-main\.is-deploying \.aw-agent-tabs,[\s\S]*?\.aw-main\.is-deploying \.aw-content,[\s\S]*?\.aw-main\.is-deploying \.aw-basic-actions\s*\{[\s\S]*?display:\s*none;/,
  );
  assert.match(projectPreviewSource, /await onDeploymentComplete\?\.\(result\)/);
  assert.match(projectPreviewSource, /runtimeId: result\.runtimeId \|\| deploymentRuntimeId/);
  assert.match(
    appSource,
    /const finishDeployment = useCallback[\s\S]*?removeWorkspaceDraft\(completedDraftId\)[\s\S]*?setEditingDraftId\(""\)[\s\S]*?await connectRuntime\([\s\S]*?waitForReady: true/,
  );
});

test("runtime update deployments stay on the existing agent row", () => {
  assert.match(workspaceSource, /const updateDraftByRuntimeId = useMemo/);
  assert.match(workspaceSource, /const latestTaskByRuntimeId = useMemo/);
  assert.match(
    workspaceSource,
    /if \(runtimeId && agentByRuntimeId\.has\(runtimeId\)\) return false/,
  );
  assert.match(workspaceSource, /leftTask\?\.status === "running"/);
  assert.match(
    workspaceSource,
    /\{ label: t\("myAgents\.deploying"\), className: " is-deploying" \}/,
  );
  assert.match(
    workspaceSource,
    /selectedUpdateCapability\?\.agent[\s\S]*?runtimeAgentDraftFromCloud\([\s\S]*?selectedUpdateCapability\.agent/,
  );
  assert.doesNotMatch(workspaceSource, /selectedAgentUpdateDraft\?\.draft/);
  assert.match(
    workspaceSource,
    /const matchingAgent = focusedTask\?\.runtimeId[\s\S]*?agentByRuntimeId\.get/,
  );
  assert.match(workspaceStyles, /\.aw-draft-badge\.is-deploying/);
  assert.doesNotMatch(
    workspaceSource,
    /task\.runtimeName === selectedDraft\.draft\.name|task\.runtimeName === selectedAgent\.label|candidate\.runtimeName === item\.draft\.name/,
  );
  assert.match(workspaceSource, /task\.agentName === selectedDraft\.draft\.name/);
  assert.match(workspaceSource, /task\.agentName === selectedAgent\.label/);
  assert.match(
    workspaceSource,
    /infoToDraft\([\s\S]*?selectedAgentInfo,[\s\S]*?selectedAgentAppName \|\| selectedAgent\?\.label \|\| "agent"/,
  );
});

test("deployed agent detail connects, refreshes the current Agent, then opens a new chat", () => {
  assert.match(workspaceSource, /onTalkAgent\?: \(agent: AgentEntry\) => void/);
  assert.match(workspaceSource, /className="aw-talk studio-update-action"[\s\S]*?t\("agentWorkspace\.chat"\)/);
  assert.match(workspaceSource, /onClick=\{\(\) => onTalkAgent\?\.\(selectedAgent\)\}/);
  assert.match(appSource, /const talkToWorkspaceAgent = async \(agent: AgentEntry\) => \{/);
  assert.match(
    appSource,
    /agent\.id\.startsWith\("detail:"\)[\s\S]*?connectRuntime\([\s\S]*?agent\.runtimeId[\s\S]*?await refreshCurrentAgentAndStartNewChat\(agentId\)/,
  );
  assert.match(
    appSource,
    /const refreshCurrentAgentAndStartNewChat[\s\S]*?loadHydratedSessions\(id, userId\)[\s\S]*?getAgentInfo\(id\)[\s\S]*?setConnections\(nextConnections\)[\s\S]*?setAgentInfo\(nextAgentInfo\)[\s\S]*?setAppName\(id\)[\s\S]*?startNewChat\(\)/,
  );
  assert.match(appSource, /await refreshCurrentAgentAndStartNewChat\(agent\.id\)/);
  assert.match(appSource, /onTalkAgent=\{talkToWorkspaceAgent\}/);
  assert.match(workspaceStyles, /\.aw-talk svg/);
  assert.match(
    workspaceStyles,
    /\.aw-root\.is-detail-only \.aw-agent-head\s*\{[\s\S]*?padding-top:\s*24px;/,
  );
});

test("workspace agents can be reordered by drag or keyboard", () => {
  assert.match(appSource, /function workspaceAgentOrderKey\(userId: string\)/);
  assert.match(appSource, /const \[workspaceAgentOrder, setWorkspaceAgentOrder\] = useState<string\[\]>\(\[\]\)/);
  assert.match(appSource, /const saveWorkspaceAgentOrder = useCallback/);
  assert.match(
    appSource,
    /agents=\{detailAgentEntry \? \[detailAgentEntry\] : orderedWorkspaceAgentEntries\}/,
  );
  assert.match(appSource, /agentOrder=\{workspaceAgentOrder\}/);
  assert.match(appSource, /onAgentOrderChange=\{saveWorkspaceAgentOrder\}/);

  assert.match(workspaceSource, /agentOrder\?: string\[\]/);
  assert.match(workspaceSource, /onAgentOrderChange\?: \(agentIds: string\[\]\) => void/);
  assert.match(workspaceSource, /draggable=\{!!onAgentOrderChange && !selectionMode\}/);
  assert.match(workspaceSource, /onDrop=\{\(event\) => \{/);
  assert.match(workspaceSource, /moveAgentNear\(draggedId, agent\.id, dropPlacement\)/);
  assert.match(workspaceSource, /event\.clientY > rect\.top \+ rect\.height \/ 2 \? "after" : "before"/);
  assert.match(workspaceSource, /aria-keyshortcuts=\{onAgentOrderChange \? "Alt\+ArrowUp Alt\+ArrowDown"/);
  assert.match(workspaceSource, /moveAgentByOffset\(agent\.id, -1\)/);
  assert.match(workspaceSource, /moveAgentByOffset\(agent\.id, 1\)/);
  assert.match(workspaceStyles, /\.aw-agent-item\[draggable="true"\]/);
  assert.match(workspaceStyles, /\.aw-agent-item\.is-drop-target/);
  assert.match(workspaceStyles, /\.aw-agent-item\.is-drop-after/);
});

test("runtime refresh preserves agent order and detail loading uses an overlay", () => {
  assert.match(
    connectionsSource,
    /const existingIndex = list\.findIndex\(\(item\) => item\.runtimeId === runtimeId\)/,
  );
  assert.match(connectionsSource, /else list\[existingIndex\] = conn/);
  assert.doesNotMatch(
    connectionsSource,
    /loadConnections\(\)\.filter\(\(c\) => c\.runtimeId !== runtimeId\), conn/,
  );
  assert.match(workspaceSource, /className="aw-detail-loading" role="status"/);
  assert.match(
    workspaceSource,
    /className="aw-detail-loading"[\s\S]*?className="loading-gap-spinner"/,
  );
  assert.match(workspaceSource, /t\("agentWorkspace\.loadingAgent"\)/);
  assert.match(workspaceSource, /const updateBlockedReason = selectedDraft/);
  assert.match(workspaceSource, /updateCapabilityLoading[\s\S]*?t\("agentWorkspace\.errors\.checkingUpdateConfig"\)/);
  assert.match(workspaceStyles, /\.aw-detail-loading\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?inset:\s*0;/);
});

test("runtime updates use the Agent selected in management instead of the active chat connection", () => {
  assert.match(clientSource, /export interface RuntimeUpdateCapability/);
  assert.match(clientSource, /recoveryStatus: RuntimeUpdateRecoveryStatus/);
  assert.match(clientSource, /editMode: "source-preserving" \| "regenerate" \| "blocked"/);
  assert.match(clientSource, /configuredEnvKeys: string\[\]/);
  assert.match(clientSource, /etag: string/);
  assert.match(clientSource, /envs: \{ key: string; value: string \}\[\]/);
  assert.match(clientSource, /network: NetworkConfig/);
  assert.match(clientSource, /agent\?:\s*\{[\s\S]*?\}\s*\| null/);
  assert.match(clientSource, /export function getRuntimeUpdateCapability/);
  assert.match(clientSource, /\/web\/runtime-update-capability\?\$\{params\.toString\(\)\}/);
  assert.match(clientSource, /new URLSearchParams\(\{ runtimeId, region \}\)/);
  assert.match(clientSource, /if \(appName\) params\.set\("appName", appName\)/);
  assert.match(clientSource, /params\.set\("currentVersion", String\(currentVersion\)\)/);
  assert.match(clientSource, /runtimeUpdateCapabilityErrorMessage/);
  assert.match(clientSource, /runtimeUpdateCapabilityCacheKey/);
  assert.match(clientSource, /runtimeUpdateCapabilityCache\.get\(key\)\?\.promise/);
  assert.match(clientSource, /waitForSharedRequest\(promise, signal\)/);
  const capabilityCallStart = workspaceSource.indexOf("getRuntimeUpdateCapability({");
  const capabilityCallEnd = workspaceSource.indexOf("}).then", capabilityCallStart);
  assert.ok(capabilityCallStart >= 0 && capabilityCallEnd > capabilityCallStart);
  const capabilityCall = workspaceSource.slice(capabilityCallStart, capabilityCallEnd);
  assert.match(
    capabilityCall,
    /runtimeId,[\s\S]*?region,[\s\S]*?appName: capabilityRuntimeAppName,[\s\S]*?currentVersion:[\s\S]*?signal/,
  );
  assert.match(workspaceSource, /onUpdateAgent: \(capability: RuntimeUpdateCapability\) => void/);
  assert.match(workspaceSource, /onUpdateAgent\(selectedUpdateCapability\)/);
  assert.match(clientSource, /appName:\s*opts\?\.appName/);
  assert.match(clientSource, /editMode:\s*opts\?\.editMode/);
  assert.match(clientSource, /draft:\s*opts\?\.draft/);
  assert.match(customCreateSource, /appName:\s*deploymentTarget\?\.appName/);
  assert.match(customCreateSource, /editMode:\s*deploymentTarget\?\.editMode/);
  assert.match(
    customCreateSource,
    /deploymentTarget \|\| mcpGatewayManaged \? codegenDraft\(draft\) : undefined/,
  );
  assert.match(customCreateSource, /updateEtag:\s*deploymentTarget\?\.etag/);
  assert.match(customCreateSource, /baseRuntimeVersion:\s*deploymentTarget\?\.currentVersion/);
  assert.match(
    customCreateSource,
    /removeRuntimeEnvKeys:\s*deploymentTarget[\s\S]*?removedConfiguredMcpEnvKeys\([\s\S]*?deploymentTarget\.configuredMcpEnvKeys[\s\S]*?draft/,
  );
  assert.match(
    customCreateSource,
    /onClick=\{\(\) =>[\s\S]*?onChange\([\s\S]*?tools\.map\([\s\S]*?clearMcpConfiguredAuth\(tool\)/,
  );
  assert.doesNotMatch(
    customCreateSource,
    /update\(i,\s*clearMcpConfiguredAuth\(/,
  );

  const handlerStart = appSource.indexOf("onUpdateAgent={async (capability) =>");
  const handlerEnd = appSource.indexOf("onEditDraft=", handlerStart);
  assert.ok(handlerStart >= 0 && handlerEnd > handlerStart);
  const handler = appSource.slice(handlerStart, handlerEnd);
  assert.doesNotMatch(handler, /currentConn/);
  assert.match(handler, /capability\.runtime\.runtimeId/);
  assert.match(handler, /capability\.runtime\.region/);
  assert.match(handler, /capability\.runtime\.currentVersion/);
  assert.match(
    handler,
    /runtimeAgentDraftFromCloud\([\s\S]*?runtimeAgent,[\s\S]*?cloudProvider,[\s\S]*?capability\.runtime\.configuredEnvKeys/,
  );
  assert.match(
    handler,
    /capability\.runtime\.envs[\s\S]*?filter\(\(\{ key \}\) => !isRuntimeModelSelectionEnv\(key\)\)[\s\S]*?\.map/,
  );
  assert.match(handler, /envValues:\s*runtimeEnvValues/);
  assert.match(
    handler,
    /runtimeEnv\.has\("FEISHU_APP_ID"\)[\s\S]*?runtimeEnv\.has\("FEISHU_APP_SECRET"\)/,
  );
  assert.doesNotMatch(handler, /draftEnvValues|selectedAgentUpdateDraft\?\.draft/);
  assert.match(handler, /hydrateRuntimeModelSelection\(/);
  assert.match(
    handler,
    /setCustomCreationSurface\([\s\S]*?classifiedDraft\.dynamicAgentDelegation === true[\s\S]*?\? "vulcan"[\s\S]*?: "traditional"/,
  );
  assert.match(handler, /network:\s*capability\.runtime\.network/);
  assert.match(handler, /etag:\s*capability\.etag/);
  assert.match(handler, /editMode:\s*capability\.editMode/);
  assert.match(
    handler,
    /configuredRuntimeEnvKeys:\s*capability\.runtime\.configuredEnvKeys/,
  );
  assert.match(
    handler,
    /setRuntimeUpdateTarget\(\{[\s\S]*?runtimeId:\s*capability\.runtime\.runtimeId,[\s\S]*?currentVersion:\s*capability\.runtime\.currentVersion,[\s\S]*?etag:\s*capability\.etag/,
  );
  assert.match(
    handler,
    /exitAgentDetailContext\(\)[\s\S]*?setCreateView\("custom"\)/,
  );
});

test("introspection-only runtime updates are visibly blocked without treating empty lists as deletions", () => {
  assert.match(
    workspaceSource,
    /selectedUpdateCapability\.recoveryStatus !== "complete"[\s\S]*?selectedUpdateCapability\.recoveryStatus !== "draft-only"/,
  );
  assert.match(workspaceSource, /t\("agentWorkspace\.updateConfigUnavailable"\)/);
  assert.match(workspaceSource, /aw-update-recovery-notice/);
  assert.match(
    workspaceSource,
    /selectedUpdateCapability\s*&&\s*!selectedUpdateCapability\.canUpdate\s*&&/,
  );
  assert.doesNotMatch(workspaceSource, /更新配置说明/);
  assert.match(workspaceSource, /updateCapabilityWarnings\.map/);
  assert.match(
    workspaceSource,
    /import \{ localeCompatibleBackendText \} from "\.\.\/i18n\/locales";/,
  );
  assert.match(workspaceStyles, /\.aw-update-recovery-notice\s*\{/);
  assert.match(workspaceStyles, /hsl\(42 92% 96%\)/);
  assert.doesNotMatch(
    workspaceSource,
    /recoveryStatus === "introspection-only"[\s\S]{0,300}runtimeAgentDraftFromCloud/,
  );
});

test("runtime-preserved skills are explained and can be removed or replaced", () => {
  assert.match(skillSourcePickerSource, /skill\.source === "runtime"/);
  assert.match(skillSourcePickerSource, /skillSourcePicker\.sources\.runtime/);
  assert.match(skillSourcePickerSource, /t\(skillSourceLabelKey\(skill\)\)/);
  assert.match(skillSourcePickerSource, /replaceRuntimeSkill/);
});

test("agent detail actions clear the detail stack before opening another view", () => {
  assert.match(
    appSource,
    /const exitAgentDetailContext = useCallback\(\(\) => \{[\s\S]*?popStudioPage\("agent-detail"\)[\s\S]*?setAgentDetailTarget\(null\)[\s\S]*?setMyAgents\(false\)[\s\S]*?setManageAgents\(false\)/,
  );
  assert.match(
    appSource,
    /const refreshCurrentAgentAndStartNewChat[\s\S]*?exitAgentDetailContext\(\)[\s\S]*?startNewChat\(\)/,
  );
  assert.match(
    appSource,
    /async function openFeedbackCaseInStudio[\s\S]*?exitAgentDetailContext\(\)[\s\S]*?await pickSession/,
  );
  assert.match(
    appSource,
    /onCreateAgent=\{\(\) => \{[\s\S]*?exitAgentDetailContext\(\)[\s\S]*?setAddMenu\(true\)/,
  );
  assert.match(
    appSource,
    /onEditDraft=\{\(item\) => \{[\s\S]*?exitAgentDetailContext\(\)[\s\S]*?setCreateView\("custom"\)/,
  );
});

test("runtime update capability checks ignore aborted and stale selections", () => {
  assert.match(workspaceSource, /const updateCapabilityRequestRef = useRef\(0\)/);
  assert.match(workspaceSource, /const controller = new AbortController\(\)/);
  assert.match(workspaceSource, /requestId !== updateCapabilityRequestRef\.current/);
  assert.match(workspaceSource, /controller\.abort\(\)[\s\S]*?window\.clearTimeout\(pollTimer\)/);
  assert.match(workspaceSource, /const updateCapabilityRequestKey = JSON\.stringify\(\[[\s\S]*?selectedAgent\?\.runtimeId[\s\S]*?selectedAgent\?\.region[\s\S]*?\]\)/);
  assert.match(
    workspaceSource,
    /const updateCapabilityRequestKey = JSON\.stringify\(\[[\s\S]*?selectedAgent\?\.currentVersion[\s\S]*?capabilityRuntimeAppName[\s\S]*?\]\)/,
  );
  assert.match(workspaceSource, /getCachedRuntimeUpdateCapability\(\{/);
  assert.match(workspaceSource, /updateCapability\?\.requestKey === updateCapabilityRequestKey/);
  assert.match(workspaceSource, /value\.runtime\.region !== region/);
  assert.match(
    workspaceSource,
    /capabilityRuntimeAppName &&[\s\S]*?value\.agent\?\.appName !== capabilityRuntimeAppName/,
  );
  assert.match(workspaceSource, /value\.canUpdate && !value\.agent\?\.appName/);
  assert.match(workspaceSource, /selectedUpdateCapability\.agent\?\.appName/);
  assert.match(workspaceSource, /updateCapabilityLoading[\s\S]*?loading-gap-spinner[\s\S]*?t\("agentWorkspace\.preparing"\)/);
  assert.match(workspaceSource, /aria-describedby=\{updateBlockedReason \? updateReasonId : undefined\}/);
  assert.match(workspaceSource, /className="aw-update-disabled-reason"[\s\S]*?role="tooltip"/);
  const capabilityRequest = workspaceSource.slice(
    workspaceSource.indexOf("const loadCapability = (initial: boolean) =>"),
    workspaceSource.indexOf("loadCapability(true);"),
  );
  assert.match(
    capabilityRequest,
    /\.catch\(\(\) => \{[\s\S]*?setUpdateCapabilityError\(t\("agentWorkspace\.errors\.checkUpdateCapability"\)\)/,
  );
  assert.doesNotMatch(capabilityRequest, /error\.message/);
  assert.match(workspaceStyles, /\.aw-update-wrap\.is-disabled:hover \.aw-update-disabled-reason/);
  assert.match(workspaceStyles, /\.aw-update-wrap\.is-disabled:focus-visible \.aw-update-disabled-reason/);
});

test("preparing recovery stops the button spinner and polls safely in the background", () => {
  assert.match(clientSource, /\| "preparing"/);
  assert.match(
    clientSource,
    /value\.recoveryStatus === "preparing"[\s\S]*?runtimeUpdateCapabilityCache\.delete\(key\)/,
  );
  assert.match(workspaceSource, /const maxPollAttempts = 60/);
  assert.match(workspaceSource, /const preparing = value\.recoveryStatus === "preparing"/);
  assert.match(
    workspaceSource,
    /setUpdateCapability\([\s\S]*?setUpdateCapabilityLoading\(false\)[\s\S]*?window\.setTimeout\(\(\) => loadCapability\(false\), 1_000\)/,
  );
  assert.match(workspaceSource, /t\("agentWorkspace\.restoringUpdateConfig"\)/);
  assert.match(
    workspaceSource,
    /selectedUpdateCapability\.recoveryStatus === "preparing"[\s\S]*?\? "status"/,
  );
});

test("workspace keeps agent deletion in selection mode and the floating detail actions", () => {
  assert.match(appSource, /deleteRuntime/);
  assert.match(appSource, /removeRuntimeConnection/);
  assert.match(appSource, /libraryRuntimePermissions/);
  assert.match(appSource, /canDelete: runtime\.canDelete/);
  assert.match(appSource, /canDelete: entry\.runtimeId[\s\S]*?libraryRuntimePermissions\[entry\.runtimeId\]\?\.canDelete === true/);
  assert.match(
    appSource,
    /const detailAgentEntry:[\s\S]*?canDelete: agentDetailTarget\.runtime\.canDelete/,
  );
  assert.match(appSource, /const deleteWorkspaceAgents = useCallback/);
  assert.match(appSource, /await deleteRuntime\(agent\.runtimeId, agent\.region\)/);
  assert.match(appSource, /const selectedRuntimeId = runtimeIdForSelection\(connections, appName\)/);
  assert.match(appSource, /deletedCurrentSelection[\s\S]*?deletedRuntimeIds\.has\(selectedRuntimeId\)/);
  assert.doesNotMatch(
    appSource,
    /if \(targets\.some\(\(agent\) => agent\.id === appName\)\) \{[\s\S]*?setAppName\(""\)[\s\S]*?\}/,
  );
  assert.match(
    appSource,
    /deletedRuntimeIds\.has\(agentDetailTarget\.runtime\.runtimeId\)[\s\S]*?exitAgentDetailContext\(\)[\s\S]*?setMyAgents\(true\)/,
  );
  assert.match(appSource, /onDeleteAgents=\{deleteWorkspaceAgents\}/);
  assert.match(appSource, /const deleteWorkspaceDrafts = useCallback/);
  assert.match(appSource, /onDeleteDrafts=\{deleteWorkspaceDrafts\}/);
  assert.match(
    appSource,
    /const deleteWorkspaceDrafts = useCallback[\s\S]*?cancelPendingWorkspaceDraft\(\)[\s\S]*?commitWorkspaceDrafts\([\s\S]*?filter\(\(item\) => !deletedDraftIds\.has\(item\.id\)\)/,
  );

  assert.match(workspaceSource, /onDeleteAgents\?: \(agents: AgentEntry\[\]\) => Promise<void>/);
  assert.match(workspaceSource, /onDeleteDrafts\?: \(drafts: WorkspaceAgentDraft\[\]\) => void/);
  assert.match(workspaceSource, /const \[selectionMode, setSelectionMode\] = useState\(false\)/);
  assert.match(workspaceSource, /const \[selectedAgentIds, setSelectedAgentIds\] = useState<Set<string>>/);
  assert.match(workspaceSource, /const \[selectedDraftIds, setSelectedDraftIds\] = useState<Set<string>>/);
  assert.match(workspaceSource, /selectedDeletableAgents/);
  assert.match(workspaceSource, /selectedDeletableDrafts/);
  const deleteSelectedStart = workspaceSource.indexOf("const deleteSelectedItems");
  const deleteSingleAgentStart = workspaceSource.indexOf("const deleteSingleAgent");
  const deleteSingleDraftStart = workspaceSource.indexOf("const deleteSingleDraft");
  const createEvaluationGroupStart = workspaceSource.indexOf("const createEvaluationGroup");
  assert.ok(deleteSelectedStart >= 0 && deleteSingleAgentStart > deleteSelectedStart);
  assert.ok(deleteSingleDraftStart > deleteSingleAgentStart);
  assert.ok(createEvaluationGroupStart > deleteSingleDraftStart);
  assert.doesNotMatch(
    workspaceSource.slice(deleteSelectedStart, createEvaluationGroupStart),
    /window\.confirm/,
  );
  assert.match(workspaceSource, /const \[deleteConfirmTarget, setDeleteConfirmTarget\]/);
  assert.match(workspaceSource, /import \{ StudioConfirmDialog \} from "\.\/StudioConfirmDialog"/);
  assert.match(workspaceSource, /<StudioConfirmDialog[\s\S]*?variant="danger"/);
  assert.match(workspaceSource, /closeLabel=\{t\("agentWorkspace\.closeDeleteConfirmation"\)\}/);
  assert.match(studioConfirmSource, /createPortal\(/);
  assert.match(studioConfirmSource, /@openai\/apps-sdk-ui\/components\/Alert/);
  assert.match(studioConfirmSource, /@openai\/apps-sdk-ui\/components\/Button/);
  assert.match(studioConfirmSource, /import \{ Warning, X \} from "@openai\/apps-sdk-ui\/components\/Icon"/);
  assert.doesNotMatch(studioConfirmSource, /function ConfirmWarningIcon|function ConfirmCloseIcon/);
  assert.doesNotMatch(
    workspaceSource.slice(0, workspaceSource.indexOf("} from \"lucide-react\"")),
    /\bAlertTriangle\b|^\s*X,\s*$/m,
  );
  assert.match(studioConfirmSource, /role="alertdialog"/);
  assert.match(studioConfirmSource, /aria-modal="true"/);
  assert.match(studioConfirmSource, /aria-labelledby=\{titleId\}/);
  assert.match(studioConfirmSource, /aria-describedby=\{descriptionId\}/);
  assert.match(studioConfirmSource, /className="studio-confirm-backdrop"/);
  assert.match(studioConfirmSource, /studio-confirm-dialog--\$\{variant\}/);
  assert.match(studioConfirmSource, /className="studio-confirm-head"/);
  assert.match(studioConfirmSource, /className="studio-confirm-body"/);
  assert.match(studioConfirmSource, /className="studio-confirm-actions"/);
  assert.match(studioConfirmSource, /className="studio-confirm-primary"/);
  assert.match(appStyles, /\.studio-confirm-dialog--warning \.studio-confirm-title-icon/);
  assert.match(appStyles, /\.studio-confirm-dialog--danger \.studio-confirm-title-icon/);
  assert.doesNotMatch(
    studioConfirmSource,
    /pp-confirm|code-browser/,
  );
  assert.match(workspaceSource, /setDeleteConfirmTarget\(\{[\s\S]*?kind: "selection"/);
  assert.match(workspaceSource, /setDeleteConfirmTarget\(\{[\s\S]*?kind: "agent"/);
  assert.match(workspaceSource, /setDeleteConfirmTarget\(\{[\s\S]*?kind: "draft"/);
  assert.match(workspaceSource, /onConfirm=\{\(\) => void confirmDeleteTarget\(\)\}/);
  assert.match(workspaceSource, /await onDeleteAgents\(agentsToDelete\)/);
  assert.match(workspaceSource, /onDeleteDrafts\?\.\(draftsToDelete\)/);
  assert.match(workspaceSource, /aria-pressed=\{selectionMode \? isSelectedForDelete : undefined\}/);
  assert.match(workspaceSource, /t\("agentWorkspace\.deleteSelected"\)/);
  assert.match(workspaceSource, /const deleteSingleAgent = \(agent: AgentEntry\) =>/);
  assert.match(workspaceSource, /const deleteSingleDraft = /);
  assert.equal(workspaceSource.match(/aria-label=\{t\("agentWorkspace\.deleteAgent"\)\}/g)?.length, 1);
  assert.match(workspaceSource, /aria-label=\{t\("myAgents\.deleteDraft"\)\}/);
  assert.match(workspaceStyles, /\.aw-selection-toolbar/);
  assert.match(workspaceStyles, /\.aw-select-marker\.is-checked/);
  assert.doesNotMatch(workspaceStyles, /\.aw-head-action(?:\s|\.|:|\{)/);
  assert.doesNotMatch(workspaceStyles, /\.aw-delete-confirm/);
  assert.match(appStyles, /\.studio-confirm-dialog\s*\{[\s\S]*?width:\s*min\(420px, calc\(100vw - 40px\)\)/);
  assert.match(appStyles, /\.studio-confirm-head\s*\{[\s\S]*?flex:\s*0 0 58px/);
  assert.match(appStyles, /\.studio-confirm-head\s*\{[\s\S]*?padding:\s*0 16px 0 18px/);
  assert.match(appStyles, /\.studio-confirm-body\s*\{[\s\S]*?padding:\s*24px 20px/);
  assert.match(
    appStyles,
    /\.studio-confirm-actions\s*\{[\s\S]*?padding:\s*12px 16px;[\s\S]*?border-top:\s*1px solid hsl\(var\(--border\)\)/,
  );
  assert.doesNotMatch(appStyles, /\.studio-confirm-close:focus-visible/);
  assert.doesNotMatch(appStyles, /\.studio-confirm-dialog--danger \.studio-confirm-actions \.studio-confirm-primary/);
  assert.match(
    workspaceSource,
    /<Button[\s\S]*?color="danger"[\s\S]*?aria-label=\{t\("agentWorkspace\.deleteAgent"\)\}/,
  );
  assert.doesNotMatch(
    workspaceSource,
    /className="aw-basic-actions"[\s\S]*?className="aw-head-action studio-update-action"/,
  );
});

test("agent detail evaluation tab reads feedback datasets", () => {
  assert.match(clientSource, /export interface AgentFeedbackCase/);
  assert.match(clientSource, /export type AgentFeedbackSource = "user" \| "auto"/);
  assert.match(clientSource, /source\?: AgentFeedbackSource/);
  assert.match(clientSource, /score\?: number \| null/);
  assert.match(clientSource, /reason\?: string/);
  assert.match(clientSource, /export async function getAgentFeedbackCases/);
  assert.match(clientSource, /export async function deleteAgentFeedbackCases/);
  assert.match(clientSource, /appName\?: string/);
  assert.match(clientSource, /appName: app/);
  assert.match(clientSource, /export function clearMessageFeedbackCache/);
  assert.match(clientSource, /\/web\/evaluation\/feedback-cases\?\$\{query\.toString\(\)\}/);
  assert.match(clientSource, /\/web\/evaluation\/feedback-cases\/delete/);
  assert.match(
    clientSource,
    /function selectedRuntimeRegionCandidates\(region\?: string\)[\s\S]*?return explicit \? \[explicit\] : runtimeRegionCandidates\(\)/,
  );
  assert.match(
    clientSource,
    /getAgentFeedbackCases[\s\S]*?for \(const region of selectedRuntimeRegionCandidates\(args\.region\)\)/,
  );
  assert.match(
    clientSource,
    /getAutomaticEvaluationStatuses[\s\S]*?for \(const region of selectedRuntimeRegionCandidates\(args\.region\)\)/,
  );
  assert.match(
    clientSource,
    /getAgentOptimizations[\s\S]*?for \(const region of selectedRuntimeRegionCandidates\(args\.region\)\)/,
  );
  assert.match(workspaceSource, /getAgentFeedbackCases\(\{/);
  assert.match(workspaceSource, /deleteAgentFeedbackCases\(\{/);
  assert.match(
    workspaceSource,
    /const selectedAgentAppName =[\s\S]*?selectedAgentInfo\?\.appName \|\| selectedAgent\?\.runtimeApp \|\| selectedAgent\?\.app \|\| ""/,
  );
  assert.match(
    workspaceSource,
    /if \(detailOnly && !selectedAgentAppName\)[\s\S]*?setFeedbackCasesLoading\(!detailAgentInfoResolved\)/,
  );
  assert.match(workspaceSource, /appName: selectedAgentAppName/);
  assert.match(workspaceSource, /setFeedbackSets\(response\.sets\)/);
  assert.match(workspaceSource, /setFeedbackCases\(/);
  assert.match(workspaceSource, /focusCaseKind\(kind\)/);
  assert.match(workspaceSource, /selectedCaseIds/);
  assert.match(workspaceSource, /expandedCaseIds/);
  assert.match(workspaceSource, /onOpenFeedbackCase/);
  assert.match(workspaceSource, /openFeedbackCase/);
  assert.match(workspaceSource, /onFeedbackCasesDeleted/);
  assert.match(workspaceSource, /focusedAgentSection/);
  assert.match(workspaceSource, /focusedCaseKind/);
  assert.match(workspaceSource, /feedbackCasePreview/);
  assert.match(workspaceSource, /const previewCase = useMemo<AgentCase \| null>/);
  assert.match(workspaceSource, /\.\.\.feedbackCases\.filter\(\(item\) =>/);
  assert.match(workspaceSource, /appliedFocusKeyRef/);
  assert.match(workspaceSource, /if \(appliedFocusKeyRef\.current === focusKey\) return/);
  assert.match(workspaceSource, /onToggleExpanded/);
  assert.match(workspaceSource, /deleteCases\(selectedVisibleCases\)/);
  assert.match(workspaceSource, /onDeleteCase=\{\(item\) => void deleteCases\(\[item\]\)\}/);
  assert.match(appSource, /openFeedbackCaseInStudio/);
  assert.match(appSource, /returnToFeedbackCases/);
  assert.match(appSource, /feedbackCaseReturnAgentId/);
  assert.match(appSource, /feedbackCaseReturnKind/);
  assert.match(appSource, /focusedWorkspaceAgentSection/);
  assert.match(appSource, /focusedWorkspaceCaseKind/);
  assert.match(appSource, /focusedCaseKind=\{focusedWorkspaceCaseKind\}/);
  assert.match(appSource, /t\("actions\.backToEvaluationCase"\)/);
  assert.match(appSource, /clearDeletedFeedbackCases/);
  assert.match(appSource, /clearMessageFeedbackCache/);
  assert.match(appSource, /onFeedbackCasesDeleted=\{clearDeletedFeedbackCases\}/);
  assert.match(appSource, /onOpenFeedbackCase=\{\(item\) => void openFeedbackCaseInStudio\(item\)\}/);
  assert.match(appSource, /turnNodeRefs/);
  assert.match(
    appSource,
    /feedbackTargetEventId &&\s*feedbackTargetEventId === feedbackEventId\s*\? "is-feedback-target"/,
  );
  assert.match(workspaceSource, /feedbackSetFor\(feedbackSets, kind\)/);
  assert.match(workspaceSource, /cases\.filter\(\(item\) => item\.kind === kind\)\.length/);
  assert.match(workspaceSource, /const count = previewCase \? localCount : set\?\.itemCount \?\? localCount/);
  assert.doesNotMatch(workspaceSource, /Math\.max\(\s*set\?\.itemCount/);
  assert.match(workspaceSource, /loading=\{feedbackCasesLoading && visibleCases\.length === 0\}/);
  assert.match(workspaceSource, /"agentWorkspace\.goodCases"/);
  assert.match(workspaceSource, /"agentWorkspace\.badCases"/);
  assert.match(workspaceSource, /"agentWorkspace\.goodCase"/);
  assert.match(workspaceSource, /"agentWorkspace\.badCase"/);
  assert.doesNotMatch(workspaceSource, />Good cases</);
  assert.doesNotMatch(workspaceSource, />Bad cases</);
  assert.match(
    workspaceSource,
    /<span>\{t\("agentWorkspace\.userInput"\)\}<\/span>[\s\S]*?<span>\{t\("agentWorkspace\.agentOutput"\)\}<\/span>[\s\S]*?<span>\{t\("agentWorkspace\.score"\)\}<\/span>[\s\S]*?<span>\{t\("agentWorkspace\.scoreReason"\)\}<\/span>[\s\S]*?<span className="aw-case-action-head">\{t\("skillCenter\.actions"\)\}<\/span>/,
  );
  assert.match(
    workspaceSource,
    /className="aw-case-actions aw-case-cell"[\s\S]*?data-label=\{t\("skillCenter\.actions"\)\}[\s\S]*?className="aw-case-delete"/,
  );
  assert.match(workspaceSource, /function DeleteCaseIcon\(\)/);
  assert.doesNotMatch(workspaceSource, /<span>来源<\/span>/);
  assert.match(workspaceSource, /t\("agentWorkspace\.automaticFeedback"\)/);
  assert.match(workspaceSource, /t\("agentWorkspace\.manualFeedback"\)/);
  assert.match(workspaceSource, /useState<AgentFeedbackSource>\("auto"\)/);
  assert.match(workspaceSource, /source !== caseSourceFilter/);
  assert.match(workspaceSource, /caseSourceFilter === source/);
  assert.match(workspaceSource, /setCaseSourceFilter\(source\)/);
  assert.match(workspaceSource, /formatCaseTime\(item\.createdAt, i18n\.resolvedLanguage \?\? i18n\.language, t\)/);
  assert.doesNotMatch(workspaceSource, /item\.source !== "auto"/);
  assert.match(workspaceSource, /Math\.round\(item\.score \* 100\)/);
  assert.match(workspaceSource, /item\.reason \|\| "—"/);
  assert.match(workspaceSource, /item\.comment\.trim\(\) !== item\.reason\?\.trim\(\)/);
  assert.match(workspaceSource, /showComment && <small title=\{item\.comment\}>\{t\("agentWorkspace\.note"\)\}\{item\.comment\}<\/small>/);
  assert.match(workspaceStyles, /\.aw-case-summary/);
  assert.match(workspaceStyles, /\.aw-case-filter-bar/);
  assert.match(workspaceStyles, /\.aw-case-source-filters/);
  assert.match(workspaceStyles, /\.aw-case-reason p/);
  assert.match(workspaceStyles, /\.aw-case-cell::before/);
  assert.match(appSource, /case-return-bar/);
  assert.match(appSource, /app: agentDetailTarget\.appName \?\? agentDetailTarget\.name/);
  assert.match(workspaceStyles, /\.aw-case-toolbar/);
  assert.match(workspaceStyles, /\.aw-case-actions/);
  assert.match(workspaceStyles, /\.aw-case-delete/);
  assert.match(workspaceStyles, /\.aw-case-output-preview/);
  assert.match(workspaceStyles, /-webkit-line-clamp: 3/);
  assert.match(workspaceStyles, /\.aw-case-expand/);
  assert.match(workspaceStyles, /\.aw-case-row\.is-focused/);
  assert.match(workspaceStyles, /\.aw-agent-tabs button[\s\S]*?font-size: 14px/);
  assert.match(workspaceStyles, /\.aw-case-error/);
});

test("Agent workspace-owned labels and sample cases are fully localized", () => {
  const defaultCasesSource = workspaceSource.slice(
    workspaceSource.indexOf("function buildDefaultCases"),
    workspaceSource.indexOf("const DEFAULT_EVALUATION_GROUPS"),
  );

  assert.match(defaultCasesSource, /function buildDefaultCases\(t: TFunction\): AgentCase\[\]/);
  assert.match(defaultCasesSource, /agentWorkspace\.defaultCases\.weeklyFeedback\.input/);
  assert.match(defaultCasesSource, /agentWorkspace\.defaultCases\.repeatedTool\.output/);
  assert.doesNotMatch(defaultCasesSource, /[\u3400-\u9fff]/);
  assert.match(workspaceSource, /t\("agentWorkspace\.agentCountLabel"\)/);
  assert.doesNotMatch(workspaceSource, /<dt>\{t\("agentWorkspace\.agentCount"\)\}<\/dt>/);
  assert.match(
    workspaceSource,
    /\{t\("agentWorkspace\.reference"\)\}: \{item\.referenceOutput\}/,
  );
  assert.doesNotMatch(workspaceSource, /Reference: \{item\.referenceOutput\}/);

  for (const catalog of [enUiCatalog, zhUiCatalog]) {
    assert.equal(typeof catalog.agentWorkspace.agentCountLabel, "string");
    assert.equal(typeof catalog.agentWorkspace.goodCases, "string");
    assert.equal(typeof catalog.agentWorkspace.badCases, "string");
    assert.equal(typeof catalog.agentWorkspace.reference, "string");
    assert.equal(typeof catalog.agentWorkspace.defaultCases.weeklyFeedback.input, "string");
    assert.equal(typeof catalog.agentWorkspace.defaultCases.uncertainConclusion.reason, "string");
  }
  assert.match(enUiCatalog.agentWorkspace.defaultCases.weeklyFeedback.input, /customer feedback/i);
  assert.match(zhUiCatalog.agentWorkspace.defaultCases.weeklyFeedback.input, /客户反馈/);
});

test("Agent detail request failures use localized messages instead of raw backend responses", () => {
  assert.match(
    workspaceSource,
    /setAgentUsageError\(t\("agentWorkspace\.errors\.loadUsage"\)\)/,
  );
  assert.match(
    workspaceSource,
    /setFeedbackCasesError\(t\("agentWorkspace\.errors\.loadEvaluations"\)\)/,
  );
  assert.match(
    workspaceSource,
    /setOptimizationsError\(t\("agentWorkspace\.errors\.loadOptimizations"\)\)/,
  );
  assert.match(
    workspaceSource,
    /setIntegrationError\(t\("agentWorkspace\.errors\.probeIntegration"\)\)/,
  );
});

test("agent detail exposes optimization recommendations between evaluations and integrations", () => {
  assert.match(clientSource, /export type AgentOptimizationModule =/);
  assert.match(clientSource, /export interface AgentOptimizationSuggestion/);
  assert.match(clientSource, /export interface AgentOptimizationGroup/);
  assert.match(clientSource, /customModule: string \| null/);
  assert.match(clientSource, /items: AgentOptimizationSuggestion\[\]/);
  assert.match(clientSource, /export async function getAgentOptimizations/);
  assert.match(clientSource, /\/web\/evaluation\/optimizations\?\$\{query\.toString\(\)\}/);
  assert.doesNotMatch(workspaceSource, /DEFAULT_OPTIMIZATION_GROUPS/);
  assert.match(workspaceSource, /section === "optimizations"/);
  assert.match(workspaceSource, /getAgentOptimizations\(\{/);
  assert.match(workspaceSource, /setOptimizationGroups\(response\.groups\)/);
  assert.match(workspaceSource, /<OptimizationTable groups=\{optimizationGroups\} \/>/);
  assert.match(workspaceSource, /t\("agentWorkspace\.noOptimizations"\)/);
  assert.match(workspaceSource, /setOptimizationsReloadToken/);
  assert.match(workspaceSource, /<th scope="col">\{t\("agentWorkspace\.fixPriority"\)\}<\/th>/);
  assert.match(workspaceSource, /<th scope="col">\{t\("agentWorkspace\.suggestedModule"\)\}<\/th>/);
  assert.match(workspaceSource, /<th scope="col">\{t\("agentWorkspace\.suggestionAndReason"\)\}<\/th>/);
  assert.match(workspaceSource, /optimizationPriorityLabel\(group\.priority, t\)/);
  assert.match(workspaceSource, /optimizationModuleLabel\(group, t\)/);
  assert.match(workspaceSource, /group\.items\.map/);
  assert.doesNotMatch(workspaceSource, /aw-option-glass/);
  assert.match(workspaceStyles, /\.aw-optimization-table/);
  assert.match(workspaceStyles, /\.aw-optimization-state/);
  assert.match(workspaceStyles, /\.aw-optimization-module/);
  assert.match(workspaceStyles, /\.aw-optimization-list li \+ li/);
  assert.match(workspaceStyles, /\.aw-priority\.is-high/);
  assert.match(workspaceStyles, /\.aw-priority\.is-medium/);
  assert.match(workspaceStyles, /\.aw-priority\.is-low/);
});

test("evaluation tab remains the PR 748 placeholder until the real feature lands", () => {
  assert.match(workspaceSource, /view === "evaluation"/);
  assert.match(workspaceSource, /aw-evaluation-glass/);
  assert.match(workspaceSource, /t\("agentWorkspace\.comingSoon"\)/);
});
