import { withAuth } from "../../adk/auth";
import {
  isSupportedCloudRegion,
  type CloudRegion,
} from "../../adk/cloudProvider";
import { withLocalUser } from "../../adk/identity";
import {
  DEFAULT_REQUEST_TIMEOUT_MS,
  requestSignal,
  TRANSFER_REQUEST_TIMEOUT_MS,
} from "../../adk/timeout";
import type {
  SkillCenterOptimizationSource,
  SkillWorkbenchActivity,
  SkillWorkbenchArtifact,
  SkillWorkbenchCapability,
  SkillWorkbenchOperation,
  SkillWorkbenchPublishProgress,
  SkillWorkbenchPublishResult,
  SkillWorkbenchRecoveryStatus,
  SkillWorkbenchTask,
  SkillWorkbenchTaskSummary,
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

function optionalIdentifier(value: unknown, label: string): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string" || !value.trim() || value.trim().length > 256) {
    throw new Error(`${label}格式错误。`);
  }
  return value.trim();
}

function optionalRecoveryStatus(
  value: unknown,
): SkillWorkbenchRecoveryStatus | undefined {
  if (value === undefined || value === null) return undefined;
  if (
    value === "pending" ||
    value === "ready" ||
    value === "failed" ||
    value === "unknown"
  ) return value;
  throw new Error("Skill 恢复点状态格式错误。");
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
    const contentType =
      response.headers.get("content-type")?.split(";", 1)[0] ||
      "Content-Type 缺失";
    return new SkillWorkbenchApiError(
      `${fallback}（HTTP ${response.status}，Content-Type: ${contentType}）。请检查代理或网关配置。`,
      response.status,
    );
  }
}

async function json(response: Response, fallback: string): Promise<unknown> {
  if (!response.ok) throw await errorFrom(response, fallback);
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) {
    const responseType = type.split(";", 1)[0] || "Content-Type 缺失";
    throw new Error(
      `${fallback}：服务端返回非 JSON 响应（HTTP ${response.status}，Content-Type: ${responseType}），请检查代理或网关配置。`,
    );
  }
  return response.json();
}

function normalizeActivities(value: unknown): SkillWorkbenchActivity[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const activity = record(item, "Skill 会话活动");
    const kind = activity.kind;
    const status = activity.status;
    if (
      typeof activity.id !== "string" ||
      !["status", "thinking", "message", "tool"].includes(String(kind)) ||
      !["running", "done"].includes(String(status))
    ) throw new Error("Skill 会话活动格式错误。");
    if (kind === "tool") {
      if (typeof activity.name !== "string") throw new Error("Skill 工具活动格式错误。");
      return {
        id: activity.id,
        kind,
        status: status as SkillWorkbenchActivity["status"],
        name: activity.name,
        ...(activity.input !== undefined ? { args: activity.input } : {}),
        ...(activity.output !== undefined ? { response: activity.output } : {}),
      };
    }
    if (typeof activity.text !== "string") throw new Error("Skill 文本活动格式错误。");
    return {
      id: activity.id,
      kind: kind as "status" | "thinking" | "message",
      status: status as SkillWorkbenchActivity["status"],
      text: activity.text,
    };
  });
}

function normalizePublication(
  value: unknown,
): (SkillWorkbenchPublishResult & { revision: number }) | undefined {
  if (value === undefined || value === null) return undefined;
  const publication = record(value, "Skill 发布结果");
  if (
    typeof publication.revision !== "number" ||
    typeof publication.skillId !== "string" ||
    typeof publication.version !== "string" ||
    !Array.isArray(publication.skillSpaceIds) ||
    !publication.skillSpaceIds.every((item) => typeof item === "string") ||
    (publication.disposition !== "create-new" && publication.disposition !== "update-source") ||
    !isSupportedCloudRegion(publication.region) ||
    typeof publication.projectName !== "string"
  ) throw new Error("Skill 发布结果格式错误。");
  return {
    revision: publication.revision,
    skillId: publication.skillId,
    version: publication.version,
    skillSpaceIds: publication.skillSpaceIds,
    disposition: publication.disposition,
    region: publication.region,
    projectName: publication.projectName,
  };
}

