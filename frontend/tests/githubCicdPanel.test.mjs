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
  assert.match(clientSource, /\/web\/github-cicd\/pipelines/);
  assert.match(clientSource, /bindGithubCicdRuntime/);
  assert.match(clientSource, /syncGithubCicdRuntime/);
  assert.match(clientSource, /\/web\/github-cicd\/runtime-sync/);
  assert.match(clientSource, /github\?:/);
  assert.match(clientSource, /githubToken/);
  assert.doesNotMatch(clientSource, /localStorage[\s\S]{0,160}githubToken/);
  assert.doesNotMatch(clientSource, /sessionStorage[\s\S]{0,160}githubToken/);
});

test("renders the GitHub CICD panel from the project deployment sidebar", () => {
  assert.match(projectPreviewSource, /GithubCicdPanel/);
  assert.match(panelSource, /GitHub 持续交付/);
  assert.match(panelSource, /githubUrl/);
  assert.match(panelSource, /githubToken/);
  assert.match(panelSource, /baseBranch/);
  assert.match(panelSource, /result\?\.github/);
  assert.match(panelSource, /bindGithubCicdRuntime/);
  assert.match(panelSource, /createGithubCicdPipeline/);
  assert.doesNotMatch(projectPreviewSource, /&& !isRuntimeUpdate && \(\s*<GithubCicdPanel/);
  assert.match(projectPreviewSource, /syncGithubCicdRuntime/);
});
