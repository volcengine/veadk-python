import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const addAgentMenuSource = readFileSync(
  new URL("../src/ui/AddAgentMenu.tsx", import.meta.url),
  "utf8",
);
const addAgentMenuStyles = readFileSync(
  new URL("../src/ui/AddAgentMenu.css", import.meta.url),
  "utf8",
);
const packageCreateSource = readFileSync(
  new URL("../src/create/CodePackageCreate.tsx", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const projectPreviewStyles = readFileSync(
  new URL("../src/ui/ProjectPreview.css", import.meta.url),
  "utf8",
);
const appStyles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const packageCreateStyles = readFileSync(
  new URL("../src/create/CodePackageCreate.css", import.meta.url),
  "utf8",
);
const zipSource = readFileSync(
  new URL("../src/create/skills/zip.ts", import.meta.url),
  "utf8",
);

test("offers code package deployment beside scratch creation", () => {
  assert.match(
    appSource,
    /key: "package"[\s\S]*?title: "从代码包添加和部署"/,
  );
  assert.match(appSource, /icon: PackageIcon/);
  assert.doesNotMatch(appSource, /import \{ FileArchive \} from "lucide-react"/);
  assert.match(appSource, /import \{ CodePackageCreate \}/);
  assert.match(appSource, /visibleCreateView === "package"/);
});

test("opens custom creation directly from scratch creation", () => {
  assert.match(
    appSource,
    /key: "scratch"[\s\S]*?setCustomCreateMode\("custom"\)[\s\S]*?setCreateView\("custom"\)/,
  );
  assert.doesNotMatch(appSource, /import \{ QuickCreate/);
  assert.doesNotMatch(appSource, /visibleCreateView === "menu"/);
});

test("imports exported YAML into custom creation", () => {
  assert.match(appSource, /import \{ yamlToDraft \} from "\.\/create\/configYaml"/);
  assert.match(
    appSource,
    /const imported = yamlToDraft\(text\)[\s\S]*?setCustomCreateMode\("yaml_import"\)[\s\S]*?setCreateView\("custom"\)/,
  );
  assert.match(
    appSource,
    /key: "yaml-import"[\s\S]*?title: "导入 YAML"[\s\S]*?onClick: openYamlImportPicker/,
  );
  assert.match(
    appSource,
    /accept="\.yaml,\.yml,text\/yaml,application\/x-yaml"/,
  );
});

test("uses thin hand-drawn icons for all add-agent options", () => {
  for (const iconName of [
    "ScratchIcon",
    "PackageIcon",
    "YamlImportIcon",
    "MigrationIcon",
  ]) {
    assert.match(
      appSource,
      new RegExp(`function ${iconName}\\([\\s\\S]*?strokeWidth="1\\.45"`),
    );
  }
  assert.match(
    appSource,
    /function ScratchIcon[\s\S]*?<rect[\s\S]*?<path d="M12 8\.5v7M8\.5 12h7"/,
  );
});

test("shows existing-project migration as an enabled option", () => {
  assert.match(
    appSource,
    /key: "migration"[\s\S]*?title: "从存量迁移"[\s\S]*?desc: "从您的 LangChain \/ Dify 等存量项目迁移至 AgentKit Runtime"[\s\S]*?setCreateView\("migration"\)/,
  );
  assert.doesNotMatch(
    appSource,
    /key: "migration"[\s\S]*?status: "敬请期待"[\s\S]*?disabled: true/,
  );
  assert.match(addAgentMenuSource, /disabled=\{c\.disabled\}/);
  assert.match(
    addAgentMenuSource,
    /c\.status && <span className="stk-card-status">\{c\.status\}<\/span>/,
  );
  assert.match(addAgentMenuStyles, /\.stk-card-status\s*\{/);
});

test("validates and previews uploaded zip projects before deployment", () => {
  assert.match(packageCreateSource, /from "\.\/skills\/zip"/);
  assert.match(packageCreateSource, /accept="\.zip,application\/zip"/);
  assert.match(packageCreateSource, /normalizePackageEntries/);
  assert.match(packageCreateSource, /agentkit\.yaml/);
  assert.match(packageCreateSource, /entry_point/);
  assert.match(packageCreateSource, /app\.py/);
  assert.match(
    packageCreateSource,
    /可使用 app\.py，或由 agentkit\.yaml 声明入口/,
  );
  assert.match(packageCreateSource, /maxUncompressedBytes: MAX_PACKAGE_BYTES/);
  assert.match(zipSource, /options\.maxUncompressedBytes/);
  assert.match(packageCreateSource, /deploymentPrimaryPane=/);
  assert.match(packageCreateSource, /className="package-source-pane"/);
  assert.match(packageCreateSource, /请上传代码包/);
  assert.doesNotMatch(packageCreateSource, /<FileArchive/);
  assert.match(packageCreateSource, /role="button"/);
  assert.match(packageCreateSource, /aria-label=\{project \? "重新上传代码包" : "上传代码包"\}/);
  assert.doesNotMatch(packageCreateSource, />选择压缩包</);
  assert.match(packageCreateSource, /onChange=\{setProject\}/);
});

test("shows upload, image build, runtime creation, and publish progress", () => {
  assert.match(
    projectPreviewSource,
    /deploymentPrimaryPane\s*\?\s*CODE_PACKAGE_DEPLOY_STEPS\s*:\s*DEPLOY_STEPS/,
  );
  assert.match(
    projectPreviewSource,
    /phase: "upload", label: "上传代码包"/,
  );
  assert.match(
    projectPreviewSource,
    /phase: "build", label: "镜像打包"/,
  );
  assert.match(
    projectPreviewSource,
    /phase: "deploy", label: "创建 Runtime"/,
  );
  assert.match(clientSource, /phase: "upload"/);
  assert.match(clientSource, /正在上传代码包/);
  assert.match(clientSource, /正在校验迁移产物/);
});

test("passes the selected region and network to AgentKit deployment", () => {
  assert.match(packageCreateSource, /region: deployRegion/);
  assert.match(packageCreateSource, /vpc_id: network\.vpcId/);
  assert.match(packageCreateSource, /subnet_ids: network\.subnetIds/);
  assert.match(packageCreateSource, /deployAgentkitProject\(/);
});

test("uses the shared deployment lifecycle for uploaded packages", () => {
  assert.match(appSource, /<CodePackageCreate[\s\S]*?onDeploymentStarted=\{startDeployment\}/);
  assert.match(appSource, /<CodePackageCreate[\s\S]*?onDeploymentComplete=\{finishDeployment\}/);
  assert.match(packageCreateSource, /onDeploymentStarted\?: \(task: DeploymentTaskUpdate\)/);
  assert.match(packageCreateSource, /onDeploymentComplete\?: \(result: DeployResult\)/);
  assert.match(packageCreateSource, /onDeploymentStarted=\{onDeploymentStarted\}/);
  assert.match(packageCreateSource, /onDeploymentComplete=\{onDeploymentComplete\}/);
});

test("hides message channels for code package deployment", () => {
  assert.match(
    projectPreviewSource,
    /!deploymentPrimaryPane\s*&&\s*\([\s\S]*?消息渠道/,
  );
});

test("centers code package deployment in a single configuration column", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-root\.is-deploy\.has-primary-pane \.pp-body\s*\{[\s\S]*?justify-content:\s*center/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-root\.is-deploy\.has-primary-pane \.pp-config\s*\{[\s\S]*?width:\s*min\(760px, 100%\)/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-root\.is-deploy\.has-primary-pane \.pp-config-head,[\s\S]*?\.pp-config-actions\s*\{[\s\S]*?border:\s*0/,
  );
  assert.match(packageCreateSource, /className="package-source-label">代码包/);
  assert.match(packageCreateStyles, /\.package-dropzone\s*\{[\s\S]*?min-height:\s*152px/);
});

test("uses a themed region menu and a centered icon-free deploy button", () => {
  assert.match(projectPreviewSource, /className="pp-region-trigger"/);
  assert.match(projectPreviewSource, /role="listbox" aria-label="部署区域"/);
  assert.match(
    projectPreviewStyles,
    /\.pp-root\.is-deploy\.has-primary-pane \.pp-config-actions\s*\{[\s\S]*?justify-content:\s*center/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-root\.is-deploy\.has-primary-pane \.pp-config-actions\s*\{[\s\S]*?position:\s*sticky/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-root\.is-deploy\.has-primary-pane \.pp-config-actions\s*\{[\s\S]*?bottom:\s*0/,
  );
  assert.doesNotMatch(projectPreviewSource, /<DeployIcon/);
});

test("uses the PR 748 update-button treatment for deployment", () => {
  assert.match(projectPreviewSource, /className="pp-deploy studio-update-action"/);
  assert.match(
    appStyles,
    /\.studio-update-action\s*\{[\s\S]*?min-width:\s*104px;[\s\S]*?min-height:\s*40px;[\s\S]*?border-radius:\s*999px;/,
  );
  assert.match(
    appStyles,
    /\.studio-update-action:not\(:disabled\):hover\s*\{[\s\S]*?background:\s*#29292b;[\s\S]*?color:\s*#fff;/,
  );
});
