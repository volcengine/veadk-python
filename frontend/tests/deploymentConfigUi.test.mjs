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
    /id: "run_code"[\s\S]*?label: "代码执行"[\s\S]*?desc: "在沙箱中执行代码"/,
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
  assert.match(
    customCreateSource,
    /createGeneratedAgentTestRun\(debugRuntimeDraft\(draft\)\)/,
  );
  assert.match(
    customCreateSource,
    /if \(isImeCompositionEvent\(e\.nativeEvent\)\) return;[\s\S]*?e\.key === "Enter"/,
  );
});

test("shares the create-page agent type icons with the deployment topology", () => {
  assert.match(customCreateSource, /from "\.\/agentTypeMeta"/);
  assert.match(projectPreviewSource, /from "\.\.\/create\/agentTypeMeta"/);
  assert.match(
    projectPreviewSource,
    /const meta = agentTypeMeta\(agent\.type\)/,
  );
  assert.doesNotMatch(projectPreviewSource, /function topologyIcon/);

  for (const icon of ["LlmIcon", "GitBranch", "Split", "Repeat", "Globe"]) {
    assert.match(agentTypeMetaSource, new RegExp(`icon: ${icon}`));
  }
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
    /remoteTypeDisabled = isRootAgent && t\.id === "a2a"/,
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
    /\.pp-env-add\s*\{[\s\S]*?min-height:\s*52px;[\s\S]*?border:\s*1px dashed/,
  );
});

test("shows the total environment variable count beside the section title", () => {
  assert.match(
    projectPreviewSource,
    /const environmentVariableCount = automaticEnvRows\.length \+ envRows\.length;/,
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

test("uses the builder typography hierarchy for deployment configuration", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-config-title\s*\{[\s\S]*?font-size:\s*17px;[\s\S]*?font-weight:\s*650;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-label\s*\{[\s\S]*?font-size:\s*15px;[\s\S]*?font-weight:\s*650;/,
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
  assert.match(
    projectPreviewSource,
    /将创建新的云端 Runtime，部署过程可能需要几分钟。确定继续吗？/,
  );
  assert.match(
    projectPreviewSource,
    /将更新并发布到当前云端 Runtime，过程可能需要几分钟。确定继续吗？/,
  );
  assert.match(projectPreviewSource, />\s*取消\s*</);
  assert.match(
    projectPreviewSource,
    /isUpdate \? "确定更新" : "确定部署"/,
  );
});
