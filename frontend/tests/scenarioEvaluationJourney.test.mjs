import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

async function loadJourneyModule() {
  try {
    const result = await build({
      entryPoints: [
        fileURLToPath(
          new URL("../src/evaluation/scenarioEvaluationJourney.ts", import.meta.url),
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

function scene(overrides = {}) {
  return {
    sceneId: "scene-1",
    sceneVersionId: "scene-v1",
    agentId: "agent-1",
    version: 1,
    sourceDraftRevision: 1,
    name: "问候场景",
    description: "验证问候回复",
    userTask: "回复用户问候",
    passCriteria: ["回复礼貌"],
    hardFailureConditions: [],
    ownerId: "owner-1",
    linkedDatasetIds: ["dataset-1"],
    enabled: true,
    requirement: "must_pass",
    createdAt: "2026-08-17T00:00:00Z",
    createdBy: "owner-1",
    ...overrides,
  };
}

function dataset(overrides = {}) {
  return {
    datasetId: "dataset-1",
    datasetVersionId: "dataset-v1",
    agentId: "agent-1",
    version: 1,
    sourceDraftRevision: 1,
    name: "问候评测数据",
    cases: [{
      caseId: "case-1",
      sceneVersionId: "scene-v1",
      input: "你好",
      expectedOutput: "你好，很高兴见到你",
      labels: [],
      forbiddenOutput: [],
      sourceFeedbackCandidateIds: [],
    }],
    createdAt: "2026-08-17T00:00:00Z",
    createdBy: "owner-1",
    ...overrides,
  };
}

function readyEvaluatorGroup(overrides = {}) {
  return {
    sceneVersionId: "scene-v1",
    sceneName: "问候场景",
    drafts: [{ evaluatorId: "evaluator-1", revision: 1, hardFailure: false }],
    versions: [{ evaluatorVersionId: "evaluator-v1" }],
    latestPublishedVersionIds: ["evaluator-v1"],
    ordinaryCheckCount: 1,
    severeCheckCount: 0,
    calibrationState: "accurate",
    calibrationBlockReason: null,
    publishState: "published",
    ...overrides,
  };
}

function policy(overrides = {}) {
  return {
    policyId: "policy-1",
    policyVersionId: "policy-v1",
    agentId: "agent-1",
    version: 1,
    sourceDraftRevision: 1,
    name: "发布前质量检查",
    bindings: [{
      sceneVersionId: "scene-v1",
      datasetVersionId: "dataset-v1",
      evaluatorVersionIds: ["evaluator-v1"],
      requirement: "must_pass",
    }],
    createdAt: "2026-08-17T00:00:00Z",
    createdBy: "owner-1",
    ...overrides,
  };
}

function candidate(overrides = {}) {
  return {
    candidateId: "candidate-v1",
    agentId: "agent-1",
    version: 1,
    artifact: {
      codeDigest: "code-v1",
      topologyDigest: "topology-v1",
      modelRefs: [],
      promptRefs: [],
      toolRefs: [],
      skillRefs: [],
      knowledgeRefs: [],
      memoryRefs: [],
      environmentRefs: [],
      runtimeProjectRef: null,
    },
    createdAt: "2026-08-17T00:00:00Z",
    createdBy: "owner-1",
    ...overrides,
  };
}

function run(status, overrides = {}) {
  return {
    evaluationId: "run-1",
    agentId: "agent-1",
    revision: 1,
    status,
    candidateId: "candidate-v1",
    baselineVersionId: null,
    policyVersionId: "policy-v1",
    dependencies: {
      candidateId: "candidate-v1",
      baselineVersionId: null,
      sceneVersionIds: ["scene-v1"],
      datasetVersionIds: ["dataset-v1"],
      evaluatorVersionIds: ["evaluator-v1"],
      policyVersionId: "policy-v1",
      environmentFingerprint: "studio-evaluation-v1",
    },
    scenes: [],
    recommendation: null,
    errorMessage: "",
    createdAt: "2026-08-17T00:00:00Z",
    updatedAt: "2026-08-17T00:01:00Z",
    createdBy: "owner-1",
    ...overrides,
  };
}

const journeyModule = await loadJourneyModule();

test("the first missing standard asks the user to create a business scene", () => {
  assert.ok(journeyModule, "expected the journey module to compile");

  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace(),
    [],
  );

  assert.equal(journey.currentStepId, "scene");
  assert.equal(journey.currentStepNumber, 1);
  assert.equal(journey.totalSteps, 7);
  assert.equal(journey.nextAction.id, "create_scene");
  assert.equal(journey.nextAction.label, "创建业务场景");
  assert.deepEqual(
    journey.steps.map((step) => step.id),
    ["scene", "dataset", "evaluator", "policy", "candidate", "run", "decision"],
  );
  assert.deepEqual(
    journey.steps.map((step) => step.state),
    ["active", "not_started", "not_started", "not_started", "not_started", "not_started", "not_started"],
  );
});

test("a published scene without compatible data asks for evaluation data", () => {
  assert.ok(journeyModule, "expected the journey module to compile");

  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({ scenes: [scene()] }),
    [],
  );

  assert.equal(journey.currentStepId, "dataset");
  assert.equal(journey.currentStepNumber, 2);
  assert.equal(journey.nextAction.id, "create_dataset");
  assert.equal(journey.nextAction.label, "创建评测数据");
  assert.match(journey.nextAction.description, /问候场景/);
});

test("complete scene standards without a plan ask for a published evaluation plan", () => {
  assert.ok(journeyModule, "expected the journey module to compile");

  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({ scenes: [scene()], datasets: [dataset()] }),
    [readyEvaluatorGroup()],
  );

  assert.equal(journey.currentStepId, "policy");
  assert.equal(journey.currentStepNumber, 4);
  assert.equal(journey.nextAction.id, "publish_policy");
  assert.equal(journey.nextAction.label, "发布评测方案");
});

test("an accurate evaluator waiting for publication stays a normal active step", () => {
  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({ scenes: [scene()], datasets: [dataset()] }),
    [readyEvaluatorGroup({
      latestPublishedVersionIds: [],
      versions: [],
      publishState: "draft",
    })],
  );

  assert.equal(journey.currentStepId, "evaluator");
  assert.equal(journey.steps[2].state, "active");
  assert.equal(journey.nextAction.label, "配置场景评估器");
});

test("complete standards without a version advance to version generation", () => {
  assert.ok(journeyModule, "expected the journey module to compile");

  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({
      scenes: [scene()],
      datasets: [dataset()],
      policies: [policy()],
    }),
    [readyEvaluatorGroup()],
  );

  assert.equal(journey.currentStepId, "candidate");
  assert.equal(journey.currentStepNumber, 5);
  assert.equal(journey.nextAction.id, "open_agent_update");
  assert.equal(journey.latestPolicyVersionId, "policy-v1");
  assert.deepEqual(
    journey.steps.map((step) => step.state),
    ["complete", "complete", "complete", "complete", "active", "not_started", "not_started"],
  );
});

test("a version without a run advances to the optional formal-evaluation choice", () => {
  assert.ok(journeyModule, "expected the journey module to compile");

  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({
      scenes: [scene()],
      datasets: [dataset()],
      policies: [policy()],
      candidates: [candidate()],
    }),
    [readyEvaluatorGroup()],
  );

  assert.equal(journey.currentStepId, "run");
  assert.equal(journey.currentStepNumber, 6);
  assert.equal(journey.nextAction.id, "start_evaluation");
  assert.equal(journey.nextAction.label, "开始正式评测");
  assert.equal(journey.latestCandidateId, "candidate-v1");
  assert.deepEqual(
    journey.steps.map((step) => step.state),
    ["complete", "complete", "complete", "complete", "complete", "active", "not_started"],
  );
});