function normalizeTask(value: unknown): SkillWorkbenchTask {
  const task = record(value, "Skill 会话");
  if (
    typeof task.jobId !== "string" ||
    (task.operation !== "create" && task.operation !== "optimize") ||
    typeof task.intent !== "string" ||
    typeof task.revision !== "number" ||
    typeof task.state !== "string"
  ) throw new Error("Skill 会话格式错误。");
  const files = Array.isArray(task.files)
    ? task.files.flatMap((item) => {
        const file = record(item, "Skill 文件");
        return typeof file.path === "string" && typeof file.size === "number"
          ? [{ path: file.path, size: file.size }]
          : [];
      })
    : [];
  const allowedStates = ["running", "ready", "failed", "cancelled", "expired", "published"];
  if (!allowedStates.includes(task.state)) throw new Error("Skill 会话状态无法识别。");
  const toolId = optionalIdentifier(task.toolId, "Tool ID");
  const sessionId = optionalIdentifier(task.sessionId, "Session ID");
  const recoveryStatus = optionalRecoveryStatus(task.recoveryStatus);
  return {
    jobId: task.jobId,
    operation: task.operation,
    intent: task.intent,
    revision: task.revision,
    ...(toolId ? { toolId } : {}),
    ...(sessionId ? { sessionId } : {}),
    ...(typeof task.sessionTtlSeconds === "number"
      ? { sessionTtlSeconds: task.sessionTtlSeconds }
      : {}),
    ...(typeof task.expiresAt === "string" ? { expiresAt: task.expiresAt } : {}),
    ...(typeof task.recoveryAvailable === "boolean"
      ? { recoveryAvailable: task.recoveryAvailable }
      : {}),
    ...(recoveryStatus ? { recoveryStatus } : {}),
    ...(typeof task.recoveredFromSnapshot === "boolean"
      ? { recoveredFromSnapshot: task.recoveredFromSnapshot }
      : {}),
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
    ...(task.publication
      ? { publication: normalizePublication(task.publication) }
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

export async function reserveSkillWorkbenchTask(
  signal?: AbortSignal,
): Promise<{ jobId: string; reservedAt: number }> {
  const value = record(await json(
    await request("/tasks/reservations", { method: "POST", signal }),
    "准备 Skill 会话失败",
  ), "Skill 会话引用");
  if (typeof value.jobId !== "string" || typeof value.reservedAt !== "number") {
    throw new Error("Skill 会话引用格式错误。");
  }
  return { jobId: value.jobId, reservedAt: value.reservedAt };
}

export async function createSkillWorkbenchTask(args: {
  jobId?: string;
  operation: SkillWorkbenchOperation;
  intent: string;
  source?: SkillCenterOptimizationSource;
  file?: File;
  signal?: AbortSignal;
}): Promise<SkillWorkbenchTask> {
  if (args.file) {
    const params = new URLSearchParams({ operation: "optimize", intent: args.intent });
    if (args.jobId) params.set("job_id", args.jobId);
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
    return normalizeTask(await json(response, "开始优化 Skill 失败"));
  }
  const response = await request("/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      operation: args.operation,
      intent: args.intent,
      ...(args.jobId ? { jobId: args.jobId } : {}),
      ...(args.source ? {
        source: {
          kind: "skill-center",
          skillId: args.source.skillId,
          skillName: args.source.name,
          version: args.source.version,
          region: args.source.region,
          projectName: args.source.projectName,
          skillSpaceId: args.source.skillSpaceId,
          skillSpaceName: args.source.skillSpaceName,
        },
      } : {}),
    }),
    signal: args.signal,
  }, TRANSFER_REQUEST_TIMEOUT_MS);
  return normalizeTask(await json(response, "开始 Skill 会话失败"));
}

