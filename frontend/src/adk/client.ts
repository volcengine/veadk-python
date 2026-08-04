// Thin client for the Google ADK API server (the same server `veadk frontend`
// launches). Uses relative URLs so it works same-origin in production and via
// the Vite dev proxy in development.

import { withAuth } from "./auth";
import { isOAuthLoginRequired, withLocalUser } from "./identity";
import {
  isAuthenticationRedirect,
  waitForAuthentication,
} from "./authSession";
import { parseJsonResponse } from "./jsonResponse";
import { formatRunSseError } from "./runSseError";
import { parseSSE } from "./sse";
import { normalizeRuntimeDescription } from "./runtimeDescription";
import {
  DEFAULT_REQUEST_TIMEOUT_MS,
  requestSignal,
  TRANSFER_REQUEST_TIMEOUT_MS,
} from "./timeout";
import type { AgentProject } from "../create/project";
import type { AgentDraft } from "../create/types";

/** An ADK event as serialised over `/run_sse` (camelCase, by_alias=True). */
export interface AdkUsage {
  totalTokenCount?: number;
  promptTokenCount?: number;
  candidatesTokenCount?: number;
  thoughtsTokenCount?: number;
  cachedContentTokenCount?: number;
}

export interface AdkEvent {
  id?: string;
  invocationId?: string;
  invocation_id?: string;
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
  // Control-flow signals from ADK EventActions. `transfer_to_agent` names the
  // delegation target when an LLM hands off; end_of_agent / escalate mark an
  // agent finishing or a loop exiting. (API may send camel or snake case.)
  actions?: {
    transferToAgent?: string;
    transfer_to_agent?: string;
    endOfAgent?: boolean;
    end_of_agent?: boolean;
    escalate?: boolean;
    artifactDelta?: Record<string, number>;
    artifact_delta?: Record<string, number>;
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
  state?: Record<string, unknown>;
  [k: string]: unknown;
}

export type MessageFeedbackRating = "good" | "bad";

export interface MessageFeedbackState {
  rating: MessageFeedbackRating | null;
  evaluationSetId?: string | null;
  evaluationSetName?: string | null;
  workspaceId?: string | null;
  evaluationItemId?: string | null;
  syncStatus: "syncing" | "synced";
  statePersistence?: "runtime" | "browser";
  updatedAt: number;
}

export interface AgentFeedbackSetSummary {
  kind: MessageFeedbackRating;
  evaluationSetId: string | null;
  evaluationSetName: string | null;
  workspaceId: string | null;
  itemCount: number;
}

export interface AgentFeedbackCase {
  id: string;
  itemKey: string;
  kind: MessageFeedbackRating;
  input: string;
  output: string;
  referenceOutput: string;
  comment: string;
  agentName: string;
  sessionId: string;
  messageId: string;
  runtimeId: string;
  invocationId: string;
  userId: string;
  createdAt: string;
  evaluationSetId: string;
  evaluationSetName: string;
  workspaceId: string;
}

export interface AgentFeedbackCasesResponse {
  agentName: string;
  runtimeId: string;
  region: string;
  projectName: string;
  sets: AgentFeedbackSetSummary[];
  items: AgentFeedbackCase[];
}

const MESSAGE_FEEDBACK_CACHE_KEY = "veadk.messageFeedback.v1";

function feedbackCacheScope(
  runtimeId: string,
  appName: string,
  userId: string,
  sessionId: string,
): string {
  return [runtimeId, appName, userId, sessionId].join(":");
}

function readMessageFeedbackCache(): Record<
  string,
  Record<string, MessageFeedbackState>
> {
  if (typeof window === "undefined") return {};
  try {
    const value = JSON.parse(localStorage.getItem(MESSAGE_FEEDBACK_CACHE_KEY) ?? "{}");
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}

function storeMessageFeedback(
  scope: string,
  eventId: string,
  feedback: MessageFeedbackState,
): void {
  if (typeof window === "undefined") return;
  const cache = readMessageFeedbackCache();
  cache[scope] = {
    ...(cache[scope] ?? {}),
    [`veadk_feedback:${eventId}`]: feedback,
  };
  localStorage.setItem(MESSAGE_FEEDBACK_CACHE_KEY, JSON.stringify(cache));
}

export function clearMessageFeedbackCache(args: {
  runtimeId: string;
  appName: string;
  userId: string;
  sessionId: string;
  eventIds: string[];
}): void {
  if (typeof window === "undefined") return;
  const scope = feedbackCacheScope(
    args.runtimeId,
    args.appName,
    args.userId,
    args.sessionId,
  );
  const cache = readMessageFeedbackCache();
  const scoped = cache[scope];
  if (!scoped) return;
  for (const eventId of args.eventIds) {
    delete scoped[`veadk_feedback:${eventId}`];
  }
  if (Object.keys(scoped).length === 0) {
    delete cache[scope];
  } else {
    cache[scope] = scoped;
  }
  localStorage.setItem(MESSAGE_FEEDBACK_CACHE_KEY, JSON.stringify(cache));
}

export interface AdkInlineData {
  mimeType?: string;
  data?: string; // base64 (no data: prefix)
  displayName?: string;
  // snake_case fallback (defensive, in case the server echoes snake_case)
  mime_type?: string;
  display_name?: string;
}

export interface AdkFileData {
  fileUri?: string;
  mimeType?: string;
  displayName?: string;
  file_uri?: string;
  mime_type?: string;
  display_name?: string;
}

export interface AdkPart {
  text?: string;
  thought?: boolean;
  inlineData?: AdkInlineData;
  inline_data?: AdkInlineData; // snake_case fallback (defensive)
  fileData?: AdkFileData;
  file_data?: AdkFileData;
  partMetadata?: Record<string, unknown>;
  part_metadata?: Record<string, unknown>;
  functionCall?: { id?: string; name?: string; args?: Record<string, unknown> };
  functionResponse?: { id?: string; name?: string; response?: Record<string, unknown> };
  // snake_case fallbacks (defensive)
  function_call?: { id?: string; name?: string; args?: Record<string, unknown> };
  function_response?: { id?: string; name?: string; response?: Record<string, unknown> };
}

/** A file attached in the composer or reconstructed from message history. */
export interface Attachment {
  id: string;
  mimeType: string;
  uri?: string;
  data?: string; // legacy inline base64 (no data: prefix)
  name?: string;
  sizeBytes?: number;
  status?: "uploading" | "ready" | "error";
  error?: string;
  previewUrl?: string;
}

const API_BASE = ""; // same origin (prod) / proxied (dev)

/** A resolved ADK endpoint. Empty = the local same-origin server. `runtimeId`
 *  routes through the server-side runtime proxy; `base`+`apiKey` is the legacy
 *  browser-direct AgentKit path. */
export interface AdkEndpoint {
  base?: string;
  apiKey?: string;
  runtimeId?: string;
  region?: string;
  retryProbe?: boolean;
}

// Routing table for remote AgentKit apps: maps a dropdown id (see
// adk/connections.ts) to its real ADK app name + endpoint. Local apps are not
// registered and fall through to the same-origin server.
//
// Two remote flavours:
//  - `runtimeId` (preferred): route through the same-origin `/web/runtime-proxy`,
//    which resolves the runtime's endpoint + apikey server-side. The browser
//    never sees the apikey.
//  - `base` + `apiKey` (legacy): the browser holds the key and talks to the
//    backend `/agentkit-proxy` forwarding it in headers.
interface RemoteApp {
  app: string;
  base?: string;
  apiKey?: string;
  runtimeId?: string;
  region?: string;
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
  if (!r) return { app: appName, ep: {} };
  return {
    app: r.app,
    ep: { base: r.base, apiKey: r.apiKey, runtimeId: r.runtimeId, region: r.region },
  };
}

/** fetch wrapper. Routing, in priority order:
 *  1. `runtimeId` → same-origin `/web/runtime-proxy/{id}{path}` (server injects
 *     the apikey; apikey never reaches the browser).
 *  2. `base` + `apiKey` → backend `/agentkit-proxy` (legacy, key in header).
 *  3. neither → the local same-origin server. */
async function apiFetch(
  path: string,
  init: RequestInit = {},
  ep: AdkEndpoint = {},
  timeoutMs: number = DEFAULT_REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const runtimeMethodOverride =
    Boolean(ep.runtimeId) && String(init.method ?? "GET").toUpperCase() === "DELETE";
  const baseOpts = {
    ...init,
    ...(runtimeMethodOverride ? { method: "POST" } : {}),
    headers: withLocalUser(init.headers),
  };
  const send = () => {
    const opts = {
      ...baseOpts,
      signal: requestSignal(init.signal, timeoutMs),
    };
    if (ep.runtimeId) {
      const runtimeParams = new URLSearchParams();
      if (ep.region) runtimeParams.set("region", ep.region);
      if (ep.retryProbe) runtimeParams.set("probe_retry", "connect");
      if (runtimeMethodOverride) runtimeParams.set("_method", "DELETE");
      const rq = runtimeParams.toString()
        ? `${path.includes("?") ? "&" : "?"}${runtimeParams.toString()}`
        : "";
      return fetch(
        withAuth(`${API_BASE}/web/runtime-proxy/${ep.runtimeId}${path}${rq}`),
        opts,
      );
    }
    if (ep.base) {
      // Use backend proxy to avoid CORS issues with remote AgentKit
      const headers = new Headers(opts.headers);
      headers.set("X-AgentKit-Base", ep.base);
      if (ep.apiKey) headers.set("X-AgentKit-Key", ep.apiKey);
      return fetch(withAuth(`${API_BASE}/agentkit-proxy${path}`), {
        ...opts,
        headers,
      });
    }
    return fetch(withAuth(`${API_BASE}${path}`), opts);
  };

  const requiresLogin = async (response: Response) => {
    if (isAuthenticationRedirect(response)) return true;
    if (response.status !== 401) return false;
    try {
      return await isOAuthLoginRequired();
    } catch {
      return false;
    }
  };

  let response = await send();
  while (await requiresLogin(response)) {
    await waitForAuthentication(init.signal);
    response = await send();
  }
  return response;
}

function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const loc = Array.isArray((item as { loc?: unknown }).loc)
            ? (item as { loc?: unknown[] }).loc?.join(".")
            : "";
          const msg = String((item as { msg?: unknown }).msg ?? "");
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(item);
      })
      .filter(Boolean)
      .join("\n");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return "";
}

