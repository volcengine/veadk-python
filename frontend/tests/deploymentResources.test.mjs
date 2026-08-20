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
  assert.match(
    projectPreviewSource,
    /\.\.\.\(!isRuntimeUpdate \? \{ resources: deployResources \} : \{\}\)/,
  );
});

test("hides and omits resource configuration when updating a Runtime", () => {
  assert.match(
    projectPreviewSource,
    /\{!isRuntimeUpdate && \([\s\S]*?>资源配置<[\s\S]*?<DeploymentResources/,
  );
  assert.match(
    projectPreviewSource,
    /if \(!isRuntimeUpdate\) \{[\s\S]*?deploymentResourcesError\(deployResources\)/,
  );
  assert.match(
    projectPreviewSource,
    /\.\.\.\(!isRuntimeUpdate \? \{ resources: deployResources \} : \{\}\)/,
  );
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
  assert.match(resourceSource, /name: resolvedRuntimeName/);
  assert.match(resourceSource, /Pipeline 与 Runtime 名称一致/);
  assert.match(projectPreviewSource, /runtimeName=\{/);
});

test("aligns resource fields on one shared grid without gray card fills", () => {
  const itemRule = resourceStyles.match(/\.pp-resource-item\s*\{[^}]*\}/)?.[0] ?? "";
  assert.match(
    resourceStyles,
    /\.pp-resource-grid\s*\{[\s\S]*?flex-direction:\s*column;[\s\S]*?gap:\s*16px;/,
  );
  assert.match(
    resourceStyles,
    /\.pp-resource-field\s*\{[\s\S]*?flex-direction:\s*column;[\s\S]*?gap:\s*8px;/,
  );
  assert.match(resourceStyles, /\.pp-resource-auto-names/);
  assert.match(itemRule, /padding:\s*16px 0/);
  assert.doesNotMatch(itemRule, /background:/);
  assert.match(
    projectPreviewStyles,
    /\.pp-config-label\s*\{[\s\S]*?background:\s*transparent/,
  );
  assert.match(
    projectPreviewStyles,
    /\.pp-env-head\s*\{[\s\S]*?background:\s*transparent/,
  );
});

test("keeps resource dropdown menus outside the generic clipped config section", () => {
  assert.match(
    projectPreviewStyles,
    /\.pp-config-section\s*\{[\s\S]*?overflow:\s*hidden/,
  );
  assert.match(
    resourceStyles,
    /\.pp-config-section\.pp-resource-section\s*\{[\s\S]*?overflow:\s*visible/,
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
  assert.match(deploymentSelectSource, /onScroll=/);
  assert.match(deploymentSelectSource, /remaining <= 24/);
  assert.match(resourceSource, /state\.loadMore/);
  assert.doesNotMatch(resourceSource, /className="pp-resource-more"/);
});

test("searches loaded cloud resources through Apps SDK UI with request cancellation", () => {
  assert.match(
    resourceSource,
    /from "@openai\/apps-sdk-ui\/components\/Select"/,
  );
  assert.match(resourceSource, /requestRef\.current\?\.abort\(\)/);
  assert.match(resourceSource, /searchPlaceholder="搜索资源名称"/);
  assert.match(resourceSource, /searchEmptyMessage="未找到匹配资源"/);
  assert.match(resourceSource, /options=\{options\}/);
  assert.doesNotMatch(resourceSource, /setTimeout\(|debouncedSearch|searchValue=|onSearchChange=/);
  assert.match(resourceSource, /valueLabel=\{value\.codePipeline\.pipelineName\}/);
});

test("does not paginate with stale state while a new resource search is loading", () => {
  assert.match(resourceSource, /loadedQueryKey === queryKey/);
  assert.match(resourceSource, /queryReady \? hasMore : false/);
  assert.match(resourceSource, /if \(!queryReady \|\| loadingRef\.current \|\| !hasMore\) return/);
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
