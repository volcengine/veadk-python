import { withAuth } from "../../adk/auth";
import { withLocalUser } from "../../adk/identity";
import {
  DEFAULT_REQUEST_TIMEOUT_MS,
  requestSignal,
  TRANSFER_REQUEST_TIMEOUT_MS,
} from "../../adk/timeout";
import type {
  SkillCenterOptimizationSource,
  SkillWorkbenchActivity,
  SkillWorkbenchCapability,
  SkillWorkbenchOperation,
  SkillWorkbenchTask,
} from "./types";

const API_ROOT = "/web/skill-workbench";

export class SkillWorkbenchApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "SKILL_WORKBENCH_ERROR",
    readonly retryable = false,
  ) {
    super(message);
    this.name = "SkillWorkbenchApiError";
  }
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label}格式错误。`);
  }
  return value as Record<string, unknown>;
}

async function request(
  path: string,
  init: RequestInit = {},
  timeout = DEFAULT_REQUEST_TIMEOUT_MS,
): Promise<Response> {
  return fetch(withAuth(`${API_ROOT}${path}`), {
    ...init,
    headers: withLocalUser(init.headers),
    signal: requestSignal(init.signal, timeout),
  });
}

async function errorFrom(response: Response, fallback: string): Promise<Error> {
  const text = await response.text().catch(() => "");
  try {
    const body = record(JSON.parse(text), "错误响应");
    const detail = body.detail && typeof body.detail === "object"
      ? record(body.detail, "错误详情")
      : body;
    return new SkillWorkbenchApiError(
      typeof detail.message === "string" ? detail.message : fallback,
      response.status,
      typeof detail.code === "string" ? detail.code : "SKILL_WORKBENCH_ERROR",
      detail.retryable === true,
    );
  } catch {
    return new SkillWorkbenchApiError(
      text || `${fallback}（HTTP ${response.status}）`,
      response.status,
    );
  }
}

async function json(response: Response, fallback: string): Promise<unknown> {
  if (!response.ok) throw await errorFrom(response, fallback);
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) {
    throw new Error(`${fallback}：服务端返回了非 JSON 响应。`);
  }
  return response.json();
}

function normalizeActivities(value: unknown): SkillWorkbenchActivity[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const activity = record(item, "任务活动");
    const kind = activity.kind;
    const status = activity.status;
    if (
      typeof activity.id !== "string" ||
      !["status", "thinking", "message", "tool"].includes(String(kind)) ||
      !["running", "done"].includes(String(status))
    ) throw new Error("任务活动格式错误。");
    if (kind === "tool") {
      if (typeof activity.name !== "string") throw new Error("任务工具活动格式错误。");
      return {
        id: activity.id,
        kind,
        status: status as SkillWorkbenchActivity["status"],
        name: activity.name,
        ...(activity.input !== undefined ? { args: activity.input } : {}),
        ...(activity.output !== undefined ? { response: activity.output } : {}),
      };
    }
    if (typeof activity.text !== "string") throw new Error("任务文本活动格式错误。");
    return {
      id: activity.id,
      kind: kind as "status" | "thinking" | "message",
      status: status as SkillWorkbenchActivity["status"],
      text: activity.text,
    };
  });
}

function normalizeTask(value: unknown): SkillWorkbenchTask {
  const task = record(value, "Skill 任务");
  if (
    typeof task.jobId !== "string" ||
    (task.operation !== "create" && task.operation !== "optimize") ||
    typeof task.intent !== "string" ||
    typeof task.revision !== "number" ||
    typeof task.state !== "string"
  ) throw new Error("Skill 任务格式错误。");
  const files = Array.isArray(task.files)
    ? task.files.flatMap((item) => {
        const file = record(item, "Skill 文件");
        return typeof file.path === "string" && typeof file.size === "number"
          ? [{ path: file.path, size: file.size }]
          : [];
      })
    : [];
  const allowedStates = ["running", "ready", "failed", "cancelled", "expired", "published"];
  if (!allowedStates.includes(task.state)) throw new Error("未知的 Skill 任务状态。");
  return {
    jobId: task.jobId,
    operation: task.operation,
    intent: task.intent,
    revision: task.revision,
    state: task.state as SkillWorkbenchTask["state"],
    stage: typeof task.stage === "string" ? task.stage : "generating",
    activities: normalizeActivities(task.activities),
    files,
    ...(task.source && typeof task.source === "object"
      ? { source: task.source as SkillWorkbenchTask["source"] }
      : {}),
    ...(typeof task.name === "string" ? { name: task.name } : {}),
    ...(typeof task.description === "string" ? { description: task.description } : {}),
    ...(typeof task.skillMd === "string" ? { skillMd: task.skillMd } : {}),
    ...(typeof task.error === "string" ? { error: task.error } : {}),
    ...(task.validation && typeof task.validation === "object"
      ? { validation: task.validation as SkillWorkbenchTask["validation"] }
      : {}),
  };
}

export async function getSkillWorkbenchCapability(
  signal?: AbortSignal,
): Promise<SkillWorkbenchCapability> {
  const body = record(await json(
    await request("/capabilities", { signal }),
    "读取 Skill 工作台能力失败",
  ), "Skill 工作台能力");
  return {
    enabled: body.enabled === true,
    reason: typeof body.reason === "string" ? body.reason : "",
    operations: Array.isArray(body.operations)
      ? body.operations.filter((item): item is SkillWorkbenchOperation =>
          item === "create" || item === "optimize"
        )
      : [],
    ...(typeof body.maxUploadBytes === "number"
      ? { maxUploadBytes: body.maxUploadBytes }
      : {}),
  };
}

export async function createSkillWorkbenchTask(args: {
  operation: SkillWorkbenchOperation;
  intent: string;
  source?: SkillCenterOptimizationSource;
  file?: File;
  signal?: AbortSignal;
}): Promise<SkillWorkbenchTask> {
  if (args.file) {
    const params = new URLSearchParams({ operation: "optimize", intent: args.intent });
    const response = await request(
      `/tasks/from-upload?${params}`,
      {
        method: "POST",
        body: args.file,
        headers: { "Content-Type": "application/zip" },
        signal: args.signal,
      },
      TRANSFER_REQUEST_TIMEOUT_MS,
    );
    return normalizeTask(await json(response, "创建 Skill 优化任务失败"));
  }
  const response = await request("/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      operation: args.operation,
      intent: args.intent,
      ...(args.source ? {
        source: {
          kind: "skill-center",
          skillId: args.source.skillId,
          version: args.source.version,
          region: args.source.region,
          projectName: args.source.projectName,
          skillSpaceId: args.source.skillSpaceId,
        },
      } : {}),
    }),
    signal: args.signal,
  }, TRANSFER_REQUEST_TIMEOUT_MS);
  return normalizeTask(await json(response, "创建 Skill 任务失败"));
}

export async function getSkillWorkbenchTask(
  jobId: string,
  signal?: AbortSignal,
): Promise<SkillWorkbenchTask> {
  return normalizeTask(await json(
    await request(`/tasks/${encodeURIComponent(jobId)}`, { signal }),
    "读取 Skill 任务失败",
  ));
}

export async function refineSkillWorkbenchTask(args: {
  jobId: string;
  intent: string;
  expectedRevision: number;
}): Promise<SkillWorkbenchTask> {
  const response = await request(`/tasks/${encodeURIComponent(args.jobId)}/refinements`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      intent: args.intent,
      expectedRevision: args.expectedRevision,
    }),
  }, TRANSFER_REQUEST_TIMEOUT_MS);
  return normalizeTask(await json(response, "继续调整 Skill 失败"));
}

export async function publishSkillWorkbenchTask(args: {
  jobId: string;
  expectedRevision: number;
  disposition: "create-new" | "update-source";
  skillSpaceIds?: string[];
  projectName?: string;
}): Promise<{ skillId: string; version: string }> {
  const response = await request(`/tasks/${encodeURIComponent(args.jobId)}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      disposition: args.disposition,
      expectedRevision: args.expectedRevision,
      skillSpaceIds: args.skillSpaceIds ?? [],
      projectName: args.projectName,
    }),
  }, TRANSFER_REQUEST_TIMEOUT_MS);
  const value = record(await json(response, "发布 Skill 失败"), "发布结果");
  if (typeof value.skillId !== "string" || typeof value.version !== "string") {
    throw new Error("发布结果格式错误。");
  }
  return { skillId: value.skillId, version: value.version };
}

export async function deleteSkillWorkbenchTask(jobId: string): Promise<void> {
  await json(
    await request(`/tasks/${encodeURIComponent(jobId)}`, { method: "DELETE" }),
    "清理 Skill 任务失败",
  );
}

export async function downloadSkillWorkbenchTask(jobId: string): Promise<void> {
  const response = await request(
    `/tasks/${encodeURIComponent(jobId)}/download`,
    {},
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
  if (!response.ok) throw await errorFrom(response, "下载 Skill 失败");
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? "skill.zip";
  const url = URL.createObjectURL(await response.blob());
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}
