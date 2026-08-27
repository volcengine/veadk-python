import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import { studioFetch } from "./client";
import { TRANSFER_REQUEST_TIMEOUT_MS } from "./timeout";

export interface IntelligentDevelopmentProject {
  schemaVersion: "1";
  projectId: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  latestVersionId: string;
  latestVersionCreatedAt: string;
  latestVersionVerified: boolean;
  latestAgentName: string;
  versionCount: number;
}

export interface IntelligentDevelopmentVersion {
  schemaVersion: "1";
  projectId: string;
  versionId: string;
  parentVersionId: string | null;
  sourceSessionId: string;
  createdAt: string;
  intentSummary: string;
  acceptanceCriteria: string[];
  artifactSha256: string;
  validationReportSha256: string;
  artifactSize: number;
  fileCount: number;
  agentName: string;
  entryPoint: string;
  verified: boolean;
  validationSummary: string;
  gateSummary: string[];
  validatedAt: string;
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const raw = await response.text().catch(() => "");
  try {
    const body = JSON.parse(raw) as {
      detail?: unknown;
      error?: unknown;
    };
    const detail = body.detail ?? body.error;
    if (typeof detail === "string" && detail.trim()) {
      return new Error(detail.trim());
    }
    if (
      detail
      && typeof detail === "object"
      && "message" in detail
      && typeof detail.message === "string"
      && detail.message.trim()
    ) {
      return new Error(detail.message.trim());
    }
  } catch {
    if (raw.trim()) return new Error(raw.trim().slice(0, 500));
  }
  return new Error(`${fallback}（HTTP ${response.status}）`);
}

function responseFilename(response: Response, fallback: string): string {
  const disposition = response.headers.get("content-disposition") ?? "";
  return disposition.match(/filename="([^"]+)"/i)?.[1] ?? fallback;
}

function parseRelease(
  value: Partial<IntelligentDevelopmentReleaseRef>,
  sessionId: string,
  expected?: {
    artifactSha256: string;
    validationReportSha256: string;
    projectId?: string;
    versionId?: string;
  },
): IntelligentDevelopmentReleaseRef {
  if (
    value.sessionId !== sessionId
    || (expected !== undefined
      && (
        value.artifactSha256 !== expected.artifactSha256
        || value.validationReportSha256 !== expected.validationReportSha256
        || (expected.projectId !== undefined
          && value.projectId !== expected.projectId)
        || (expected.versionId !== undefined
          && value.versionId !== expected.versionId)
      ))
    || typeof value.artifactSha256 !== "string"
    || typeof value.validationReportSha256 !== "string"
    || typeof value.agentName !== "string"
    || typeof value.entryPoint !== "string"
    || typeof value.fileCount !== "number"
    || typeof value.artifactSize !== "number"
    || typeof value.validatedAt !== "string"
    || typeof value.deployable !== "boolean"
    || typeof value.verified !== "boolean"
    || typeof value.validationSummary !== "string"
    || !Array.isArray(value.gateSummary)
    || !value.gateSummary.every((item) => typeof item === "string")
    || !Array.isArray(value.files)
    || !value.files.every(
      (item) => item && typeof item.path === "string" && typeof item.content === "string",
    )
    || ((value.projectId !== undefined || value.versionId !== undefined)
      && (typeof value.projectId !== "string" || typeof value.versionId !== "string"))
    || !(
      value.parentVersionId === undefined
      || value.parentVersionId === null
      || typeof value.parentVersionId === "string"
    )
  ) {
    throw new Error("源码快照的响应格式无效。");
  }
  return value as IntelligentDevelopmentReleaseRef;
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

async function responseJson(response: Response, message: string): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new Error(message);
  }
}