function normalizeTaskSummary(value: unknown): SkillWorkbenchTaskSummary {
  const task = record(value, "Skill 会话摘要");
  const allowedStates = ["running", "ready", "failed", "cancelled", "expired", "published"];
  if (
    typeof task.jobId !== "string" ||
    (task.operation !== "create" && task.operation !== "optimize") ||
    typeof task.intent !== "string" ||
    typeof task.revision !== "number" ||
    typeof task.state !== "string" ||
    !allowedStates.includes(task.state) ||
    typeof task.createdAt !== "number"
  ) throw new Error("Skill 会话摘要格式错误。");
  const recoveryStatus = optionalRecoveryStatus(task.recoveryStatus);
  return {
    jobId: task.jobId,
    operation: task.operation,
    intent: task.intent,
    revision: task.revision,
    state: task.state as SkillWorkbenchTaskSummary["state"],
    stage: typeof task.stage === "string" ? task.stage : "generating",
    createdAt: task.createdAt,
    ...(typeof task.name === "string" ? { name: task.name } : {}),
    ...(typeof task.sourceName === "string" ? { sourceName: task.sourceName } : {}),
    ...(typeof task.recoveryAvailable === "boolean"
      ? { recoveryAvailable: task.recoveryAvailable }
      : {}),
    ...(recoveryStatus ? { recoveryStatus } : {}),
  };
}

export async function listSkillWorkbenchTasks(
  signal?: AbortSignal,
  excludeJobId?: string,
): Promise<SkillWorkbenchTaskSummary[]> {
  const params = new URLSearchParams();
  if (excludeJobId) params.set("exclude_job_id", excludeJobId);
  const query = params.size > 0 ? `?${params.toString()}` : "";
  const body = record(await json(
    await request(`/tasks${query}`, { signal }),
    "读取 Skill 会话列表失败",
  ), "Skill 会话列表");
  if (!Array.isArray(body.tasks)) throw new Error("Skill 会话列表格式错误。");
  return body.tasks.map(normalizeTaskSummary);
}

export async function getSkillWorkbenchTask(
  jobId: string,
  signal?: AbortSignal,
): Promise<SkillWorkbenchTask> {
  return normalizeTask(await json(
    await request(`/tasks/${encodeURIComponent(jobId)}`, { signal }),
    "读取 Skill 会话失败",
  ));
}

