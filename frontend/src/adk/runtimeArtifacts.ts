import { studioFetch } from "./client";
import { TRANSFER_REQUEST_TIMEOUT_MS } from "./timeout";

export interface RuntimeArtifactScope {
  runtimeId: string;
  region: string;
  appName: string;
  sessionId: string;
}

export interface RuntimeArtifact {
  path: string;
  name: string;
  sizeBytes: number;
  mimeType: string;
  updatedAt: string;
}

export interface RuntimeArtifactList {
  available: boolean;
  reason?: string;
  items: RuntimeArtifact[];
  nextCursor: string | null;
}

export const MAX_ARTIFACT_PREVIEW_BYTES = 5 * 1024 * 1024;

export class RuntimeArtifactRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

function artifactUrl(scope: RuntimeArtifactScope, path?: string, download = false, cursor?: string) {
  const base = `/web/runtime-artifacts/${encodeURIComponent(scope.runtimeId)}/sessions/${encodeURIComponent(scope.sessionId)}`;
  const params = new URLSearchParams({ region: scope.region, appName: scope.appName });
  if (download) params.set("download", "true");
  if (cursor) params.set("cursor", cursor);
  if (!path) params.set("limit", "200");
  const suffix = path ? `/content/${path.split("/").map(encodeURIComponent).join("/")}` : "";
  return `${base}${suffix}?${params}`;
}

async function artifactResponse(response: Response): Promise<Response> {
  if (response.ok) return response;
  const fallback = response.status === 403
    ? "没有访问此会话产物的权限"
    : response.status === 404 ? "产物不存在或已被删除" : `产物请求失败（${response.status}），请重试`;
  if (response.headers.get("content-type")?.includes("application/json")) {
    const payload: unknown = await response.json();
    if (payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string") {
      throw new RuntimeArtifactRequestError(payload.detail, response.status);
    }
  }
  throw new RuntimeArtifactRequestError(fallback, response.status);
}

export async function listRuntimeArtifacts(scope: RuntimeArtifactScope, signal?: AbortSignal, cursor?: string): Promise<RuntimeArtifactList> {
  const response = await artifactResponse(await studioFetch(artifactUrl(scope, undefined, false, cursor), { signal }));
  const value: unknown = await response.json();
  if (!value || typeof value !== "object" || !("available" in value) || typeof value.available !== "boolean" || !("items" in value) || !Array.isArray(value.items)) {
    throw new Error("产物列表响应格式不正确，请检查 Studio 服务版本");
  }
  const items = value.items.map((item: unknown): RuntimeArtifact => {
    if (!item || typeof item !== "object" || !("path" in item) || typeof item.path !== "string"
      || !("name" in item) || typeof item.name !== "string"
      || !("sizeBytes" in item) || typeof item.sizeBytes !== "number" || !Number.isFinite(item.sizeBytes) || item.sizeBytes < 0
      || !("mimeType" in item) || typeof item.mimeType !== "string"
      || item.path.split("/").some(part => !part || part === "." || part === ".." || part.includes("\\"))) {
      throw new Error("产物列表包含无效文件信息");
    }
    return { path: item.path, name: item.name, sizeBytes: item.sizeBytes, mimeType: item.mimeType,
      updatedAt: "updatedAt" in item && typeof item.updatedAt === "string" ? item.updatedAt : "" };
  });
  return { available: value.available, items,
    reason: "reason" in value && typeof value.reason === "string" ? value.reason : undefined,
    nextCursor: "nextCursor" in value && typeof value.nextCursor === "string" ? value.nextCursor : null };
}

export async function getRuntimeArtifact(scope: RuntimeArtifactScope, path: string, signal?: AbortSignal, download = false): Promise<Blob> {
  const response = await artifactResponse(await studioFetch(artifactUrl(scope, path, download), { signal }, TRANSFER_REQUEST_TIMEOUT_MS));
  if (download) return response.blob();
  const tooLarge = () => new Error("文件超过 5 MB，请下载后查看");
  if (Number(response.headers.get("content-length")) > MAX_ARTIFACT_PREVIEW_BYTES) {
    await response.body?.cancel();
    throw tooLarge();
  }
  const reader = response.body?.getReader();
  if (!reader) return response.blob();
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_ARTIFACT_PREVIEW_BYTES) {
        await reader.cancel();
        throw tooLarge();
      }
      chunks.push(new Uint8Array(value));
    }
  } finally {
    reader.releaseLock();
  }
  return new Blob(chunks, { type: response.headers.get("content-type") ?? "application/octet-stream" });
}