async function httpErrorMessage(res: Response, fallback: string): Promise<string> {
  const text = await res.text().catch(() => "");
  if (!text) return `${fallback} (${res.status})`;
  try {
    const data = JSON.parse(text) as { detail?: unknown; error?: unknown };
    const detail = formatErrorDetail(data.detail ?? data.error);
    return detail || text || `${fallback} (${res.status})`;
  } catch {
    return text || `${fallback} (${res.status})`;
  }
}

export async function listApps(): Promise<string[]> {
  const res = await apiFetch(`/list-apps`);
  if (!res.ok) throw new Error(`list-apps failed: ${res.status}`);
  return res.json();
}

/** A runtime exists but the current identity is not allowed to use it. */
export class RuntimeAccessDeniedError extends Error {
  constructor() {
    super("当前账号无权访问该 Runtime，请刷新列表或重新登录后重试。");
    this.name = "RuntimeAccessDeniedError";
  }
}

/** The Runtime is visible to Studio, but its Agent Server cannot be probed. */
export class RuntimeProbeError extends Error {
  constructor(
    message: string,
    readonly unsupported = false,
  ) {
    super(message);
    this.name = "RuntimeProbeError";
  }
}

const PRIVATE_RUNTIME_UNREACHABLE_MESSAGE =
  "Runtime 已部署成功，但当前 Studio 无法访问私网 Runtime。请使用已绑定相同 VPC 的 Studio 访问，或改用公网 / 公网+VPC 部署。";
const RUNTIME_ENDPOINT_UNREACHABLE_MESSAGE =
  "Runtime 已部署成功，但 Studio 暂时无法连接服务。网关域名可能仍在生效，或当前网络/DNS 无法访问该 Runtime，请稍后在智能体管理页重试连接。";
const RUNTIME_REGION_FALLBACKS = ["cn-beijing", "cn-shanghai"] as const;
const RUNTIME_APPS_CACHE_TTL_MS = 30_000;
const RUNTIME_METADATA_CACHE_TTL_MS = 5 * 60 * 1000;
const FEEDBACK_CASES_CACHE_TTL_MS = 60 * 1000;

interface ClientCacheEntry<T> {
  value?: T;
  promise?: Promise<T>;
  updatedAt: number;
}

interface ClientCacheOptions {
  force?: boolean;
}

const runtimeAppsCache = new Map<
  string,
  { apps: string[]; expiresAt: number }
>();
const runtimeAgentInfoCache = new Map<string, ClientCacheEntry<AgentInfo>>();
const runtimeDetailCache = new Map<string, ClientCacheEntry<RuntimeDetail>>();
const feedbackCasesCache =
  new Map<string, ClientCacheEntry<AgentFeedbackCasesResponse>>();

function runtimeAppsCacheKey(runtimeId: string, region: string): string {
  return `${region}:${runtimeId}`;
}

function runtimeRegionCandidates(region?: string): string[] {
  const primary = region || "cn-beijing";
  return [
    primary,
    ...RUNTIME_REGION_FALLBACKS.filter((candidate) => candidate !== primary),
  ];
}

function cacheKey(...parts: Array<string | number | undefined>): string {
  return parts.map((part) => String(part ?? "")).join("\u0001");
}

function freshCacheValue<T>(
  cache: Map<string, ClientCacheEntry<T>>,
  key: string,
  ttlMs: number,
): T | null {
  const entry = cache.get(key);
  if (!entry?.value) return null;
  return Date.now() - entry.updatedAt <= ttlMs ? entry.value : null;
}

function rememberClientCache<T>(
  cache: Map<string, ClientCacheEntry<T>>,
  key: string,
  value: T,
): T {
  cache.set(key, { value, updatedAt: Date.now() });
  return value;
}

async function runtimeProxyErrorCode(response: Response): Promise<string> {
  try {
    const payload = (await response.clone().json()) as {
      detail?: unknown;
    };
    return typeof payload.detail === "string" ? payload.detail : "";
  } catch {
    return "";
  }
}

/** List the apps a remote AgentKit server exposes (also validates URL + key).
 *  Pass `ep` to probe via the runtime proxy instead of a raw base+key. */
export async function fetchRemoteApps(
  base: string,
  apiKey: string,
  ep?: AdkEndpoint,
): Promise<string[]> {
  const res = await apiFetch(`/list-apps`, {}, ep ?? { base, apiKey });
  const runtimeErrorCode = ep?.runtimeId
    ? await runtimeProxyErrorCode(res)
    : "";
  if (ep?.runtimeId && runtimeErrorCode === "runtime_access_denied") {
    throw new RuntimeAccessDeniedError();
  }
  if (
    ep?.runtimeId &&
    runtimeErrorCode === "runtime_private_endpoint_unreachable"
  ) {
    throw new RuntimeProbeError(PRIVATE_RUNTIME_UNREACHABLE_MESSAGE);
  }
  if (
    ep?.runtimeId &&
    [
      "runtime_proxy_connect_error",
      "runtime_proxy_timeout",
      "runtime_json_connect_error",
      "runtime_json_timeout",
    ].includes(runtimeErrorCode)
  ) {
    throw new RuntimeProbeError(RUNTIME_ENDPOINT_UNREACHABLE_MESSAGE);
  }
  if (ep?.runtimeId && res.status === 404) {
    throw new RuntimeProbeError(
      "该 Runtime 的 Agent Server 未提供连接接口，请确认 Runtime 已就绪且版本兼容。",
      true,
    );
  }
  if (ep?.runtimeId && (res.status === 401 || res.status === 403)) {
    throw new RuntimeProbeError(
      "Runtime 服务拒绝了连接请求，请检查 Runtime 的鉴权配置。",
    );
  }
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "读取 Agent 列表失败"));
  }
  const apps = (await res.json()) as string[];
  if (ep?.runtimeId) {
    runtimeAppsCache.set(runtimeAppsCacheKey(ep.runtimeId, ep.region ?? ""), {
      apps,
      expiresAt: Date.now() + RUNTIME_APPS_CACHE_TTL_MS,
    });
  }
  return apps;
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
  if (!res.ok) {
    const fallback = `创建会话失败 (${res.status})`;
    const detail = await httpErrorMessage(res, "创建会话失败");
    throw new Error(detail === fallback ? fallback : `${fallback}：${detail}`);
  }
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
    `/apps/${app}/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}`,
    {},
    ep,
  );
  if (!res.ok) {
    const detail = await httpErrorMessage(res, "读取会话失败");
    throw new Error(`get session failed: ${res.status}：${detail}`);
  }
  const session = (await res.json()) as AdkSession;
  if (ep.runtimeId) {
    const scope = feedbackCacheScope(ep.runtimeId, app, userId, sessionId);
    session.state = {
      ...(readMessageFeedbackCache()[scope] ?? {}),
      ...(session.state ?? {}),
    };
  }
  return session;
}

export async function submitMessageFeedback(args: {
  appName: string;
  userId: string;
  sessionId: string;
  eventId: string;
  rating: MessageFeedbackRating | null;
  comment?: string;
}): Promise<MessageFeedbackState> {
  const { app, ep } = resolve(args.appName);
  if (!ep.runtimeId) {
    throw new Error("只有连接到 AgentKit Runtime 的会话支持反馈回流");
  }
  if (!ep.region) throw new Error("Runtime 缺少地域信息，无法提交反馈");
  const res = await apiFetch(
    "/web/evaluation/feedback",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        runtimeId: ep.runtimeId,
        region: ep.region,
        appName: app,
        userId: args.userId,
        sessionId: args.sessionId,
        eventId: args.eventId,
        rating: args.rating,
        comment: args.comment ?? "",
      }),
    },
    {},
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "提交反馈失败"));
  }
  const feedback = (await res.json()) as MessageFeedbackState;
  const scope = feedbackCacheScope(
    ep.runtimeId,
    app,
    args.userId,
    args.sessionId,
  );
  storeMessageFeedback(scope, args.eventId, feedback);
  return feedback;
}