function parseProject(value: unknown): IntelligentDevelopmentProject {
  const item = record(value);
  if (
    item?.schemaVersion !== "1"
    || typeof item.projectId !== "string"
    || typeof item.name !== "string"
    || typeof item.createdAt !== "string"
    || typeof item.updatedAt !== "string"
    || typeof item.latestVersionId !== "string"
    || typeof item.latestVersionCreatedAt !== "string"
    || typeof item.latestVersionVerified !== "boolean"
    || typeof item.latestAgentName !== "string"
    || typeof item.versionCount !== "number"
    || !Number.isInteger(item.versionCount)
    || item.versionCount < 1
  ) {
    throw new Error("项目列表的响应格式无效。");
  }
  return item as unknown as IntelligentDevelopmentProject;
}

function parseVersion(value: unknown): IntelligentDevelopmentVersion {
  const item = record(value);
  if (
    item?.schemaVersion !== "1"
    || typeof item.projectId !== "string"
    || typeof item.versionId !== "string"
    || !(item.parentVersionId === null || typeof item.parentVersionId === "string")
    || typeof item.sourceSessionId !== "string"
    || typeof item.createdAt !== "string"
    || typeof item.intentSummary !== "string"
    || !Array.isArray(item.acceptanceCriteria)
    || !item.acceptanceCriteria.every((entry) => typeof entry === "string")
    || typeof item.artifactSha256 !== "string"
    || typeof item.validationReportSha256 !== "string"
    || typeof item.artifactSize !== "number"
    || !Number.isInteger(item.artifactSize)
    || item.artifactSize < 1
    || typeof item.fileCount !== "number"
    || !Number.isInteger(item.fileCount)
    || item.fileCount < 1
    || typeof item.agentName !== "string"
    || typeof item.entryPoint !== "string"
    || typeof item.verified !== "boolean"
    || typeof item.validationSummary !== "string"
    || !Array.isArray(item.gateSummary)
    || !item.gateSummary.every((entry) => typeof entry === "string")
    || typeof item.validatedAt !== "string"
  ) {
    throw new Error("项目版本的响应格式无效。");
  }
  return item as unknown as IntelligentDevelopmentVersion;
}

export async function fetchIntelligentDevelopmentProjects(
  signal?: AbortSignal,
): Promise<IntelligentDevelopmentProject[]> {
  const response = await studioFetch(
    "/web/intelligent-development/projects",
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) {
    throw await responseError(response, "无法读取已保存项目");
  }
  const body = record(await responseJson(response, "项目列表的响应格式无效。"));
  if (!Array.isArray(body?.projects)) {
    throw new Error("项目列表的响应格式无效。");
  }
  return body.projects.map(parseProject);
}

export async function fetchIntelligentDevelopmentVersions(
  projectId: string,
  signal?: AbortSignal,
): Promise<IntelligentDevelopmentVersion[]> {
  const response = await studioFetch(
    `/web/intelligent-development/projects/${encodeURIComponent(projectId)}/versions`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) {
    throw await responseError(response, "无法读取项目版本");
  }
  const body = record(await responseJson(response, "项目版本的响应格式无效。"));
  if (!Array.isArray(body?.versions)) {
    throw new Error("项目版本的响应格式无效。");
  }
  return body.versions.map(parseVersion);
}

