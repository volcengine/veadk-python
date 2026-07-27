import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

const appSource = read("App.tsx");
const sidebarSource = read("ui/Sidebar.tsx");
const searchSource = read("ui/Search.tsx");
const workspaceSource = read("ui/AgentWorkspace.tsx");
const workspaceStyles = read("ui/AgentWorkspace.css");
const customCreateSource = read("create/CustomCreate.tsx");
const customCreateStyles = read("create/CustomCreate.css");

test("reduces the primary sidebar to new chat, agents, and search", () => {
  const newChat = sidebarSource.indexOf('aria-label="新会话"');
  const agents = sidebarSource.indexOf('aria-label="智能体"');
  const search = sidebarSource.indexOf("<SearchButton");

  assert.ok(newChat >= 0 && agents > newChat && search > agents);
  assert.doesNotMatch(sidebarSource, /SkillCenterButton|>添加 Agent<|>管理 Agent</);
  assert.match(searchSource, /aria-label="搜索"[\s\S]*?sidebar-nav-label">搜索/);
});

test("renders the unified agent workspace from the app", () => {
  assert.match(appSource, /AgentWorkspace,[\s\S]*from "\.\/ui\/AgentWorkspace"/);
  assert.match(appSource, /showManageAgents \? \([\s\S]*?<AgentWorkspace/);
  assert.match(appSource, /showManageAgents[\s\S]*?\? "智能体"/);
});

test("starts new Agents from the creation-method chooser", () => {
  const createStart = appSource.indexOf("onCreateAgent={() => {");
  const updateStart = appSource.indexOf("onUpdateAgent={(nextDraft)", createStart);
  assert.ok(createStart >= 0 && updateStart > createStart);
  const createBlock = appSource.slice(createStart, updateStart);
  assert.match(createBlock, /setAddMenu\(true\)/);
  assert.match(createBlock, /setCreateView\(null\)/);
  assert.doesNotMatch(createBlock, /setCreateView\("custom"\)/);
  assert.match(
    appSource,
    /<QuickCreate[\s\S]*?onSelect=\{\(k\) => \{[\s\S]*?k === "custom" \? `draft-\$\{Date\.now\(\)\.toString\(36\)\}` : ""[\s\S]*?setCreateView\(k\)/,
  );
});

test("normalizes legacy cloud topology nodes with omitted collections", () => {
  assert.match(workspaceSource, /const runtimeTools = node\.tools \?\? \[\]/);
  assert.match(workspaceSource, /builtinTools:\s*builtinTools\.map\(\(tool\) => tool\.id\)/);
  assert.match(workspaceSource, /skills:\s*\(node\.skills \?\? \[\]\)\.map/);
  assert.match(workspaceSource, /subAgents:\s*\(node\.children \?\? \[\]\)\.map\(graphNodeToDraft\)/);
  assert.match(workspaceSource, /info\?\.skills\?\.map/);
});

test("uses a lightweight Agent list with an explicit empty selection", () => {
  assert.match(workspaceSource, /className="aw-view-tabs"/);
  assert.doesNotMatch(workspaceSource, /className="aw-header"/);
  assert.match(workspaceSource, /className="aw-create-card"[\s\S]*?新建 Agent/);
  assert.match(workspaceSource, /useState\(""\)[\s\S]*?未选择智能体/);
  assert.match(workspaceStyles, /\.aw-create-card\s*\{[\s\S]*?border:\s*1px dashed/);
  assert.doesNotMatch(workspaceStyles, /\.aw-agent-copy small::before/);
  assert.match(workspaceStyles, /\.aw-content\s*\{[\s\S]*?margin-top:\s*12px[\s\S]*?padding:\s*0 24px 80px/);
  assert.match(workspaceStyles, /\.aw-agent-list\s*\{[\s\S]*?flex:\s*1 1 auto/);
  assert.match(workspaceStyles, /\.aw-list-empty\s*\{[\s\S]*?flex:\s*1 1 auto[\s\S]*?align-items:\s*center[\s\S]*?justify-content:\s*center/);
  assert.match(workspaceStyles, /\.aw-list-count\s*\{[\s\S]*?flex:\s*0 0 auto/);
});

test("combines basic information, evaluation sets, optimization, and deployment", () => {
  for (const label of ["基本信息", "评测集"]) {
    assert.match(workspaceSource, new RegExp(`label: "${label}"`));
  }
  assert.doesNotMatch(workspaceSource, /label: "优化项"|label: "部署配置"/);
  assert.match(workspaceSource, /<AgentBuildCanvas[\s\S]*?readOnly[\s\S]*?interactivePreview/);
  assert.match(workspaceSource, /className="aw-basic-stack"[\s\S]*?aw-canvas-card[\s\S]*?aw-details-card[\s\S]*?aw-deployment-panel[\s\S]*?aw-option-panel[\s\S]*?onUpdateAgent\(draft\)/);
  assert.match(workspaceSource, /上下文优化[\s\S]*?幻觉抑制[\s\S]*?工具调用优化/);
  assert.match(workspaceSource, /aw-deployment-panel[\s\S]*?aw-readonly-config/);
  assert.doesNotMatch(workspaceSource, /aw-readonly-badge|>只读</);
  assert.doesNotMatch(workspaceSource, /aw-coming-soon/);
  assert.match(workspaceSource, /className="aw-option-content"[\s\S]*?className="aw-option-list"[\s\S]*?className="aw-option-glass" role="status"[\s\S]*?暂未开放/);
  assert.match(workspaceStyles, /\.aw-option-glass\s*\{[\s\S]*?backdrop-filter:\s*blur\(10px\)/);
  assert.doesNotMatch(workspaceSource, /保存配置|workspace-network|setDeploymentSaved/);
  assert.match(workspaceStyles, /\.aw-basic-actions\s*\{[\s\S]*?position:\s*absolute[\s\S]*?left:\s*50%[\s\S]*?transform:\s*translateX\(-50%\)/);
  assert.match(workspaceSource, /section === "evaluations"[\s\S]*?className="aw-case-filters"[\s\S]*?<CaseTable/);
  assert.match(workspaceSource, /Good case[\s\S]*?Bad case[\s\S]*?aria-label="搜索评测案例"/);
  assert.doesNotMatch(workspaceSource, /caseFilter === "all"|<span>类型<\/span>/);
  assert.match(workspaceSource, /item\.input} \$\{item\.expectation} \$\{item\.tag}/);
  assert.doesNotMatch(workspaceSource, /沉淀 Good Case 与 Bad Case/);
  assert.match(workspaceStyles, /\.aw-update\s*\{[\s\S]*?border:\s*0[\s\S]*?border-radius:\s*999px[\s\S]*?background:\s*rgba\(232, 232, 237, 0\.72\)[\s\S]*?box-shadow:\s*none[\s\S]*?backdrop-filter:\s*blur\(7px\)/);
  assert.match(workspaceStyles, /\.aw-update:not\(:disabled\):hover\s*\{[\s\S]*?border:\s*0[\s\S]*?background:\s*#000[\s\S]*?color:\s*white/);
  assert.match(workspaceSource, /aw-version-badge[\s\S]*?v\{agent\.currentVersion\}/);
});

test("shows the selected Agent deployment progress and reuses its draft for updates", () => {
  assert.match(appSource, /<AgentWorkspace[\s\S]*?deploymentTasks=\{deploymentTasks\}/);
  assert.match(workspaceSource, /task\.runtimeId === selectedAgent\.runtimeId/);
  assert.match(workspaceSource, /task\.runtimeName === selectedAgent\.label/);
  assert.match(workspaceSource, /className=\{`aw-deploy-progress-card is-\$\{task\.status\}`\}/);
  assert.match(workspaceSource, /const DEPLOYMENT_STEPS = \[[\s\S]*?准备部署[\s\S]*?构建镜像[\s\S]*?部署服务[\s\S]*?发布服务[\s\S]*?部署完成/);
  assert.match(workspaceSource, /deploymentTask\?\.status === "running"[\s\S]*?aw-deployment-focus[\s\S]*?<DeploymentProgressCard/);
  assert.match(workspaceSource, /className="aw-deploy-steps"[\s\S]*?is-\$\{status\}/);
  assert.match(workspaceSource, /role="progressbar"[\s\S]*?aria-valuenow=\{Math\.round\(progress\)\}/);
  assert.match(workspaceStyles, /\.aw-deploy-step-copy p\s*\{[\s\S]*?overflow-wrap:\s*anywhere[\s\S]*?word-break:\s*break-word/);
  assert.match(workspaceSource, /if \(info\?\.draft\) return info\.draft/);
  assert.match(workspaceSource, /agentInfoAgentId === activeAgentId \? agentInfo : null/);
  assert.match(workspaceSource, /disabled=\{[\s\S]*?loadingAgentInfo[\s\S]*?!selectedAgentInfo[\s\S]*?\}/);
  assert.match(appSource, /setImportedDraft\(nextDraft\)[\s\S]*?runtimeId: currentConn\.runtimeId[\s\S]*?setCreateView\("custom"\)/);
  assert.match(appSource, /initialDraft=\{importedDraft \?\? undefined\}[\s\S]*?deploymentTarget=\{runtimeUpdateTarget \?\? undefined\}/);
  assert.match(appSource, /getAgentInfo\(appName\)[\s\S]*?\}, \[agentInfoRefreshKey, appName\]\)/);
});

test("creates update drafts only after a real edit and supports discarding changes", () => {
  const updateStart = appSource.indexOf("onUpdateAgent={(nextDraft)");
  const editDraftStart = appSource.indexOf("onEditDraft={(item)", updateStart);
  assert.ok(updateStart >= 0 && editDraftStart > updateStart);
  assert.doesNotMatch(appSource.slice(updateStart, editDraftStart), /saveWorkspaceDraft/);
  assert.match(
    customCreateSource,
    /initialDraftSnapshotRef = useRef\(JSON\.stringify\(draft\)\)[\s\S]*?lastNotifiedDraftSnapshotRef[\s\S]*?draftDirty = draftSnapshot !== initialDraftSnapshotRef\.current/,
  );
  assert.match(
    customCreateSource,
    /if \(draftSnapshot === lastNotifiedDraftSnapshotRef\.current\) return;[\s\S]*?onDraftChangeRef\.current\?\.\(draft, draftDirty\)/,
  );
  assert.match(
    appSource,
    /onDraftChange=\{\(nextDraft, dirty\) => \{[\s\S]*?if \(dirty\)[\s\S]*?saveWorkspaceDraft[\s\S]*?restoreWorkspaceDraftBaseline\(editingDraftId\)/,
  );
  assert.match(
    customCreateSource,
    /className="cw-discard-edit"[\s\S]*?放弃编辑[\s\S]*?放弃本次编辑？/,
  );
  assert.match(
    appSource,
    /onDiscard=\{\(\) => \{[\s\S]*?restoreWorkspaceDraftBaseline\(editingDraftId\)[\s\S]*?setManageAgents\(true\)/,
  );
  assert.match(
    customCreateStyles,
    /\.cw-discard-edit:hover:not\(:disabled\)\s*\{[\s\S]*?var\(--destructive\)/,
  );
});

test("supports configurable evaluation groups and historical results", () => {
  assert.match(workspaceSource, /智能体库/);
  assert.match(workspaceSource, /新建评测组/);
  assert.match(workspaceSource, /评测配置[\s\S]*?历史结果/);
  assert.match(workspaceSource, /参评智能体[\s\S]*?评测集[\s\S]*?评估器/);
  assert.match(workspaceSource, /评测指标/);
  assert.match(workspaceSource, /并发数/);
  assert.match(workspaceSource, /group\.history\.map/);
  assert.match(workspaceSource, /aw-workspace-frame[\s\S]*?view === "evaluation"[\s\S]*?aw-evaluation-glass[\s\S]*?敬请期待/);
  assert.match(workspaceStyles, /\.aw-evaluation-glass\s*\{[\s\S]*?inset:\s*0[\s\S]*?backdrop-filter:\s*blur\(9px\)/);
  assert.match(workspaceStyles, /\.aw-search:focus-within\s*\{[\s\S]*?background:\s*hsl\(var\(--secondary\) \/ 0\.42\)[\s\S]*?box-shadow:\s*none/);
  assert.match(workspaceStyles, /\.aw-search input:focus-visible[\s\S]*?outline:\s*none !important/);
  assert.match(workspaceStyles, /\.aw-workspace\s*\{[\s\S]*?grid-template-columns:\s*304px minmax\(0, 1fr\)/);
});