export async function getAgentFeedbackCases(args: {
  runtimeId: string;
  region?: string;
  appName: string;
  pageSize?: number;
}, options: ClientCacheOptions = {}): Promise<AgentFeedbackCasesResponse> {
  const key = cacheKey(
    args.runtimeId,
    args.region || "cn-beijing",
    args.appName,
    args.pageSize ?? 100,
  );
  const cached = freshCacheValue(
    feedbackCasesCache,
    key,
    FEEDBACK_CASES_CACHE_TTL_MS,
  );
  if (!options.force && cached) return cached;
  const existing = feedbackCasesCache.get(key);
  if (!options.force && existing?.promise) return existing.promise;
  let lastError: Error | null = null;
  const promise = (async () => {
    for (const region of runtimeRegionCandidates(args.region)) {
      const query = new URLSearchParams({
        runtimeId: args.runtimeId,
        region,
        appName: args.appName,
        page_size: String(args.pageSize ?? 100),
      });
      const res = await apiFetch(`/web/evaluation/feedback-cases?${query.toString()}`);
      if (res.ok) {
        return rememberClientCache(
          feedbackCasesCache,
          key,
          await res.json() as AgentFeedbackCasesResponse,
        );
      }
      lastError = new Error(await httpErrorMessage(res, "读取评测集失败"));
    }
    throw lastError ?? new Error("读取评测集失败");
  })();
  feedbackCasesCache.set(key, {
    ...existing,
    promise,
    updatedAt: existing?.updatedAt ?? 0,
  });
  try {
    return await promise;
  } finally {
    const current = feedbackCasesCache.get(key);
    if (current?.promise === promise) {
      feedbackCasesCache.set(key, {
        value: current.value,
        updatedAt: current.updatedAt,
      });
    }
  }
}

export function getCachedAgentFeedbackCases(args: {
  runtimeId: string;
  region?: string;
  appName: string;
  pageSize?: number;
}): AgentFeedbackCasesResponse | null {
  return freshCacheValue(
    feedbackCasesCache,
    cacheKey(
      args.runtimeId,
      args.region || "cn-beijing",
      args.appName,
      args.pageSize ?? 100,
    ),
    FEEDBACK_CASES_CACHE_TTL_MS,
  );
}

export function prefetchAgentFeedbackCases(args: {
  runtimeId: string;
  region?: string;
  appName: string;
  pageSize?: number;
}): void {
  void getAgentFeedbackCases(args).catch(() => {});
}

export function refreshAgentFeedbackCases(args: {
  runtimeId: string;
  region?: string;
  appName: string;
  pageSize?: number;
}): void {
  void getAgentFeedbackCases(args, { force: true }).catch(() => {});
}

function feedbackSetsWithCounts(
  sets: AgentFeedbackSetSummary[],
  items: AgentFeedbackCase[],
): AgentFeedbackSetSummary[] {
  return (["good", "bad"] as const).map((kind) => {
    const current = sets.find((set) => set.kind === kind);
    return {
      kind,
      evaluationSetId: current?.evaluationSetId ?? null,
      evaluationSetName: current?.evaluationSetName ?? null,
      workspaceId: current?.workspaceId ?? null,
      itemCount: items.filter((item) => item.kind === kind).length,
    };
  });
}

export function upsertCachedAgentFeedbackCase(args: {
  runtimeId: string;
  region?: string;
  appName: string;
  userId: string;
  sessionId: string;
  messageId: string;
  invocationId?: string;
  rating: MessageFeedbackRating | null;
  input: string;
  output: string;
  referenceOutput?: string;
  createdAt?: string;
}): void {
  for (const [key, entry] of feedbackCasesCache.entries()) {
    const value = entry.value;
    if (
      !value ||
      value.runtimeId !== args.runtimeId ||
      value.agentName !== args.appName
    ) continue;
    const withoutCurrent = value.items.filter((item) =>
      item.sessionId !== args.sessionId || item.messageId !== args.messageId
    );
    const items = args.rating
      ? [
          {
            id: `local:${args.runtimeId}:${args.sessionId}:${args.messageId}`,
            itemKey: `local:${args.messageId}`,
            kind: args.rating,
            input: args.input,
            output: args.output,
            referenceOutput: args.referenceOutput ?? args.output,
            comment: "",
            agentName: args.appName,
            sessionId: args.sessionId,
            messageId: args.messageId,
            runtimeId: args.runtimeId,
            invocationId: args.invocationId ?? "",
            userId: args.userId,
            createdAt: args.createdAt ?? new Date().toISOString(),
            evaluationSetId: "",
            evaluationSetName: "",
            workspaceId: "",
          },
          ...withoutCurrent,
        ]
      : withoutCurrent;
    feedbackCasesCache.set(key, {
      value: {
        ...value,
        sets: feedbackSetsWithCounts(value.sets, items),
        items,
      },
      updatedAt: Date.now(),
      promise: entry.promise,
    });
  }
}

export async function deleteAgentFeedbackCases(args: {
  runtimeId: string;
  region: string;
  appName: string;
  itemIds: string[];
}): Promise<{ deletedCount: number }> {
  let lastError: Error | null = null;
  for (const region of runtimeRegionCandidates(args.region)) {
    const res = await apiFetch(
      "/web/evaluation/feedback-cases/delete",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          runtimeId: args.runtimeId,
          region,
          appName: args.appName,
          itemIds: args.itemIds,
        }),
      },
      {},
      TRANSFER_REQUEST_TIMEOUT_MS,
    );
    if (res.ok) {
      const response = await res.json() as { deletedCount: number };
      const deletedIds = new Set(args.itemIds);
      for (const [key, entry] of feedbackCasesCache.entries()) {
        const value = entry.value;
        if (
          !value ||
          value.runtimeId !== args.runtimeId ||
          value.agentName !== args.appName
        ) continue;
        const items = value.items.filter((item) => !deletedIds.has(item.id));
        feedbackCasesCache.set(key, {
          value: {
            ...value,
            sets: feedbackSetsWithCounts(value.sets, items),
            items,
          },
          updatedAt: Date.now(),
        });
      }
      return response;
    }
    lastError = new Error(await httpErrorMessage(res, "删除评测案例失败"));
  }
  throw lastError ?? new Error("删除评测案例失败");
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

