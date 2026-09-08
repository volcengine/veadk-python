import type { NewChatVideoConfig, VideoTaskMode } from "./video-types";
import { newChatT } from "./newChatI18n";

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

export function videoTaskModeLabel(
  mode: VideoTaskMode | null,
  locale?: string,
): string {
  return newChatT(`video.taskNames.${mode ?? "auto"}`, locale ? { lng: locale } : {});
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

export function videoTaskSteps(
  task: VideoGenerationTask,
  locale?: string,
): VideoTaskStep[] {
  const options = locale ? { lng: locale } : {};
  const taskLabel = videoTaskModeLabel(task.resolvedMode, locale);
  const optimizationFailed =
    task.status === "error" && task.errorStage === "optimization";
  const generationFailed =
    task.status === "error" && task.errorStage === "generation";
  const optimizationDone =
    Boolean(task.optimizedPrompt) && !optimizationFailed;

  return [
    {
      id: "optimization",
      label: newChatT(
        optimizationFailed
          ? "video.task.steps.optimizationFailed"
          : optimizationDone
            ? "video.task.steps.optimizationDone"
            : "video.task.steps.optimizationActive",
        options,
      ),
      status: optimizationFailed
        ? "failed"
        : optimizationDone
          ? "done"
          : "active",
    },
    {
      id: "generation",
      label: newChatT(
        task.status === "success"
          ? "video.task.steps.generationDone"
          : generationFailed
            ? "video.task.steps.generationFailed"
            : task.status === "generating"
              ? task.providerStatus === "queued"
                ? "video.task.steps.generationQueued"
                : task.providerStatus === "running"
                  ? "video.task.steps.generationRunning"
                  : "video.task.steps.generationActive"
              : "video.task.steps.generationPending",
        { ...options, task: taskLabel },
      ),
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

export function formatVideoTaskElapsed(elapsedMs: number, locale?: string): string {
  const options = locale ? { lng: locale } : {};
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1_000));
  const hours = Math.floor(totalSeconds / 3_600);
  const minutes = Math.floor((totalSeconds % 3_600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return newChatT("video.task.elapsedHours", {
      ...options,
      hours,
      minutes: String(minutes).padStart(2, "0"),
    });
  }
  if (minutes > 0) {
    return newChatT("video.task.elapsedMinutes", {
      ...options,
      minutes,
      seconds: String(seconds).padStart(2, "0"),
    });
  }
  return newChatT("video.task.elapsedSeconds", { ...options, seconds });
}

export function currentVideoTaskStatus(
  task: VideoGenerationTask,
  locale?: string,
): string {
  const steps = videoTaskSteps(task, locale);
  return steps.find((step) => step.status === "active")?.label
    ?? steps.find((step) => step.status === "failed")?.label
    ?? newChatT("video.task.steps.generationComplete", locale ? { lng: locale } : {});
}

export function isVideoTaskRunning(task: VideoGenerationTask | null): boolean {
  return task?.status === "optimizing" || task?.status === "generating";
}
