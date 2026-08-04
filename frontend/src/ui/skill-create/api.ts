import { withAuth } from "../../adk/auth";
import { withLocalUser } from "../../adk/identity";
import {
  type PublishedSkill,
  type PublishSkillOptions,
  type SkillActivity,
  type SkillCandidate,
  type SkillCandidateStage,
  type SkillCandidateStatus,
  type SkillCreationJob,
  type SkillFile,
  type SkillValidation,
} from "./types";

const API_ROOT = "/web/skill-creator";

export class SkillCreatorApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "SkillCreatorApiError";
    this.status = status;
  }
}

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} 格式错误`);
  }
  return value as Record<string, unknown>;
}

function stringValue(record: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value) return value;
  }
  return undefined;
}

function numberValue(record: Record<string, unknown>, ...keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return undefined;
}

async function apiRequest(path: string, init?: RequestInit): Promise<Response> {
  return fetch(withAuth(`${API_ROOT}${path}`), {
    ...init,
    headers: withLocalUser({
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    }),
  });
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const body = asRecord(await response.json(), "错误响应");
    return stringValue(body, "detail", "message", "error") ?? fallback;
  }
  const text = (await response.text()).trim();
  return text || fallback;
}

async function jsonResponse(response: Response, fallback: string): Promise<unknown> {
  if (!response.ok) {
    throw new SkillCreatorApiError(await errorMessage(response, fallback), response.status);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new Error(`${fallback}：服务端返回了非 JSON 响应`);
  }
  return response.json();
}

function normalizeStatus(value: unknown): SkillCandidateStatus {
  if (value === "queued") return "queued";
  if (value === "running") return "running";
  if (value === "succeeded") return "succeeded";
  if (value === "failed") return "failed";
  throw new Error(`未知的 Skill 生成状态：${String(value)}`);
}

function normalizeStage(value: unknown): SkillCandidateStage {
  if (
    value === "provisioning" ||
    value === "generating" ||
    value === "validating" ||
    value === "packaging" ||
    value === "completed" ||
    value === "failed"
  ) return value;
  throw new Error(`未知的 Skill 生成阶段：${String(value)}`);
}

function normalizeFiles(value: unknown): SkillFile[] {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    const file = asRecord(item, `文件 ${index + 1}`);
    const path = stringValue(file, "path");
    if (!path) throw new Error(`文件 ${index + 1} 缺少 path`);
    const size = numberValue(file, "size");
    if (size === undefined) throw new Error(`文件 ${index + 1} 缺少 size`);
    return { path, size };
  });
}

function normalizeValidation(value: unknown): SkillValidation | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const validation = value as Record<string, unknown>;
  const errors = Array.isArray(validation.errors)
    ? validation.errors.map(String)
    : [];
  const warnings = Array.isArray(validation.warnings)
    ? validation.warnings.map(String)
    : [];
  const valid = typeof validation.valid === "boolean"
    ? validation.valid
    : errors.length === 0;
  return { valid, errors, warnings };
}

function normalizeActivities(value: unknown): SkillActivity[] {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw new Error("Skill 生成活动记录格式错误");
  return value.map((item, index) => {
    const activity = asRecord(item, `活动 ${index + 1}`);
    const id = stringValue(activity, "id");
    const kind = stringValue(activity, "kind");
    const status = stringValue(activity, "status");
    if (!id || !kind || !["status", "thinking", "tool", "message"].includes(kind)) {
      throw new Error(`活动 ${index + 1} 格式错误`);
    }
    if (status !== "running" && status !== "done") {
      throw new Error(`活动 ${index + 1} 状态错误`);
    }
    if (kind === "tool") {
      const name = stringValue(activity, "name");
      if (!name) throw new Error(`活动 ${index + 1} 缺少工具名称`);
      return {
        id,
        kind,
        name,
        args: activity.input,
        response: activity.output,
        status,
      };
    }
    const text = stringValue(activity, "text");
    if (!text) throw new Error(`活动 ${index + 1} 缺少文本`);
    return {
      id,
      kind: kind as "status" | "thinking" | "message",
      text,
      status,
    };
  });
}

function normalizeCandidate(value: unknown, index: number): SkillCandidate {
  const candidate = asRecord(value, `候选方案 ${index + 1}`);
  const id = stringValue(candidate, "id", "candidate_id", "candidateId");
  const model = stringValue(candidate, "model", "model_id", "modelId");
  if (!id || !model) throw new Error(`候选方案 ${index + 1} 缺少 id 或 model`);
  return {
    id,
    model,
    modelLabel: stringValue(candidate, "modelLabel", "model_label") ?? model,
    status: normalizeStatus(candidate.status),
    stage: normalizeStage(candidate.stage),
    name: stringValue(candidate, "name", "skill_name", "skillName"),
    description: stringValue(candidate, "description"),
    skillMd: stringValue(candidate, "skillMd", "skill_md"),
    files: normalizeFiles(candidate.files),
    activities: normalizeActivities(candidate.activities),
    validation: normalizeValidation(candidate.validation),
    durationMs: numberValue(candidate, "elapsedMs", "elapsed_ms"),
    error: stringValue(candidate, "error", "error_message", "errorMessage"),
    published: candidate.published === true,
    skillId: stringValue(candidate, "skill_id", "skillId"),
    version: stringValue(candidate, "version"),
  };
}

function normalizeJob(value: unknown, fallbackPrompt = ""): SkillCreationJob {
  const job = asRecord(value, "Skill 创建任务");
  const id = stringValue(job, "id", "job_id", "jobId");
  if (!id) throw new Error("Skill 创建任务缺少 id");
  const candidates = Array.isArray(job.candidates)
    ? job.candidates.map(normalizeCandidate)
    : [];
  const status = stringValue(job, "status") ?? "running";
  if (status !== "provisioning" && status !== "running" && status !== "completed") {
    throw new Error(`未知的 Skill 任务状态：${status}`);
  }
  return {
    id,
    prompt: stringValue(job, "prompt") ?? fallbackPrompt,
    status,
    candidates,
  };
}

export async function createSkillJob(
  prompt: string,
  onProgress?: (job: SkillCreationJob) => void,
): Promise<SkillCreationJob> {
  const response = await apiRequest("/jobs", {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
  if (!response.ok) {
    throw new SkillCreatorApiError(
      await errorMessage(response, "创建 Skill 任务失败"),
      response.status,
    );
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const job = normalizeJob(await response.json(), prompt);
    onProgress?.(job);
    return job;
  }
  if (!contentType.includes("application/x-ndjson") || !response.body) {
    throw new Error("创建 Skill 任务失败：服务端返回了非流式响应");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let latest: SkillCreationJob | undefined;
  const consume = (line: string) => {
    if (!line.trim()) return;
    const event = asRecord(JSON.parse(line), "Skill 创建进度");
    if (event.type === "error") {
      throw new Error(stringValue(event, "error") ?? "创建 Skill 任务失败");
    }
    if (event.type !== "progress" && event.type !== "complete") {
      throw new Error("未知的 Skill 创建进度事件");
    }
    latest = normalizeJob(event.job, prompt);
    onProgress?.(latest);
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    lines.forEach(consume);
    if (done) break;
  }
  consume(buffer);
  if (!latest) throw new Error("创建 Skill 任务失败：服务端未返回任务");
  return latest;
}

export async function getSkillJob(jobId: string): Promise<SkillCreationJob> {
  const response = await apiRequest(`/jobs/${encodeURIComponent(jobId)}`);
  return normalizeJob(await jsonResponse(response, "读取 Skill 任务失败"));
}

export async function deleteSkillJob(jobId: string): Promise<void> {
  const response = await apiRequest(`/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
  await jsonResponse(response, "清理 Skill 任务失败");
}