function decodeArtifactData(value: string): Uint8Array {
  const standard = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = standard.padEnd(Math.ceil(standard.length / 4) * 4, "=");
  const binary = window.atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export async function downloadArtifact(
  appName: string,
  userId: string,
  sessionId: string,
  filename: string,
  version?: number,
): Promise<void> {
  const { blob, downloadName } = await fetchArtifactBlob(
    appName,
    userId,
    sessionId,
    filename,
    version,
  );
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = downloadName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

async function fetchArtifactBlob(
  appName: string,
  userId: string,
  sessionId: string,
  filename: string,
  version?: number,
): Promise<{ blob: Blob; downloadName: string }> {
  const { app, ep } = resolve(appName);
  const params = version == null ? "" : `?version=${encodeURIComponent(version)}`;
  const path = `/apps/${encodeURIComponent(app)}/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}/artifacts/${encodeURIComponent(filename)}${params}`;
  const res = await apiFetch(path, {}, ep, TRANSFER_REQUEST_TIMEOUT_MS);
  if (!res.ok) throw new Error(await httpErrorMessage(res, "下载文件失败"));
  const part = (await res.json()) as AdkPart;
  const inline = part.inlineData ?? part.inline_data;
  if (!inline?.data) throw new Error("文件内容不可用");
  const bytes = decodeArtifactData(inline.data);
  const buffer = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  ) as ArrayBuffer;
  const blob = new Blob([buffer], {
    type: inline.mimeType ?? inline.mime_type ?? "application/octet-stream",
  });
  return {
    blob,
    downloadName: inline.displayName ?? inline.display_name ?? filename,
  };
}

export async function previewArtifact(
  appName: string,
  userId: string,
  sessionId: string,
  filename: string,
  version?: number,
): Promise<string> {
  const { blob } = await fetchArtifactBlob(
    appName,
    userId,
    sessionId,
    filename,
    version,
  );
  return URL.createObjectURL(blob);
}

export interface MediaCapabilities {
  maxFileBytes: number;
  mimeTypes: string[];
  storage: "local" | "tos" | string;
}

export async function getMediaCapabilities(appName: string): Promise<MediaCapabilities> {
  void appName;
  const res = await apiFetch("/web/media/capabilities");
  if (!res.ok) throw new Error(await httpErrorMessage(res, "media capabilities failed"));
  return res.json();
}

export async function uploadMedia(
  appName: string,
  userId: string,
  sessionId: string,
  file: File,
): Promise<Attachment> {
  const { app } = resolve(appName);
  const body = new FormData();
  body.set("app_name", app);
  body.set("user_id", userId);
  body.set("session_id", sessionId);
  body.set("file", file);
  const res = await apiFetch(
    "/web/media",
    { method: "POST", body },
    {},
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
  if (!res.ok) throw new Error(await httpErrorMessage(res, "文件上传失败"));
  const media = (await res.json()) as {
    id: string;
    uri: string;
    name: string;
    mimeType: string;
    sizeBytes: number;
  };
  return { ...media, status: "ready" };
}

export async function deleteSessionMedia(
  appName: string,
  userId: string,
  sessionId: string,
): Promise<void> {
  const { app } = resolve(appName);
  const path = `/web/media/${encodeURIComponent(app)}/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/delete`;
  const res = await apiFetch(path, { method: "POST" });
  if (!res.ok && res.status !== 404) {
    throw new Error(await httpErrorMessage(res, "media cleanup failed"));
  }
}

function mediaApiPath(uri: string): string | undefined {
  try {
    const parsed = new URL(uri);
    if (parsed.protocol !== "veadk-media:" || parsed.hostname !== "apps") return undefined;
    const segments = parsed.pathname.split("/").filter(Boolean).map(decodeURIComponent);
    if (
      segments.length !== 7 ||
      segments[1] !== "users" ||
      segments[3] !== "sessions" ||
      segments[5] !== "media"
    ) return undefined;
    return `/web/media/${segments.map(encodeURIComponent).filter((_, i) => ![1, 3, 5].includes(i)).join("/")}`;
  } catch {
    return undefined;
  }
}

/** Delete one uploaded media object that has not been sent in a message. */
export async function deleteMedia(appName: string, uri: string): Promise<void> {
  const path = mediaApiPath(uri);
  if (!path) throw new Error("Invalid VeADK media URI");
  void appName;
  const res = await apiFetch(`${path}/delete`, { method: "POST" });
  if (!res.ok && res.status !== 404) {
    throw new Error(await httpErrorMessage(res, "media cleanup failed"));
  }
}

/** Resolve a stable media URI to an authenticated same-origin delivery URL. */
export function mediaContentUrl(appName: string, uri: string): string {
  if (uri.startsWith("data:") || uri.startsWith("blob:") || /^https?:/.test(uri)) return uri;
  const basePath = mediaApiPath(uri);
  if (!basePath) return uri;
  const path = `${basePath}/content`;
  void appName;
  return withAuth(`${API_BASE}${path}`);
}

export async function getSessionTrace(
  appName: string,
  sessionId: string,
): Promise<TraceSpan[]> {
  const { app, ep } = resolve(appName);
  const res = await apiFetch(
    `/dev/apps/${encodeURIComponent(app)}/debug/trace/session/${encodeURIComponent(sessionId)}`,
    {},
    ep,
  );
  if (!res.ok) throw new Error(`trace failed: ${res.status}`);
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const responseType = contentType.split(";", 1)[0] || "Content-Type 缺失";
    throw new Error(
      `trace failed: 服务端返回了非 JSON 响应（${responseType}），请检查 Studio API 代理配置`,
    );
  }
  const spans = (await res.json()) as unknown;
  if (!Array.isArray(spans)) throw new Error("trace failed: 返回格式无效");
  return spans as TraceSpan[];
}

/** The agent-type vocabulary shared with the create wizard. */
export type AgentNodeType = "llm" | "sequential" | "parallel" | "loop" | "a2a";

/** One node of the recursive agent topology returned by `/web/agent-info`. */
export interface AgentNode {
  /** Stable ADK agent identifier used by event.author and transfer actions. */
  id?: string;
  name: string;
  description: string;
  instruction?: string;
  type: AgentNodeType;
  model: string;
  tools: string[];
  skills: AgentSkill[];
  path: string[];
  mentionable: boolean;
  children: AgentNode[];
}

export interface AgentSkill {
  name: string;
  description: string;
}

/** One runtime component mounted on an Agent. Unknown kinds are intentionally
 *  preserved so newer Agent Server versions remain visible to older clients. */
export interface AgentComponent {
  kind: string;
  name: string;
  description?: string;
  backend?: string;
  source?: string;
}

export interface AgentTarget {
  name: string;
  description: string;
  type: AgentNodeType;
  path: string[];
}

export interface FrontendInvocation {
  skills: AgentSkill[];
  targetAgent?: AgentTarget;
}

/** Introspected metadata for an agent app, served locally or by Agent Server. */
export interface AgentInfo {
  /** Real ADK app id used in runtime proxy paths; display names may differ. */
  appName?: string;
  name: string;
  description: string;
  type?: AgentNodeType;
  model: string;
  tools: string[];
  skills: AgentSkill[];
  /** False when an older Agent Server omits Skill introspection entirely. */
  skillsPreviewSupported: boolean;
  subAgents: string[];
  /** Optional for compatibility with Agent Servers released before this field. */
  components?: AgentComponent[];
  /** Search sources that are actually mounted on this Agent. */
  searchSources?: AgentSearchCapability[];
  /** Recursive typed tree; only the local server provides it. */
  graph?: AgentNode;
  /** Complete sanitized builder state exposed by newly generated Agents. */
  draft?: AgentDraft;
}

export interface SessionCapabilityItem {
  id: string;
  kind: "tool" | "skill";
  name: string;
  custom: boolean;
  description?: string;
  skillSourceId?: string;
  version?: string;
}

export interface SessionCapabilities {
  schemaVersion: number;
  revision: number;
  tools: SessionCapabilityItem[];
  skills: SessionCapabilityItem[];
}

export interface AddSessionCapability {
  kind: "tool" | "skill";
  name: string;
  skillSourceId?: string;
  description?: string;
  version?: string;
}

export interface SessionSkillSpace {
  id: string;
  name: string;
  description: string;
  status: string;
  region?: string;
  projectName?: string;
  skillCount?: number;
}

export interface SessionSkillCatalogItem {
  skillId: string;
  skillName: string;
  skillDescription: string;
  version: string;
  skillStatus: string;
}

export interface SessionPublicSkill {
  slug: string;
  name: string;
  description: string;
  sourceType: string;
  sourceRepo: string;
  downloadCount: number;
  evaluationScore: number;
  version: string;
  updatedAt: string;
}

export interface SessionPublicSkillSearchResult {
  items: SessionPublicSkill[];
  totalCount: number;
}

function normalizeSessionCapabilities(payload: Record<string, unknown>): SessionCapabilities {
  const normalizeItem = (item: Record<string, unknown>): SessionCapabilityItem => ({
    id: String(item.id ?? ""),
    kind: item.kind === "skill" ? "skill" : "tool",
    name: String(item.name ?? ""),
    custom: item.custom === true,
    description: typeof item.description === "string" ? item.description : undefined,
    skillSourceId: typeof item.skill_source_id === "string" ? item.skill_source_id : undefined,
    version: typeof item.version === "string" ? item.version : undefined,
  });
  return {
    schemaVersion: Number(payload.schema_version ?? 1),
    revision: Number(payload.revision ?? 0),
    tools: Array.isArray(payload.tools)
      ? payload.tools.map((item) => normalizeItem(item as Record<string, unknown>))
      : [],
    skills: Array.isArray(payload.skills)
      ? payload.skills.map((item) => normalizeItem(item as Record<string, unknown>))
      : [],
  };
}

function sessionCapabilitiesPath(
  app: string,
  userId: string,
  sessionId: string,
): string {
  return `/harness/apps/${encodeURIComponent(app)}/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}/capabilities`;
}

export async function getSessionCapabilities(
  appName: string,
  userId: string,
  sessionId: string,
): Promise<SessionCapabilities> {
  const { app, ep } = resolve(appName);
  const res = await apiFetch(sessionCapabilitiesPath(app, userId, sessionId), {}, ep);
  if (!res.ok) throw new Error(await httpErrorMessage(res, "读取会话能力失败"));
  return normalizeSessionCapabilities(await res.json());
}

export async function listSessionBuiltinTools(appName: string): Promise<string[]> {
  const { ep } = resolve(appName);
  const res = await apiFetch("/harness/capabilities/tools", {}, ep);
  if (!res.ok) throw new Error(await httpErrorMessage(res, "读取内置工具失败"));
  const payload = (await res.json()) as { tools?: { name?: string }[] };
  return (payload.tools ?? [])
    .map((tool) => tool.name?.trim() ?? "")
    .filter(Boolean);
}

export async function listSessionSkillSpaces(
  appName: string,
): Promise<SessionSkillSpace[]> {
  const { ep } = resolve(appName);
  const res = await apiFetch("/harness/skills/spaces?region=all", {}, ep);
  if (!res.ok) throw new Error(await httpErrorMessage(res, "读取 Skill Space 失败"));
  const payload = (await res.json()) as { items?: SessionSkillSpace[] };
  return payload.items ?? [];
}

export async function listSessionSkillsInSpace(
  appName: string,
  spaceId: string,
  region?: string,
): Promise<SessionSkillCatalogItem[]> {
  const { ep } = resolve(appName);
  const params = new URLSearchParams({ region: region || "cn-beijing" });
  const path = `/harness/skills/spaces/${encodeURIComponent(spaceId)}/skills?${params.toString()}`;
  const res = await apiFetch(path, {}, ep);
  if (!res.ok) throw new Error(await httpErrorMessage(res, "读取 Skill 列表失败"));
  const payload = (await res.json()) as { items?: SessionSkillCatalogItem[] };
  return payload.items ?? [];
}

export async function searchSessionPublicSkills(
  appName: string,
  query: string,
  pageNumber = 1,
  pageSize = 20,
): Promise<SessionPublicSkillSearchResult> {
  const { ep } = resolve(appName);
  const params = new URLSearchParams({
    query,
    page_number: String(pageNumber),
    page_size: String(pageSize),
  });
  const res = await apiFetch(`/harness/skills/findskill?${params.toString()}`, {}, ep);
  if (!res.ok) throw new Error(await httpErrorMessage(res, "搜索 Skill Hub 失败"));
  const payload = (await res.json()) as Partial<SessionPublicSkillSearchResult>;
  return {
    items: payload.items ?? [],
    totalCount: Number(payload.totalCount ?? 0),
  };
}

export async function addSessionCapability(
  appName: string,
  userId: string,
  sessionId: string,
  capability: AddSessionCapability,
  expectedRevision: number,
): Promise<SessionCapabilities> {
  const { app, ep } = resolve(appName);
  const res = await apiFetch(
    sessionCapabilitiesPath(app, userId, sessionId),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: capability.kind,
        name: capability.name,
        skill_source_id: capability.skillSourceId,
        description: capability.description,
        version: capability.version,
        expected_revision: expectedRevision,
      }),
    },
    ep,
  );
  if (!res.ok) throw new Error(await httpErrorMessage(res, "添加会话能力失败"));
  return normalizeSessionCapabilities(await res.json());
}

