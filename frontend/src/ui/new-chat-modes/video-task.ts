import type { NewChatVideoConfig, VideoTaskMode } from "./video-types";

export type VideoTaskStatus =
  | "optimizing"
  | "generating"
  | "success"
  | "error";

export type VideoTaskErrorStage = "optimization" | "generation";
export type VideoProviderStatus = "queued" | "running";

export interface VideoTaskOutput {
  previewUrl: string;
  fileName: string;
  mimeType: string;
}

export interface VideoGenerationTask {
  localId: string;
  remoteTaskId: string;
  runId: number;
  status: VideoTaskStatus;
  requestedPrompt: string;
  optimizedPrompt: string;
  requestedMode: VideoTaskMode;
  resolvedMode: VideoTaskMode | null;
  config: NewChatVideoConfig;
  enhancerModel: string;
  generationModel: string;
  providerStatus: VideoProviderStatus | null;
  generationStartedAt: number | null;
  assetIds: string[];
  output: VideoTaskOutput | null;
  errorStage: VideoTaskErrorStage | null;
  error: string;
}

export type VideoTaskEvent =
  | {
      type: "optimization_succeeded";
      optimizedPrompt: string;
      resolvedMode: VideoTaskMode;
      enhancerModel: string;
    }
  | { type: "assets_uploaded"; assetIds: string[] }
  | {
      type: "generation_started";
      remoteTaskId: string;
      generationModel: string;
      startedAt: number;
    }
  | {
      type: "generation_status_changed";
      providerStatus: VideoProviderStatus;
    }
  | { type: "generation_succeeded"; output: VideoTaskOutput }
  | { type: "failed"; stage: VideoTaskErrorStage; error: string }
  | { type: "retry"; stage: VideoTaskErrorStage };

export interface VideoTaskStep {
  id: "optimization" | "generation";
  label: string;
  status: "pending" | "active" | "done" | "failed";
}

const VIDEO_TASK_LABELS: Record<VideoTaskMode, string> = {
  auto: "视频生成",
  text_to_video: "文生视频",
  reference_to_video: "参考素材生视频",
  video_editing: "视频编辑",
  video_extension: "视频续写",
  first_last_frame: "首尾帧生成",
};

export function videoTaskModeLabel(mode: VideoTaskMode | null): string {
  return mode ? VIDEO_TASK_LABELS[mode] : "视频生成";
}

export function createVideoGenerationTask({
  prompt,
  config,
  enhancerModel,
  generationModel,
}: {
  prompt: string;
  config: NewChatVideoConfig;
  enhancerModel: string;
  generationModel: string;
}): VideoGenerationTask {
  return {
    localId: crypto.randomUUID(),
    remoteTaskId: "",
    runId: 1,
    status: "optimizing",
    requestedPrompt: prompt,
    optimizedPrompt: "",
    requestedMode: config.taskMode,
    resolvedMode: null,
    config: { ...config },
    enhancerModel,
    generationModel,
    providerStatus: null,
    generationStartedAt: null,
    assetIds: [],
    output: null,
    errorStage: null,
    error: "",
  };
}

export function updateVideoGenerationTask(
  task: VideoGenerationTask,
  event: VideoTaskEvent,
): VideoGenerationTask {
  if (event.type === "optimization_succeeded") {
    return {
      ...task,
      status: "generating",
      optimizedPrompt: event.optimizedPrompt,
      resolvedMode: event.resolvedMode,
      enhancerModel: event.enhancerModel,
      errorStage: null,
      error: "",
    };
  }
  if (event.type === "assets_uploaded") {
    return { ...task, assetIds: event.assetIds };
  }
  if (event.type === "generation_started") {
    return {
      ...task,
      status: "generating",
      remoteTaskId: event.remoteTaskId,
      generationModel: event.generationModel,
      providerStatus: "queued",
      generationStartedAt: event.startedAt,
      errorStage: null,
      error: "",
    };
  }
  if (event.type === "generation_status_changed") {
    if (task.providerStatus === event.providerStatus) return task;
    return { ...task, providerStatus: event.providerStatus };
  }
  if (event.type === "generation_succeeded") {
    return {
      ...task,
      status: "success",
      providerStatus: null,
      output: event.output,
      errorStage: null,
      error: "",
    };
  }
  if (event.type === "failed") {
    return {
      ...task,
      status: "error",
      providerStatus: null,
      errorStage: event.stage,
      error: event.error,
    };
  }
  return {
    ...task,
    runId: task.runId + 1,
    status: event.stage === "optimization" ? "optimizing" : "generating",
    remoteTaskId: "",
    providerStatus: null,
    generationStartedAt: null,
    optimizedPrompt: event.stage === "optimization" ? "" : task.optimizedPrompt,
    resolvedMode: event.stage === "optimization" ? null : task.resolvedMode,
    output: null,
    errorStage: null,
    error: "",
  };
}

export function videoTaskSteps(task: VideoGenerationTask): VideoTaskStep[] {
  const taskLabel = videoTaskModeLabel(task.resolvedMode);
  const optimizationFailed =
    task.status === "error" && task.errorStage === "optimization";
  const generationFailed =
    task.status === "error" && task.errorStage === "generation";
  const optimizationDone =
    Boolean(task.optimizedPrompt) && !optimizationFailed;

  return [
    {
      id: "optimization",
      label: optimizationFailed
        ? "提示词优化失败"
        : optimizationDone
          ? "提示词优化完成"
          : "提示词优化中",
      status: optimizationFailed
        ? "failed"
        : optimizationDone
          ? "done"
          : "active",
    },
    {
      id: "generation",
      label: task.status === "success"
        ? `${taskLabel}已完成`
        : generationFailed
          ? `${taskLabel}失败`
          : task.status === "generating"
            ? task.providerStatus === "queued"
              ? `${taskLabel}排队中`
              : task.providerStatus === "running"
                ? `${taskLabel}生成中`
                : `${taskLabel}进行中`
            : "等待视频生成",
      status: task.status === "success"
        ? "done"
        : generationFailed
          ? "failed"
          : task.status === "generating"
            ? "active"
            : "pending",
    },
  ];
}

export function formatVideoTaskElapsed(elapsedMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1_000));
  const hours = Math.floor(totalSeconds / 3_600);
  const minutes = Math.floor((totalSeconds % 3_600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}小时${String(minutes).padStart(2, "0")}分`;
  if (minutes > 0) return `${minutes}分${String(seconds).padStart(2, "0")}秒`;
  return `${seconds}秒`;
}

export function currentVideoTaskStatus(task: VideoGenerationTask): string {
  return videoTaskSteps(task).find((step) => step.status === "active")?.label
    ?? videoTaskSteps(task).find((step) => step.status === "failed")?.label
    ?? "视频生成完成";
}

export function isVideoTaskRunning(task: VideoGenerationTask | null): boolean {
  return task?.status === "optimizing" || task?.status === "generating";
}
