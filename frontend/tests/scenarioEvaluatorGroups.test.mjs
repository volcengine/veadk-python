import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

async function loadEvaluatorGroupsModule() {
  try {
    const result = await build({
      entryPoints: [
        fileURLToPath(
          new URL("../src/evaluation/scenarioEvaluatorGroups.ts", import.meta.url),
        ),
      ],
      bundle: true,
      format: "esm",
      platform: "node",
      target: "node20",
      write: false,
    });
    const source = result.outputFiles[0]?.text;
    if (!source) return null;
    return import(
      `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
    );
  } catch {
    return null;
  }
}

function emptyWorkspace(overrides = {}) {
  return {
    agentId: "agent-1",
    feedbackCandidates: [],
    sceneDrafts: [],
    scenes: [],
    datasetDrafts: [],
    datasets: [],
    evaluatorDrafts: [],
    evaluatorTrials: [],
    evaluators: [],
    policyDrafts: [],
    policies: [],
    candidates: [],
    runs: [],
    badcases: [],
    publishRecoveryIssues: [],
    publishedVersion: null,
    ...overrides,
  };
}

function scene(sceneVersionId, name, hardFailureConditions = []) {
  return {
    sceneId: `${sceneVersionId}-asset`,
    sceneVersionId,
    agentId: "agent-1",
    version: 1,
    sourceDraftRevision: 1,
    name,
    description: "验证问候回复",
    userTask: "回复用户问候",
    passCriteria: ["回复礼貌"],
    hardFailureConditions,
    ownerId: "owner-1",
    linkedDatasetIds: [],
    enabled: true,
    requirement: "must_pass",
    createdAt: "2026-08-17T00:00:00Z",
    createdBy: "owner-1",
  };
}

function evaluatorDraft(evaluatorId, sceneVersionId, hardFailure) {
  return {
    evaluatorId,
    agentId: "agent-1",
    revision: 1,
    name: hardFailure ? "严重失败检查" : "普通检查",
    sceneVersionId,
    kind: "deterministic",
    rule: "output_contains_expected",
    rubric: "",
    hardFailure,
    updatedAt: "2026-08-17T00:00:00Z",
    updatedBy: "owner-1",
  };
}

function evaluatorVersion(
  evaluatorVersionId,
  evaluatorId,
  sceneVersionId,
  hardFailure,
  version,
) {
  return {
    ...evaluatorDraft(evaluatorId, sceneVersionId, hardFailure),
    evaluatorVersionId,
    version,
    sourceDraftRevision: 1,
    trialReportId: `${evaluatorVersionId}-trial`,
    trialDatasetVersionId: "dataset-v1",
    createdAt: "2026-08-17T00:00:00Z",
    createdBy: "owner-1",
  };
}

function trialResult(outcome, hardFailure = false, overrides = {}) {
  return {
    sampleId: "case-1",
    expectedOutcome: "pass",
    outcome,
    matchesExpectation: outcome === "pass",
    hardFailure,
    reason: outcome === "pass" ? "符合标准" : "不符合标准",
    errorMessage: "",
    ...overrides,
  };
}

function trialReport(evaluatorId, result, evaluatorRevision = 1) {
  return {
    reportId: `${evaluatorId}-report`,
    agentId: "agent-1",
    evaluatorId,
    evaluatorRevision,
    datasetVersionId: "dataset-v1",
    results: [result],
    createdAt: "2026-08-17T00:00:00Z",
    createdBy: "owner-1",
  };
}

const evaluatorGroups = await loadEvaluatorGroupsModule();

test("an empty scene evaluator asks for its first check without showing an execution error", () => {
  const group = evaluatorGroups.buildSceneEvaluatorGroups(emptyWorkspace({
    scenes: [scene("scene-v1", "问候场景")],
  }))[0];

  assert.equal(group.calibrationState, "not_started");
  assert.equal(
    group.calibrationBlockReason,
    "尚未配置检查，请先添加或生成至少一项检查",
  );
});

test("groups ordinary and severe checks as one scene evaluator", () => {
  assert.ok(evaluatorGroups, "expected the evaluator-group module to compile");
  const groups = evaluatorGroups.buildSceneEvaluatorGroups(emptyWorkspace({
    scenes: [scene("scene-v1", "问候场景", ["不得泄露隐私"])],
    evaluatorDrafts: [
      evaluatorDraft("ordinary", "scene-v1", false),
      evaluatorDraft("severe", "scene-v1", true),
    ],
    evaluators: [
      evaluatorVersion("ordinary-v1", "ordinary", "scene-v1", false, 1),
      evaluatorVersion("severe-v1", "severe", "scene-v1", true, 1),
    ],
  }));

  assert.equal(groups.length, 1);
  assert.equal(groups[0].sceneName, "问候场景");
  assert.equal(groups[0].ordinaryCheckCount, 1);
  assert.equal(groups[0].severeCheckCount, 1);
  assert.deepEqual(
    groups[0].latestPublishedVersionIds,
    ["ordinary-v1", "severe-v1"],
  );
});

test("uses the combined evaluator judgment for calibration accuracy", () => {
  const groups = evaluatorGroups.buildSceneEvaluatorGroups(emptyWorkspace({
    scenes: [scene("scene-v1", "问候场景", ["不得泄露隐私"])],
    evaluatorDrafts: [
      evaluatorDraft("ordinary", "scene-v1", false),
      evaluatorDraft("severe", "scene-v1", true),
    ],
    evaluatorTrials: [
      trialReport("ordinary", trialResult("pass", false, {
        expectedOutcome: "fail",
        matchesExpectation: false,
      })),
      trialReport("severe", trialResult("fail", true, {
        expectedOutcome: "fail",
        matchesExpectation: true,
      })),
    ],
  }));

  assert.equal(groups[0].calibrationState, "accurate");
});

test("reports whether a scene evaluator is unpublished, partial, or published", () => {
  assert.ok(evaluatorGroups, "expected the evaluator-group module to compile");
  const base = {
    scenes: [scene("scene-v1", "问候场景", ["不得泄露隐私"])],
    evaluatorDrafts: [
      evaluatorDraft("ordinary", "scene-v1", false),
      evaluatorDraft("severe", "scene-v1", true),
    ],
  };

  const unpublished = evaluatorGroups.buildSceneEvaluatorGroups(
    emptyWorkspace(base),
  )[0];
  const partial = evaluatorGroups.buildSceneEvaluatorGroups(emptyWorkspace({
    ...base,
    evaluators: [
      evaluatorVersion("ordinary-v1", "ordinary", "scene-v1", false, 1),
    ],
  }))[0];
  const published = evaluatorGroups.buildSceneEvaluatorGroups(emptyWorkspace({
    ...base,
    evaluators: [
      evaluatorVersion("ordinary-v1", "ordinary", "scene-v1", false, 1),
      evaluatorVersion("severe-v1", "severe", "scene-v1", true, 1),
    ],
  }))[0];

  assert.equal(unpublished.publishState, "draft");
  assert.equal(partial.publishState, "partial");
  assert.equal(published.publishState, "published");
});

test("returns only current internal checks that still need publication", () => {
  assert.ok(evaluatorGroups, "expected the evaluator-group module to compile");
  const ordinary = evaluatorDraft("ordinary", "scene-v1", false);
  const severe = {
    ...evaluatorDraft("severe", "scene-v1", true),
    revision: 2,
  };
  const group = evaluatorGroups.buildSceneEvaluatorGroups(emptyWorkspace({
    scenes: [scene("scene-v1", "问候场景", ["不得泄露隐私"])],
    evaluatorDrafts: [ordinary, severe],
    evaluators: [
      evaluatorVersion("ordinary-v1", "ordinary", "scene-v1", false, 1),
      evaluatorVersion("severe-v1", "severe", "scene-v1", true, 1),
    ],
  }))[0];

  assert.deepEqual(
    evaluatorGroups.unpublishedEvaluatorDrafts(group).map((draft) => draft.evaluatorId),
    ["severe"],
  );
});

test("a failed severe check wins the combined scene-evaluator judgment", () => {
  assert.ok(evaluatorGroups, "expected the evaluator-group module to compile");

  assert.deepEqual(
    evaluatorGroups.combineSceneEvaluatorTrialResults("pass", [
      {
        label: "普通检查",
        hardFailure: false,
        result: trialResult("pass"),
      },
      {
        label: "严重失败检查",
        hardFailure: true,
        result: trialResult("fail", true),
      },
    ]),
    {
      humanJudgment: "通过",
      evaluatorJudgment: "不通过",
      verdict: "判断不一致，场景评估器本次存在误判",
      explanation: "严重失败检查：不符合标准",
      tone: "inaccurate",
      hardFailure: true,
    },
  );
});

test("an infrastructure failure leaves scene-evaluator accuracy unavailable", () => {
  assert.ok(evaluatorGroups, "expected the evaluator-group module to compile");

  assert.deepEqual(
    evaluatorGroups.combineSceneEvaluatorTrialResults("pass", [
      {
        label: "普通检查",
        hardFailure: false,
        result: trialResult("infra_error", false, {
          reason: "",
          errorMessage: "评估服务暂不可用",
        }),
      },
    ]),
    {
      humanJudgment: "通过",
      evaluatorJudgment: "执行异常",
      verdict: "本次校准未完成，暂时无法判断准确性",
      explanation: "普通检查：评估服务暂不可用",
      tone: "unavailable",
      hardFailure: false,
    },
  );
});

test("a scene evaluator is calibrated only when every current check is accurate", () => {
  assert.ok(evaluatorGroups, "expected the evaluator-group module to compile");
  const base = {
    scenes: [scene("scene-v1", "问候场景", ["不得泄露隐私"])],
    evaluatorDrafts: [
      evaluatorDraft("ordinary", "scene-v1", false),
      evaluatorDraft("severe", "scene-v1", true),
    ],
  };
  const incomplete = evaluatorGroups.buildSceneEvaluatorGroups(emptyWorkspace({
    ...base,
    evaluatorTrials: [trialReport("ordinary", trialResult("pass"))],
  }))[0];
  const accurate = evaluatorGroups.buildSceneEvaluatorGroups(emptyWorkspace({
    ...base,
    evaluatorTrials: [
      trialReport("ordinary", trialResult("pass")),
      trialReport("severe", trialResult("pass", true)),
    ],
  }))[0];

  assert.equal(incomplete.calibrationState, "not_started");
  assert.equal(accurate.calibrationState, "accurate");
});

test("an unavailable current check keeps the scene evaluator unavailable", () => {
  assert.ok(evaluatorGroups, "expected the evaluator-group module to compile");
  const group = evaluatorGroups.buildSceneEvaluatorGroups(emptyWorkspace({
    scenes: [scene("scene-v1", "问候场景")],
    evaluatorDrafts: [evaluatorDraft("ordinary", "scene-v1", false)],
    evaluatorTrials: [
      trialReport("ordinary", trialResult("infra_error", false, {
        matchesExpectation: false,
        errorMessage: "评估服务暂不可用",
      })),
    ],
  }))[0];

  assert.equal(group.calibrationState, "unavailable");
});