export async function removeSessionCapability(
  appName: string,
  userId: string,
  sessionId: string,
  capabilityId: string,
  expectedRevision: number,
): Promise<SessionCapabilities> {
  const { app, ep } = resolve(appName);
  const path = `${sessionCapabilitiesPath(app, userId, sessionId)}/${encodeURIComponent(capabilityId)}?expected_revision=${expectedRevision}`;
  const res = await apiFetch(path, { method: "DELETE" }, ep);
  if (!res.ok) throw new Error(await httpErrorMessage(res, "移除会话能力失败"));
  return normalizeSessionCapabilities(await res.json());
}

async function fetchAgentInfo(
  app: string,
  ep: AdkEndpoint,
  loadDraft = true,
): Promise<AgentInfo> {
  const res = await apiFetch(`/web/agent-info/${app}`, {}, ep);
  if (!res.ok) throw new Error(`agent-info failed: ${res.status}`);
  const info = (await res.json()) as Partial<AgentInfo>;
  if (loadDraft && !info.draft) {
    try {
      const draftRes = await apiFetch(`/web/agent-draft/${app}`, {}, ep);
      if (draftRes.ok) {
        const payload = (await draftRes.json()) as { draft?: AgentDraft };
        info.draft = payload.draft;
      }
    } catch {
      // Older or non-Studio Agents do not expose editable builder metadata.
    }
  }
  return {
    appName: app,
    name: info.name ?? app,
    description: info.description ?? "",
    type: info.type,
    model: info.model ?? "",
    tools: info.tools ?? [],
    skillsPreviewSupported: Array.isArray(info.skills),
    skills: info.skills ?? [],
    subAgents: info.subAgents ?? [],
    components: info.components ?? [],
    searchSources: info.searchSources ?? [],
    graph: info.graph,
    draft: info.draft,
  };
}

export async function getAgentInfo(appName: string): Promise<AgentInfo> {
  const { app, ep } = resolve(appName);
  return fetchAgentInfo(app, ep, false);
}

/** Read Agent metadata for a Runtime without connecting or persisting it. */
async function fetchRuntimeAgentInfo(
  runtimeId: string,
  region: string,
  knownApp?: string,
): Promise<AgentInfo> {
  let lastError: Error | null = null;
  for (const candidate of runtimeRegionCandidates(region)) {
    const ep = { runtimeId, region: candidate };
    try {
      const appCacheKey = runtimeAppsCacheKey(runtimeId, candidate);
      const cached = runtimeAppsCache.get(appCacheKey);
      if (cached && cached.expiresAt <= Date.now()) {
        runtimeAppsCache.delete(appCacheKey);
      }
      const freshCached = runtimeAppsCache.get(appCacheKey);
      const app =
        knownApp ||
        freshCached?.apps[0] ||
        (await fetchRemoteApps("", "", ep))[0];
      if (!app) throw new Error("该 Runtime 未提供可预览的 Agent。");
      return fetchAgentInfo(app, ep);
    } catch (error) {
      if (
        error instanceof RuntimeAccessDeniedError ||
        (error instanceof RuntimeProbeError && !error.unsupported)
      ) {
        throw error;
      }
      lastError = error instanceof Error ? error : new Error(String(error));
    }
  }
  throw lastError ?? new Error("该 Runtime 未提供可预览的 Agent。");
}

/** Read Agent metadata for a Runtime without connecting or persisting it. */
export async function getRuntimeAgentInfo(
  runtimeId: string,
  region: string,
  knownAppOrOptions: string | ClientCacheOptions = {},
  maybeOptions: ClientCacheOptions = {},
): Promise<AgentInfo> {
  const knownApp = typeof knownAppOrOptions === "string"
    ? knownAppOrOptions
    : undefined;
  const options = typeof knownAppOrOptions === "string"
    ? maybeOptions
    : knownAppOrOptions;
  const key = cacheKey(runtimeId, region || "cn-beijing", knownApp ?? "");
  const cached = freshCacheValue(
    runtimeAgentInfoCache,
    key,
    RUNTIME_METADATA_CACHE_TTL_MS,
  );
  if (!options.force && cached) return cached;
  const existing = runtimeAgentInfoCache.get(key);
  if (!options.force && existing?.promise) return existing.promise;
  const promise = fetchRuntimeAgentInfo(runtimeId, region, knownApp).then((info) =>
    rememberClientCache(runtimeAgentInfoCache, key, info),
  );
  runtimeAgentInfoCache.set(key, {
    ...existing,
    promise,
    updatedAt: existing?.updatedAt ?? 0,
  });
  try {
    return await promise;
  } finally {
    const current = runtimeAgentInfoCache.get(key);
    if (current?.promise === promise) {
      runtimeAgentInfoCache.set(key, {
        value: current.value,
        updatedAt: current.updatedAt,
      });
    }
  }
}

export function getCachedRuntimeAgentInfo(
  runtimeId: string,
  region: string,
  knownApp = "",
): AgentInfo | null {
  return freshCacheValue(
    runtimeAgentInfoCache,
    cacheKey(runtimeId, region || "cn-beijing", knownApp),
    RUNTIME_METADATA_CACHE_TTL_MS,
  );
}

export function prefetchRuntimeAgentInfo(
  runtimeId: string,
  region: string,
  knownApp = "",
): void {
  void getRuntimeAgentInfo(runtimeId, region, knownApp).catch(() => {});
}

/** One web-search hit (Volcengine WebSearch WebItem, trimmed for the UI). */
export interface WebHit {
  title: string;
  url: string;
  siteName: string;
  summary: string;
}

export type AgentSearchSource = "knowledge" | "memory";
export type AgentSearchCapability = AgentSearchSource | "web";

export interface AgentSearchHit {
  content: string;
  author?: string;
  timestamp?: number;
}

export interface AgentSearchResponse {
  mounted: boolean;
  sourceName?: string;
  sourceType?: string;
  results: AgentSearchHit[];
  error?: string;
}

/** Search a KnowledgeBase or long-term memory mounted inside the Agent process. */
export async function componentSearch(
  appName: string,
  source: AgentSearchSource,
  query: string,
  userId: string,
): Promise<AgentSearchResponse> {
  const { app, ep } = resolve(appName);
  const params = new URLSearchParams({
    source,
    app_name: app,
    q: query,
    user_id: userId,
  });
  const res = await apiFetch(`/web/search?${params.toString()}`, {}, ep);
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "Agent 检索失败"));
  }
  return res.json();
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
  invocation?: FrontendInvocation;
  /** Function responses to send instead of/alongside text — used to resume a
   *  long-running call (e.g. answering ADK's `adk_request_credential`). */
  functionResponses?: { id: string; name: string; response: unknown }[];
  /** Abort the stream (e.g. when the user switches to another session). */
  signal?: AbortSignal;
  /** Use the session-aware harness runner when the server exposes it. */
  sessionCapabilities?: boolean;
}

