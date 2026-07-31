import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { requestSignal } from "./timeout";

export type EmbeddedAgentKind = "openclaw" | "hermes";

export interface EmbeddedAgentCapability {
  kind: EmbeddedAgentKind;
  label: string;
  enabled: boolean;
  reason: string;
}

export interface EmbeddedAgentSession {
  kind: EmbeddedAgentKind;
  id: string;
  webuiUrl: string;
  terminalUrl: string;
  createdAt: number;
  expiresAt: number;
  ttlSeconds: number;
}

interface EmbeddedAgentSessionResponse {
  kind?: unknown;
  sessionId?: unknown;
  webuiUrl?: unknown;
  terminalUrl?: unknown;
  createdAt?: unknown;
  expiresAt?: unknown;
  ttlSeconds?: unknown;
}

const CAPABILITY_TIMEOUT_MS = 30_000;
const START_TIMEOUT_MS = 330_000;
const CLOSE_TIMEOUT_MS = 15_000;

function headers(): Headers {
  return withLocalUser({ Accept: "application/json" });
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  try {
    const payload = await response.json() as {
      detail?: unknown;
      message?: unknown;
    };
    const nested = payload.detail;
    const detail =
      nested && typeof nested === "object" && "message" in nested
        ? (nested as { message?: unknown }).message
        : nested ?? payload.message;
    if (typeof detail === "string" && detail) return new Error(detail);
  } catch {
    // Fall through to the stable public error below.
  }
  return new Error(`${fallback}（HTTP ${response.status}）`);
}

function api(kind: EmbeddedAgentKind): string {
  return `/web/${kind}`;
}

function parseSession(value: EmbeddedAgentSessionResponse): EmbeddedAgentSession {
  if (
    (value.kind !== "openclaw" && value.kind !== "hermes") ||
    typeof value.sessionId !== "string" ||
    !value.sessionId ||
    typeof value.webuiUrl !== "string" ||
    !value.webuiUrl.startsWith("/") ||
    typeof value.terminalUrl !== "string" ||
    !value.terminalUrl.startsWith("/")
  ) {
    throw new Error("AgentKit 返回了无效的智能体 Session。");
  }
  return {
    kind: value.kind,
    id: value.sessionId,
    webuiUrl: withAuth(value.webuiUrl),
    terminalUrl: withAuth(value.terminalUrl),
    createdAt: typeof value.createdAt === "number" ? value.createdAt : 0,
    expiresAt: typeof value.expiresAt === "number" ? value.expiresAt : 0,
    ttlSeconds: typeof value.ttlSeconds === "number" ? value.ttlSeconds : 0,
  };
}

export const embeddedAgentClient = {
  async capabilities(
    kind: EmbeddedAgentKind,
    signal?: AbortSignal,
  ): Promise<EmbeddedAgentCapability> {
    const response = await fetch(withAuth(`${api(kind)}/capabilities`), {
      headers: headers(),
      signal: requestSignal(signal, CAPABILITY_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw await responseError(response, `无法读取 ${kind} 配置。`);
    }
    const value = await response.json() as Partial<EmbeddedAgentCapability>;
    if (
      value.kind !== kind ||
      typeof value.label !== "string" ||
      typeof value.enabled !== "boolean"
    ) {
      throw new Error("智能体配置服务返回了无效响应。");
    }
    return {
      kind,
      label: value.label,
      enabled: value.enabled,
      reason: typeof value.reason === "string" ? value.reason : "",
    };
  },

  async start(
    kind: EmbeddedAgentKind,
    signal?: AbortSignal,
  ): Promise<EmbeddedAgentSession> {
    const response = await fetch(withAuth(`${api(kind)}/sessions`), {
      method: "POST",
      headers: headers(),
      signal: requestSignal(signal, START_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw await responseError(response, `无法启动 ${kind} 智能体。`);
    }
    return parseSession(await response.json() as EmbeddedAgentSessionResponse);
  },

  async close(
    session: Pick<EmbeddedAgentSession, "kind" | "id">,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(
      withAuth(`${api(session.kind)}/sessions/${encodeURIComponent(session.id)}`),
      {
        method: "DELETE",
        headers: headers(),
        signal: requestSignal(signal, CLOSE_TIMEOUT_MS),
      },
    );
    if (!response.ok && response.status !== 404) {
      throw await responseError(response, "无法关闭临时智能体 Session。");
    }
  },
};
