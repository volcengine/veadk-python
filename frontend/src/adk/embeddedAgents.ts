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

export interface EmbeddedAgentCloudSession {
  kind: EmbeddedAgentKind;
  id: string;
  userSessionId: string;
  displayName: string;
  status: string;
  createdAt: string;
  expireAt: string;
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

interface EmbeddedAgentCloudSessionResponse {
  kind?: unknown;
  sessionId?: unknown;
  userSessionId?: unknown;
  displayName?: unknown;
  status?: unknown;
  createdAt?: unknown;
  expireAt?: unknown;
}

const CAPABILITY_TIMEOUT_MS = 30_000;
const LIST_TIMEOUT_MS = 30_000;
const START_TIMEOUT_MS = 330_000;
const DISCONNECT_TIMEOUT_MS = 15_000;

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

function parseCloudSession(
  value: EmbeddedAgentCloudSessionResponse,
  kind: EmbeddedAgentKind,
): EmbeddedAgentCloudSession {
  if (
    value.kind !== kind ||
    typeof value.sessionId !== "string" ||
    !value.sessionId ||
    typeof value.status !== "string"
  ) {
    throw new Error("AgentKit 返回了无效的智能体 Session 列表。");
  }
  return {
    kind,
    id: value.sessionId,
    userSessionId:
      typeof value.userSessionId === "string" ? value.userSessionId : "",
    displayName:
      typeof value.displayName === "string" ? value.displayName : "",
    status: value.status,
    createdAt: typeof value.createdAt === "string" ? value.createdAt : "",
    expireAt: typeof value.expireAt === "string" ? value.expireAt : "",
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

  async listSessions(
    kind: EmbeddedAgentKind,
    signal?: AbortSignal,
  ): Promise<EmbeddedAgentCloudSession[]> {
    const response = await fetch(withAuth(`${api(kind)}/sessions`), {
      headers: headers(),
      signal: requestSignal(signal, LIST_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw await responseError(response, `无法读取 ${kind} 智能体列表。`);
    }
    const payload = await response.json() as { sessions?: unknown };
    if (!Array.isArray(payload.sessions)) {
      throw new Error("智能体列表服务返回了无效响应。");
    }
    return payload.sessions.map((value) =>
      parseCloudSession(value as EmbeddedAgentCloudSessionResponse, kind));
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

  async connect(
    session: Pick<EmbeddedAgentCloudSession, "kind" | "id">,
    signal?: AbortSignal,
  ): Promise<EmbeddedAgentSession> {
    const response = await fetch(
      withAuth(
        `${api(session.kind)}/sessions/${encodeURIComponent(session.id)}/connect`,
      ),
      {
        method: "POST",
        headers: headers(),
        signal: requestSignal(signal, START_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法进入智能体 Session。");
    }
    return parseSession(await response.json() as EmbeddedAgentSessionResponse);
  },

  async disconnect(
    session: Pick<EmbeddedAgentSession, "kind" | "id">,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(
      withAuth(
        `/web/embedded/${encodeURIComponent(session.id)}/${session.kind}/disconnect`,
      ),
      {
        method: "POST",
        headers: headers(),
        signal: requestSignal(signal, DISCONNECT_TIMEOUT_MS),
      },
    );
    if (!response.ok && response.status !== 404) {
      throw await responseError(response, "无法关闭智能体工作区。");
    }
  },
};