test("choosing not to run a formal evaluation advances to an explicit risk decision", () => {
  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({
      scenes: [scene()],
      datasets: [dataset()],
      policies: [policy()],
      candidates: [candidate()],
    }),
    [readyEvaluatorGroup()],
    { evaluationSkipped: true },
  );

  assert.equal(journey.currentStepId, "decision");
  assert.equal(journey.currentStepNumber, 7);
  assert.equal(journey.steps[5].state, "complete");
  assert.equal(journey.steps[6].state, "needs_attention");
  assert.equal(journey.nextAction.id, "skip_publish");
  assert.equal(journey.nextAction.label, "继续发布确认");
  assert.match(journey.nextAction.description, /没有质量建议/);
});

test("an active formal evaluation owns step six while workspace data refreshes", () => {
  assert.ok(journeyModule, "expected the journey module to compile");

  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({
      candidates: [candidate()],
      runs: [run("running")],
    }),
    [],
  );

  assert.equal(journey.currentStepId, "run");
  assert.equal(journey.currentStepNumber, 6);
  assert.equal(journey.nextAction.id, "wait_evaluation");
  assert.equal(journey.currentRunId, "run-1");
  assert.equal(journey.steps[5].state, "active");
});

test("a current successful recommendation advances to the decision stage", () => {
  assert.ok(journeyModule, "expected the journey module to compile");
  const completedRun = run("succeeded", {
    recommendation: {
      value: "recommend",
      dependencyFingerprint: "dependencies-v1",
      requiredSceneResults: [],
      observationSceneResults: [],
      warningSceneVersionIds: [],
    },
  });

  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({
      scenes: [scene()],
      datasets: [dataset()],
      policies: [policy()],
      candidates: [candidate()],
      runs: [completedRun],
    }),
    [readyEvaluatorGroup()],
  );

  assert.equal(journey.currentStepId, "decision");
  assert.equal(journey.currentStepNumber, 7);
  assert.equal(journey.nextAction.id, "publish");
  assert.equal(journey.nextAction.label, "去发布");
  assert.equal(journey.currentRunId, "run-1");
  assert.deepEqual(
    journey.steps.map((step) => step.state),
    ["complete", "complete", "complete", "complete", "complete", "complete", "active"],
  );
});

