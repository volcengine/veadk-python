// Thin client for the Google ADK API server (the same server `veadk frontend`
// launches). Uses relative URLs so it works same-origin in production and via
// the Vite dev proxy in development.

import { withAuth } from "./auth";
import { parseSSE } from "./sse";

/** An ADK event as serialised over `/run_sse` (camelCase, by_alias=True). */
export interface AdkUsage {
  totalTokenCount?: number;
  promptTokenCount?: number;
  candidatesTokenCount?: number;
  thoughtsTokenCount?: number;
  cachedContentTokenCount?: number;
}

export interface AdkEvent {
  author?: string;
  partial?: boolean;
  timestamp?: number;
  usageMetadata?: AdkUsage;
  usage_metadata?: AdkUsage;
  // Set when the model/run fails; /run_sse emits it as a `data: {"error": ...}`
  // frame (also seen as errorMessage / error_message).
  error?: string;
  errorMessage?: string;
  error_message?: string;
  content?: {
    role?: string;
    parts?: AdkPart[];
  };
  [k: string]: unknown;
}

/** A single OpenTelemetry span as returned by /debug/trace/session/{id}. */
export interface TraceSpan {
  name: string;
  span_id: number;
  trace_id: number;
  start_time: number; // nanoseconds
  end_time: number; // nanoseconds
  attributes: Record<string, unknown>;
  parent_span_id: number | null;
}

export interface AdkSession {
  id: string;
  lastUpdateTime?: number;
  events?: AdkEvent[];
  [k: string]: unknown;
}

export interface AdkInlineData {
  mimeType?: string;
  data?: string; // base64 (no data: prefix)
  displayName?: string;
  // snake_case fallback (defensive, in case the server echoes snake_case)
  mime_type?: string;
  display_name?: string;
}

export interface AdkPart {
  text?: string;
  thought?: boolean;
  inlineData?: AdkInlineData;
  inline_data?: AdkInlineData; // snake_case fallback (defensive)
  functionCall?: { id?: string; name?: string; args?: Record<string, unknown> };
  functionResponse?: { id?: string; name?: string; response?: Record<string, unknown> };
  // snake_case fallbacks (defensive)
  function_call?: { id?: string; name?: string; args?: Record<string, unknown> };
  function_response?: { id?: string; name?: string; response?: Record<string, unknown> };
}

/** A file the user attached in the composer, encoded for `/run_sse`. */
export interface Attachment {
  mimeType: string;
  data: string; // base64 (no data: prefix)
  name?: string;
}

const API_BASE = ""; // same origin (prod) / proxied (dev)

/** A resolved ADK endpoint. Empty `base` = the local same-origin server. */
export interface AdkEndpoint {
  base?: string;
  apiKey?: string;
}

// Routing table for remote AgentKit apps: maps a dropdown id (see
// adk/connections.ts) to its real ADK app name + endpoint. Local apps are not
// registered and fall through to the same-origin server.
interface RemoteApp {
  app: string;
  base: string;
  apiKey: string;
}
const remoteApps = new Map<string, RemoteApp>();

export function registerRemoteApp(id: string, info: RemoteApp): void {
  remoteApps.set(id, info);
}
export function clearRemoteApps(): void {
  remoteApps.clear();
}

/** Resolve a dropdown id to its real ADK app name + endpoint. */
function resolve(appName: string): { app: string; ep: AdkEndpoint } {
  const r = remoteApps.get(appName);
  return r ? { app: r.app, ep: { base: r.base, apiKey: r.apiKey } } : { app: appName, ep: {} };
}

/** fetch wrapper: same-origin (forwarding the gateway auth querystring) for the
 *  local server, or a remote AgentKit base URL with a Bearer API key. */
function apiFetch(path: string, init: RequestInit = {}, ep: AdkEndpoint = {}): Promise<Response> {
  if (ep.base) {
    // Use backend proxy to avoid CORS issues with remote AgentKit
    const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
    headers["X-AgentKit-Base"] = ep.base;
    if (ep.apiKey) headers["X-AgentKit-Key"] = ep.apiKey;
    return fetch(withAuth(`${API_BASE}/agentkit-proxy${path}`), { ...init, headers });
  }
  return fetch(withAuth(`${API_BASE}${path}`), init);
}

export async function listApps(): Promise<string[]> {
  const res = await apiFetch(`/list-apps`);
  if (!res.ok) throw new Error(`list-apps failed: ${res.status}`);
  return res.json();
}

/** List the apps a remote AgentKit server exposes (also validates URL + key). */
export async function fetchRemoteApps(base: string, apiKey: string): Promise<string[]> {
  const res = await apiFetch(`/list-apps`, {}, { base, apiKey });
  if (!res.ok) throw new Error(`list-apps failed: ${res.status}`);
  return res.json();
}

export async function createSession(
  appName: string,
  userId: string,
): Promise<string> {
  const { app, ep } = resolve(appName);
  const res = await apiFetch(
    `/apps/${app}/users/${encodeURIComponent(userId)}/sessions`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
    ep,
  );
  if (!res.ok) throw new Error(`create session failed: ${res.status}`);
  const session = await res.json();
  return session.id;
}

export async function listSessions(
  appName: string,
  userId: string,
): Promise<AdkSession[]> {
  const { app, ep } = resolve(appName);
  const res = await apiFetch(`/apps/${app}/users/${encodeURIComponent(userId)}/sessions`, {}, ep);
  if (!res.ok) throw new Error(`list sessions failed: ${res.status}`);
  return res.json();
}

