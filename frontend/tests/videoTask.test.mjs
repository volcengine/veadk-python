import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/ui/new-chat-modes/video-task.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const {
  createVideoGenerationTask,
  currentVideoTaskStatus,
  formatVideoTaskElapsed,
  isVideoTaskRunning,
  updateVideoGenerationTask,
  videoTaskSteps,
} = await import(moduleUrl);

const config = {
  taskMode: "auto",
  aspectRatio: "16:9",
  resolution: "720p",
  durationSeconds: 8,
  referenceImage: null,
  referenceVideo: null,
  firstFrame: null,
  lastFrame: null,
};

function createTask() {
  return createVideoGenerationTask({
    prompt: "一只猫穿过雨巷",
    config,
    enhancerModel: "enhancer-native-id",
    generationModel: "generator-native-id",
  });
}

test("derives the two visible progress steps from real task state", () => {
  const optimizing = createTask();
  assert.equal(currentVideoTaskStatus(optimizing), "提示词优化中");
  assert.deepEqual(videoTaskSteps(optimizing).map((step) => step.status), ["active", "pending"]);

  const generating = updateVideoGenerationTask(optimizing, {
    type: "optimization_succeeded",
    optimizedPrompt: "电影感雨巷，镜头跟随一只猫缓慢前行。",
    resolvedMode: "text_to_video",
    enhancerModel: "enhancer-from-server",
  });
  assert.equal(currentVideoTaskStatus(generating), "文生视频进行中");
  assert.deepEqual(videoTaskSteps(generating).map((step) => step.status), ["done", "active"]);

  const success = updateVideoGenerationTask(generating, {
    type: "generation_succeeded",
    output: {
      previewUrl: "/preview.mp4",
      fileName: "video-result.mp4",
      mimeType: "video/mp4",
    },
  });
  assert.equal(currentVideoTaskStatus(success), "视频生成完成");
  assert.deepEqual(videoTaskSteps(success).map((step) => step.label), [
    "提示词优化完成",
    "文生视频已完成",
  ]);
});

test("preserves the real provider phase without inventing a percentage", () => {
  let task = updateVideoGenerationTask(createTask(), {
    type: "optimization_succeeded",
    optimizedPrompt: "电影感雨巷，镜头跟随一只猫缓慢前行。",
    resolvedMode: "text_to_video",
    enhancerModel: "enhancer-from-server",
  });
  task = updateVideoGenerationTask(task, {
    type: "generation_started",
    remoteTaskId: "task-1",
    generationModel: "generator-from-server",
    startedAt: 10_000,
  });

  assert.equal(task.providerStatus, "queued");
  assert.equal(task.generationStartedAt, 10_000);
  assert.equal(currentVideoTaskStatus(task), "文生视频排队中");

  task = updateVideoGenerationTask(task, {
    type: "generation_status_changed",
    providerStatus: "running",
  });
  assert.equal(task.providerStatus, "running");
  assert.equal(currentVideoTaskStatus(task), "文生视频生成中");
});

test("formats elapsed generation time for the progress display", () => {
  assert.equal(formatVideoTaskElapsed(0), "0秒");
  assert.equal(formatVideoTaskElapsed(59_900), "59秒");
  assert.equal(formatVideoTaskElapsed(65_000), "1分05秒");
  assert.equal(formatVideoTaskElapsed(3_725_000), "1小时02分");
});

test("generation retry keeps enhanced prompt and uploaded assets", () => {
  let task = createTask();
  task = updateVideoGenerationTask(task, {
    type: "assets_uploaded",
    assetIds: ["asset-1"],
  });
  task = updateVideoGenerationTask(task, {
    type: "optimization_succeeded",
    optimizedPrompt: "增强后的提示词",
    resolvedMode: "reference_to_video",
    enhancerModel: "enhancer-from-server",
  });
  task = updateVideoGenerationTask(task, {
    type: "failed",
    stage: "generation",
    error: "上游繁忙",
  });
  const retried = updateVideoGenerationTask(task, {
    type: "retry",
    stage: "generation",
  });

  assert.equal(retried.status, "generating");
  assert.equal(retried.optimizedPrompt, "增强后的提示词");
  assert.equal(retried.resolvedMode, "reference_to_video");
  assert.deepEqual(retried.assetIds, ["asset-1"]);
  assert.equal(retried.runId, task.runId + 1);
  assert.equal(isVideoTaskRunning(retried), true);
});

test("optimization failure exposes a retryable first step", () => {
  const failed = updateVideoGenerationTask(createTask(), {
    type: "failed",
    stage: "optimization",
    error: "增强服务不可用",
  });
  assert.deepEqual(videoTaskSteps(failed).map((step) => step.status), ["failed", "pending"]);
  const retried = updateVideoGenerationTask(failed, {
    type: "retry",
    stage: "optimization",
  });
  assert.equal(retried.status, "optimizing");
  assert.equal(retried.error, "");
  assert.equal(currentVideoTaskStatus(retried), "提示词优化中");
});

test("generation failure preserves the complete provider error", () => {
  const providerError = `{
  "code": "OutputTextSensitiveContentDetected",
  "message": "The request was blocked by the provider copyright policy.",
  "request_id": "provider-request-id"
}`;
  const failed = updateVideoGenerationTask(createTask(), {
    type: "failed",
    stage: "generation",
    error: providerError,
  });

  assert.equal(failed.status, "error");
  assert.equal(failed.error, providerError);
});
