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

test("Agent navigation opens the PR 748 workspace with creation and evaluation", () => {
  assert.match(appSource, /import \{[\s\S]*?AgentWorkspace[\s\S]*?\} from "\.\/ui\/AgentWorkspace"/);
  assert.match(appSource, /<AgentWorkspace[\s\S]*?agents=\{orderedWorkspaceAgentEntries\}/);
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
  assert.match(workspaceStyles, /\.aw-workspace-frame/);
  assert.match(workspaceStyles, /\.aw-sidebar/);
});

test("workspace publish flow restores PR 748 deployment lifecycle hooks", () => {
  assert.match(appSource, /const openDeploymentDetail = useCallback/);
  assert.match(appSource, /setFocusedDeploymentTaskId\(task\.id\)/);
  assert.match(appSource, /const finishDeployment = useCallback/);
  assert.match(appSource, /await connectRuntime\([\s\S]*?result\.runtimeId[\s\S]*?result\.version/);
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

test("workspace agents can be reordered by drag or keyboard", () => {
  assert.match(appSource, /function workspaceAgentOrderKey\(userId: string\)/);
  assert.match(appSource, /const \[workspaceAgentOrder, setWorkspaceAgentOrder\] = useState<string\[\]>\(\[\]\)/);
  assert.match(appSource, /const saveWorkspaceAgentOrder = useCallback/);
  assert.match(appSource, /agents=\{orderedWorkspaceAgentEntries\}/);
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

test("workspace supports selecting and deleting authorized agents", () => {
  assert.match(appSource, /deleteRuntime/);
  assert.match(appSource, /removeRuntimeConnection/);
  assert.match(appSource, /libraryRuntimePermissions/);
  assert.match(appSource, /canDelete: runtime\.canDelete/);
  assert.match(appSource, /canDelete: entry\.runtimeId[\s\S]*?libraryRuntimePermissions\[entry\.runtimeId\]\?\.canDelete === true/);
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
});

test("evaluation tab remains the PR 748 placeholder until the real feature lands", () => {
  assert.match(workspaceSource, /view === "evaluation"/);
  assert.match(workspaceSource, /aw-evaluation-glass/);
  assert.match(workspaceSource, /敬请期待/);
});