export async function getSession(
  appName: string,
  userId: string,
  sessionId: string,
): Promise<AdkSession> {
  const { app, ep } = resolve(appName);
  const res = await apiFetch(
    `/apps/${app}/users/${encodeURIComponent(userId)}/sessions/${sessionId}`,
    {},
    ep,
  );
  if (!res.ok) throw new Error(`get session failed: ${res.status}`);
  return res.json();
}

export async function deleteSession(
  appName: string,
  userId: string,
  sessionId: string,
): Promise<void> {
  const { app, ep } = resolve(appName);
  const res = await apiFetch(
    `/apps/${app}/users/${encodeURIComponent(userId)}/sessions/${sessionId}`,
    { method: "DELETE" },
    ep,
  );
  if (!res.ok && res.status !== 404) throw new Error(`delete session failed: ${res.status}`);
}

export async function getSessionTrace(sessionId: string): Promise<TraceSpan[]> {
  const res = await apiFetch(`/debug/trace/session/${sessionId}`);
  if (!res.ok) throw new Error(`trace failed: ${res.status}`);
  return res.json();
}

/** Introspected metadata for an agent app (model, tools), for the picker.
 *  Only the local server implements `/web/agent-info`; remote AgentKit apps
 *  will reject this and the caller falls back to a basic flyout. */
export interface AgentInfo {
  name: string;
  description: string;
  model: string;
  tools: string[];
  subAgents: string[];
}

export async function getAgentInfo(appName: string): Promise<AgentInfo> {
  const { app, ep } = resolve(appName);
  const res = await apiFetch(`/web/agent-info/${app}`, {}, ep);
  if (!res.ok) throw new Error(`agent-info failed: ${res.status}`);
  return res.json();
}

/** One web-search hit (Volcengine WebSearch WebItem, trimmed for the UI). */
export interface WebHit {
  title: string;
  url: string;
  siteName: string;
  summary: string;
}

/** Run an agent's web-search tool on the local server (which holds the env
 *  credentials). `mounted` is false when a known agent has no web-search tool;
 *  `error` is set when the search ran but the API reported a problem. */
export async function webSearch(
  appName: string,
  query: string,
): Promise<{ mounted: boolean; results: WebHit[]; error?: string }> {
  const { app } = resolve(appName);
  const res = await apiFetch(
    `/web/search?source=web&app_name=${encodeURIComponent(app)}&q=${encodeURIComponent(query)}`,
  );
  if (!res.ok) throw new Error(`web search failed: ${res.status}`);
  return res.json();
}

export interface RunArgs {
  appName: string;
  userId: string;
  sessionId: string;
  text: string;
  attachments?: Attachment[];
  /** Function responses to send instead of/alongside text — used to resume a
   *  long-running call (e.g. answering ADK's `adk_request_credential`). */
  functionResponses?: { id: string; name: string; response: unknown }[];
}

/** Stream agent events for one user turn. */
export async function* runSSE({
  appName,
  userId,
  sessionId,
  text,
  attachments = [],
  functionResponses = [],
}: RunArgs): AsyncGenerator<AdkEvent, void, unknown> {
  const { app, ep } = resolve(appName);
  const parts: Record<string, unknown>[] = [
    ...attachments.map((a) => ({
      inlineData: { mimeType: a.mimeType, data: a.data, displayName: a.name },
    })),
    ...functionResponses.map((fr) => ({
      functionResponse: { id: fr.id, name: fr.name, response: fr.response },
    })),
    ...(text.trim() ? [{ text }] : []),
  ];
  const res = await apiFetch(
    `/run_sse`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_name: app,
        user_id: userId,
        session_id: sessionId,
        new_message: { role: "user", parts },
        streaming: true,
      }),
    },
    ep,
  );
  if (!res.ok) throw new Error(`run_sse failed: ${res.status}`);
  for await (const evt of parseSSE(res)) {
    yield evt as AdkEvent;
  }
}

/** Deploy a temporary agent for testing. */
export async function deployTempAgent(
  name: string,
  files: { path: string; content: string }[],
): Promise<string> {
  const res = await apiFetch("/web/deploy-temp-agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, files }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Deploy failed: ${err}`);
  }
  const data = await res.json();
  return data.appName;
}

/** Delete a temporary agent. */
export async function deleteTempAgent(appName: string): Promise<void> {
  const res = await apiFetch(`/web/deploy-temp-agent/${appName}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) {
    throw new Error(`Delete failed: ${res.status}`);
  }
}

export interface DeployAgentkitResult {
  apikey: string;
  url: string;
  agentName: string;
}

interface DeployAgentkitResponse extends Partial<DeployAgentkitResult> {
  success?: boolean;
  error?: string;
  detail?: string;
}

export async function deployAgentkitProject(
  name: string,
  files: { path: string; content: string }[],
  config: { region: string; projectName: string },
): Promise<DeployAgentkitResult> {
  const res = await apiFetch("/web/deploy-agentkit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, files, config }),
  });

  const text = await res.text();
  let data: DeployAgentkitResponse = {};
  try {
    data = text ? (JSON.parse(text) as DeployAgentkitResponse) : {};
  } catch {
    throw new Error(text || `部署失败 (${res.status})`);
  }

  if (!res.ok) {
    throw new Error(data.error || data.detail || "部署失败");
  }
  if (!data.success) {
    throw new Error(data.error || "部署失败");
  }
  if (!data.apikey || !data.url || !data.agentName) {
    throw new Error("部署失败：返回缺少 AgentKit 连接信息");
  }

  return {
    apikey: data.apikey,
    url: data.url,
    agentName: data.agentName,
  };
}