test("a do-not-recommend result leads to failed-sample repair", () => {
  assert.ok(journeyModule, "expected the journey module to compile");
  const completedRun = run("succeeded", {
    recommendation: {
      value: "do_not_recommend",
      dependencyFingerprint: "dependencies-v1",
      requiredSceneResults: [],
      observationSceneResults: [],
      warningSceneVersionIds: ["scene-v1"],
    },
  });
  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({
      scenes: [scene()],
      datasets: [dataset()],
      policies: [policy()],
      candidates: [candidate()],
      runs: [completedRun],
    }),
    [readyEvaluatorGroup()],
  );

  assert.equal(journey.currentStepId, "decision");
  assert.equal(journey.steps[6].state, "needs_attention");
  assert.equal(journey.nextAction.id, "view_failed_samples");
  assert.equal(journey.nextAction.label, "查看失败样本");
});

test("an indeterminate result leads to environment repair or reevaluation", () => {
  assert.ok(journeyModule, "expected the journey module to compile");
  const completedRun = run("succeeded", {
    recommendation: {
      value: "indeterminate",
      dependencyFingerprint: "dependencies-v1",
      requiredSceneResults: [],
      observationSceneResults: [],
      warningSceneVersionIds: ["scene-v1"],
    },
  });
  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({
      scenes: [scene()],
      datasets: [dataset()],
      policies: [policy()],
      candidates: [candidate()],
      runs: [completedRun],
    }),
    [readyEvaluatorGroup()],
  );

  assert.equal(journey.steps[6].state, "needs_attention");
  assert.equal(journey.nextAction.id, "retry_evaluation");
  assert.equal(journey.nextAction.label, "修复环境或重新评测");
});

test("a historical result with changed evaluator versions is stale", () => {
  assert.ok(journeyModule, "expected the journey module to compile");
  const staleRun = run("succeeded", {
    dependencies: {
      ...run("succeeded").dependencies,
      evaluatorVersionIds: ["evaluator-v0"],
    },
    recommendation: {
      value: "recommend",
      dependencyFingerprint: "old-dependencies",
      requiredSceneResults: [],
      observationSceneResults: [],
      warningSceneVersionIds: [],
    },
  });
  const journey = journeyModule.buildScenarioEvaluationJourney(
    emptyWorkspace({
      scenes: [scene()],
      datasets: [dataset()],
      policies: [policy()],
      candidates: [candidate()],
      runs: [staleRun],
    }),
    [readyEvaluatorGroup()],
  );

  assert.equal(journey.currentStepId, "run");
  assert.equal(journey.steps[5].state, "needs_attention");
  assert.equal(journey.nextAction.id, "retry_evaluation");
  assert.equal(journey.nextAction.label, "按当前口径重新评测");
  assert.match(journey.nextAction.description, /场景评估器版本已变化/);
});

for (const [status, label, description] of [
  ["cancelled", "重新开始正式评测", "本次评测已取消，未生成有效质量建议"],
  ["failed", "修复问题并重新评测", "本次评测执行失败，未生成有效质量建议"],
]) {
  test(`${status} evaluation restores an explicit optional-evaluation choice`, () => {
    assert.ok(journeyModule, "expected the journey module to compile");
    const journey = journeyModule.buildScenarioEvaluationJourney(
      emptyWorkspace({
        scenes: [scene()],
        datasets: [dataset()],
        policies: [policy()],
        candidates: [candidate()],
        runs: [run(status, { errorMessage: status === "failed" ? "服务不可用" : "" })],
      }),
      [readyEvaluatorGroup()],
    );

    assert.equal(journey.currentStepId, "run");
    assert.equal(journey.steps[5].state, "needs_attention");
    assert.equal(journey.nextAction.id, "retry_evaluation");
    assert.equal(journey.nextAction.label, label);
    assert.match(journey.nextAction.description, new RegExp(description));
  });
}
