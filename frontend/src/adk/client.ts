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
  functionCall?: { name?: string; args?: Record<string, unknown> };
  functionResponse?: { name?: string; response?: Record<string, unknown> };
  // snake_case fallbacks (defensive)
  function_call?: { name?: string; args?: Record<string, unknown> };
  function_response?: { name?: string; response?: Record<string, unknown> };
}

/** A file the user attached in the composer, encoded for `/run_sse`. */
export interface Attachment {
  mimeType: string;
  data: string; // base64 (no data: prefix)
  name?: string;
}

const API_BASE = ""; // same origin (prod) / proxied (dev)

/** fetch wrapper that forwards the gateway auth querystring on every request. */
function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(withAuth(`${API_BASE}${path}`), init);
}

export async function listApps(): Promise<string[]> {
  const res = await apiFetch(`/list-apps`);
  if (!res.ok) throw new Error(`list-apps failed: ${res.status}`);
  return res.json();
}

export async function createSession(
  appName: string,
  userId: string,
): Promise<string> {
  const res = await apiFetch(`/apps/${appName}/users/${encodeURIComponent(userId)}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!res.ok) throw new Error(`create session failed: ${res.status}`);
  const session = await res.json();
  return session.id;
}

export async function listSessions(
  appName: string,
  userId: string,
): Promise<AdkSession[]> {
  const res = await apiFetch(`/apps/${appName}/users/${encodeURIComponent(userId)}/sessions`);
  if (!res.ok) throw new Error(`list sessions failed: ${res.status}`);
  return res.json();
}

export async function getSession(
  appName: string,
  userId: string,
  sessionId: string,
): Promise<AdkSession> {
  const res = await apiFetch(`/apps/${appName}/users/${encodeURIComponent(userId)}/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`get session failed: ${res.status}`);
  return res.json();
}

export async function deleteSession(
  appName: string,
  userId: string,
  sessionId: string,
): Promise<void> {
  const res = await apiFetch(`/apps/${appName}/users/${encodeURIComponent(userId)}/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) throw new Error(`delete session failed: ${res.status}`);
}

export async function getSessionTrace(sessionId: string): Promise<TraceSpan[]> {
  const res = await apiFetch(`/debug/trace/session/${sessionId}`);
  if (!res.ok) throw new Error(`trace failed: ${res.status}`);
  return res.json();
}

export interface RunArgs {
  appName: string;
  userId: string;
  sessionId: string;
  text: string;
  attachments?: Attachment[];
}

/** Stream agent events for one user turn. */
export async function* runSSE({
  appName,
  userId,
  sessionId,
  text,
  attachments = [],
}: RunArgs): AsyncGenerator<AdkEvent, void, unknown> {
  const parts: AdkPart[] = [
    ...attachments.map((a) => ({
      inlineData: { mimeType: a.mimeType, data: a.data, displayName: a.name },
    })),
    ...(text.trim() ? [{ text }] : []),
  ];
  const res = await apiFetch(`/run_sse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      app_name: appName,
      user_id: userId,
      session_id: sessionId,
      new_message: { role: "user", parts },
      streaming: true,
    }),
  });
  if (!res.ok) throw new Error(`run_sse failed: ${res.status}`);
  for await (const evt of parseSSE(res)) {
    yield evt as AdkEvent;
  }
}
