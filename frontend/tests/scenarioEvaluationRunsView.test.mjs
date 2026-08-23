import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);

async function loadRunsModule() {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(
      "../src/evaluation/ScenarioEvaluationRuns.tsx",
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
  assert.ok(source, "expected run panels to compile");
  const module = { exports: {} };
  Function("require", "module", "exports", source)(require, module, module.exports);
  return module.exports;
}

const runs = await loadRunsModule();

const workspace = {
  candidates: [{
    candidateId: "candidate-1",
    agentId: "agent-1",
    version: 2,
    artifact: {},
    createdAt: "2026-08-17T00:00:00Z",
    createdBy: "owner",
  }],
  policies: [],
  runs: [{
    evaluationId: "evaluation-1",
    revision: 1,
    candidateId: "candidate-1",
    status: "failed",
    recommendation: null,
    errorMessage: "Candidate has no generated runtime project snapshot.",
    scenes: [],
    createdAt: "2026-08-17T00:00:00Z",
    updatedAt: "2026-08-17T00:01:00Z",
  }],
  badcases: [{
    badcaseId: "badcase-1",
    caseId: "sample-1",
    status: "open",
    sourceEvaluationId: "evaluation-1",
  }],
  publishedVersion: null,
};

test("candidate and result panels use plain Chinese business terms", () => {
  const html = renderToStaticMarkup(React.createElement(React.Fragment, null,
    React.createElement(runs.CandidatePanel, { workspace }),
    React.createElement(runs.ResultsPanel, {
      agentId: "agent-1",
      workspace,
      mutationKey: "",
      mutate: async () => undefined,
    }),
  ));

  assert.match(html, /待测版本/);
  assert.match(html, /待测版本 v2/);
  assert.match(html, /失败样本/);
  assert.match(html, /评测样本/);
  assert.match(html, /待测版本缺少运行项目快照/);
  assert.doesNotMatch(html, /candidate-1/);
  assert.doesNotMatch(html, /\b(?:Candidate|Badcase|Scene|Case|Attempt|Evaluator|Trace)\b/);
});

test("formal evaluation shows the latest failure reason beside the retry form", () => {
  const html = renderToStaticMarkup(React.createElement(runs.FormalEvaluationPanel, {
    agentId: "agent-1",
    workspace,
    mutationKey: "",
    mutate: async () => undefined,
  }));

  assert.match(html, /上次正式评测失败/);
  assert.match(html, /待测版本缺少运行项目快照/);
  assert.match(html, /修复后可重新发起评测/);
  assert.match(html, /暂不评测，继续发布/);
});
