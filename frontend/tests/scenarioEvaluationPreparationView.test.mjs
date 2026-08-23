import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);

async function loadPreparationModule() {
  try {
    const result = await build({
      entryPoints: [fileURLToPath(new URL(
        "../src/evaluation/ScenarioEvaluationPreparation.tsx",
        import.meta.url,
      ))],
      bundle: true,
      external: ["react"],
      format: "cjs",
      platform: "node",
      target: "node20",
      write: false,
    });
    const source = result.outputFiles[0]?.text;
    if (!source) return null;
    const module = { exports: {} };
    Function("require", "module", "exports", source)(require, module, module.exports);
    return module.exports;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`failed to load preparation view: ${message}`);
  }
}

function workspace() {
  const baseDraft = {
    agentId: "agent-1",
    revision: 1,
    sceneVersionId: "scene-v1",
    kind: "deterministic",
    rule: "output_contains_expected",
    rubric: "",
    updatedAt: "2026-08-17T00:00:00Z",
    updatedBy: "owner-1",
  };
  return {
    agentId: "agent-1",
    feedbackCandidates: [],
    sceneDrafts: [],
    scenes: [{
      sceneId: "scene-1",
      sceneVersionId: "scene-v1",
      agentId: "agent-1",
      version: 1,
      sourceDraftRevision: 1,
      name: "问候场景",
      description: "验证问候回复",
      userTask: "回复用户问候",
      passCriteria: ["回复礼貌"],
      hardFailureConditions: ["不得泄露隐私"],
      ownerId: "owner-1",
      linkedDatasetIds: ["dataset-1"],
      enabled: true,
      requirement: "must_pass",
      createdAt: "2026-08-17T00:00:00Z",
      createdBy: "owner-1",
    }],
    datasetDrafts: [],
    datasets: [],
    evaluatorDrafts: [
      { ...baseDraft, evaluatorId: "ordinary", name: "普通检查", hardFailure: false },
      { ...baseDraft, evaluatorId: "severe", name: "严重失败检查", hardFailure: true },
    ],
    evaluatorTrials: [],
    evaluators: [],
    policyDrafts: [],
    policies: [],
    candidates: [],
    runs: [],
    badcases: [],
    publishRecoveryIssues: [],
    publishedVersion: null,
  };
}

const preparation = await loadPreparationModule();

test("renders one scene evaluator for ordinary and severe internal checks", () => {
  assert.ok(preparation, "expected the preparation module to compile");
  const html = renderToStaticMarkup(React.createElement(preparation.GovernancePanel, {
    step: "evaluator",
    agentId: "agent-1",
    workspace: workspace(),
    mutationKey: "",
    mutationFeedback: null,
    mutate: async () => undefined,
  }));

  assert.equal((html.match(/class="se-scene-evaluator"/g) ?? []).length, 1);
  assert.match(html, /问候场景/);
  assert.match(html, /普通检查 1 项/);
  assert.match(html, /严重失败检查 1 项/);
  assert.match(html, /校准场景评估器/);
  assert.match(html, /发布场景评估器/);
  assert.match(html, /还有 2 项检查未完成本轮校准/);
  assert.match(
    html,
    /<button[^>]*disabled=""[^>]*>发布场景评估器<\/button>/,
  );
  assert.match(html, /输出必须匹配正则/);
  assert.match(html, /输出不得匹配正则/);
  assert.match(html, /场景和评测样本中的业务标准会自动进入判断上下文/);
});
