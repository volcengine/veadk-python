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
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
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

test("Agent navigation opens the PR 748 workspace with creation and evaluation", () => {
  assert.match(appSource, /import \{[\s\S]*?AgentWorkspace[\s\S]*?\} from "\.\/ui\/AgentWorkspace"/);
  assert.match(
    appSource,
    /<AgentWorkspace[\s\S]*?agents=\{detailAgentEntry \? \[detailAgentEntry\] : orderedWorkspaceAgentEntries\}/,
  );
  assert.match(appSource, /const selectWorkspaceAgentFromNavbar = \(id: string\) => \{/);
  assert.match(
    appSource,
    /setFocusedWorkspaceAgentId\(id\)[\s\S]*?setFocusedWorkspaceAgentSection\("basic"\)[\s\S]*?selectAgent\(id\)/,
  );
  assert.match(appSource, /onAppChange=\{showManageAgents \? selectWorkspaceAgentFromNavbar : selectAgent\}/);
  assert.doesNotMatch(appSource, /showManageAgents\s*\?\s*"智能体"/);
  assert.match(workspaceSource, /智能体库/);
  assert.match(workspaceSource, /评测/);
  assert.match(workspaceSource, /view === "library" \? "新建 Agent" : "新建评测组"/);
  assert.match(workspaceSource, /开始评测/);
});

test("workspace drafts stay wired to custom Agent creation", () => {
  assert.match(appSource, /function loadWorkspaceDrafts/);
  assert.match(appSource, /saveWorkspaceDraft/);
  assert.match(appSource, /onDraftChange=\{\(draft, dirty\) =>/);
  assert.match(appSource, /deploymentTarget=\{runtimeUpdateTarget \?\? undefined\}/);
  assert.match(
    appSource,
    /if \(dirty\)[\s\S]*?saveWorkspaceDraft[\s\S]*?else[\s\S]*?restoreWorkspaceDraftBaseline\(editingDraftId\)/,
  );
  assert.match(
    appSource,
    /onDiscard=\{editingDraftId \? \(\) => \{[\s\S]*?restoreWorkspaceDraftBaseline\(editingDraftId\)[\s\S]*?setFocusedWorkspaceAgentId\(appName\)/,
  );
});

test("workspace layout keeps the library and evaluation panes available", () => {
  assert.match(workspaceStyles, /\.aw-view-tabs/);
  assert.match(workspaceStyles, /\.aw-view-tabs button\s*\{[\s\S]*?font-size:\s*14px;/);
  assert.match(workspaceStyles, /\.aw-workspace-frame/);
  assert.match(workspaceStyles, /\.aw-sidebar/);
  assert.doesNotMatch(workspaceSource, /只读预览，可拖动与缩放/);
  assert.match(workspaceStyles, /\.aw-canvas\s*\{[\s\S]*?height:\s*220px;/);
  assert.doesNotMatch(workspaceStyles, /\.aw-canvas-card\s*\{[^}]*min-height:\s*330px/);
});

test("focused agent details can render without the workspace tabs or list sidebar", () => {
  assert.match(workspaceSource, /detailOnly\?: boolean/);
  assert.match(workspaceSource, /aw-root\$\{detailOnly \? " is-detail-only" : ""\}/);
  assert.match(workspaceStyles, /\.aw-root\.is-detail-only \.aw-view-tabs,[\s\S]*?\.aw-root\.is-detail-only \.aw-sidebar[\s\S]*?display: none/);
  assert.match(workspaceStyles, /\.aw-root\.is-detail-only \.aw-workspace\s*\{[\s\S]*?grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(
    appSource,
    /focusedAgentId=\{detailAgentEntry\?\.id \?\? focusedWorkspaceAgentId\}[\s\S]*?detailOnly=\{!!detailAgentEntry \|\| !!focusedDeploymentTaskId\}/,
  );
});

test("agent details show capability badges and deployment state before the flow", () => {
  assert.match(workspaceSource, /const toolNames = useMemo/);
  assert.match(workspaceSource, /const skillNames = useMemo/);
  assert.match(workspaceSource, /<dt>工具<\/dt>[\s\S]*?className="aw-fact-badges"[\s\S]*?toolNames\.map/);
  assert.match(workspaceSource, /<dt>技能<\/dt>[\s\S]*?className="aw-fact-badges"[\s\S]*?skillNames\.map/);
  assert.match(workspaceStyles, /\.aw-fact-badges span\s*\{[\s\S]*?border-radius:\s*999px;/);
  assert.ok(
    workspaceSource.indexOf("<h3>部署配置</h3>") < workspaceSource.indexOf("<strong>执行流程</strong>"),
  );
  assert.match(workspaceSource, /status\.toLowerCase\(\) === "ready"[\s\S]*?className="aw-status-dot"/);
  assert.match(workspaceStyles, /\.aw-readonly-config dd\.is-ready\s*\{[\s\S]*?color:\s*hsl\(142 62% 30%\)/);
  assert.match(workspaceSource, /const executionFlowKey = selectedAgentInfo/);
  assert.match(workspaceSource, /const draftFlowKey = useMemo\(\(\) => canvasDraftKey\(draft\), \[draft\]\)/);
  assert.match(workspaceSource, /const runtimeVersionKey =[\s\S]*?runtimeDetail\?\.currentVersion[\s\S]*?selectedAgent\?\.currentVersion/);
  assert.match(workspaceSource, /detailOnly && selectedAgent\?\.runtimeId && !detailAgentInfoResolved/);
  assert.match(
    workspaceSource,
    /loadingExecutionFlow \? \([\s\S]*?className="aw-canvas-loading"[\s\S]*?正在加载执行流程[\s\S]*?<AgentBuildCanvas[\s\S]*?key=\{executionFlowKey\}/,
  );
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

test("workspace publish flow restores PR 748 deployment lifecycle hooks", () => {
  assert.match(appSource, /const openDeploymentDetail = useCallback/);
  assert.match(appSource, /setFocusedDeploymentTaskId\(task\.id\)/);
  assert.match(appSource, /setAgentDetailTarget\(null\)[\s\S]*?setFocusedDeploymentTaskId\(task\.id\)/);
  assert.match(appSource, /const finishDeployment = useCallback/);
  assert.match(appSource, /await connectRuntime\([\s\S]*?result\.runtimeId[\s\S]*?result\.version/);
  assert.match(appSource, /const \[agentInfoRefreshKey, setAgentInfoRefreshKey\] = useState\(0\)/);
  assert.match(appSource, /}, \[appName, agentInfoRefreshKey\]\);/);
  assert.match(
    appSource,
    /const finishDeployment = useCallback[\s\S]*?setConnections\(loadConnections\(\)\);[\s\S]*?setAgentInfoRefreshKey\(\(key\) => key \+ 1\)/,
  );
  assert.match(appSource, /onDeploymentStarted=\{openDeploymentDetail\}/);
  assert.match(appSource, /onDeploymentComplete=\{finishDeployment\}/);

  assert.match(customCreateSource, /onDeploymentComplete\?: \(result: DeployResult\)/);
  assert.match(customCreateSource, /onDeploymentStarted\?: \(task: DeploymentTaskUpdate\)/);
  assert.match(customCreateSource, /<ProjectPreview[\s\S]*?embedded[\s\S]*?project=\{project\}/);
  assert.match(customCreateSource, /deploymentActionLabel=\{deploymentTarget \? "更新并发布" : "部署"\}/);
  assert.match(customCreateSource, /deploymentRuntimeId=\{deploymentTarget\?\.runtimeId\}/);
  assert.match(customCreateSource, /onDeploymentStarted=\{onDeploymentStarted\}/);
  assert.match(customCreateSource, /onDeploymentComplete=\{onDeploymentComplete\}/);

  assert.match(projectPreviewSource, /deploymentRuntimeId\?: string/);
  assert.match(projectPreviewSource, /onDeploymentStarted\?: \(task: DeploymentTaskUpdate\)/);
  assert.match(projectPreviewSource, /onDeploymentComplete\?: \(result: DeployResult\)/);
  assert.match(projectPreviewSource, /const isRuntimeUpdate = deploymentActionLabel\.includes\("更新"\)/);
  assert.match(projectPreviewSource, /onDeploymentStarted\?\.\(initialTask\)/);
  assert.doesNotMatch(workspaceSource, /aw-deployment-focus/);
  assert.match(
    workspaceSource,
    /className="aw-agent-head"[\s\S]*?deploymentTask\.status !== "success"[\s\S]*?className="aw-detail-deployment"[\s\S]*?<DeploymentProgressCard task=\{deploymentTask\} \/>[\s\S]*?<nav className="aw-agent-tabs"/,
  );
  assert.doesNotMatch(
    workspaceSource,
    /className="aw-basic-stack">\s*\{deploymentTask && <DeploymentProgressCard/,
  );
  assert.match(workspaceStyles, /\.aw-detail-deployment\s*\{[\s\S]*?padding:\s*0 24px 16px;/);
  assert.match(projectPreviewSource, /await onDeploymentComplete\?\.\(result\)/);
  assert.match(projectPreviewSource, /runtimeId: result\.runtimeId \|\| deploymentRuntimeId/);
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
    /\{ label: "部署中", className: " is-deploying" \}/,
  );
  assert.match(
    workspaceSource,
    /selectedAgentUpdateDraft[\s\S]*?onEditDraft\?\.\(selectedAgentUpdateDraft\)/,
  );
  assert.match(
    workspaceSource,
    /const matchingAgent = focusedTask\?\.runtimeId[\s\S]*?agentByRuntimeId\.get/,
  );
  assert.match(workspaceStyles, /\.aw-draft-badge\.is-deploying/);
});

test("deployed agent detail can jump directly to chat", () => {
  assert.match(workspaceSource, /onTalkAgent\?: \(id: string\) => void/);
  assert.match(workspaceSource, /className="aw-talk studio-update-action"[\s\S]*?去对话/);
  assert.match(workspaceSource, /onClick=\{\(\) => onTalkAgent\?\.\(selectedAgent\.id\)\}/);
  assert.match(appSource, /const talkToWorkspaceAgent = \(id: string\) => \{/);
  assert.match(
    appSource,
    /setManageAgents\(false\)[\s\S]*?selectAgent\(id\)/,
  );
  assert.match(appSource, /onTalkAgent=\{talkToWorkspaceAgent\}/);
  assert.match(workspaceStyles, /\.aw-talk svg/);
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
  assert.match(workspaceSource, /正在加载智能体/);
  assert.match(
    workspaceSource,
    /!canUpdate \|\| \(!loadingAgentInfo && !selectedAgentInfo\)/,
  );
  assert.doesNotMatch(
    workspaceSource,
    /!canUpdate \|\| loadingAgentInfo \|\| !selectedAgentInfo/,
  );
  assert.match(workspaceStyles, /\.aw-detail-loading\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?inset:\s*0;/);
});

test("workspace supports deleting individual authorized agents", () => {
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
  assert.match(appSource, /await deleteRuntime\(agent\.runtimeId, agent\.region \?\? "cn-beijing"\)/);
  assert.match(appSource, /onDeleteAgents=\{deleteWorkspaceAgents\}/);
  assert.match(appSource, /const deleteWorkspaceDrafts = useCallback/);
  assert.match(appSource, /onDeleteDrafts=\{deleteWorkspaceDrafts\}/);

  assert.match(workspaceSource, /onDeleteAgents\?: \(agents: AgentEntry\[\]\) => Promise<void>/);
  assert.match(workspaceSource, /onDeleteDrafts\?: \(drafts: WorkspaceAgentDraft\[\]\) => void/);
  assert.match(workspaceSource, /const \[selectionMode, setSelectionMode\] = useState\(false\)/);
  assert.match(workspaceSource, /const \[selectedAgentIds, setSelectedAgentIds\] = useState<Set<string>>/);
  assert.match(workspaceSource, /const \[selectedDraftIds, setSelectedDraftIds\] = useState<Set<string>>/);
  assert.match(workspaceSource, /selectedDeletableAgents/);
  assert.match(workspaceSource, /selectedDeletableDrafts/);
  assert.match(workspaceSource, /window\.confirm\(confirmText\)/);
  assert.match(workspaceSource, /await onDeleteAgents\(selectedDeletableAgents\)/);
  assert.match(workspaceSource, /onDeleteDrafts\?\.\(selectedDeletableDrafts\)/);
  assert.match(workspaceSource, /aria-pressed=\{selectionMode \? isSelectedForDelete : undefined\}/);
  assert.match(workspaceSource, /删除所选/);
  assert.match(workspaceSource, /const deleteSingleAgent = async/);
  assert.match(workspaceSource, /const deleteSingleDraft = /);
  assert.match(workspaceSource, /删除 Agent/);
  assert.match(workspaceSource, /删除草稿/);
  assert.match(workspaceStyles, /\.aw-selection-toolbar/);
  assert.match(workspaceStyles, /\.aw-select-marker\.is-checked/);
  assert.match(workspaceStyles, /\.aw-head-delete/);
  assert.match(
    workspaceStyles,
    /\.aw-head-delete\.studio-update-action:hover:not\(:disabled\)[\s\S]*?color:\s*#fff;/,
  );
  assert.match(
    workspaceSource,
    /className="aw-basic-actions"[\s\S]*?className="aw-update studio-update-action"[\s\S]*?className="aw-head-delete studio-update-action"/,
  );
});

test("agent detail evaluation tab reads feedback datasets", () => {
  assert.match(clientSource, /export interface AgentFeedbackCase/);
  assert.match(clientSource, /export async function getAgentFeedbackCases/);
  assert.match(clientSource, /export async function deleteAgentFeedbackCases/);
  assert.match(clientSource, /export function clearMessageFeedbackCache/);
  assert.match(clientSource, /\/web\/evaluation\/feedback-cases\?\$\{query\.toString\(\)\}/);
  assert.match(clientSource, /\/web\/evaluation\/feedback-cases\/delete/);
  assert.match(workspaceSource, /getAgentFeedbackCases\(\{/);
  assert.match(workspaceSource, /deleteAgentFeedbackCases\(\{/);
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
  assert.match(appSource, /返回评测案例/);
  assert.match(appSource, /clearDeletedFeedbackCases/);
  assert.match(appSource, /clearMessageFeedbackCache/);
  assert.match(appSource, /onFeedbackCasesDeleted=\{clearDeletedFeedbackCases\}/);
  assert.match(appSource, /onOpenFeedbackCase=\{\(item\) => void openFeedbackCaseInStudio\(item\)\}/);
  assert.match(appSource, /turnNodeRefs/);
  assert.match(appSource, /is-feedback-target/);
  assert.match(workspaceSource, /feedbackSetFor\(feedbackSets, kind\)/);
  assert.match(workspaceSource, /Good cases/);
  assert.match(workspaceSource, /Bad cases/);
  assert.match(workspaceSource, /AgentKit 评测集/);
  assert.match(workspaceStyles, /\.aw-case-summary/);
  assert.match(appSource, /case-return-bar/);
  assert.match(workspaceStyles, /\.aw-case-toolbar/);
  assert.match(workspaceStyles, /\.aw-case-delete/);
  assert.match(workspaceStyles, /\.aw-case-output-preview/);
  assert.match(workspaceStyles, /-webkit-line-clamp: 3/);
  assert.match(workspaceStyles, /\.aw-case-expand/);
  assert.match(workspaceStyles, /\.aw-case-row\.is-focused/);
  assert.match(workspaceStyles, /\.aw-case-tag\.is-good/);
  assert.match(workspaceStyles, /\.aw-case-error/);
});

test("evaluation tab remains the PR 748 placeholder until the real feature lands", () => {
  assert.match(workspaceSource, /view === "evaluation"/);
  assert.match(workspaceSource, /aw-evaluation-glass/);
  assert.match(workspaceSource, /敬请期待/);
});
