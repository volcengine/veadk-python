import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/ui/new-chat-modes/video-task.ts", import.meta.url))],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
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
  assert.equal(currentVideoTaskStatus(optimizing, "zh-CN"), "提示词优化中");
  assert.deepEqual(videoTaskSteps(optimizing, "zh-CN").map((step) => step.status), ["active", "pending"]);

  const generating = updateVideoGenerationTask(optimizing, {
    type: "optimization_succeeded",
    optimizedPrompt: "电影感雨巷，镜头跟随一只猫缓慢前行。",
    resolvedMode: "text_to_video",
    enhancerModel: "enhancer-from-server",
  });
  assert.equal(currentVideoTaskStatus(generating, "zh-CN"), "文生视频进行中");
  assert.equal(currentVideoTaskStatus(generating, "en-US"), "Text-to-video in progress");
  assert.deepEqual(videoTaskSteps(generating, "zh-CN").map((step) => step.status), ["done", "active"]);

  const success = updateVideoGenerationTask(generating, {
    type: "generation_succeeded",
    output: {
      previewUrl: "/preview.mp4",
      fileName: "video-result.mp4",
      mimeType: "video/mp4",
    },
  });
  assert.equal(currentVideoTaskStatus(success, "zh-CN"), "视频生成完成");
  assert.deepEqual(videoTaskSteps(success, "zh-CN").map((step) => step.label), [
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
  assert.equal(currentVideoTaskStatus(task, "zh-CN"), "文生视频排队中");

  task = updateVideoGenerationTask(task, {
    type: "generation_status_changed",
    providerStatus: "running",
  });
  assert.equal(task.providerStatus, "running");
  assert.equal(currentVideoTaskStatus(task, "zh-CN"), "文生视频生成中");
});

test("formats elapsed generation time for the progress display", () => {
  assert.equal(formatVideoTaskElapsed(0, "zh-CN"), "0秒");
  assert.equal(formatVideoTaskElapsed(59_900, "zh-CN"), "59秒");
  assert.equal(formatVideoTaskElapsed(65_000, "zh-CN"), "1分05秒");
  assert.equal(formatVideoTaskElapsed(3_725_000, "zh-CN"), "1小时02分");
  assert.equal(formatVideoTaskElapsed(65_000, "en-US"), "1m 05s");
  assert.equal(formatVideoTaskElapsed(3_725_000, "en-US"), "1h 02m");
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
  assert.deepEqual(videoTaskSteps(failed, "zh-CN").map((step) => step.status), ["failed", "pending"]);
  const retried = updateVideoGenerationTask(failed, {
    type: "retry",
    stage: "optimization",
  });
  assert.equal(retried.status, "optimizing");
  assert.equal(retried.error, "");
  assert.equal(currentVideoTaskStatus(retried, "zh-CN"), "提示词优化中");
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
