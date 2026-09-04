import { httpErrorMessage, studioFetch } from "./client";
import { adkT, withLocaleHeaders } from "./i18n";
import type { SandboxToolLaunch } from "./sandbox";

const API = "/web/agentkit-cli";
const REQUEST_TIMEOUT_MS = 60_000;
const CREATE_TIMEOUT_MS = 330_000;

export function agentKitCliUnconfiguredMessage(): string {
  return adkT("agentkitCli.unconfigured");
}

/** @deprecated Prefer agentKitCliUnconfiguredMessage() for runtime language changes. */
export const AGENTKIT_CLI_UNCONFIGURED_MESSAGE = agentKitCliUnconfiguredMessage();

export interface AgentKitCliCapabilities {
  enabled: boolean;
  reason: string;
}

export interface AgentKitCliSession {
  id: string;
  status: string;
  displayName: string;
  expireAt: string;
}

interface RequestOptions {
  signal?: AbortSignal;
}

function headers(json = false): Headers {
  const value = withLocaleHeaders({ Accept: "application/json" });
  if (json) value.set("Content-Type", "application/json");
  return value;
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  return new Error(await httpErrorMessage(response, fallback));
}

function parseSession(value: unknown): AgentKitCliSession {
  const session = value as {
    sessionId?: unknown;
    status?: unknown;
    displayName?: unknown;
    expireAt?: unknown;
  };
  if (typeof session?.sessionId !== "string" || typeof session.status !== "string") {
    throw new Error(adkT("agentkitCli.invalidSession"));
  }
  return {
    id: session.sessionId,
    status: session.status,
    displayName: typeof session.displayName === "string" ? session.displayName : "",
    expireAt: typeof session.expireAt === "string" ? session.expireAt : "",
  };
}

export const agentKitCliClient = {
  async capabilities(options: RequestOptions = {}): Promise<AgentKitCliCapabilities> {
    const response = await studioFetch(
      `${API}/capabilities`,
      { headers: headers(), signal: options.signal },
      REQUEST_TIMEOUT_MS,
    );
    if (!response.ok) throw await responseError(response, adkT("agentkitCli.loadCapabilitiesFailed"));
    const value = (await response.json()) as { enabled?: unknown; reason?: unknown };
    if (typeof value.enabled !== "boolean") {
      throw new Error(adkT("agentkitCli.invalidCapabilities"));
    }
    return {
      enabled: value.enabled,
      reason: typeof value.reason === "string" ? value.reason : "",
    };
  },

  async listSessions(options: RequestOptions = {}): Promise<AgentKitCliSession[]> {
    const response = await studioFetch(
      `${API}/sessions`,
      { headers: headers(), signal: options.signal },
      REQUEST_TIMEOUT_MS,
    );
    if (!response.ok) throw await responseError(response, adkT("agentkitCli.listSessionsFailed"));
    const value = (await response.json()) as { sessions?: unknown };
    if (!Array.isArray(value.sessions)) {
      throw new Error(adkT("agentkitCli.invalidSessionList"));
    }
    return value.sessions.map(parseSession);
  },

  async createSession(options: RequestOptions = {}): Promise<AgentKitCliSession> {
    const response = await studioFetch(
      `${API}/sessions`,
      {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({ persistent: false }),
        signal: options.signal,
      },
      CREATE_TIMEOUT_MS,
    );
    if (!response.ok) throw await responseError(response, adkT("agentkitCli.createSessionFailed"));
    return parseSession(await response.json());
  },

  async openSession(sessionId: string, options: RequestOptions = {}): Promise<void> {
    const response = await studioFetch(
      `${API}/sessions/${encodeURIComponent(sessionId)}/open`,
      { method: "POST", headers: headers(), signal: options.signal },
      REQUEST_TIMEOUT_MS,
    );
    if (!response.ok) throw await responseError(response, adkT("agentkitCli.openSessionFailed"));
  },

  async launchTerminal(
    sessionId: string,
    options: RequestOptions = {},
  ): Promise<SandboxToolLaunch> {
    const response = await studioFetch(
      `${API}/sessions/${encodeURIComponent(sessionId)}/terminal`,
      { method: "POST", headers: headers(), signal: options.signal },
      REQUEST_TIMEOUT_MS,
    );
    if (!response.ok) throw await responseError(response, adkT("agentkitCli.openTerminalFailed"));
    const value = (await response.json()) as { url?: unknown; shellSessionId?: unknown };
    if (typeof value.url !== "string" || !value.url) {
      throw new Error(adkT("agentkitCli.invalidTerminalUrl"));
    }
    return {
      url: value.url,
      ...(typeof value.shellSessionId === "string"
        ? { shellSessionId: value.shellSessionId }
        : {}),
    };
  },
};
