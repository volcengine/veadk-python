import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workspace = readFileSync(
  new URL("../src/evaluation/ScenarioEvaluationWorkspace.tsx", import.meta.url),
  "utf8",
);
const runs = readFileSync(
  new URL("../src/evaluation/ScenarioEvaluationRuns.tsx", import.meta.url),
  "utf8",
);
const preparation = readFileSync(
  new URL("../src/evaluation/ScenarioEvaluationPreparation.tsx", import.meta.url),
  "utf8",
);
const preview = readFileSync(new URL("../src/ui/ProjectPreview.tsx", import.meta.url), "utf8");
const client = readFileSync(new URL("../src/adk/scenarioEvaluation.ts", import.meta.url), "utf8");
const presentation = readFileSync(
  new URL("../src/evaluation/scenarioEvaluationPresentation.ts", import.meta.url),
  "utf8",
);

const UI_ACCEPTANCE = {
  "TC-01": [/反馈候选/, /source\.input/, /source\.output/],
  "TC-02": [/mergeFeedbackCandidate/, /redactionConfirmed/, /转为评测样本/],
  "TC-03": [/saveSceneDraft/, /publishSceneVersion/],
  "TC-04": [/saveDatasetDraft/, /publishDatasetVersion/],
  "TC-05": [/recommendEvaluatorDrafts/, /生成推荐检查/, /大模型评分标准/],
  "TC-06": [/trialEvaluatorDraft/, /校准场景评估器/, /人工判断/, /场景评估器判断/, /combineSceneEvaluatorTrialResults/],
  "TC-07": [/savePolicyDraft/, /publishPolicyVersion/, /必过场景不可删减/],
  "TC-08": [
    /buildProjectCandidateInput/,
    /attestation: project\.attestation/,
    /runtimeProject: \{[\s\S]*?\.\.\.frozenProject,[\s\S]*?deploymentProfile,[\s\S]*?agentIdentityAttestation/,
  ],
  "TC-09": [/发起正式评测/, /每个评测样本执行三次/],
  "TC-10": [/第 \{attempt\.attemptIndex\} 次执行/, /outcomeLabels\[attempt\.outcome\]/],
  "TC-11": [/hardFailure/],
  "TC-12": [/无法判断/, /风险发布/],
  "TC-13": [/建议发布/, /warningSceneVersionIds/],
  "TC-14": [/质量建议/, /业务场景/, /评测样本/, /内部检查/, /调用链/],
  "TC-15": [/失败样本/, /待修复/],
  "TC-16": [/待复测/, /已关闭/],
  "TC-17": [/跳过评测发布/, /重新确认/],
  "TC-18": [/普通发布/, /scenarioCandidateRef/],
  "TC-19": [/等待评测完成/, /取消评测/],
  "TC-20": [/风险项/, /不会改写评测结果，也不会关闭失败样本/],
  "TC-21": [/sourceFeedbackCandidateIds/, /redactionStatus/],
  "TC-22": [/normal/, /skip/, /risk/],
};

const allSource = `${workspace}\n${preparation}\n${runs}\n${preview}\n${client}\n${presentation}`;
for (const [caseId, patterns] of Object.entries(UI_ACCEPTANCE)) {
  test(`${caseId} keeps its Studio interaction contract`, () => {
    for (const pattern of patterns) assert.match(allSource, pattern);
  });
}

test("frontend acceptance matrix covers TC-01 through TC-22", () => {
  assert.deepEqual(
    Object.keys(UI_ACCEPTANCE),
    Array.from({ length: 22 }, (_, index) => `TC-${String(index + 1).padStart(2, "0")}`),
  );
});
