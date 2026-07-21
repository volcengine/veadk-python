// Thin client for the Google ADK API server (the same server `veadk frontend`
// launches). Uses relative URLs so it works same-origin in production and via
// the Vite dev proxy in development.

import { withAuth } from "./auth";
import { formatRunSseError } from "./runSseError";
import { parseSSE } from "./sse";
import {
  DEFAULT_REQUEST_TIMEOUT_MS,
  requestSignal,
  TRANSFER_REQUEST_TIMEOUT_MS,
} from "./timeout";
import type { AgentProject } from "../create/project";
import type { AgentDraft } from "../create/types";
import { withLocalUser } from "./identity";

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
function apiFetch(
  path: string,
  init: RequestInit = {},
  ep: AdkEndpoint = {},
  timeoutMs: number = DEFAULT_REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const opts = {
    ...init,
    headers: withLocalUser(init.headers),
    signal: requestSignal(init.signal, timeoutMs),
  };
  if (ep.runtimeId) {
    const rq = ep.region ? `${path.includes("?") ? "&" : "?"}region=${encodeURIComponent(ep.region)}` : "";
    return fetch(withAuth(`${API_BASE}/web/runtime-proxy/${ep.runtimeId}${path}${rq}`), opts);
  }
  if (ep.base) {
    // Use backend proxy to avoid CORS issues with remote AgentKit
    const headers = new Headers(opts.headers);
    headers.set("X-AgentKit-Base", ep.base);
    if (ep.apiKey) headers.set("X-AgentKit-Key", ep.apiKey);
    return fetch(withAuth(`${API_BASE}/agentkit-proxy${path}`), { ...opts, headers });
  }
  return fetch(withAuth(`${API_BASE}${path}`), opts);
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
    super("你没有权限访问该 Runtime，请刷新列表后重试。");
    this.name = "RuntimeAccessDeniedError";
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
  if ((res.status === 403 || res.status === 404) && ep?.runtimeId) {
    throw new RuntimeAccessDeniedError();
  }
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "读取 Agent 列表失败"));
  }
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
  const path = `/web/media/${encodeURIComponent(app)}/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}`;
  const res = await apiFetch(path, { method: "DELETE" });
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
  const res = await apiFetch(path, { method: "DELETE" });
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
  name: string;
  description: string;
  type?: AgentNodeType;
  model: string;
  tools: string[];
  skills: AgentSkill[];
  subAgents: string[];
  /** Optional for compatibility with Agent Servers released before this field. */
  components?: AgentComponent[];
  /** Recursive typed tree; only the local server provides it. */
  graph?: AgentNode;
}

async function fetchAgentInfo(app: string, ep: AdkEndpoint): Promise<AgentInfo> {
  const res = await apiFetch(`/web/agent-info/${app}`, {}, ep);
  if (!res.ok) throw new Error(`agent-info failed: ${res.status}`);
  const info = (await res.json()) as Partial<AgentInfo>;
  return {
    name: info.name ?? app,
    description: info.description ?? "",
    type: info.type,
    model: info.model ?? "",
    tools: info.tools ?? [],
    skills: info.skills ?? [],
    subAgents: info.subAgents ?? [],
    components: info.components ?? [],
    graph: info.graph,
  };
}

export async function getAgentInfo(appName: string): Promise<AgentInfo> {
  const { app, ep } = resolve(appName);
  return fetchAgentInfo(app, ep);
}

/** Read Agent metadata for a Runtime without connecting or persisting it. */
export async function getRuntimeAgentInfo(
  runtimeId: string,
  region: string,
): Promise<AgentInfo> {
  const ep = { runtimeId, region };
  const apps = await fetchRemoteApps("", "", ep);
  const app = apps[0];
  if (!app) throw new Error("该 Runtime 未提供可预览的 Agent。");
  return fetchAgentInfo(app, ep);
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
  invocation?: FrontendInvocation;
  /** Function responses to send instead of/alongside text — used to resume a
   *  long-running call (e.g. answering ADK's `adk_request_credential`). */
  functionResponses?: { id: string; name: string; response: unknown }[];
  /** Abort the stream (e.g. when the user switches to another session). */
  signal?: AbortSignal;
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
        custom_metadata: invocationMetadata
          ? { veadkInvocation: invocationMetadata }
          : undefined,
      }),
      signal,
    },
    ep,
    0,
  );
  if (!res.ok) throw new Error(formatRunSseError(`run_sse failed: ${res.status}`));
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
  feishuChannel?: {
    enabled: boolean;
    transport: string;
    runtimeId?: string;
  };
}

/** One live progress frame streamed during a deployment. */
export interface DeployStage {
  level: "info" | "success" | "warning" | "error";
  phase: "build" | "deploy" | "publish" | string;
  message: string;
  pct?: number;
  runtimeName?: string;
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
          im: opts?.im,
          envs: opts?.envs,
        }),
      },
      {},
      0,
    );
  } catch (error) {
    clearController();
    throw error;
  }
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    clearController();
    throw new Error(t || `部署失败 (${res.status})`);
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
  if (!final.url || !final.agentName) {
    throw new Error("部署失败：返回缺少 AgentKit 连接信息");
  }
  // Note: the runtime's data-plane apikey is intentionally NOT persisted in the
  // browser (it's a secret; clear-text localStorage would be XSS-exposed). The
  // "管理 Agent" view shows control-plane detail instead.
  return {
    apikey: final.apikey ?? "",
    url: final.url,
    agentName: final.agentName,
    runtimeId: final.runtimeId,
    consoleUrl: final.consoleUrl,
    region: final.region,
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
}

/** List AgentKit runtimes the server authorizes this user to manage.
 *  `region="all"` merges results from all supported regions. */
export async function getMyRuntimes(region = "all"): Promise<ManagedRuntime[]> {
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

/** One AgentKit runtime as listed by `/web/runtimes` (control-plane). */
export interface CloudRuntime {
  name: string;
  runtimeId: string;
  status: string;
  region: string;
  author: string;
  /** True when this runtime was deployed by the current user (veadk:author). */
  isMine: boolean;
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
  if (!res.ok) throw new Error(`加载 Runtime 失败 (${res.status})`);
  const d = (await res.json()) as Partial<RuntimePage>;
  return { runtimes: d.runtimes ?? [], nextToken: d.nextToken ?? "" };
}

/** Probe whether a runtime speaks the ADK api-server protocol by calling its
 *  `/list-apps` through the proxy. Returns the app list on success, or null when
 *  the runtime does not support it (non-200 / not an ADK server). */
export async function probeRuntimeApps(
  runtimeId: string,
  region = "cn-beijing",
): Promise<string[] | null> {
  try {
    const res = await fetchRemoteApps("", "", { runtimeId, region });
    return res;
  } catch (error) {
    if (error instanceof RuntimeAccessDeniedError) throw error;
    return null;
  }
}

/** Delete a deployed runtime by id. */
export async function deleteRuntime(
  runtimeId: string,
  region = "cn-beijing",
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
}

/** Fetch a runtime's control-plane detail (config/status/envs). */
export async function getRuntimeDetail(
  runtimeId: string,
  region = "cn-beijing",
): Promise<RuntimeDetail> {
  const res = await apiFetch(
    `/web/runtime-detail?runtimeId=${encodeURIComponent(runtimeId)}&region=${encodeURIComponent(region)}`,
  );
  if (!res.ok) {
    throw new Error(await httpErrorMessage(res, "加载 Runtime 详情失败"));
  }
  return res.json();
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
  return res.json();
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
  const session = await res.json();
  return session.id;
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