/** Stream agent events for one user turn. */
export async function* runSSE({
  appName,
  userId,
  sessionId,
  text,
  attachments = [],
  invocation,
  functionResponses = [],
  signal,
  sessionCapabilities = false,
}: RunArgs): AsyncGenerator<AdkEvent, void, unknown> {
  const { app, ep } = resolve(appName);
  const attachmentParts = attachments.flatMap<Record<string, unknown>>((a) => {
      if (a.status && a.status !== "ready") return [];
      if (a.uri) {
        return [{
          fileData: { mimeType: a.mimeType, fileUri: a.uri, displayName: a.name },
          partMetadata: {
            veadkMedia: {
              id: a.id,
              uri: a.uri,
              name: a.name,
              mimeType: a.mimeType,
              sizeBytes: a.sizeBytes,
            },
          },
        }];
      }
      return a.data ? [{
        inlineData: { mimeType: a.mimeType, data: a.data, displayName: a.name },
      }] : [];
    });
  const invocationMetadata = invocation &&
    (invocation.skills.length > 0 || invocation.targetAgent)
    ? invocation
    : undefined;
  const parts: Record<string, unknown>[] = [
    ...attachmentParts,
    ...functionResponses.map((fr) => ({
      functionResponse: { id: fr.id, name: fr.name, response: fr.response },
    })),
    ...(text.trim() ? [{ text }] : []),
  ];
  if (invocationMetadata && parts.length > 0) {
    const firstPart = parts[0];
    const partMetadata = firstPart.partMetadata as Record<string, unknown> | undefined;
    parts[0] = {
      ...firstPart,
      partMetadata: {
        ...partMetadata,
        veadkInvocation: invocationMetadata,
      },
    };
  }
  const res = await apiFetch(
    sessionCapabilities ? `/harness/run_sse` : `/run_sse`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_name: app,
        user_id: userId,
        session_id: sessionId,
        new_message: { role: "user", parts },
        streaming: true,
        custom_metadata: invocationMetadata
          ? { veadkInvocation: invocationMetadata }
          : undefined,
      }),
      signal,
    },
    ep,
    0,
  );
  if (!res.ok) {
    const detail = await httpErrorMessage(res, "运行会话失败");
    throw new Error(
      formatRunSseError(`run_sse failed: ${res.status}：${detail}`),
    );
  }
  for await (const evt of parseSSE(res)) {
    const event = evt as AdkEvent;
    if (typeof event.error === "string") event.error = formatRunSseError(event.error);
    if (typeof event.errorMessage === "string") {
      event.errorMessage = formatRunSseError(event.errorMessage);
    }
    if (typeof event.error_message === "string") {
      event.error_message = formatRunSseError(event.error_message);
    }
    yield event;
  }
}

export interface DeployAgentkitResult {
  apikey: string;
  url: string;
  agentName: string;
  runtimeId?: string;
  consoleUrl?: string;
  region?: string;
  version?: number | null;
  feishuChannel?: {
    enabled: boolean;
    transport: string;
    runtimeId?: string;
  };
}

export interface DeployBuildLogSnapshot {
  source: "code-pipeline";
  status: "running" | "complete" | "error";
  text: string;
  lineCount: number;
  truncated: boolean;
  omittedEarly?: boolean;
  snapshotTruncated?: boolean;
  updatedAt: number;
  pipelineId?: string;
  pipelineName?: string;
  pipelineRunId?: string;
  workspaceId?: string;
  workspaceName?: string;
  error?: string;
  pendingMessage?: string;
}

/** One live progress frame streamed during a deployment. */
export interface DeployStage {
  level: "info" | "success" | "warning" | "error";
  phase: "build" | "deploy" | "publish" | string;
  message: string;
  pct?: number;
  runtimeName?: string;
  buildLog?: DeployBuildLogSnapshot;
}

interface DeployFrame extends Partial<DeployAgentkitResult> {
  done?: boolean;
  success?: boolean;
  error?: string;
  phase?: string;
}

const deploymentControllers = new Map<string, AbortController>();

/** Deploy to AgentKit, consuming the server's SSE progress stream. `onStage`
 *  is called for each build/deploy/publish step; resolves with the connection
 *  info once the terminal frame arrives. */
export async function deployAgentkitProject(
  name: string,
  files: { path: string; content: string }[],
  config: {
    region: string;
    projectName: string;
    network?: {
      mode: string;
      vpc_id?: string;
      subnet_ids?: string;
      enable_shared_internet_access?: boolean;
    };
  },
  opts?: {
    taskId?: string;
    runtimeId?: string;
    appName?: string;
    sessionStorage?: "in-memory" | "persistent";
    minInstance?: number;
    maxInstance?: number;
    description?: string;
    onStage?: (s: DeployStage) => void;
    im?: {
      feishu?: {
        enabled: boolean;
      };
    };
    envs?: { key: string; value: string }[];
  },
): Promise<DeployAgentkitResult> {
  const taskId = opts?.taskId;
  const controller = taskId ? new AbortController() : undefined;
  if (taskId && controller) deploymentControllers.set(taskId, controller);
  const clearController = () => {
    if (taskId && deploymentControllers.get(taskId) === controller) {
      deploymentControllers.delete(taskId);
    }
  };

  let res: Response;
  try {
    opts?.onStage?.({
      level: "info",
      phase: "upload",
      message: "正在上传代码包",
      pct: 0,
    });
    res = await apiFetch(
      "/web/deploy-agentkit",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller?.signal,
        body: JSON.stringify({
          name,
          files,
          config,
          taskId,
          runtimeId: opts?.runtimeId,
          appName: opts?.appName,
          sessionStorage: opts?.sessionStorage,
          minInstance: opts?.minInstance,
          maxInstance: opts?.maxInstance,
          description: normalizeRuntimeDescription(opts?.description ?? ""),
          im: opts?.im,
          envs: opts?.envs,
        }),
      },
      {},
      0,
    );
    opts?.onStage?.({
      level: "success",
      phase: "upload",
      message: "代码包上传完成",
      pct: 100,
    });
  } catch (error) {
    clearController();
    throw error;
  }
  if (!res.ok) {
    const detail = await httpErrorMessage(res, "部署失败");
    clearController();
    throw new Error(detail);
  }

  let final: DeployFrame | null = null;
  try {
    for await (const raw of parseSSE(res)) {
      const ev = raw as DeployFrame & DeployStage;
      if (ev && ev.done) {
        final = ev;
        break;
      }
      if (ev && ev.message) opts?.onStage?.(ev);
    }
  } catch (error) {
    clearController();
    throw error;
  }
  clearController();

  if (!final) throw new Error("部署失败：连接中断");
  if (!final.success) throw new Error(final.error || "部署失败");
  if (!final.agentName) {
    throw new Error("部署失败：返回缺少 Agent 名称");
  }
  if (!final.runtimeId && !final.url) {
    throw new Error("部署失败：返回缺少 AgentKit 连接信息");
  }
  // Note: the runtime's data-plane apikey is intentionally NOT persisted in the
  // browser (it's a secret; clear-text localStorage would be XSS-exposed). The
  // "管理 Agent" view shows control-plane detail instead.
  return {
    apikey: final.apikey ?? "",
    url: final.url ?? "",
    agentName: final.agentName,
    runtimeId: final.runtimeId,
    consoleUrl: final.consoleUrl,
    region: final.region,
    version: final.version,
    feishuChannel: final.feishuChannel,
  };
}

/** Cancel an in-flight deployment and ask the backend to destroy its Runtime. */
export async function cancelAgentkitDeployment(taskId: string): Promise<void> {
  const res = await apiFetch("/web/cancel-deploy-agentkit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ taskId }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `取消部署失败 (${res.status})`);
  }
  deploymentControllers.get(taskId)?.abort();
  deploymentControllers.delete(taskId);
}

/** A deployed runtime owned by the current user (for the "管理 Agent" view). */
export interface ManagedRuntime {
  name: string;
  runtimeId: string;
  status: string;
  createdAt: string;
  author?: string;
  region: string;
  currentVersion?: number | null;
}

/** List AgentKit runtimes the server authorizes this user to manage. */
export async function getMyRuntimes(
  region = "cn-beijing",
): Promise<ManagedRuntime[]> {
  const res = await apiFetch(`/web/my-runtimes?region=${encodeURIComponent(region)}`);
  if (!res.ok) throw new Error(`加载失败 (${res.status})`);
  const d = (await res.json()) as { runtimes?: ManagedRuntime[] };
  return d.runtimes ?? [];
}

/** Per-module feature gates the SPA reads at startup (studio mode disables
 *  the chat-centric modules). Unknown/failed fetch falls back to all-enabled. */
