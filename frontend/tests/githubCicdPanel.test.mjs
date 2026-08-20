import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const panelSource = readFileSync(
  new URL("../src/ui/GithubCicdPanel.tsx", import.meta.url),
  "utf8",
);

test("exposes a GitHub CICD pipeline client without persisting tokens", () => {
  assert.match(clientSource, /createGithubCicdPipeline/);
  assert.match(clientSource, /\/web\/github-delivery\/source-sync/);
  assert.doesNotMatch(clientSource, /\/web\/github-delivery\/source-pr/);
  assert.doesNotMatch(clientSource, /\/web\/github-cicd\/pipelines/);
  assert.match(clientSource, /createGithubDeliveryCicdPipeline/);
  assert.match(clientSource, /\/web\/github-delivery\/cicd-pipeline/);
  assert.match(clientSource, /attachGithubDeliveryCicdToSourceSync/);
  assert.match(clientSource, /\/web\/github-delivery\/source-sync\/cicd/);
  assert.match(clientSource, /initializeGithubDeliveryMain/);
  assert.match(clientSource, /\/web\/github-delivery\/init-main/);
  assert.match(clientSource, /getGithubDeliveryVersions/);
  assert.match(clientSource, /\/web\/github-delivery\/versions/);
  assert.match(clientSource, /createGithubDeliveryRollbackPr/);
  assert.match(clientSource, /\/web\/github-delivery\/rollback-pr/);
  assert.match(clientSource, /bindGithubCicdRuntime/);
  assert.match(clientSource, /syncGithubCicdRuntime/);
  assert.match(clientSource, /\/web\/github-cicd\/runtime-sync/);
  assert.match(clientSource, /github\?:/);
  assert.match(clientSource, /githubToken/);
  assert.match(clientSource, /cloudProvider: params\.cloudProvider/);
  assert.doesNotMatch(clientSource, /localStorage[\s\S]{0,160}githubToken/);
  assert.doesNotMatch(clientSource, /sessionStorage[\s\S]{0,160}githubToken/);
});

test("renders the GitHub CICD panel from the project deployment sidebar", () => {
  assert.match(projectPreviewSource, /GithubCicdPanel/);
  assert.match(projectPreviewSource, /cloudProvider=\{cloudProvider\}/);
  assert.match(panelSource, /GitHub 代码同步/);
  assert.match(panelSource, /挂载持续交付/);
  assert.doesNotMatch(panelSource, /<span>GitHub 持续交付<\/span>/);
  assert.doesNotMatch(panelSource, /disabled\s+title="下一阶段接入 GitHub Actions 持续交付"/);
  assert.match(panelSource, /createGithubDeliveryCicdPipeline/);
  assert.match(panelSource, /挂载持续交付/);
  assert.match(panelSource, /workflowPath/);
  assert.match(panelSource, /githubUrl/);
  assert.match(panelSource, /githubToken/);
  assert.match(panelSource, /baseBranch/);
  assert.match(panelSource, /volcengineAccessKey/);
  assert.match(panelSource, /volcengineSecretKey/);
  assert.match(panelSource, /credentialProviderLabel/);
  assert.match(panelSource, /cloudProvider === "byteplus" \? "BytePlus" : "火山"/);
  assert.match(projectPreviewSource, /pendingGithubCicd\.volcengineAccessKey/);
  assert.match(projectPreviewSource, /pendingGithubCicd\.volcengineSecretKey/);
  assert.match(projectPreviewSource, /pendingGithubCicd\.cloudProvider/);
  assert.match(clientSource, /volcengineAccessKey/);
  assert.match(clientSource, /volcengineSecretKey/);
  assert.doesNotMatch(clientSource, /localStorage[\s\S]{0,160}volcengineAccessKey/);
  assert.doesNotMatch(clientSource, /sessionStorage[\s\S]{0,160}volcengineAccessKey/);
  assert.match(panelSource, /onPendingCicdChange/);
  assert.match(panelSource, /部署时挂载持续交付/);
  assert.match(panelSource, /直接 push 到目标分支/);
  assert.match(panelSource, /同步代码/);
  assert.doesNotMatch(panelSource, /创建 PR/);
  assert.doesNotMatch(panelSource, /更新 PR/);
  assert.match(panelSource, /首次部署成功后初始化目标分支/);
  assert.doesNotMatch(panelSource, /pendingResult/);
  assert.doesNotMatch(panelSource, /status:\s*"pending"/);
  assert.match(panelSource, /已选择，部署时挂载/);
  assert.doesNotMatch(panelSource, /挂载持续交付需要先部署 Runtime/);
  assert.match(panelSource, /result\?\.github/);
  assert.match(panelSource, /bindGithubCicdRuntime/);
  assert.match(panelSource, /createGithubCicdPipeline/);
  assert.doesNotMatch(projectPreviewSource, /&& !isRuntimeUpdate && \(\s*<GithubCicdPanel/);
  assert.match(projectPreviewSource, /syncGithubCicdRuntime/);
  assert.match(projectPreviewSource, /pendingGithubCicd/);
  assert.match(projectPreviewSource, /initializeGithubDeliveryMain/);
  assert.match(projectPreviewSource, /cloudProvider:\s*pendingGithubCicd\.cloudProvider/);
  assert.match(projectPreviewSource, /volcengineAccessKey:\s*pendingGithubCicd\.volcengineAccessKey/);
  assert.match(projectPreviewSource, /volcengineSecretKey:\s*pendingGithubCicd\.volcengineSecretKey/);
  assert.match(projectPreviewSource, /GitHub 持续交付已初始化目标分支/);
  assert.match(projectPreviewSource, /代码已提交到 GitHub，GitHub Actions 正在更新同一个 Runtime/);
  assert.doesNotMatch(projectPreviewSource, /GitHub 持续交付已写入初始化 PR/);
  assert.match(projectPreviewSource, /showSetup=\{!isRuntimeUpdate\}/);
});
