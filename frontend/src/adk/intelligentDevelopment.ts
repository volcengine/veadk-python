import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import { studioFetch } from "./client";
import { TRANSFER_REQUEST_TIMEOUT_MS } from "./timeout";

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
  if (
    value.sessionId !== sessionId
    || value.artifactSha256 !== artifactSha256
    || value.validationReportSha256 !== validationReportSha256
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
  ) {
    throw new Error("源码快照的响应格式无效。");
  }
  return value as IntelligentDevelopmentReleaseRef;
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
  const response = await studioFetch(
    `/web/intelligent-development/releases/download?${params}`,
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