export interface UiFeatures {
  newChat: boolean;
  search: boolean;
  skillCenter: boolean;
  history: boolean;
  addAgent: boolean;
  manageAgents: boolean;
  addAgentkit: boolean;
  generatedAgentTestRun?: boolean;
  generatedAgentTestRunDisabledReason?: string;
}

export interface SiteBranding {
  title: string;
  logoUrl: string;
}

export interface UiConfig {
  studio: boolean;
  version: string;
  branding: SiteBranding;
  features: UiFeatures;
  defaultView: "chat" | "addAgent";
  /** Where the agent picker sources agents: local apps (`--dev`) or the user's
   *  cloud AgentKit runtimes (default). */
  agentsSource: "local" | "cloud";
}

export const DEFAULT_SITE_BRANDING: SiteBranding = {
  title: "VeADK Studio",
  logoUrl: "",
};

const DEFAULT_UI_CONFIG: UiConfig = {
  studio: false,
  version: "",
  branding: DEFAULT_SITE_BRANDING,
  features: {
    newChat: true,
    search: true,
    skillCenter: true,
    history: true,
    addAgent: true,
    manageAgents: true,
    addAgentkit: true,
    generatedAgentTestRun: true,
  },
  defaultView: "chat",
  agentsSource: "local",
};

/** Fetch the UI feature gates; falls back to all-enabled on any error. */
export async function getUiConfig(): Promise<UiConfig> {
  try {
    const res = await apiFetch("/web/ui-config");
    if (!res.ok) return DEFAULT_UI_CONFIG;
    const d = (await res.json()) as Partial<Omit<UiConfig, "branding">> & {
      branding?: Partial<SiteBranding>;
    };
    const logoUrl = typeof d.branding?.logoUrl === "string"
      ? d.branding.logoUrl
      : DEFAULT_SITE_BRANDING.logoUrl;
    return {
      studio: d.studio ?? false,
      version: typeof d.version === "string" ? d.version : "",
      branding: {
        title: typeof d.branding?.title === "string"
          ? d.branding.title
          : DEFAULT_SITE_BRANDING.title,
        logoUrl: logoUrl ? withAuth(logoUrl) : "",
      },
      features: { ...DEFAULT_UI_CONFIG.features, ...(d.features ?? {}) },
      defaultView: d.defaultView ?? "chat",
      agentsSource: d.agentsSource === "cloud" ? "cloud" : "local",
    };
  } catch {
    return DEFAULT_UI_CONFIG;
  }
}

export type StudioRole = "admin" | "developer" | "user";
export type RuntimeScope = "all" | "mine";

export interface StudioAccess {
  role: StudioRole;
  capabilities: {
    createAgents: boolean;
    manageAgents: boolean;
    runtimeScope: RuntimeScope;
  };
}

/** Least-privileged fallback while access is loading or unavailable. */
export const DEFAULT_STUDIO_ACCESS: StudioAccess = {
  role: "user",
  capabilities: {
    createAgents: false,
    manageAgents: false,
    runtimeScope: "mine",
  },
};

/** Resolve the signed-in user's Studio role and capabilities. */
export async function getStudioAccess(): Promise<StudioAccess> {
  const res = await apiFetch("/web/access");
  if (!res.ok) throw new Error(`加载权限失败 (${res.status})`);
  const access = (await res.json()) as StudioAccess;
  if (
    !["admin", "developer", "user"].includes(access.role) ||
    typeof access.capabilities?.createAgents !== "boolean" ||
    typeof access.capabilities?.manageAgents !== "boolean" ||
    !["all", "mine"].includes(access.capabilities?.runtimeScope)
  ) {
    throw new Error("权限服务返回了无法解析的响应");
  }
  return access;
}

export interface StudioReleaseOption {
  version: string;
  gitSha: string;
  createdAt: string;
  changelog: string[];
}

export interface StudioUpdateStatus {
  enabled: boolean;
  currentVersion: string;
  latestVersion: string;
  latestGitSha: string;
  releases: StudioReleaseOption[];
  available: boolean;
  state: "disabled" | "idle" | "updating" | "error";
  message: string;
  progressStage:
    | "idle"
    | "resolving"
    | "downloading"
    | "preparing"
    | "submitting"
    | "publishing"
    | "complete"
    | "error";
  progressMessage: string;
  targetVersion: string;
  startedAt: number;
  errorId: string;
  errorStage: string;
  errorLog: string;
  updateLogs: string[];
  consoleUrl: string;
}

/** Check the configured immutable Studio main release channel. */
export async function getStudioUpdateStatus(
  targetVersion?: string,
  startedAt?: number,
): Promise<StudioUpdateStatus> {
  const params = new URLSearchParams();
  if (targetVersion) params.set("targetVersion", targetVersion);
  if (startedAt) params.set("startedAt", String(startedAt));
  const query = params.size ? `?${params.toString()}` : "";
  const res = await apiFetch(`/web/studio-update${query}`);
  if (!res.ok) throw new Error(`检查 Studio 更新失败 (${res.status})`);
  return (await res.json()) as StudioUpdateStatus;
}

/** Stage the latest full Studio bundle and submit a VeFaaS release. */
export async function startStudioUpdate(
  version: string,
): Promise<{ version: string }> {
  const res = await apiFetch("/web/studio-update", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VeADK-Studio-Update": "1",
    },
    body: JSON.stringify({ version }),
  }, {}, TRANSFER_REQUEST_TIMEOUT_MS);
  if (!res.ok) {
    let detail = "";
    try {
      const payload = (await res.json()) as { detail?: unknown };
      detail = typeof payload.detail === "string" ? payload.detail : "";
    } catch {
      detail = "";
    }
    throw new Error(detail || `提交 Studio 更新失败 (${res.status})`);
  }
  return (await res.json()) as { version: string };
}

/** One AgentKit runtime as listed by `/web/runtimes` (control-plane). */
export interface CloudRuntime {
  name: string;
  runtimeId: string;
  status: string;
  region: string;
  author: string;
  description?: string;
  cpuMilli?: number | null;
  memoryMb?: number | null;
  createdAt?: string;
  currentVersion?: number | null;
  /** True when this runtime was deployed by the current user (veadk:author). */
  isMine: boolean;
  /** Server-authorized deletion capability for this managed Runtime. */
  canDelete: boolean;
}

/** One page of cloud runtimes plus the token to fetch the next page. */
export interface RuntimePage {
  runtimes: CloudRuntime[];
  nextToken: string;
}

/** List one authorized page of AgentKit runtimes. `nextToken` from a prior
 *  page continues pagination; the server derives ownership from identity. */
export async function getRuntimes(
  opts: {
    nextToken?: string;
    pageSize?: number;
    region?: string;
    scope?: "all" | "mine";
  } = {},
): Promise<RuntimePage> {
  const p = new URLSearchParams({
    scope: opts.scope ?? "all",
    page_size: String(opts.pageSize ?? 30),
    region: opts.region ?? "all",
  });
  if (opts.nextToken) p.set("next_token", opts.nextToken);
  const res = await apiFetch(`/web/runtimes?${p.toString()}`);
  if (!res.ok) {
    const detail = await httpErrorMessage(res, "加载 Runtime 失败");
    const summary = `加载 Runtime 失败（HTTP ${res.status}）`;
    throw new Error(detail === `加载 Runtime 失败 (${res.status})` ? summary : `${summary}：${detail}`);
  }
  const d = (await res.json()) as Partial<RuntimePage>;
  return { runtimes: d.runtimes ?? [], nextToken: d.nextToken ?? "" };
}

/** Probe whether a runtime speaks the ADK api-server protocol by calling its
 *  `/list-apps` through the proxy. Returns the app list on success, or null when
 *  the runtime does not support it (non-200 / not an ADK server). */
export async function probeRuntimeApps(
  runtimeId: string,
  region: string,
  options: { retryProbe?: boolean } = {},
): Promise<string[] | null> {
  try {
    const endpoint: AdkEndpoint = { runtimeId, region };
    if (options.retryProbe) endpoint.retryProbe = true;
    const res = await fetchRemoteApps("", "", endpoint);
    return res;
  } catch (error) {
    if (
      error instanceof RuntimeAccessDeniedError ||
      error instanceof RuntimeProbeError
    ) {
      throw error;
    }
    return null;
  }
}

export interface RuntimeA2aIntegration {
  name: string;
  description: string;
  endpoint: string;
}