export async function downloadSkillCandidate(jobId: string, candidateId: string): Promise<void> {
  const response = await apiRequest(
    `/jobs/${encodeURIComponent(jobId)}/candidates/${encodeURIComponent(candidateId)}/download`,
  );
  if (!response.ok) throw new Error(await errorMessage(response, "下载 Skill 失败"));
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? "skill.zip";
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function publishSkillCandidate(
  jobId: string,
  candidateId: string,
  options: PublishSkillOptions,
): Promise<PublishedSkill> {
  const response = await apiRequest(
    `/jobs/${encodeURIComponent(jobId)}/candidates/${encodeURIComponent(candidateId)}/publish`,
    { method: "POST", body: JSON.stringify(options) },
  );
  const body = asRecord(await jsonResponse(response, "添加到 AgentKit 失败"), "发布结果");
  const skillId = stringValue(body, "skill_id", "skillId", "id");
  if (!skillId) throw new Error("发布结果缺少 skill_id");
  return {
    skillId,
    name: stringValue(body, "name"),
    version: stringValue(body, "version"),
    skillSpaceIds: Array.isArray(body.skillSpaceIds)
      ? body.skillSpaceIds.map(String)
      : Array.isArray(body.skill_space_ids) ? body.skill_space_ids.map(String) : [],
    message: stringValue(body, "message"),
  };
}
