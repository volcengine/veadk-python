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
  assert.match(appSource, /<AgentWorkspace[\s\S]*?agents=\{workspaceAgentEntries\}/);
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

test("evaluation tab remains the PR 748 placeholder until the real feature lands", () => {
  assert.match(workspaceSource, /view === "evaluation"/);
  assert.match(workspaceSource, /aw-evaluation-glass/);
  assert.match(workspaceSource, /敬请期待/);
});
