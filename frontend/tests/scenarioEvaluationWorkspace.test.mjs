import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/scenarioEvaluation.ts", import.meta.url),
  "utf8",
);
const workspaceSource = readFileSync(
  new URL("../src/evaluation/ScenarioEvaluationWorkspace.tsx", import.meta.url),
  "utf8",
);
const runsSource = readFileSync(
  new URL("../src/evaluation/ScenarioEvaluationRuns.tsx", import.meta.url),
  "utf8",
);
const preparationSource = readFileSync(
  new URL("../src/evaluation/ScenarioEvaluationPreparation.tsx", import.meta.url),
  "utf8",
);
const journeySource = readFileSync(
  new URL("../src/evaluation/scenarioEvaluationJourney.ts", import.meta.url),
  "utf8",
);
const journeyViewSource = readFileSync(
  new URL("../src/evaluation/ScenarioEvaluationJourneyView.tsx", import.meta.url),
  "utf8",
);
const evaluatorGroupsSource = readFileSync(
  new URL("../src/evaluation/scenarioEvaluatorGroups.ts", import.meta.url),
  "utf8",
);
const workspaceFeatureSource = `${workspaceSource}\n${preparationSource}\n${runsSource}\n${evaluatorGroupsSource}`;
const workspaceStyles = readFileSync(
  new URL("../src/evaluation/ScenarioEvaluationWorkspace.css", import.meta.url),
  "utf8",
);
const agentWorkspaceSource = readFileSync(
  new URL("../src/ui/AgentWorkspace.tsx", import.meta.url),
  "utf8",
);

test("scenario evaluation client uses the typed workspace route and preserves server errors", () => {
  assert.match(clientSource, /export async function getScenarioEvaluationWorkspace/);
  assert.match(clientSource, /SCENARIO_API = "\/web\/scenario-evaluation"/);
  assert.match(clientSource, /`\/workspace\?\$\{params\.toString\(\)\}`/);
  assert.match(clientSource, /agentId/);
  assert.match(clientSource, /signal/);
  assert.match(clientSource, /class ScenarioEvaluationApiError extends Error/);
  assert.match(clientSource, /retryable/);
  assert.match(clientSource, /detail\?\.code/);
  assert.match(clientSource, /detail\?\.message/);
});

test("scenario evaluation client exposes one mutation for every MVP lifecycle", () => {
  for (const name of [
    "reviewFeedbackCandidate",
    "rejectFeedbackCandidate",
    "mergeFeedbackCandidate",
    "convertFeedbackCandidate",
    "saveSceneDraft",
    "publishSceneVersion",
    "saveDatasetDraft",
    "publishDatasetVersion",
    "saveEvaluatorDraft",
    "recommendEvaluatorDrafts",
    "trialEvaluatorDraft",
    "publishEvaluatorVersion",
    "publishEvaluatorGroup",
    "savePolicyDraft",
    "publishPolicyVersion",
    "createCandidateVersion",
    "startFormalEvaluation",
    "cancelFormalEvaluation",
    "retryInvalidEvaluationAttempt",
    "prepareScenarioPublish",
    "getPublishAudits",
    "finalizeScenarioPublishRecovery",
  ]) {
    assert.match(clientSource, new RegExp(`export (?:async )?function ${name}`));
  }
});

test("Agent details mount a real scenario evaluation workspace", () => {
  assert.match(
    agentWorkspaceSource,
    /type AgentSection =[^;]*"scenarioEvaluation"/s,
  );
  assert.match(
    agentWorkspaceSource,
    /\{ id: "scenarioEvaluation", label: "场景评测" \}/,
  );
  assert.match(agentWorkspaceSource, /<ScenarioEvaluationWorkspace/);
  assert.match(agentWorkspaceSource, /agentId=\{selectedAgentAppName\}/);
  assert.doesNotMatch(agentWorkspaceSource, /DEFAULT_EVALUATION_GROUPS/);
});

test("scenario evaluation workspace presents seven guided steps and a quality strip", () => {
  for (const label of [
    "定义业务场景",
    "准备评测数据",
    "配置并校准场景评估器",
    "创建评测方案",
    "生成待测版本",
    "运行正式评测",
    "查看结论并决定发布",
  ]) {
    assert.match(`${journeySource}\n${journeyViewSource}`, new RegExp(label));
  }
  assert.match(journeyViewSource, /aria-current/);
  assert.match(journeyViewSource, /第 \{selectedStep\.number\} 步，共 \{journey\.totalSteps\} 步/);
  assert.match(journeyViewSource, /当前步骤/);
  assert.doesNotMatch(workspaceSource, /role="tablist"/);
  assert.match(workspaceSource, /selectedStepId === "scene"/);
  assert.match(workspaceSource, /selectedStepId === "dataset"/);
  assert.match(workspaceSource, /selectedStepId === "evaluator"/);
  assert.match(workspaceSource, /selectedStepId === "policy"/);
  assert.match(workspaceSource, /se-quality-strip/);
  assert.match(workspaceSource, /质量建议不等于发布权限/);
  assert.match(workspaceSource, /已选择暂不评测/);
  assert.match(workspaceSource, /建议发布/);
  assert.match(workspaceSource, /不建议发布/);
  assert.match(workspaceSource, /无法判断/);
});