export async function deleteIntelligentDevelopmentVersion(
  projectId: string,
  versionId: string,
  signal?: AbortSignal,
): Promise<{ projectDeleted: boolean }> {
  const response = await studioFetch(
    `/web/intelligent-development/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}`,
    { method: "DELETE", headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) {
    throw await responseError(response, "删除项目版本失败");
  }
  const body = record(await responseJson(response, "删除项目版本的响应格式无效。"));
  if (body?.deleted !== true || typeof body.projectDeleted !== "boolean") {
    throw new Error("删除项目版本的响应格式无效。");
  }
  return { projectDeleted: body.projectDeleted };
}

export async function fetchIntelligentDevelopmentVersionSource(
  version: IntelligentDevelopmentVersion,
  signal?: AbortSignal,
): Promise<IntelligentDevelopmentReleaseRef> {
  return fetchStoredRelease(
    version.projectId,
    version.versionId,
    version.sourceSessionId,
    version.artifactSha256,
    version.validationReportSha256,
    signal,
  );
}

async function fetchStoredRelease(
  projectId: string,
  versionId: string,
  sessionId: string,
  artifactSha256: string,
  validationReportSha256: string,
  signal?: AbortSignal,
): Promise<IntelligentDevelopmentReleaseRef> {
  const response = await studioFetch(
    `/web/intelligent-development/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/source`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) {
    throw await responseError(response, "无法读取项目源码");
  }
  const value = await responseJson(
    response,
    "源码快照的响应格式无效。",
  ) as Partial<IntelligentDevelopmentReleaseRef>;
  return parseRelease(value, sessionId, {
    artifactSha256,
    validationReportSha256,
    projectId,
    versionId,
  });
}

export async function fetchIntelligentDevelopmentProjectRelease(
  projectId: string,
  versionId: string,
  sessionId: string,
  artifactSha256: string,
  validationReportSha256: string,
  signal?: AbortSignal,
): Promise<IntelligentDevelopmentReleaseRef> {
  return fetchStoredRelease(
    projectId,
    versionId,
    sessionId,
    artifactSha256,
    validationReportSha256,
    signal,
  );
}

export async function fetchIntelligentDevelopmentRelease(
  sessionId: string,
  artifactSha256: string,
  validationReportSha256: string,
  signal?: AbortSignal,
): Promise<IntelligentDevelopmentReleaseRef> {
  const params = new URLSearchParams({
    sessionId,
    artifactSha256,
    validationReportSha256,
  });
  const response = await studioFetch(
    `/web/intelligent-development/releases/summary?${params}`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) {
    throw await responseError(response, "无法读取源码快照");
  }
  const value = await response.json() as Partial<IntelligentDevelopmentReleaseRef>;
  return parseRelease(value, sessionId, {
    artifactSha256,
    validationReportSha256,
  });
}

export async function fetchCurrentIntelligentDevelopmentRelease(
  sessionId: string,
  signal?: AbortSignal,
): Promise<IntelligentDevelopmentReleaseRef | null> {
  const params = new URLSearchParams({ sessionId });
  const response = await studioFetch(
    `/web/intelligent-development/releases/current?${params}`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (response.status === 204) return null;
  if (!response.ok) {
    throw await responseError(response, "无法恢复当前源码快照");
  }
  const value = await response.json() as Partial<IntelligentDevelopmentReleaseRef>;
  return parseRelease(value, sessionId);
}

export async function downloadIntelligentDevelopmentRelease(
  delivery: IntelligentDevelopmentReleaseRef,
  signal?: AbortSignal,
): Promise<{ blob: Blob; filename: string }> {
  const params = new URLSearchParams({
    sessionId: delivery.sessionId,
    artifactSha256: delivery.artifactSha256,
    validationReportSha256: delivery.validationReportSha256,
  });
  const path = delivery.projectId && delivery.versionId
    ? `/web/intelligent-development/projects/${encodeURIComponent(delivery.projectId)}/versions/${encodeURIComponent(delivery.versionId)}/download`
    : `/web/intelligent-development/releases/download?${params}`;
  const response = await studioFetch(
    path,
    {
      headers: { Accept: "application/zip" },
      signal,
    },
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw await responseError(response, "下载源码失败");
  }
  const contentType = response.headers.get("content-type")
    ?.split(";", 1)[0]
    .trim()
    .toLowerCase();
  if (contentType !== "application/zip") {
    throw new Error("源码下载响应不是 ZIP 文件。");
  }
  const blob = await response.blob();
  if (blob.size !== delivery.artifactSize) {
    throw new Error("源码压缩包大小与发布记录不一致，请重试。");
  }
  const fallback = `${delivery.agentName}-source-${delivery.artifactSha256.slice(0, 12)}.zip`;
  return { blob, filename: responseFilename(response, fallback) };
}
