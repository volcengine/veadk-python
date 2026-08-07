import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const resourceSource = readFileSync(
  new URL("../src/ui/DeploymentResources.tsx", import.meta.url),
  "utf8",
);
const resourceStyles = readFileSync(
  new URL("../src/ui/DeploymentResources.css", import.meta.url),
  "utf8",
);
const deploymentSelectSource = readFileSync(
  new URL("../src/ui/DeploymentSelect.tsx", import.meta.url),
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

test("places resource configuration immediately before environment variables", () => {
  const resourceIndex = projectPreviewSource.indexOf(">资源配置<");
  const environmentIndex = projectPreviewSource.indexOf("环境变量\n");

  assert.notEqual(resourceIndex, -1);
  assert.notEqual(environmentIndex, -1);
  assert.ok(resourceIndex < environmentIndex);
  assert.match(projectPreviewSource, /resources: deployResources,/);
});

test("supports automatic, named, and existing TOS CR and CodePipeline resources", () => {
  assert.match(resourceSource, /label: "自动创建"/);
  assert.match(resourceSource, /label: "指定名称"/);
  assert.match(resourceSource, /label: "选择已有"/);
  assert.match(resourceSource, />TOS 存储桶</);
  assert.match(resourceSource, />容器镜像仓库/);
  assert.match(resourceSource, />CodePipeline/);
  assert.match(resourceSource, /kind: "cr-namespace"[\s\S]*?registry:/);
  assert.match(
    resourceSource,
    /kind: "cr-repository"[\s\S]*?registry:[\s\S]*?namespace:/,
  );
  assert.match(resourceSource, /kind: "cp-pipeline"[\s\S]*?workspaceId:/);
  assert.match(resourceSource, /valueField="name"/);
  assert.match(projectPreviewSource, /previousDeployRegionRef/);
});

test("shows AgentKit automatic resource naming rules", () => {
  assert.match(projectPreviewSource, /agentName=\{agentName \|\| project\.name/);
  assert.match(resourceSource, /agentkit-platform-\{账号 ID\}/);
  assert.match(resourceSource, /region\.startsWith\("cn-"\)/);
  assert.match(resourceSource, /\{ label: "命名空间", name: "agentkit" \}/);
  assert.match(resourceSource, /\$\{resolvedAgentName\}-\{4 位随机字符\}/);
  assert.match(resourceSource, /agentkit-cli-workspace/);
  assert.match(resourceSource, /\$\{resolvedAgentName\}-\{8 位随机字符\}/);
  assert.match(resourceSource, /与 Runtime 同名/);
});

test("aligns resource fields on one shared grid without gray card fills", () => {
  assert.match(resourceStyles, /--pp-resource-mode-column:/);
  assert.match(resourceStyles, /grid-template-columns:\s*var\(--pp-resource-mode-column\)/);
  assert.match(resourceStyles, /\.pp-resource-auto-names/);
  assert.match(
    resourceStyles,
    /\.pp-resource-item\s*\{[\s\S]*?background:\s*hsl\(var\(--background\)\)/,
  );
  assert.doesNotMatch(
    resourceStyles,
    /\.pp-resource-item\s*\{[\s\S]*?background:\s*hsl\(var\(--secondary\)/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-config-label\s*\{[\s\S]*?background:\s*transparent/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-env-head\s*\{[\s\S]*?background:\s*transparent/,
  );
});

test("resource requests expose loading empty error retry and cancellation", () => {
  assert.match(resourceSource, /new AbortController\(\)/);
  assert.match(resourceSource, /requestRef\.current\?\.abort\(\)/);
  assert.match(resourceSource, /role="alert"/);
  assert.match(resourceSource, />重试</);
  assert.match(resourceSource, /暂无可用资源/);
  assert.match(resourceSource, /aria-live="polite"/);
  assert.match(resourceStyles, /\.pp-resource-error/);
  assert.match(resourceStyles, /\.pp-resource-status/);
});

test("loads large resource collections one page at a time", () => {
  assert.match(clientSource, /pageNumber\?: number/);
  assert.match(clientSource, /pageSize\?: number/);
  assert.match(clientSource, /params\.set\("pageNumber"/);
  assert.match(resourceSource, /loadMore: \(\) => void/);
  assert.match(resourceSource, /state\.hasMore/);
  assert.match(resourceSource, /"加载更多"/);
});

test("uses repository-owned SVGs for deployment select icons", () => {
  assert.doesNotMatch(deploymentSelectSource, /from "lucide-react"/);
  assert.match(deploymentSelectSource, /function SelectChevronIcon/);
  assert.match(deploymentSelectSource, /function SelectCheckIcon/);
  assert.match(deploymentSelectSource, /aria-hidden="true"/);
});

test("sends typed deployment resources through the AgentKit deploy request", () => {
  assert.match(clientSource, /export interface DeployResources/);
  assert.match(clientSource, /`\/web\/deployment-resources\?\$\{/);
  assert.match(clientSource, /resources: opts\?\.resources/);
});
