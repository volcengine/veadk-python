import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(new URL("../src/adk/client.ts", import.meta.url), "utf8");
const scenarioClientSource = readFileSync(
  new URL("../src/adk/scenarioEvaluation.ts", import.meta.url),
  "utf8",
);
const previewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const previewStyles = readFileSync(
  new URL("../src/ui/ProjectPreview.css", import.meta.url),
  "utf8",
);

test("deployment client forwards only the prepared scenario publish authority", () => {
  assert.match(clientSource, /scenarioPublishIntentId\?: string/);
  assert.match(clientSource, /scenarioAgentId\?: string/);
  assert.match(clientSource, /scenarioDeploymentProfile\?: Record<string, unknown>/);
  assert.match(clientSource, /publishIntentId: opts\?\.scenarioPublishIntentId/);
  assert.match(clientSource, /agentId: opts\?\.scenarioAgentId/);
  assert.match(clientSource, /deploymentProfile: opts\?\.scenarioDeploymentProfile/);
  assert.doesNotMatch(clientSource, /scenarioPermissionFingerprint/);
  assert.doesNotMatch(clientSource, /recommendationValue: opts/);
  assert.doesNotMatch(clientSource, /riskItems: opts/);
  assert.doesNotMatch(clientSource, /publishPath: opts/);
});

test("project candidate builder freezes code and draft references with SHA-256 digests", () => {
  assert.match(scenarioClientSource, /export async function buildProjectCandidateInput/);
  assert.match(scenarioClientSource, /crypto\.subtle\.digest\("SHA-256"/);
  assert.match(scenarioClientSource, /files: \[\.\.\.project\.files\]/);
  assert.match(scenarioClientSource, /modelRefs/);
  assert.match(scenarioClientSource, /promptRefs/);
  assert.match(scenarioClientSource, /toolRefs/);
  assert.match(scenarioClientSource, /skillRefs/);
  assert.match(scenarioClientSource, /knowledgeRefs/);
  assert.match(scenarioClientSource, /memoryRefs/);
  assert.match(scenarioClientSource, /environmentRefs/);
});

test("shared deployment confirmation creates one candidate and reads server quality", () => {
  assert.match(previewSource, /buildProjectCandidateInput/);
  assert.match(previewSource, /createCandidateVersion/);
  assert.match(previewSource, /getScenarioEvaluationWorkspace/);
  assert.match(previewSource, /scenarioCandidateRef/);
  assert.match(previewSource, /scenarioPreparationSequenceRef/);
  assert.match(previewSource, /candidate\.candidateId/);
  assert.match(previewSource, /workspace\.runs\][\s\S]*?\.filter[\s\S]*?\.sort/);
  assert.match(previewSource, /workspace\.policies/);
});

test("publish confirmation supports formal evaluation, wait, cancel, and guarded risk paths", () => {
  assert.match(previewSource, /startFormalEvaluation/);
  assert.match(previewSource, /cancelFormalEvaluation/);
  assert.match(previewSource, /等待评测完成/);
  assert.match(previewSource, /取消评测/);
  assert.match(previewSource, /二次确认/);
  assert.match(previewSource, /发布原因/);
  assert.match(previewSource, /不会改写评测结果，也不会关闭失败样本/);
  assert.match(previewSource, /scenarioAcknowledged/);
  assert.match(previewSource, /scenarioPublishReason\.trim\(\)/);
  assert.match(previewSource, /scenarioPreparing/);
});

test("deployment obtains a server prepared intent before sending the project", () => {
  assert.match(previewSource, /prepareScenarioPublish/);
  assert.match(previewSource, /secondConfirmation: scenarioAcknowledged/);
  assert.match(previewSource, /reason: scenarioPublishReason\.trim\(\)/);
  assert.match(previewSource, /scenarioPublishIntentId: intent\.intentId/);
  assert.match(previewSource, /scenarioAgentId/);
  assert.match(previewSource, /scenarioDeploymentProfile/);
  assert.match(previewSource, /intent\.path/);
  assert.doesNotMatch(previewSource, /path:\s*"(?:normal|skip|risk)"/);
});

test("GitHub continuous delivery preserves governed publish authority", () => {
  assert.match(clientSource, /syncGithubCicdRuntime[\s\S]*?scenarioPublishIntentId\?: string/);
  assert.match(
    clientSource,
    /publishIntentId: params\.scenarioPublishIntentId[\s\S]*?agentId: params\.scenarioAgentId[\s\S]*?deploymentProfile: params\.scenarioDeploymentProfile/,
  );
  assert.match(previewSource, /githubCicdBinding\.cicd\?\.enabled/);
  assert.match(previewSource, /syncGithubCicdRuntime\(\{[\s\S]*?scenarioPublishIntentId: intent\.intentId/);
});

test("quality confirmation styling keeps the existing dialog hierarchy responsive", () => {
  assert.match(previewStyles, /\.pp-confirm-quality/);
  assert.match(previewStyles, /\.pp-confirm-risk-reason/);
  assert.match(previewStyles, /@media \(max-width:\s*720px\)/);
  assert.match(previewStyles, /\.pp-confirm-quality[\s\S]*?font-size:\s*1[234]px/);
});
