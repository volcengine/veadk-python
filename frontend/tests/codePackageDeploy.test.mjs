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
    /key: "package"[\s\S]*?title: t\("addAgent\.package\.title"\)/,
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

test("uses thin hand-drawn icons for all add-agent options", () => {
  for (const iconName of ["ScratchIcon", "PackageIcon", "MigrationIcon"]) {
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
    /key: "migration"[\s\S]*?title: t\("addAgent\.migrate\.title"\)[\s\S]*?desc: t\("addAgent\.migrate\.description"\)[\s\S]*?setCreateView\("migration"\)/,
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
    /t\("codePackage\.errors\.defaultEntryPointMissing"\)/,
  );
  assert.match(packageCreateSource, /maxUncompressedBytes: MAX_PACKAGE_BYTES/);
  assert.match(zipSource, /options\.maxUncompressedBytes/);
  assert.match(packageCreateSource, /deploymentPrimaryPane=/);
  assert.match(packageCreateSource, /className="package-source-pane"/);
  assert.match(packageCreateSource, /t\("codePackage\.uploadPrompt"\)/);
  assert.doesNotMatch(packageCreateSource, /<FileArchive/);
  assert.match(packageCreateSource, /role="button"/);
  assert.match(
    packageCreateSource,
    /aria-label=\{project \? t\("codePackage\.reupload"\) : t\("codePackage\.upload"\)\}/,
  );
  assert.doesNotMatch(packageCreateSource, />选择压缩包</);
  assert.match(packageCreateSource, /onChange=\{setProject\}/);
});

test("shows upload, image build, runtime creation, and publish progress", () => {
  assert.match(
    projectPreviewSource,
    /deploymentPrimaryPane\s*\?\s*codePackageDeploySteps\(t\)\s*:\s*deploySteps\(t\)/,
  );
  assert.match(
    projectPreviewSource,
    /phase: "upload", label: t\("projectPreview\.steps\.uploadPackage"\)/,
  );
  assert.match(
    projectPreviewSource,
    /phase: "build", label: t\("projectPreview\.steps\.packageImage"\)/,
  );
  assert.match(
    projectPreviewSource,
    /phase: "deploy", label: t\("projectPreview\.steps\.createRuntime"\)/,
  );
  assert.match(clientSource, /phase: "upload"/);
  assert.match(clientSource, /adkT\("client\.uploadingCodePackage"\)/);
  assert.match(clientSource, /adkT\("client\.validatingMigrationArtifact"\)/);
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
    /!deploymentPrimaryPane\s*&&\s*\([\s\S]*?t\("projectPreview\.messageChannels"\)/,
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
  assert.match(
    packageCreateSource,
    /className="package-source-label">\{t\("codePackage\.name"\)\}/,
  );
  assert.match(packageCreateStyles, /\.package-dropzone\s*\{[\s\S]*?min-height:\s*152px/);
});

test("uses a themed region menu and a centered icon-free deploy button", () => {
  assert.match(projectPreviewSource, /className="pp-region-trigger"/);
  assert.match(projectPreviewSource, /role="listbox" aria-label=\{t\("projectPreview\.deployRegion"\)\}/);
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