/** Probe the standard A2A Agent Card without exposing Runtime credentials. */
export async function probeRuntimeA2a(
  runtimeId: string,
  region: string,
  options: { retryProbe?: boolean } = {},
): Promise<RuntimeA2aIntegration | null> {
  const endpoint: AdkEndpoint = { runtimeId, region };
  if (options.retryProbe) endpoint.retryProbe = true;
  const res = await apiFetch("/.well-known/agent-card.json", {}, endpoint);
  const runtimeErrorCode = await runtimeProxyErrorCode(res);
  if (runtimeErrorCode === "runtime_access_denied") {
    throw new RuntimeAccessDeniedError();
  }
  if (runtimeErrorCode === "runtime_private_endpoint_unreachable") {
    throw new RuntimeProbeError(PRIVATE_RUNTIME_UNREACHABLE_MESSAGE);
  }
  if (
    ["runtime_proxy_connect_error", "runtime_proxy_timeout"].includes(
      runtimeErrorCode,
    )
  ) {
    throw new RuntimeProbeError(RUNTIME_ENDPOINT_UNREACHABLE_MESSAGE);
  }
  if (res.status === 404) return null;
  if (res.status === 401 || res.status === 403) {
    throw new RuntimeProbeError(
      "Runtime 服务拒绝了 A2A 探测请求，请检查 Runtime 的鉴权配置。",
    );
  }
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "读取 A2A Agent Card 失败"));
  }
  const payload = (await res.json().catch(() => null)) as Record<
    string,
    unknown
  > | null;
  const integrationEndpoint =
    typeof payload?.url === "string" ? payload.url.trim() : "";
  if (!integrationEndpoint) return null;
  return {
    name: typeof payload?.name === "string" ? payload.name : "",
    description:
      typeof payload?.description === "string" ? payload.description : "",
    endpoint: integrationEndpoint,
  };
}

/** Delete a deployed runtime by id. */
export async function deleteRuntime(
  runtimeId: string,
  region: string,
): Promise<void> {
  const res = await apiFetch("/web/delete-runtime", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ runtimeId, region }),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(t || `删除失败 (${res.status})`);
  }
}

/** Server-authorized update compatibility for one concrete Runtime app. */
export interface RuntimeUpdateCapability {
  canUpdate: boolean;
  reason: string;
  runtime: {
    runtimeId: string;
    name: string;
    region: string;
    currentVersion?: number | null;
  };
  agent?: {
    appName: string;
    name?: string;
    description?: string;
    draft?: AgentDraft;
  } | null;
}

export async function getRuntimeUpdateCapability({
  runtimeId,
  region,
  signal,
}: {
  runtimeId: string;
  region: string;
  signal?: AbortSignal;
}): Promise<RuntimeUpdateCapability> {
  const params = new URLSearchParams({ runtimeId, region });
  const res = await apiFetch(
    `/web/runtime-update-capability?${params.toString()}`,
    { signal },
  );
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "检查 Runtime 更新能力失败"));
  }
  return (await res.json()) as RuntimeUpdateCapability;
}

/** Control-plane detail for a runtime (GetRuntime), for the 管理 Agent view. */
export interface RuntimeDetail {
  runtimeId: string;
  name: string;
  description: string;
  status: string;
  statusMessage: string;
  model: string;
  project: string;
  region: string;
  createdAt: string;
  updatedAt: string;
  currentVersion?: number | null;
  resources: {
    cpuMilli?: number | null;
    memoryMb?: number | null;
    minInstance?: number | null;
    maxInstance?: number | null;
    maxConcurrency?: number | null;
  };
  envs: { key: string; value: string }[];
  memoryId: string;
  toolId: string;
  knowledgeId: string;
  mcpToolsetId: string;
  artifactUrl: string;
  artifactType: string;
  networkTypes: string[];
  endpoint: string;
  authType: "none" | "key_auth" | "custom_jwt" | "unknown";
}

/** Fetch a runtime's control-plane detail (config/status/envs). */
async function fetchRuntimeDetail(
  runtimeId: string,
  region: string,
): Promise<RuntimeDetail> {
  let lastError: Error | null = null;
  for (const candidate of runtimeRegionCandidates(region)) {
    const res = await apiFetch(
      `/web/runtime-detail?runtimeId=${encodeURIComponent(runtimeId)}&region=${encodeURIComponent(candidate)}`,
    );
    if (res.ok) return res.json();
    lastError = new Error(await httpErrorMessage(res, "加载 Runtime 详情失败"));
  }
  throw lastError ?? new Error("加载 Runtime 详情失败");
}

/** Fetch a runtime's control-plane detail (config/status/envs). */
export async function getRuntimeDetail(
  runtimeId: string,
  region = "cn-beijing",
  options: ClientCacheOptions = {},
): Promise<RuntimeDetail> {
  const key = cacheKey(runtimeId, region || "cn-beijing");
  const cached = freshCacheValue(
    runtimeDetailCache,
    key,
    RUNTIME_METADATA_CACHE_TTL_MS,
  );
  if (!options.force && cached) return cached;
  const existing = runtimeDetailCache.get(key);
  if (!options.force && existing?.promise) return existing.promise;
  const promise = fetchRuntimeDetail(runtimeId, region).then((detail) =>
    rememberClientCache(runtimeDetailCache, key, detail),
  );
  runtimeDetailCache.set(key, {
    ...existing,
    promise,
    updatedAt: existing?.updatedAt ?? 0,
  });
  try {
    return await promise;
  } finally {
    const current = runtimeDetailCache.get(key);
    if (current?.promise === promise) {
      runtimeDetailCache.set(key, {
        value: current.value,
        updatedAt: current.updatedAt,
      });
    }
  }
}

export function getCachedRuntimeDetail(
  runtimeId: string,
  region = "cn-beijing",
): RuntimeDetail | null {
  return freshCacheValue(
    runtimeDetailCache,
    cacheKey(runtimeId, region || "cn-beijing"),
    RUNTIME_METADATA_CACHE_TTL_MS,
  );
}

export function prefetchRuntimeDetail(
  runtimeId: string,
  region = "cn-beijing",
): void {
  void getRuntimeDetail(runtimeId, region).catch(() => {});
}

export interface GeneratedAgentTestRun {
  runId: string;
  appName: string;
  expiresAt: number;
}

export async function generateAgentProject(
  draft: AgentDraft,
): Promise<AgentProject> {
  const res = await apiFetch("/web/generated-agent-projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft }),
  });
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "生成项目失败"));
  }
  return res.json();
}

export interface GeneratedAgentDraftResult {
  draft: AgentDraft;
  summary: string;
  unresolvedItems: string[];
}

const GENERATED_AGENT_DRAFT_TIMEOUT_MS = 190_000;

export async function generateAgentDraftFromRequirement(
  requirement: string,
): Promise<GeneratedAgentDraftResult> {
  const res = await apiFetch(
    "/web/generated-agent-drafts",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requirement }),
    },
    {},
    GENERATED_AGENT_DRAFT_TIMEOUT_MS,
  );
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "生成 Agent 配置失败"));
  }
  return parseJsonResponse<GeneratedAgentDraftResult>(res, "生成 Agent 配置失败");
}

export async function createGeneratedAgentTestRun(
  draft: AgentDraft,
): Promise<GeneratedAgentTestRun> {
  const res = await apiFetch("/web/generated-agent-test-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft }),
  });
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "创建调试运行失败"));
  }
  return parseJsonResponse<GeneratedAgentTestRun>(res, "创建调试运行失败");
}

export async function createGeneratedAgentTestSession(
  runId: string,
  userId: string,
): Promise<string> {
  const res = await apiFetch(`/web/generated-agent-test-runs/${runId}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId }),
  });
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "创建调试会话失败"));
  }
  const session = await parseJsonResponse<{ id: string }>(res, "创建调试会话失败");
  return session.id;
}

export async function getGeneratedAgentTestTrace(
  runId: string,
  sessionId: string,
): Promise<TraceSpan[]> {
  const res = await apiFetch(
    `/web/generated-agent-test-runs/${encodeURIComponent(runId)}/trace/session/${encodeURIComponent(sessionId)}`,
  );
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "加载调试调用链路失败"));
  }
  const spans = await parseJsonResponse<unknown>(res, "加载调试调用链路失败");
  if (!Array.isArray(spans)) throw new Error("加载调试调用链路失败：返回格式无效");
  return spans as TraceSpan[];
}

export async function* runGeneratedAgentTestSSE({
  runId,
  userId,
  sessionId,
  text,
  signal,
}: {
  runId: string;
  userId: string;
  sessionId: string;
  text: string;
  signal?: AbortSignal;
}): AsyncGenerator<AdkEvent, void, unknown> {
  const parts: Record<string, unknown>[] = text.trim() ? [{ text }] : [];
  const res = await apiFetch(
    `/web/generated-agent-test-runs/${runId}/run_sse`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        session_id: sessionId,
        new_message: { role: "user", parts },
        streaming: true,
      }),
      signal,
    },
    {},
    0,
  );
  if (!res.ok) throw new Error(await httpErrorMessage(res, "调试运行失败"));
  for await (const evt of parseSSE(res)) {
    yield evt as AdkEvent;
  }
}

export async function deleteGeneratedAgentTestRun(runId: string): Promise<void> {
  const res = await apiFetch(`/web/generated-agent-test-runs/${runId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) {
    throw new Error(await httpErrorMessage(res, "清理调试运行失败"));
  }
}
