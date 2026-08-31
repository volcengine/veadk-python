import { withAuth } from "./auth";
import type { CloudProvider } from "./cloudProvider";
import { withLocalUser } from "./identity";
import { parseSSE } from "./sse";

const INSTANCE_HEADER = "X-Studio-FaaS-Instance";
const REQUEST_ID_HEADER = "X-Studio-FaaS-Request-Id";

export interface RuntimeLogTarget {
  runtimeId: string;
  region: string;
  instanceName?: string;
  requestId?: string;
}

export interface RuntimeLogErrorEvent {
  type: "error";
  message: string;
  detail?: string;
  statusCode?: string;
  errorCode?: string;
  requestId?: string;
  responseBody?: string;
}

export type RuntimeLogEvent =
  | { type: "context"; instanceName: string; consoleUrl: string }
  | { type: "logs"; text: string; updatedAt: number }
  | RuntimeLogErrorEvent
  | { type: "done" };

export type RuntimeLogLevel = "error" | "warning" | "info" | "debug" | "default";

export function runtimeContextFromResponse(
  response: Response,
  runtimeId: string,
  region: string,
): RuntimeLogTarget | null {
  const instanceName = response.headers.get(INSTANCE_HEADER)?.trim() ?? "";
  if (!runtimeId || !region || !instanceName) return null;
  const requestId = response.headers.get(REQUEST_ID_HEADER)?.trim() ?? "";
  return {
    runtimeId,
    region,
    instanceName,
    ...(requestId ? { requestId } : {}),
  };
}

export function runtimeConsoleUrl(
  provider: CloudProvider,
  region: string,
  runtimeId: string,
  instanceName: string,
): string {
  const origin = provider === "byteplus"
    ? "https://console.byteplus.com"
    : "https://console.volcengine.com";
  const query = new URLSearchParams({
    projectName: "default",
    runtimeId,
    instanceName,
  });
  return `${origin}/agentkit/region:agentkit+${encodeURIComponent(region)}/runtime?${query}`;
}

export function runtimeLogLevel(line: string): RuntimeLogLevel {
  if (/\b(?:ERROR|FATAL|CRITICAL)\b/i.test(line)) return "error";
  if (/\bWARN(?:ING)?\b/i.test(line)) return "warning";
  if (/\bDEBUG\b/i.test(line)) return "debug";
  if (/\bINFO\b/i.test(line)) return "info";
  return "default";
}

function isRuntimeLogEvent(value: unknown): value is RuntimeLogEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Record<string, unknown>;
  if (event.type === "done") return true;
  if (event.type === "context") {
    return typeof event.instanceName === "string" && typeof event.consoleUrl === "string";
  }
  if (event.type === "logs") {
    return typeof event.text === "string" && typeof event.updatedAt === "number";
  }
  if (event.type === "error") {
    return typeof event.message === "string" &&
      (event.detail === undefined || typeof event.detail === "string") &&
      (event.statusCode === undefined || typeof event.statusCode === "string") &&
      (event.errorCode === undefined || typeof event.errorCode === "string") &&
      (event.requestId === undefined || typeof event.requestId === "string") &&
      (event.responseBody === undefined || typeof event.responseBody === "string");
  }
  return false;
}

export function runtimeLogErrorText(error: Omit<RuntimeLogErrorEvent, "type">): string {
  const lines = [error.message];
  const metadata = [
    error.statusCode ? `HTTP 状态码：${error.statusCode}` : "",
    error.errorCode ? `错误码：${error.errorCode}` : "",
    error.requestId ? `Request ID：${error.requestId}` : "",
  ].filter(Boolean);
  if (metadata.length > 0) lines.push(metadata.join("\n"));
  if (error.detail && error.detail !== error.message) lines.push(error.detail);
  if (
    error.responseBody &&
    !error.detail?.includes(error.responseBody)
  ) {
    lines.push(`云端响应正文：\n${error.responseBody}`);
  }
  return lines.join("\n\n");
}

async function responseError(response: Response): Promise<string> {
  const status = `HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ""}`;
  const body = await response.text();
  if (!body) return status;
  try {
    const payload = JSON.parse(body) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail) {
      return `${status}\n\n${payload.detail}`;
    }
    if (payload.detail && typeof payload.detail === "object") {
      const detail = payload.detail as Partial<RuntimeLogErrorEvent>;
      if (typeof detail.message === "string") {
        return runtimeLogErrorText({
          message: detail.message,
          ...(typeof detail.detail === "string" ? { detail: detail.detail } : {}),
          ...(typeof detail.statusCode === "string" ? { statusCode: detail.statusCode } : {}),
          ...(typeof detail.errorCode === "string" ? { errorCode: detail.errorCode } : {}),
          ...(typeof detail.requestId === "string" ? { requestId: detail.requestId } : {}),
          ...(typeof detail.responseBody === "string"
            ? { responseBody: detail.responseBody }
            : {}),
        });
      }
    }
    return `${status}\n\n${JSON.stringify(payload, null, 2)}`;
  } catch {
    return `${status}\n\n${body}`;
  }
}

export async function* streamRuntimeLogs({
  runtimeId,
  region,
  instanceName,
  sessionId,
  follow = true,
  signal,
}: {
  runtimeId: string;
  region: string;
  instanceName?: string;
  sessionId?: string;
  follow?: boolean;
  signal?: AbortSignal;
}): AsyncGenerator<RuntimeLogEvent, void, unknown> {
  const query = new URLSearchParams({
    region,
    follow: String(follow),
  });
  if (instanceName) query.set("instance_name", instanceName);
  if (sessionId) query.set("session_id", sessionId);
  const response = await fetch(
    withAuth(
      `/web/runtime-logs/${encodeURIComponent(runtimeId)}/stream?${query.toString()}`,
    ),
    {
      headers: withLocalUser({ Accept: "text/event-stream" }),
      cache: "no-store",
      signal,
    },
  );
  if (!response.ok) {
    throw new Error(`读取实例日志失败：${await responseError(response)}`);
  }
  for await (const value of parseSSE(response)) {
    if (!isRuntimeLogEvent(value)) {
      throw new Error("读取实例日志失败：服务返回格式无效");
    }
    yield value;
  }
}