export async function getSkillWorkbenchArtifact(
  jobId: string,
  expectedRevision: number,
  signal?: AbortSignal,
): Promise<SkillWorkbenchArtifact> {
  const params = new URLSearchParams();
  params.set("expected_revision", String(expectedRevision));
  const artifact = record(await json(
    await request(
      `/tasks/${encodeURIComponent(jobId)}/artifact?${params.toString()}`,
      { signal },
    ),
    "读取 Skill 产物失败",
  ), "Skill 产物");
  if (
    artifact.jobId !== jobId ||
    artifact.revision !== expectedRevision ||
    !Number.isSafeInteger(artifact.revision) ||
    artifact.revision < 1 ||
    typeof artifact.sha256 !== "string" ||
    !/^[0-9a-f]{64}$/.test(artifact.sha256) ||
    typeof artifact.name !== "string" ||
    typeof artifact.description !== "string" ||
    !Array.isArray(artifact.files)
  ) throw new Error("Skill 产物格式错误。");
  const files = artifact.files.map((item) => {
    const file = record(item, "Skill 产物文件");
    if (
      typeof file.path !== "string" ||
      typeof file.size !== "number" ||
      typeof file.content !== "string"
    ) throw new Error("Skill 产物文件格式错误。");
    return { path: file.path, size: file.size, content: file.content };
  });
  return {
    jobId: artifact.jobId,
    revision: artifact.revision,
    sha256: artifact.sha256,
    name: artifact.name,
    description: artifact.description,
    files,
  };
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

export async function stopSkillWorkbenchTask(args: {
  jobId: string;
  expectedRevision: number;
}): Promise<SkillWorkbenchTask> {
  const response = await request(`/tasks/${encodeURIComponent(args.jobId)}/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expectedRevision: args.expectedRevision }),
  });
  return normalizeTask(await json(response, "停止当前 Skill 任务失败"));
}

export async function publishSkillWorkbenchTask(args: {
  jobId: string;
  expectedRevision: number;
  expectedArtifactSha256: string;
  disposition: "create-new" | "update-source";
  skillSpaceIds?: string[];
  projectName?: string;
  region?: CloudRegion;
  signal?: AbortSignal;
  onProgress?: (progress: SkillWorkbenchPublishProgress) => void;
}): Promise<SkillWorkbenchPublishResult> {
  const response = await request(`/tasks/${encodeURIComponent(args.jobId)}/publish-stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/x-ndjson",
    },
    body: JSON.stringify({
      disposition: args.disposition,
      expectedRevision: args.expectedRevision,
      expectedArtifactSha256: args.expectedArtifactSha256,
      skillSpaceIds: args.skillSpaceIds ?? [],
      projectName: args.projectName,
      region: args.region,
    }),
    signal: args.signal,
  }, 0);
  if (!response.ok) throw await errorFrom(response, "发布 Skill 失败");
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/x-ndjson")) {
    throw new Error("发布 Skill 失败：服务端返回了非 NDJSON 响应。");
  }
  if (!response.body) throw new Error("发布 Skill 失败：服务端没有返回进度流。");

  const phases = new Set([
    "preparing",
    "uploading",
    "registering",
    "activating",
    "publishing",
  ]);
  let result: SkillWorkbenchPublishResult | null = null;
  let buffered = "";
  const decoder = new TextDecoder();
  const reader = response.body.getReader();

  const consumeLine = (line: string) => {
    if (!line.trim()) return;
    const event = record(JSON.parse(line), "发布进度");
    if (event.type === "progress") {
      if (
        typeof event.phase !== "string" ||
        !phases.has(event.phase) ||
        typeof event.message !== "string"
      ) throw new Error("发布进度格式错误。");
      args.onProgress?.({
        phase: event.phase as SkillWorkbenchPublishProgress["phase"],
        message: event.message,
      });
      return;
    }
    if (event.type === "error") {
      const detail = record(event.error, "发布错误");
      throw new SkillWorkbenchApiError(
        typeof detail.message === "string" ? detail.message : "发布 Skill 失败",
        500,
        typeof detail.code === "string" ? detail.code : "SKILL_PUBLISH_FAILED",
        detail.retryable === true,
      );
    }
    if (event.type !== "complete") throw new Error("未知的发布进度事件。");
    const value = record(event.result, "发布结果");
    if (
      typeof value.skillId !== "string" ||
      typeof value.version !== "string" ||
      !Array.isArray(value.skillSpaceIds) ||
      !value.skillSpaceIds.every((item) => typeof item === "string") ||
      (value.disposition !== "create-new" && value.disposition !== "update-source") ||
      !isSupportedCloudRegion(value.region) ||
      typeof value.projectName !== "string"
    ) throw new Error("发布结果格式错误。");
    result = {
      skillId: value.skillId,
      version: value.version,
      skillSpaceIds: value.skillSpaceIds,
      disposition: value.disposition,
      region: value.region,
      projectName: value.projectName,
    };
  };

  while (true) {
    const { value, done } = await reader.read();
    buffered += decoder.decode(value, { stream: !done });
    const lines = buffered.split("\n");
    buffered = lines.pop() ?? "";
    lines.forEach(consumeLine);
    if (done) break;
  }
  consumeLine(buffered);
  if (!result) {
    throw new Error(
      "发布进度流提前结束，无法确认发布结果。请刷新技能中心确认状态。",
    );
  }
  return result;
}

export async function deleteSkillWorkbenchTask(jobId: string): Promise<void> {
  await json(
    await request(`/tasks/${encodeURIComponent(jobId)}`, { method: "DELETE" }),
    "删除 Skill 会话失败",
  );
}

export async function downloadSkillWorkbenchTask(
  jobId: string,
  expectedRevision: number,
  expectedSha256: string,
): Promise<void> {
  const params = new URLSearchParams();
  params.set("expected_revision", String(expectedRevision));
  params.set("expected_sha256", expectedSha256);
  const response = await request(
    `/tasks/${encodeURIComponent(jobId)}/download?${params.toString()}`,
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