test("scenario workspace handles stale requests, retry, empty, permission and mutations", () => {
  assert.match(workspaceSource, /new AbortController\(\)/);
  assert.match(workspaceSource, /requestSequenceRef/);
  assert.match(workspaceSource, /controller\.abort\(\)/);
  assert.match(workspaceSource, /role="alert"/);
  assert.match(workspaceSource, />重试</);
  assert.match(workspaceSource, /暂无反馈候选/);
  assert.match(workspaceSource, /权限不足/);
  assert.match(workspaceSource, /mutationKey/);
  assert.match(workspaceSource, /disabled=\{Boolean\(mutationKey\)\}/);
  assert.match(workspaceSource, /nextAction === "convert"[\s\S]*item\.decision === "reviewed"/);
  assert.match(workspaceSource, /重试审计收口/);
});

test("asset publishing exposes running, success and retry feedback beside the action", () => {
  assert.match(workspaceSource, /buildPublishActionPresentation/);
  assert.match(workspaceSource, /PublishVersionControl/);
  assert.match(workspaceSource, /aria-live="polite"/);
  assert.match(workspaceSource, /正在发布/);
  assert.match(workspaceSource, /latestVersionForDraft/);
  assert.match(workspaceSource, /publishedVersion:\s*version\.version/);
  assert.match(workspaceStyles, /se-publish-control/);
  assert.match(workspaceStyles, /se-action-feedback/);
  assert.doesNotMatch(
    workspaceSource,
    /mutationFeedback\?\.kind === "success" && !assetPublishFeedback/,
  );
});

test("evaluator calibration follows output, human judgment, run and comparison order", () => {
  const outputIndex = preparationSource.indexOf("模拟 Agent 输出");
  const judgmentIndex = preparationSource.indexOf("人工判断", outputIndex);
  const runIndex = preparationSource.indexOf("试跑场景评估器", judgmentIndex);
  const comparisonIndex = preparationSource.indexOf("对比判断结果", runIndex);

  assert.ok(outputIndex >= 0);
  assert.ok(judgmentIndex > outputIndex);
  assert.ok(runIndex > judgmentIndex);
  assert.ok(comparisonIndex > runIndex);
  assert.match(preparationSource, /校准场景评估器/);
  assert.match(preparationSource, /combineSceneEvaluatorTrialResults/);
  assert.match(preparationSource, /人工判断/);
  assert.match(preparationSource, /场景评估器综合判断/);
  assert.match(preparationSource, /准确性结论/);
  assert.match(workspaceStyles, /se-calibration-comparison/);
  assert.match(workspaceStyles, /se-calibration-verdict/);
});

test("checkboxes and save operations expose unmistakable state feedback", () => {
  assert.match(workspaceStyles, /\.se-check input[^}]*appearance:\s*none/s);
  assert.match(workspaceStyles, /\.se-check input:checked[^}]*background:/s);
  assert.match(workspaceStyles, /\.se-check input:checked::after[^}]*content:\s*"✓"/s);
  assert.match(workspaceStyles, /\.se-check:has\(input:checked\)/);
  assert.match(workspaceSource, /mutationFeedback\?\.kind === "success"/);
  assert.match(workspaceSource, /业务场景草稿已保存/);
  assert.match(workspaceSource, /评测数据草稿已保存/);
  assert.match(preparationSource, /内部检查草稿已保存/);
  assert.match(preparationSource, /评测方案草稿已保存/);
});

test("scenario standards keep structured release contracts", () => {
  for (const field of [
    "userTask",
    "passCriteria",
    "hardFailureConditions",
    "ownerId",
    "sceneVersionId",
    "sourceRefs",
    "redactionStatus",
    "datasetVersionId",
    "expectedOutcome",
    "matchesExpectation",
  ]) {
    assert.match(workspaceFeatureSource, new RegExp(field));
  }
  assert.match(preparationSource, /activeScenes\.map/);
  assert.match(preparationSource, /calibrationState/);
  assert.match(workspaceFeatureSource, /仅重试无效执行/);
  assert.match(workspaceFeatureSource, /对比基线/);
});

test("scenario workspace supports evidence drill-down and responsive controls", () => {
  assert.match(runsSource, /业务场景/);
  assert.match(runsSource, /评测样本/);
  assert.match(runsSource, /次执行/);
  assert.match(runsSource, /内部检查/);
  assert.match(runsSource, /调用链/);
  assert.match(workspaceStyles, /min-height:\s*34px/);
  assert.match(workspaceStyles, /font-size:\s*1[234]px/);
  assert.match(workspaceStyles, /@media \(max-width:\s*720px\)/);
  assert.match(workspaceStyles, /:focus-visible/);
  assert.match(workspaceStyles, /prefers-reduced-motion:\s*reduce/);
});
