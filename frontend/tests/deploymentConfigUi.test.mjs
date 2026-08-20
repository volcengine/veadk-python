import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const projectPreviewStyles = readFileSync(
  new URL("../src/ui/ProjectPreview.css", import.meta.url),
  "utf8",
);
const adkClientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const agentTypeMetaSource = readFileSync(
  new URL("../src/create/agentTypeMeta.tsx", import.meta.url),
  "utf8",
);
const catalogSource = readFileSync(
  new URL("../src/create/veadkCatalog.ts", import.meta.url),
  "utf8",
);

test("offers code execution with its sandbox configuration", () => {
  assert.match(
    catalogSource,
    /id: "run_code"[\s\S]*?label: "代码沙箱"[\s\S]*?desc: "在沙箱中执行代码"/,
  );
  assert.match(
    catalogSource,
    /importLine: "from veadk\.tools\.builtin_tools\.run_code import run_code"/,
  );
  assert.match(
    catalogSource,
    /key: "AGENTKIT_TOOL_ID",\s*required: true,\s*placeholder: "t-xxxx"/,
  );
  assert.match(
    catalogSource,
    /key: "AGENTKIT_TOOL_REGION",\s*required: false,\s*placeholder: "cn-beijing"/,
  );
  assert.doesNotMatch(catalogSource, /AGENTKIT_TOOL_ID_SCRIPT/);
  assert.match(
    customCreateSource,
    /builtinTools\.includes\("run_code"\)[\s\S]*?<RuntimeEnvFields/,
  );
  assert.match(customCreateSource, /代码沙箱配置[\s\S]*?指定 AgentKit 代码沙箱/);
  assert.match(
    customCreateSource,
    /createGeneratedAgentTestRun\([\s\S]*?debugRuntimeDraft\(variantDraft, transientModelSecretValues\)[\s\S]*?runtimeId: deploymentTarget\.runtimeId[\s\S]*?region: deploymentTarget\.region/,
  );
  assert.match(
    customCreateSource,
    /if \(isImeCompositionEvent\(event\.nativeEvent\)\) return;[\s\S]*?event\.key === "Enter"/,
  );
});

test("reuses the build canvas as a full embedded canvas and expandable standalone preview", () => {
  const embeddedBranchStart = projectPreviewSource.indexOf("{embedded ? (");
  const standaloneBranchStart = projectPreviewSource.indexOf(
    ") : (",
    embeddedBranchStart,
  );
  const embeddedBranch = projectPreviewSource.slice(
    embeddedBranchStart,
    standaloneBranchStart,
  );
  assert.notEqual(embeddedBranchStart, -1);
  assert.notEqual(standaloneBranchStart, -1);
  assert.match(
    projectPreviewSource,
    /import \{ AgentBuildCanvas \} from "\.\.\/create\/AgentBuildCanvas"/,
  );
  assert.match(
    projectPreviewSource,
    /embedded \? \([\s\S]*?<AgentBuildCanvas[\s\S]*?direction="vertical"[\s\S]*?readOnly/,
  );
  assert.match(
    projectPreviewSource,
    /: \([\s\S]*?className="pp-flow-thumbnail"[\s\S]*?<AgentBuildCanvas[\s\S]*?direction="horizontal"[\s\S]*?readOnly/,
  );
  assert.match(
    projectPreviewSource,
    /className="pp-flow-dialog"[\s\S]*?<AgentBuildCanvas[\s\S]*?interactivePreview/,
  );
  assert.doesNotMatch(projectPreviewSource, /Agent 拓扑|pp-topology-pane/);
  assert.doesNotMatch(projectPreviewSource, /导出 YAML|查看源代码|下载源代码|artifactActions/);
  assert.match(
    projectPreviewSource,
    /className="pp-release-description"[\s\S]*?title=\{agentDraft\.description\}/,
  );
  assert.match(
    projectPreviewSource,
    /<dt>Agent 数量<\/dt>/,
  );
  assert.match(projectPreviewSource, /<dt>模型<\/dt>/);
  assert.match(projectPreviewSource, /<dt>描述<\/dt>/);
  assert.match(projectPreviewSource, /<dt>系统提示词<\/dt>/);
  assert.match(projectPreviewSource, /<dt>优化选项<\/dt>/);
  assert.match(
    projectPreviewSource,
    /className="pp-flow-expand"[\s\S]*?aria-label="放大查看执行流程"[\s\S]*?<Maximize2 aria-hidden \/>/,
  );
  assert.doesNotMatch(embeddedBranch, /className="pp-flow-(?:thumbnail|expand)"/);
  assert.doesNotMatch(projectPreviewSource, /<span>放大查看<\/span>/);
  assert.match(
    projectPreviewStyles,
    /\.pp-release-preview\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\)[\s\S]*?\.pp-flow-thumbnail\s*\{[\s\S]*?height:\s*200px;/,
  );
  assert.match(projectPreviewSource, /className="pp-release-card-head">Agent 概览/);
  assert.match(
    projectPreviewSource,
    /: \([\s\S]*?<div className="pp-release-preview">[\s\S]*?<div className="pp-release-info">/,
  );
});

test("lets the whole publish page scroll without a detached action bar", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-root\.is-deploy\s*\{[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-scroll\s*\{[\s\S]*?display:\s*block;[\s\S]*?overflow:\s*visible;/,
  );
  assert.doesNotMatch(
    projectPreviewStyles,
    /\.pp-config-scroll\s*>\s*\.pp-config-section:nth-child/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-section\s*\{[\s\S]*?border:\s*1px solid[\s\S]*?border-radius:\s*18px;[\s\S]*?\.pp-config-label\s*\{[\s\S]*?background:\s*transparent/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-section\s*\{[\s\S]*?box-shadow:\s*none;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-release-info\s*\{[\s\S]*?box-shadow:\s*none;/,
  );
  assert.doesNotMatch(projectPreviewStyles, /\.pp-config-actions\s*\{/);
  assert.doesNotMatch(projectPreviewSource, /className="pp-config-actions"/);
});

test("keeps Runtime name help and errors below the input", () => {
  assert.match(
    projectPreviewSource,
    /className="pp-form-field pp-runtime-name-field"[\s\S]*?className="pp-runtime-name-input"[\s\S]*?className="pp-config-note pp-form-help"[\s\S]*?className="pp-runtime-name-error"/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-form-field\s*\{[\s\S]*?flex-direction:\s*column;[\s\S]*?gap:\s*8px;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-runtime-name-field > \.pp-config-note,[\s\S]*?\.pp-runtime-name-field > \.pp-runtime-name-error\s*\{[\s\S]*?margin:\s*0;/,
  );
  assert.match(
    projectPreviewSource,
    /默认根据 Root Agent 名称生成，并添加随机后缀避免重名/,
  );
  assert.doesNotMatch(projectPreviewSource, /默认根据 Root Agent 名称生成。支持/);
});

test("lets deployment dropdowns escape rounded configuration cards", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-config-section:has\(\.pp-network-region\)\s*\{[^}]*overflow:\s*visible;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-section:has\(\.pp-network-region\) > \.pp-config-label\s*\{[^}]*border-radius:\s*17px 17px 0 0;/,
  );
});

test("aligns the publish overview and deployment settings to one restrained content width", () => {
  assert.match(
    projectPreviewStyles,
    /--pp-publish-content-width:\s*min\(760px, calc\(100% - 48px\)\)/,
  );
  assert.doesNotMatch(
    projectPreviewStyles,
    /--pp-publish-content-width:\s*[^;]*max\(680px/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-root\.is-deploy\.is-embedded\s*\{[\s\S]*?--pp-publish-content-width:\s*100%;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-release-preview\s*\{[\s\S]*?width:\s*var\(--pp-publish-content-width\)/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-head\s*\{[\s\S]*?width:\s*var\(--pp-publish-content-width\)/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-scroll\s*\{[\s\S]*?width:\s*var\(--pp-publish-content-width\)/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-release-info h2\s*\{[\s\S]*?font-size:\s*18px/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-flow-thumbnail \.abc-root,[\s\S]*?width:\s*100%;[\s\S]*?min-width:\s*0;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-release-overview\s*\{[\s\S]*?border-bottom:\s*0;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-release-overview\s*\{[\s\S]*?background:\s*transparent;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-flow-thumbnail\s*\{[\s\S]*?background:\s*transparent;[\s\S]*?box-shadow:\s*none;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-flow-expand\s*\{[\s\S]*?border:\s*0;[\s\S]*?background:\s*transparent;/,
  );
  assert.doesNotMatch(projectPreviewStyles, /\.pp-artifact-actions/);
  assert.match(
    projectPreviewStyles,
    /@media \(max-width:\s*860px\)[\s\S]*?--pp-publish-content-width:\s*min\(88%, calc\(100% - 36px\)\)/,
  );
  assert.doesNotMatch(projectPreviewSource, /DeployIcon|RotateCcw className="pp-ic"/);
  assert.doesNotMatch(projectPreviewSource, /pp-deploy studio-update-action|deploymentActionTargetId/);
});

test("uses a flipping Feishu channel card instead of a switch", () => {
  assert.match(
    projectPreviewSource,
    /className=\{`pp-channel-card\$\{feishuEnabled \? " is-flipped" : ""\}`\}/,
  );
  assert.match(projectPreviewSource, /import feishuLogo from "\.\.\/assets\/feishu-logo\.svg"/);
  assert.match(projectPreviewSource, /<img src=\{feishuLogo\} alt="" \/>/);
  assert.match(projectPreviewSource, /飞书配置/);
  assert.match(projectPreviewSource, /取消中…/);
  assert.doesNotMatch(projectPreviewSource, /role="switch"|className="pp-switch"/);
  assert.match(
    projectPreviewStyles,
    /\.pp-channel-card-inner\s*\{[\s\S]*?transform-style:\s*preserve-3d;[\s\S]*?transition:\s*transform 420ms/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-channel-card\.is-flipped \.pp-channel-card-inner\s*\{[\s\S]*?rotateY\(180deg\)/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-channel-card\s*\{[\s\S]*?grid-template-rows:\s*112px;[\s\S]*?width:\s*clamp\(154px, 33\.333%, 236px\);/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-channel-card\.is-flipped\s*\{[\s\S]*?grid-template-rows:\s*176px/,
  );

  assert.doesNotMatch(projectPreviewSource, /<select[\s\S]*?aria-label="部署区域"/);
  assert.match(projectPreviewSource, /deploymentRegionPicker\(true\)/);
  assert.match(
    projectPreviewSource,
    /<Select[\s\S]*?id="pp-deploy-region"[\s\S]*?triggerClassName="pp-app-select-trigger"/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-region-help\s*\{[\s\S]*?font-size:\s*12px;[\s\S]*?line-height:\s*1\.5;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-channel-remove\s*\{[\s\S]*?background:\s*hsl\(var\(--destructive\) \/ 0\.07\);[\s\S]*?color:\s*hsl\(0 46% 36%\);/,
  );
});

test("matches Agent configuration typography and reduced-motion behavior", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-form-field > label,[\s\S]*?font-size:\s*13px;[\s\S]*?font-weight:\s*400;/,
  );
  assert.match(
    projectPreviewStyles,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.pp-channel-card,[\s\S]*?transition:\s*none;[\s\S]*?\.spin\s*\{[\s\S]*?animation:\s*none;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-channel-card\s*\{[\s\S]*?grid-template-rows:\s*112px;[\s\S]*?transition:\s*grid-template-rows 180ms ease;/,
  );
  assert.doesNotMatch(
    projectPreviewStyles,
    /\.pp-channel-card\s*\{[\s\S]*?transition:\s*height/,
  );
  assert.match(
    projectPreviewStyles,
    /@media \(max-width: 1000px\)[\s\S]*?\.pp-root\.is-deploy\.is-embedded \.pp-config-head\s*\{[\s\S]*?padding-inline:\s*20px;/,
  );
});

test("configures API Key or Identity user-pool authentication for deployment", () => {
  assert.match(
    projectPreviewSource,
    /useState<DeployAuthentication\["type"\]>\("api_key"\)/,
  );
  assert.match(projectPreviewSource, />访问鉴权</);
  assert.match(projectPreviewSource, /label: "API Key"/);
  assert.match(projectPreviewSource, /label: "用户池"/);
  assert.match(
    projectPreviewSource,
    /description: pool\.isCurrent[\s\S]*?`当前用户池 · \$\{pool\.domain \|\| pool\.uid\}`/,
  );
  assert.match(projectPreviewSource, /当前 Studio/);
  assert.match(
    projectPreviewSource,
    /className="pp-user-pool-error" role="alert"[\s\S]*?部署后无法从 Studio[\s\S]*?调用此 Runtime/,
  );
  assert.match(
    projectPreviewSource,
    /<Select[\s\S]*?id="pp-deployment-user-pool"[\s\S]*?loading=\{loading\}[\s\S]*?searchPlaceholder="搜索用户池"/,
  );
  assert.match(
    projectPreviewSource,
    /authenticationType === "user_pool"[\s\S]*?userPoolUid/,
  );
  assert.match(adkClientSource, /"\/web\/identity\/user-pools"/);
  assert.match(adkClientSource, /authentication: opts\?\.authentication/);
  assert.match(projectPreviewSource, /triggerClassName="pp-app-select-trigger"/);
});

test("offers the AgentKit-backed remote Agent type", () => {
  assert.match(agentTypeMetaSource, /label: "远程智能体"/);
  assert.match(
    agentTypeMetaSource,
    /export const AGENT_TYPES:[\s\S]*?AGENT_TYPE_META\.a2a/,
  );
  assert.match(customCreateSource, /AgentKit 智能体中心/);
  assert.match(
    customCreateSource,
    /remoteTypeDisabled\s*=\s*isRootAgent && t\.id === "a2a"/,
  );
});

test("places the add-variable row before any environment variable rows", () => {
  const addRowIndex = projectPreviewSource.indexOf('className="pp-env-add"');
  const tableIndex = projectPreviewSource.indexOf('className="pp-env-table"');

  assert.notEqual(addRowIndex, -1);
  assert.notEqual(tableIndex, -1);
  assert.ok(addRowIndex < tableIndex);
  assert.doesNotMatch(projectPreviewSource, /pp-env-empty|暂无环境变量/);
  assert.match(
    projectPreviewStyles,
    /\.pp-env-add\s*\{[\s\S]*?min-height:\s*40px;[\s\S]*?border:\s*1px dashed/,
  );
});

test("shows the total environment variable count beside the section title", () => {
  assert.match(
    projectPreviewSource,
    /const environmentVariableCount =\s*automaticEnvRows\.length \+ requiredSecretEnv\.length \+ envRows\.length;/,
  );
  assert.match(
    projectPreviewSource,
    /环境变量\s*<span className="pp-agent-child-count pp-env-count">\s*\{environmentVariableCount\} 项/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-env-head \.pp-config-label\s*\{[\s\S]*?align-items:\s*center;[\s\S]*?gap:\s*7px;/,
  );
});

test("keeps ordinary environment values visible while masking secrets", () => {
  assert.doesNotMatch(projectPreviewSource, /showEnvValues|隐藏全部|显示全部/);
  assert.match(
    projectPreviewSource,
    /row\.serverManaged\s*&&\s*row\.key === "MODEL_AGENT_API_KEY"/,
  );
  assert.match(
    projectPreviewSource,
    /type=\{\s*serverManagedModelApiKey\s*\? "text"\s*:\s*row\.secret\s*\? "password"\s*:\s*"text"\s*\}/,
  );
  assert.match(
    projectPreviewSource,
    /className="pp-env-value"[\s\S]*?type="password"[\s\S]*?placeholder="必填，仅用于本次发布"/,
  );
  assert.match(
    projectPreviewSource,
    /placeholder="名称"[\s\S]*?type="text"[\s\S]*?placeholder="值"/,
  );
});

test("lays out network settings as vertical Apps SDK UI controls", () => {
  assert.match(
    projectPreviewSource,
    /className="pp-form-stack pp-network-layout"[\s\S]*?<Select[\s\S]*?id="pp-deployment-network-mode"[\s\S]*?className="pp-network-fields"/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-network-layout\s*\{[\s\S]*?width:\s*100%;/,
  );
});

test("uses the full deployment width for compact environment variables", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-env-section\s*\{[\s\S]*?width:\s*100%/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-env-add\s*\{[\s\S]*?min-height:\s*40px/,
  );
});

test("uses the builder typography hierarchy for deployment configuration", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-config-title\s*\{[\s\S]*?font-size:\s*18px;[\s\S]*?font-weight:\s*650;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-label\s*\{[\s\S]*?font-size:\s*14px;[\s\S]*?font-weight:\s*620;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-env-row input:first-child\s*\{[\s\S]*?font-family:\s*inherit;/,
  );
});

test("requires explicit confirmation before starting deployment", () => {
  const requestConfirmation = projectPreviewSource.slice(
    projectPreviewSource.indexOf(
      "async function requestDeploymentConfirmation",
    ),
    projectPreviewSource.indexOf("async function performDeployment"),
  );
  const performDeployment = projectPreviewSource.slice(
    projectPreviewSource.indexOf("async function performDeployment"),
    projectPreviewSource.indexOf("async function handleAddAgent"),
  );

  assert.match(requestConfirmation, /setDeployConfirmOpen\(true\)/);
  assert.doesNotMatch(requestConfirmation, /await onDeploy/);
  assert.match(performDeployment, /await onDeploy/);
  assert.match(projectPreviewSource, /将创建新的云端 Runtime/);
  assert.match(projectPreviewSource, /将更新并发布到当前云端 Runtime/);
  assert.match(projectPreviewSource, />\s*取消\s*</);
  assert.match(projectPreviewSource, /isUpdate \? "确定更新" : "确定部署"/);
  assert.match(
    projectPreviewSource,
    /disabled=\{deploying \|\| isRuntimeUpdate \|\| !onDeployRegionChange\}/,
  );
  assert.match(
    projectPreviewSource,
    /disabled=\{deploying \|\| isRuntimeUpdate \|\| !onNetworkChange\}/,
  );
  assert.match(projectPreviewSource, /现有 Runtime 的区域与网络模式保持不变。/);
  assert.match(projectPreviewSource, /const networkMode = network\?\.mode \?\? "public"/);
  assert.match(
    projectPreviewSource,
    /id="pp-deployment-network-mode"[\s\S]*?disabled=\{deploying \|\| isRuntimeUpdate \|\| !onNetworkChange\}/,
  );
});

test("creates feedback evaluation sets by default and sends the deployment choice", () => {
  assert.match(
    projectPreviewSource,
    /useState\(true\)[\s\S]*?<strong>自动创建评测集<\/strong>[\s\S]*?部署成功后，自动创建 Good Case 和 Bad Case 评测集。/,
  );
  assert.match(
    projectPreviewSource,
    /const supportsEvaluationSets = cloudProvider !== "byteplus"/,
  );
  assert.match(
    projectPreviewSource,
    /const effectiveCreateEvaluationSets =[\s\S]*supportsEvaluationSets && createEvaluationSets/,
  );
  assert.match(
    projectPreviewSource,
    /<Checkbox[\s\S]*?checked=\{createEvaluationSets\}[\s\S]*?onCheckedChange=\{setCreateEvaluationSets\}/,
  );
  assert.match(
    projectPreviewSource,
    /createEvaluationSets: effectiveCreateEvaluationSets,\s*[\s\S]*?envs,/,
  );
  assert.match(
    adkClientSource,
    /createEvaluationSets:\s*opts\?\.createEvaluationSets/,
  );
  assert.match(
    projectPreviewSource,
    /deployResult\.warnings[\s\S]*?role="status"/,
  );
  assert.match(
    projectPreviewSource,
    /effectiveCreateEvaluationSets[\s\S]*?\[\.\.\.deploymentStepsWithInstanceUpdate, EVALUATION_SET_STEP\][\s\S]*?: deploymentStepsWithInstanceUpdate/,
  );
  assert.match(
    projectPreviewSource,
    /const initialTask: DeploymentTaskUpdate =[\s\S]*?createEvaluationSets: effectiveCreateEvaluationSets,\s*\n\s*};/,
  );
});
