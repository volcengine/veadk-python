import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

async function loadPresentationModule() {
  try {
    const result = await build({
      entryPoints: [
        fileURLToPath(
          new URL(
            "../src/evaluation/scenarioEvaluationPresentation.ts",
            import.meta.url,
          ),
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

const presentation = await loadPresentationModule();

test("publish action distinguishes idle, running, published and retryable failure states", () => {
  assert.ok(presentation, "expected the presentation module to compile");

  assert.deepEqual(
    presentation.buildPublishActionPresentation({
      isRunning: false,
      publishedVersion: null,
      feedback: null,
    }),
    {
      label: "发布版本",
      disabled: false,
      status: null,
      tone: "idle",
    },
  );
  assert.deepEqual(
    presentation.buildPublishActionPresentation({
      isRunning: true,
      publishedVersion: null,
      feedback: null,
    }),
    {
      label: "正在发布…",
      disabled: true,
      status: "正在发布版本",
      tone: "running",
    },
  );
  assert.deepEqual(
    presentation.buildPublishActionPresentation({
      isRunning: false,
      publishedVersion: 3,
      feedback: null,
    }),
    {
      label: "已发布 v3",
      disabled: true,
      status: "已发布 v3",
      tone: "success",
    },
  );
  assert.deepEqual(
    presentation.buildPublishActionPresentation({
      isRunning: false,
      publishedVersion: null,
      feedback: { kind: "error", message: "网络连接中断" },
    }),
    {
      label: "重新发布",
      disabled: false,
      status: "发布失败：网络连接中断",
      tone: "error",
    },
  );
  assert.deepEqual(
    presentation.buildPublishActionPresentation({
      isRunning: false,
      publishedVersion: null,
      feedback: {
        kind: "success",
        message: "评估器“问候评估”已发布为 v1",
        publishedVersion: 1,
      },
    }),
    {
      label: "已发布 v1",
      disabled: true,
      status: "评估器“问候评估”已发布为 v1",
      tone: "success",
    },
  );
});

test("published draft feedback survives workspace refreshes", () => {
  assert.ok(presentation, "expected the presentation module to compile");

  assert.equal(
    presentation.latestVersionForDraft(
      [
        { version: 1, sourceDraftRevision: 1 },
        { version: 2, sourceDraftRevision: 2 },
        { version: 3, sourceDraftRevision: 2 },
      ],
      2,
    ),
    3,
  );
  assert.equal(
    presentation.latestVersionForDraft(
      [{ version: 1, sourceDraftRevision: 1 }],
      4,
    ),
    null,
  );
});

test("calibration presentation shows matching human and evaluator judgments", () => {
  assert.ok(presentation, "expected the presentation module to compile");

  assert.deepEqual(
    presentation.buildCalibrationPresentation({
      sampleId: "case-1",
      expectedOutcome: "pass",
      outcome: "pass",
      matchesExpectation: true,
      hardFailure: false,
      reason: "输出包含期望内容",
      errorMessage: "",
    }),
    {
      humanJudgment: "通过",
      evaluatorJudgment: "通过",
      verdict: "判断一致，评估器本次判断准确",
      explanation: "输出包含期望内容",
      tone: "accurate",
    },
  );
});

test("calibration presentation exposes evaluator misjudgment", () => {
  assert.ok(presentation, "expected the presentation module to compile");

  assert.deepEqual(
    presentation.buildCalibrationPresentation({
      sampleId: "case-2",
      expectedOutcome: "pass",
      outcome: "fail",
      matchesExpectation: false,
      hardFailure: false,
      reason: "缺少关键字段",
      errorMessage: "",
    }),
    {
      humanJudgment: "通过",
      evaluatorJudgment: "不通过",
      verdict: "判断不一致，评估器本次存在误判",
      explanation: "缺少关键字段",
      tone: "inaccurate",
    },
  );
});

test("calibration presentation does not call infrastructure failure inaccurate", () => {
  assert.ok(presentation, "expected the presentation module to compile");

  assert.deepEqual(
    presentation.buildCalibrationPresentation({
      sampleId: "case-3",
      expectedOutcome: "fail",
      outcome: "infra_error",
      matchesExpectation: false,
      hardFailure: false,
      reason: "",
      errorMessage: "评估服务暂不可用",
    }),
    {
      humanJudgment: "不通过",
      evaluatorJudgment: "执行异常",
      verdict: "本次校准未完成，暂时无法判断准确性",
      explanation: "评估服务暂不可用",
      tone: "unavailable",
    },
  );
});
