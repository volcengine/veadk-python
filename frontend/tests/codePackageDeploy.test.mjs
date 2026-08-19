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
const createAgentIconsSource = readFileSync(
  new URL("../src/ui/icons/CreateAgentIcons.tsx", import.meta.url),
  "utf8",
);
const createAgentHeaderSource = readFileSync(
  new URL("../src/ui/CreateAgentHeader.tsx", import.meta.url),
  "utf8",
);
const createAgentHeaderStyles = readFileSync(
  new URL("../src/ui/CreateAgentHeader.css", import.meta.url),
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
    addAgentMenuSource,
    /key: "template"[\s\S]*?title: "从空白创建"[\s\S]*?description: "手动配置并创建智能体"/,
  );
  assert.doesNotMatch(addAgentMenuSource, /基于模板|选择模板进行创建/);
  assert.match(
    addAgentMenuSource,
    /key: "package"[\s\S]*?title: "上传代码包"/,
  );
  assert.match(addAgentMenuSource, /icon: CodePackageIcon/);
  assert.doesNotMatch(appSource, /import \{ FileArchive \} from "lucide-react"/);
  assert.match(appSource, /import \{ CodePackageCreate \}/);
  assert.match(appSource, /visibleCreateView === "package"/);
});

test("opens custom creation directly from the template entry", () => {
  assert.match(
    appSource,
    /onTemplate=\{\(\) => \{[\s\S]*?setCustomCreateMode\("custom"\)[\s\S]*?setCreateView\("custom"\)/,
  );
  assert.doesNotMatch(appSource, /import \{ QuickCreate/);
  assert.doesNotMatch(appSource, /visibleCreateView === "menu"/);
});

test("uses the Figma SVG paths for all create-agent entry icons", () => {
  for (const iconName of [
    "TemplateBlocksIcon",
    "CodePackageIcon",
    "ExistingMigrationIcon",
  ]) {
    assert.match(
      createAgentIconsSource,
      new RegExp(`function ${iconName}\\(`),
    );
  }
  assert.match(
    createAgentIconsSource,
    /M10 21V8C10 7\.73478/,
  );
  assert.match(createAgentIconsSource, /M13\.2675 2\.83686/);
  assert.match(createAgentIconsSource, /M12 9\.00019L4\.06386/);
  assert.doesNotMatch(addAgentMenuSource, /lucide-react/);
});

test("shows existing-project migration as an enabled option", () => {
  assert.match(
    addAgentMenuSource,
    /key: "migration"[\s\S]*?title: "存量迁移"[\s\S]*?description: "从 LangChain\/Dify 等迁移"/,
  );
  assert.match(
    addAgentMenuSource,
    /from "@openai\/apps-sdk-ui\/components\/Button"/,
  );
  assert.match(
    addAgentMenuSource,
    /from "@openai\/apps-sdk-ui\/components\/Input"/,
  );
  assert.match(
    createAgentHeaderSource,
    /from "@openai\/apps-sdk-ui\/components\/SegmentedControl"/,
  );
  assert.match(appSource, /onMigration=\{\(\) => \{[\s\S]*?setCreateView\("migration"\)/);
  assert.match(addAgentMenuStyles, /\.create-entry-card\s*\{/);
  assert.doesNotMatch(addAgentMenuSource, /Badge|ChevronRight/);
});

test("matches the Figma create-agent landing geometry", () => {
  assert.match(addAgentMenuSource, /描述你想创建的智能体/);
  assert.doesNotMatch(createAgentHeaderSource, /画布模式|表单模式/);
  assert.match(createAgentHeaderSource, /<CreateDownloadIcon \/>[\s\S]*?代码/);
  assert.match(createAgentHeaderSource, /<CreateDebugIcon \/>[\s\S]*?调试/);
  assert.match(createAgentHeaderSource, /<CreateDeployIcon \/>[\s\S]*?部署/);
  assert.match(createAgentHeaderSource, /画布预览/);
  assert.match(createAgentHeaderSource, /列表预览/);
  assert.match(createAgentHeaderSource, /添加对照/);
  assert.match(createAgentHeaderSource, /退出调试/);
  assert.doesNotMatch(createAgentHeaderSource, /CreateShareIcon|collaborator/);
  assert.match(addAgentMenuStyles, /--create-canvas:\s*#f0f0f0/);
  assert.match(addAgentMenuStyles, /background-size:\s*18px 18px/);
  assert.match(addAgentMenuStyles, /\.create-entry-input\s*\{[\s\S]*?--input-size:\s*54px/);
  assert.match(addAgentMenuStyles, /\.create-entry-cards\s*\{[\s\S]*?width:\s*min\(800px/);
  assert.match(addAgentMenuStyles, /\.create-entry-card\s*\{[\s\S]*?width:\s*256px[\s\S]*?height:\s*80px/);
  assert.doesNotMatch(addAgentMenuStyles, /rotate\(/);
  assert.match(addAgentMenuStyles, /\.create-entry-card-title,[\s\S]*?\.create-entry-card-description[\s\S]*?\.create-entry-card-title\s*\{[\s\S]*?font-size:\s*14px/);
  assert.match(addAgentMenuStyles, /\.create-entry-card-description\s*\{[\s\S]*?font-size:\s*12px/);
  assert.match(addAgentMenuStyles, /\.create-entry-card-icon\s*\{[\s\S]*?width:\s*48px[\s\S]*?border-radius:\s*14px/);
  assert.doesNotMatch(addAgentMenuSource, /从 0 快速创建|智能模式/);
});

test("does not show browser history in the create-agent description input", () => {
  assert.match(
    addAgentMenuSource,
    /className="create-entry-form"[\s\S]*?autoComplete="off"/,
  );
  assert.match(
    addAgentMenuSource,
    /<Input[\s\S]*?autoComplete="off"[\s\S]*?allowAutofillExtensions=\{false\}/,
  );
});

test("focuses the create description and reuses the homepage Composer send control", () => {
  assert.match(addAgentMenuSource, /<Input[\s\S]*?autoFocus/);
  assert.match(
    addAgentMenuSource,
    /import \{ ComposerSendIcon \} from "\.\/icons\/ComposerIcons"/,
  );
  assert.match(
    addAgentMenuSource,
    /<motion\.button[\s\S]*?className="comp-send create-entry-send"[\s\S]*?<ComposerSendIcon className="icon"/,
  );
  assert.doesNotMatch(addAgentMenuSource, /CreateSendIcon/);
  assert.doesNotMatch(
    addAgentMenuStyles,
    /\.create-entry-send::before|\.create-entry-send\[data-disabled\]/,
  );
  assert.match(
    addAgentMenuStyles,
    /\.create-entry-input\[data-focused="true"\]\s*\{[\s\S]*?var\(--create-control-border\) inset,[\s\S]*?0 6px 18px rgb\(16 16 19 \/ 7%\)/,
  );
  assert.doesNotMatch(
    addAgentMenuStyles,
    /\.create-entry-input\[data-focused="true"\]\s*\{[\s\S]*?rgb\(16 16 19 \/ 30%\)/,
  );
});

test("uses Apps SDK UI controls for the create header actions", () => {
  assert.match(
    createAgentHeaderSource,
    /import \{ Button \} from "@openai\/apps-sdk-ui\/components\/Button"/,
  );
  assert.match(
    createAgentHeaderSource,
    /import \{ SegmentedControl \} from "@openai\/apps-sdk-ui\/components\/SegmentedControl"/,
  );
  assert.doesNotMatch(createAgentHeaderSource, /<button\b/);
  assert.match(
    createAgentHeaderSource,
    /className="create-agent-header-actions"[\s\S]*?role="group"[\s\S]*?aria-label="创建工具"/,
  );
  assert.match(
    createAgentHeaderSource,
    /<Button[\s\S]*?inert[\s\S]*?className="create-agent-header-action is-code"[\s\S]*?>[\s\S]*?<CreateDownloadIcon \/>[\s\S]*?代码[\s\S]*?<\/Button>/,
  );
  assert.match(
    createAgentHeaderSource,
    /<Button[\s\S]*?variant="outline"[\s\S]*?className="create-agent-header-action is-debug"[\s\S]*?onClick=\{onDebug\}[\s\S]*?>[\s\S]*?<CreateDebugIcon \/>[\s\S]*?调试[\s\S]*?<\/Button>/,
  );
  assert.match(
    createAgentHeaderSource,
    /<Button[\s\S]*?color="primary"[\s\S]*?className="create-agent-header-action is-deploy"[\s\S]*?onClick=\{onDeploy\}[\s\S]*?>[\s\S]*?<CreateDeployIcon \/>[\s\S]*?部署[\s\S]*?<\/Button>/,
  );
  assert.match(
    createAgentHeaderSource,
    /className="create-agent-header-debug-action is-add"[\s\S]*?disabled=\{comparisonDisabled\}[\s\S]*?onClick=\{onAddComparison\}/,
  );
  assert.match(
    createAgentHeaderStyles,
    /\.create-agent-header-action\s*\{[\s\S]*?--button-size:\s*36px;[\s\S]*?min-width:\s*80px;/,
  );
  assert.match(
    createAgentHeaderStyles,
    /\.create-agent-header-action\.is-debug\s*\{[\s\S]*?--button-icon-size:\s*10px;[\s\S]*?--button-gap:\s*4px;[\s\S]*?font-weight:\s*400;[\s\S]*?line-height:\s*22px;/,
  );
  assert.match(
    createAgentHeaderStyles,
    /\.create-agent-header-action\.is-debug::before\s*\{[\s\S]*?border:\s*0\.5px solid #c9cdd4 !important;[\s\S]*?background:\s*#fff !important;[\s\S]*?box-shadow:\s*none !important;/,
  );
});

test("animates the debug header between preview and results geometry", () => {
  assert.match(
    createAgentHeaderStyles,
    /\.create-agent-header\s*\{[\s\S]*?background:\s*transparent;/,
  );
  assert.match(
    createAgentHeaderSource,
    /showDebugPreview[\s\S]*?"is-debug-preview"[\s\S]*?"is-debug-results"/,
  );
  assert.match(
    createAgentHeaderStyles,
    /--create-agent-header-motion-duration:\s*220ms/,
  );
  assert.match(
    createAgentHeaderStyles,
    /transition:[\s\S]*?width var\(--create-agent-header-motion-duration\)[\s\S]*?height var\(--create-agent-header-motion-duration\)[\s\S]*?flex-basis var\(--create-agent-header-motion-duration\)[\s\S]*?margin-left var\(--create-agent-header-motion-duration\)[\s\S]*?margin-right var\(--create-agent-header-motion-duration\)/,
  );
  assert.match(
    createAgentHeaderStyles,
    /\.create-agent-header\.is-debug-results\s*\{[\s\S]*?width:\s*calc\(100% - 40px\);[\s\S]*?height:\s*60px;[\s\S]*?flex-basis:\s*60px;[\s\S]*?margin-inline:\s*20px;/,
  );
  assert.match(
    createAgentHeaderStyles,
    /@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*?\.create-agent-header\s*\{[\s\S]*?transition:\s*none;/,
  );
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
