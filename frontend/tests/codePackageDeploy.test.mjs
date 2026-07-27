import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const quickCreateSource = readFileSync(
  new URL("../src/ui/QuickCreate.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
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
  assert.doesNotMatch(quickCreateSource, /QuickCreateKind[\s\S]*?"package"/);
  assert.match(
    appSource,
    /key: "package"[\s\S]*?title: "从代码包添加和部署"/,
  );
  assert.match(appSource, /icon: FileArchive/);
  assert.match(appSource, /import \{ CodePackageCreate \}/);
  assert.match(appSource, /visibleCreateView === "package"/);
});

test("validates and previews uploaded zip projects before deployment", () => {
  assert.match(packageCreateSource, /from "\.\/skills\/zip"/);
  assert.match(packageCreateSource, /accept="\.zip,application\/zip"/);
  assert.match(packageCreateSource, /normalizePackageEntries/);
  assert.match(packageCreateSource, /必须包含 app\.py/);
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
  assert.match(
    clientSource,
    /phase: "upload"[\s\S]*?message: "正在上传代码包"/,
  );
});

test("passes the selected region and network to AgentKit deployment", () => {
  assert.match(packageCreateSource, /region: deployRegion/);
  assert.match(packageCreateSource, /vpc_id: network\.vpcId/);
  assert.match(packageCreateSource, /subnet_ids: network\.subnetIds/);
  assert.match(packageCreateSource, /deployAgentkitProject\(/);
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
  assert.doesNotMatch(projectPreviewSource, /<DeployIcon/);
});

test("uses the PR 748 update-button treatment for deployment", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-config-actions \.pp-deploy\s*\{[\s\S]*?min-width:\s*104px;[\s\S]*?min-height:\s*40px;[\s\S]*?border-radius:\s*999px;/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-actions \.pp-deploy:hover:not\(:disabled\)\s*\{[\s\S]*?background:\s*hsl\(var\(--foreground\)\);[\s\S]*?color:\s*hsl\(var\(--background\)\);/,
  );
});
