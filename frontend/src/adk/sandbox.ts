import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { requestSignal } from "./timeout";
import type { Block } from "../blocks";

const SANDBOX_API = "/web/sandbox/sessions";
const CODEX_PROJECT_HANDOFF_API = "/web/sandbox/codex-project-handoff";
const LIST_TIMEOUT_MS = 30_000;
const START_TIMEOUT_MS = 330_000;
const CONNECT_TIMEOUT_MS = 60_000;
const MESSAGE_TIMEOUT_MS = 600_000;
const CLOSE_TIMEOUT_MS = 15_000;
const SETTINGS_TIMEOUT_MS = 60_000;
const UPLOAD_TIMEOUT_MS = 330_000;
const CODEX_PROJECT_HANDOFF_TIMEOUT_MS = 30_000;
export const CODEX_PROJECT_HANDOFF_PAIRING_TTL_SECONDS = 60 * 60;

export const SANDBOX_DISPLAY_NAME_MAX_LENGTH = 40;
export type SandboxAgentKind = "deepseek-harness" | "openclaw" | "hermes";

export function sandboxStatusLabel(status: string): string {
  switch (status.trim().toLowerCase()) {
    case "ready":
      return "就绪";
    case "wakeable":
      return "可唤醒";
    case "creating":
      return "创建中";
    case "starting":
    case "initializing":
      return "启动中";
    case "pending":
      return "等待中";
    case "running":
      return "运行中";
    case "failed":
    case "error":
      return "异常";
    case "stopped":
      return "已停止";
    case "expired":
      return "已过期";
    case "deleting":
      return "删除中";
    case "deleted":
      return "已删除";
    default:
      return "未知状态";
  }
}

export type SandboxApprovalPolicy = "untrusted" | "on-request" | "never";
export type SandboxApprovalsReviewer = "user" | "auto_review";
export type SandboxMode =
  | "read-only"
  | "workspace-write"
  | "danger-full-access";
export type SandboxApprovalDecision =
  | "accept"
  | "acceptForSession"
  | "decline"
  | "cancel";

export interface SandboxPermissions {
  approvalPolicy: SandboxApprovalPolicy;
  approvalsReviewer: SandboxApprovalsReviewer;
  sandboxMode: SandboxMode;
  networkAccess: boolean;
}

export interface SandboxApproval {
  id: string;
  kind: "command" | "file";
  method: string;
  reason?: string;
  command?: string;
  cwd?: string;
  grantRoot?: string;
  changes?: unknown;
  threadId?: string;
  turnId?: string;
  itemId?: string;
}

export interface SandboxDirectoryEntry {
  name: string;
  path: string;
}

export interface SandboxDirectoryListing {
  path: string;
  parent?: string;
  directories: SandboxDirectoryEntry[];
}

export interface SandboxToolLaunch {
  url: string;
  shellSessionId?: string;
}

export interface SandboxEndpointExport {
  endpoint: string;
  sessionId: string;
  expireAt?: string;
}

export interface CodexProjectHandoffPairing {
  pairingCode: string;
  expireAt: string;
  studioUrl: string;
}

export type CodexProjectHandoffState =
  | "issued"
  | "creating"
  | "session-created"
  | "continuing"
  | "running"
  | "completed"
  | "failed";

export interface CodexProjectHandoffStatus {
  state: CodexProjectHandoffState;
  expireAt: string;
  projectName?: string;
  agentName?: string;
  sessionId?: string;
  error?: string;
  failedStage?: "creating-session" | "continuing-task";
}

export interface SandboxUploadedFile {
  id: string;
  path: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
}

export interface SandboxTokenUsage {
  totalTokens: number;
  inputTokens: number;
  cachedInputTokens: number;
  outputTokens: number;
  reasoningOutputTokens: number;
}

export interface SandboxTokenUsageUpdate {
  turnId: string;
  usage: SandboxTokenUsage;
  threadTotal?: SandboxTokenUsage;
  modelContextWindow?: number;
}

export interface SandboxModel {
  id: string;
  displayName: string;
  description: string;
  isDefault: boolean;
}

export interface SandboxSkill {
  id: string;
  name: string;
  description: string;
}

export interface SandboxThreadSummary {
  id: string;
  name?: string;
  preview: string;
  cwd: string;
  modelProvider: string;
  createdAt: number;
  updatedAt: number;
  status: string;
}

export interface SandboxThreadMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  skillNames?: string[];
}

export interface SandboxThreadSnapshot {
  thread: SandboxThreadSummary;
  threadId: string;
  messages: SandboxThreadMessage[];
  model?: string;
  cwd?: string;
  workspaceLocked: boolean;
  permissions: SandboxPermissions;
}

export interface SandboxThreadPage {
  threads: SandboxThreadSummary[];
  nextCursor?: string;
}

export interface SandboxStatus extends SandboxSessionSettings {
  threadTotal?: SandboxTokenUsage;
  modelContextWindow?: number;
}

export interface SandboxRequestOptions {
  signal?: AbortSignal;
  onBlocks?: (blocks: Block[]) => void;
  onApproval?: (approval: SandboxApproval) => void;
  onApprovalResolved?: (approvalId: string) => void;
  onUsage?: (update: SandboxTokenUsageUpdate) => void;
}

export interface SandboxStartOptions extends SandboxRequestOptions {
  displayName?: string;
  persistent?: boolean;
}

export interface SandboxSession {
  resourceType: "session";
  id: string;
  toolName: "codex" | SandboxAgentKind;
  userSessionId: string;
  displayName: string;
  status: string;
  createdAt: string;
  expireAt: string;
  persistent: boolean;
  toolType: string;
  createdBy: string;
  threadId: string;
  cwd: string;
  workspaceLocked: boolean;
  busy: boolean;
  model?: string;
  permissions: SandboxPermissions;
}

export interface SandboxSnapshot {
  resourceType: "snapshot";
  id: string;
  snapshotId: string;
  sourceSessionId: string;
  toolName: "codex" | SandboxAgentKind;
  userSessionId: string;
  displayName: string;
  status: string;
  snapshotStatus: string;
  reason: string;
  createdAt: string;
  createdBy: string;
}

export type SandboxAgentResource = SandboxSession | SandboxSnapshot;

export interface SandboxAgentWorkspace {
  session: SandboxSession;
  kind: SandboxAgentKind;
  webuiUrl: string;
}

export interface SandboxMessage {
  sessionId: string;
  text: string;
  skillIds?: string[];
}

export interface SandboxReply {
  text: string;
  blocks: Block[];
  usage?: SandboxTokenUsageUpdate;
}

export interface AgentKitSandboxClient {
  listSessions(options?: SandboxRequestOptions): Promise<SandboxAgentResource[]>;
  startSession(options?: SandboxStartOptions): Promise<SandboxSession>;
  listAgentSessions(
    kind: SandboxAgentKind,
    options?: SandboxRequestOptions,
  ): Promise<SandboxAgentResource[]>;
  startAgentSession(
    kind: SandboxAgentKind,
    options?: SandboxStartOptions,
  ): Promise<SandboxSession>;
  openAgentSession(
    kind: SandboxAgentKind,
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxAgentWorkspace>;
  launchAgentTerminal(
    kind: SandboxAgentKind,
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxToolLaunch>;
  deleteAgentSession(
    kind: SandboxAgentKind,
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<void>;
  resumeSnapshot(
    kind: "codex" | SandboxAgentKind,
    snapshotId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxSession>;
  deleteSnapshot(
    kind: "codex" | SandboxAgentKind,
    snapshotId: string,
    options?: SandboxRequestOptions,
  ): Promise<void>;
  connectSession(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxSession>;
  sendMessage(
    message: SandboxMessage,
    options?: SandboxRequestOptions,
  ): Promise<SandboxReply>;
  getStatus(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxStatus>;
  getEndpoint(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxEndpointExport>;
  createCodexProjectHandoffPairing(
    options?: SandboxRequestOptions,
  ): Promise<CodexProjectHandoffPairing>;
  getCodexProjectHandoffStatus(
    pairingCode: string,
    options?: SandboxRequestOptions,
  ): Promise<CodexProjectHandoffStatus>;
  listModels(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxModel[]>;
  setModel(
    sessionId: string,
    model: string,
    options?: SandboxRequestOptions,
  ): Promise<string>;
  listSkills(
    sessionId: string,
    forceReload?: boolean,
    options?: SandboxRequestOptions,
  ): Promise<SandboxSkill[]>;
  listThreads(
    sessionId: string,
    query?: { cursor?: string; search?: string; archived?: boolean },
    options?: SandboxRequestOptions,
  ): Promise<SandboxThreadPage>;
  readThread(
    sessionId: string,
    threadId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxThreadSnapshot>;
  newThread(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxThreadSnapshot>;
  resumeThread(
    sessionId: string,
    threadId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxThreadSnapshot>;
  forkThread(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxThreadSnapshot>;
  archiveThread(
    sessionId: string,
    threadId: string,
    options?: SandboxRequestOptions,
  ): Promise<{ archived: true; snapshot?: SandboxThreadSnapshot }>;
  deleteThread(
    sessionId: string,
    threadId: string,
    options?: SandboxRequestOptions,
  ): Promise<{ deleted: true; snapshot?: SandboxThreadSnapshot }>;
  compactThread(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<void>;
  getSettings(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxSessionSettings>;
  updatePermissions(
    sessionId: string,
    permissions: SandboxPermissions,
    options?: SandboxRequestOptions,
  ): Promise<SandboxPermissions>;
  updateWorkspace(
    sessionId: string,
    cwd: string,
    options?: SandboxRequestOptions,
  ): Promise<string>;
  listDirectories(
    sessionId: string,
    path: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxDirectoryListing>;
  resolveApproval(
    sessionId: string,
    approvalId: string,
    decision: SandboxApprovalDecision,
    options?: SandboxRequestOptions,
  ): Promise<void>;
  launchTerminal(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxToolLaunch>;
  launchBrowser(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxToolLaunch>;
  uploadFile(
    sessionId: string,
    file: File,
    options?: SandboxRequestOptions,
  ): Promise<SandboxUploadedFile>;
  closeSession(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<void>;
  deleteSession(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<void>;
}

export interface SandboxSessionSettings {
  threadId: string;
  cwd: string;
  model?: string;
  workspaceLocked: boolean;
  busy: boolean;
  permissions: SandboxPermissions;
}

interface SessionResponse {
  sessionId: string;
  userSessionId?: string;
  displayName?: string;
  status: string;
  createdAt?: string;
  expireAt?: string;
  persistent?: boolean;
  toolType?: string;
  createdBy?: string;
  threadId?: string;
  cwd?: string;
  workspaceLocked?: boolean;
  busy?: boolean;
  model?: string;
  permissions?: unknown;
}

interface ListSessionsResponse {
  sessions?: SessionResponse[];
  snapshots?: SnapshotResponse[];
}

interface SnapshotResponse {
  snapshotId: string;
  sessionId?: string;
  userSessionId?: string;
  displayName?: string;
  status: string;
  snapshotStatus?: string;
  reason?: string;
  createdAt?: string;
  createdBy?: string;
}

interface SandboxErrorPayload {
  detail?: unknown;
  error?: unknown;
  message?: unknown;
}

interface SandboxStreamPayload {
  id?: unknown;
  kind?: unknown;
  status?: unknown;
  text?: unknown;
  name?: unknown;
  args?: unknown;
  response?: unknown;
  message?: unknown;
  approvalId?: unknown;
  method?: unknown;
  reason?: unknown;
  command?: unknown;
  cwd?: unknown;
  grantRoot?: unknown;
  changes?: unknown;
  threadId?: unknown;
  turnId?: unknown;
  itemId?: unknown;
  usage?: unknown;
  threadTotal?: unknown;
  modelContextWindow?: unknown;
}

function sandboxHeaders(headers?: HeadersInit): Headers {
  const next = withLocalUser(headers);
  if (!next.has("Accept")) next.set("Accept", "application/json");
  return next;
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const text = await response.text().catch(() => "");
  let payload: SandboxErrorPayload = {};
  try {
    payload = JSON.parse(text) as SandboxErrorPayload;
  } catch {
    const summary = `${fallback}（HTTP ${response.status}）`;
    return new Error(text ? `${summary}：${text}` : summary);
  }
  const nestedDetail = payload.detail;
  const detail =
    nestedDetail && typeof nestedDetail === "object" && "message" in nestedDetail
      ? (nestedDetail as SandboxErrorPayload).message
      : (nestedDetail ?? payload.error ?? payload.message);
  const detailText = typeof detail === "string"
    ? detail
    : detail == null
      ? ""
      : JSON.stringify(detail);
  const summary = `${fallback}（HTTP ${response.status}）`;
  return new Error(detailText ? `${summary}：${detailText}` : summary);
}

function parseSession(
  data: SessionResponse,
  toolName: SandboxSession["toolName"] = "codex",
): SandboxSession {
  if (!data.sessionId || !data.status) {
    throw new Error("AgentKit 沙箱返回了无效的 Session 信息。");
  }
  return {
    resourceType: "session",
    id: data.sessionId,
    toolName,
    userSessionId: data.userSessionId ?? "",
    displayName: data.displayName ?? "",
    status: data.status,
    createdAt: data.createdAt ?? "",
    expireAt: data.expireAt ?? "",
    persistent: data.persistent !== false,
    toolType: data.toolType ?? "",
    createdBy: data.createdBy ?? "",
    threadId: data.threadId ?? "",
    cwd: data.cwd ?? "",
    workspaceLocked: data.workspaceLocked === true,
    busy: data.busy === true,
    ...(typeof data.model === "string" ? { model: data.model } : {}),
    permissions: parsePermissions(data.permissions),
  };
}

function parseSnapshot(
  data: SnapshotResponse,
  toolName: SandboxSession["toolName"] = "codex",
): SandboxSnapshot {
  if (!data.snapshotId || !data.status) {
    throw new Error("AgentKit 沙箱返回了无效的 Snapshot 信息。");
  }
  return {
    resourceType: "snapshot",
    id: data.snapshotId,
    snapshotId: data.snapshotId,
    sourceSessionId: data.sessionId ?? "",
    toolName,
    userSessionId: data.userSessionId ?? "",
    displayName: data.displayName ?? "",
    status: data.status,
    snapshotStatus: data.snapshotStatus ?? "Unknown",
    reason: data.reason ?? "",
    createdAt: data.createdAt ?? "",
    createdBy: data.createdBy ?? "",
  };
}

const DEFAULT_PERMISSIONS: SandboxPermissions = {
  approvalPolicy: "on-request",
  approvalsReviewer: "user",
  sandboxMode: "workspace-write",
  networkAccess: false,
};

function parsePermissions(value: unknown): SandboxPermissions {
  if (!value || typeof value !== "object") return { ...DEFAULT_PERMISSIONS };
  const data = value as Partial<SandboxPermissions>;
  const approvalPolicy = data.approvalPolicy;
  const approvalsReviewer = data.approvalsReviewer;
  const sandboxMode = data.sandboxMode;
  return {
    approvalPolicy:
      approvalPolicy === "untrusted" ||
      approvalPolicy === "on-request" ||
      approvalPolicy === "never"
        ? approvalPolicy
        : DEFAULT_PERMISSIONS.approvalPolicy,
    approvalsReviewer:
      approvalsReviewer === "user" || approvalsReviewer === "auto_review"
        ? approvalsReviewer
        : DEFAULT_PERMISSIONS.approvalsReviewer,
    sandboxMode:
      sandboxMode === "read-only" ||
      sandboxMode === "workspace-write" ||
      sandboxMode === "danger-full-access"
        ? sandboxMode
        : DEFAULT_PERMISSIONS.sandboxMode,
    networkAccess:
      typeof data.networkAccess === "boolean"
        ? data.networkAccess
        : DEFAULT_PERMISSIONS.networkAccess,
  };
}

function parseSettings(value: unknown): SandboxSessionSettings {
  if (!value || typeof value !== "object") {
    throw new Error("Sandbox 返回了无效设置。");
  }
  const data = value as SessionResponse;
  return {
    threadId: typeof data.threadId === "string" ? data.threadId : "",
    cwd: typeof data.cwd === "string" ? data.cwd : "",
    ...(typeof data.model === "string" ? { model: data.model } : {}),
    workspaceLocked: data.workspaceLocked === true,
    busy: data.busy === true,
    permissions: parsePermissions(data.permissions),
  };
}

function recordOf(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function parseModel(value: unknown): SandboxModel | undefined {
  const data = recordOf(value);
  if (!data || typeof data.id !== "string" || !data.id) return undefined;
  return {
    id: data.id,
    displayName:
      typeof data.displayName === "string" ? data.displayName : data.id,
    description:
      typeof data.description === "string" ? data.description : "",
    isDefault: data.isDefault === true,
  };
}

function parseSkill(value: unknown): SandboxSkill | undefined {
  const data = recordOf(value);
  if (
    !data ||
    typeof data.id !== "string" ||
    !data.id ||
    typeof data.name !== "string" ||
    !data.name
  ) return undefined;
  return {
    id: data.id,
    name: data.name,
    description:
      typeof data.description === "string" ? data.description : "",
  };
}

function parseThreadSummary(value: unknown): SandboxThreadSummary | undefined {
  const data = recordOf(value);
  if (!data || typeof data.id !== "string" || !data.id) return undefined;
  return {
    id: data.id,
    ...(typeof data.name === "string" && data.name
      ? { name: data.name }
      : {}),
    preview: typeof data.preview === "string" ? data.preview : "",
    cwd: typeof data.cwd === "string" ? data.cwd : "",
    modelProvider:
      typeof data.modelProvider === "string" ? data.modelProvider : "",
    createdAt:
      typeof data.createdAt === "number" && Number.isFinite(data.createdAt)
        ? data.createdAt
        : 0,
    updatedAt:
      typeof data.updatedAt === "number" && Number.isFinite(data.updatedAt)
        ? data.updatedAt
        : 0,
    status: typeof data.status === "string" ? data.status : "unknown",
  };
}

function parseThreadSnapshot(value: unknown): SandboxThreadSnapshot {
  const data = recordOf(value);
  const thread = parseThreadSummary(data?.thread);
  if (
    !data ||
    !thread ||
    typeof data.threadId !== "string" ||
    !Array.isArray(data.messages)
  ) {
    throw new Error("Sandbox 返回了无效 Thread 快照。");
  }
  const messages = data.messages.flatMap((value): SandboxThreadMessage[] => {
    const message = recordOf(value);
    if (
      !message ||
      typeof message.id !== "string" ||
      (message.role !== "user" && message.role !== "assistant") ||
      typeof message.content !== "string" ||
      typeof message.timestamp !== "number"
    ) return [];
    const skillNames = Array.isArray(message.skillNames)
      ? message.skillNames.filter(
          (name): name is string => typeof name === "string" && Boolean(name),
        )
      : [];
    return [{
      id: message.id,
      role: message.role,
      content: message.content,
      timestamp: message.timestamp,
      ...(skillNames.length ? { skillNames } : {}),
    }];
  });
  return {
    thread,
    threadId: data.threadId,
    messages,
    ...(typeof data.model === "string" ? { model: data.model } : {}),
    ...(typeof data.cwd === "string" ? { cwd: data.cwd } : {}),
    workspaceLocked: data.workspaceLocked === true,
    permissions: parsePermissions(data.permissions),
  };
}

function parseTokenUsage(value: unknown): SandboxTokenUsage | undefined {
  if (!value || typeof value !== "object") return undefined;
  const data = value as Partial<SandboxTokenUsage>;
  const fields = [
    data.totalTokens,
    data.inputTokens,
    data.cachedInputTokens,
    data.outputTokens,
    data.reasoningOutputTokens,
  ];
  if (fields.some((field) =>
    typeof field !== "number" || !Number.isFinite(field) || field < 0
  )) return undefined;
  return {
    totalTokens: Math.trunc(data.totalTokens as number),
    inputTokens: Math.trunc(data.inputTokens as number),
    cachedInputTokens: Math.trunc(data.cachedInputTokens as number),
    outputTokens: Math.trunc(data.outputTokens as number),
    reasoningOutputTokens: Math.trunc(data.reasoningOutputTokens as number),
  };
}

function parseUsageUpdate(
  payload: SandboxStreamPayload,
): SandboxTokenUsageUpdate | undefined {
  const usage = parseTokenUsage(payload.usage);
  if (!usage || typeof payload.turnId !== "string") return undefined;
  const threadTotal = parseTokenUsage(payload.threadTotal);
  const context = payload.modelContextWindow;
  return {
    turnId: payload.turnId,
    usage,
    ...(threadTotal ? { threadTotal } : {}),
    ...(typeof context === "number" &&
      Number.isFinite(context) &&
      context >= 0
      ? { modelContextWindow: Math.trunc(context) }
      : {}),
  };
}

function parseApproval(payload: SandboxStreamPayload): SandboxApproval | null {
  if (
    typeof payload.id !== "string" ||
    (payload.kind !== "command" && payload.kind !== "file") ||
    typeof payload.method !== "string"
  ) return null;
  return {
    id: payload.id,
    kind: payload.kind,
    method: payload.method,
    ...(typeof payload.reason === "string" ? { reason: payload.reason } : {}),
    ...(typeof payload.command === "string" ? { command: payload.command } : {}),
    ...(typeof payload.cwd === "string" ? { cwd: payload.cwd } : {}),
    ...(typeof payload.grantRoot === "string"
      ? { grantRoot: payload.grantRoot }
      : {}),
    ...(payload.changes !== undefined ? { changes: payload.changes } : {}),
    ...(typeof payload.threadId === "string"
      ? { threadId: payload.threadId }
      : {}),
    ...(typeof payload.turnId === "string" ? { turnId: payload.turnId } : {}),
    ...(typeof payload.itemId === "string" ? { itemId: payload.itemId } : {}),
  };
}

async function parseSandboxStream(
  response: Response,
  options: SandboxRequestOptions = {},
): Promise<SandboxReply> {
  if (!response.body) throw new Error("沙箱对话服务未返回内容。");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let reply = "";
  const blocks: Block[] = [];
  const activityIndexes = new Map<string, number>();
  let latestUsage: SandboxTokenUsageUpdate | undefined;

  function emitBlocks(): void {
    options.onBlocks?.(blocks.map((block) => ({ ...block })));
  }

  function appendReply(text: string): void {
    reply += text;
    const last = blocks[blocks.length - 1];
    if (last?.kind === "text") last.text += text;
    else blocks.push({ kind: "text", text });
    emitBlocks();
  }

  function applyActivity(payload: SandboxStreamPayload): void {
    if (
      typeof payload.id !== "string" ||
      (payload.kind !== "thinking" && payload.kind !== "tool") ||
      (payload.status !== "running" && payload.status !== "done")
    ) return;
    const done = payload.status === "done";
    let block: Block;
    if (payload.kind === "thinking") {
      if (typeof payload.text !== "string" || !payload.text) return;
      block = { kind: "thinking", text: payload.text, done };
    } else {
      if (typeof payload.name !== "string" || !payload.name) return;
      block = {
        kind: "tool",
        name: payload.name,
        args: payload.args,
        response: payload.response,
        done,
      };
    }
    const existing = activityIndexes.get(payload.id);
    if (existing === undefined) {
      activityIndexes.set(payload.id, blocks.length);
      blocks.push(block);
    } else {
      blocks[existing] = block;
    }
    emitBlocks();
  }

  function consumeFrame(frame: string): void {
    let event = "message";
    const data: string[] = [];
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length === 0) return;

    let payload: SandboxStreamPayload;
    try {
      payload = JSON.parse(data.join("\n")) as SandboxStreamPayload;
    } catch {
      throw new Error("沙箱对话服务返回了无法解析的响应。");
    }
    if (event === "error") {
      throw new Error(
        typeof payload.message === "string" && payload.message
          ? payload.message
          : "沙箱对话失败，请稍后重试。",
      );
    }
    if (event === "activity") applyActivity(payload);
    if (event === "approval") {
      const approval = parseApproval(payload);
      if (approval) options.onApproval?.(approval);
    }
    if (event === "usage") {
      const update = parseUsageUpdate(payload);
      if (update) {
        latestUsage = update;
        options.onUsage?.(update);
      }
    }
    if (
      event === "approval_resolved" &&
      typeof payload.approvalId === "string"
    ) {
      options.onApprovalResolved?.(payload.approvalId);
    }
    if (event === "delta" && typeof payload.text === "string") {
      appendReply(payload.text);
    }
    if (event === "done" && !reply && typeof payload.text === "string") {
      appendReply(payload.text);
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    frames.forEach(consumeFrame);
    if (done) break;
  }
  if (buffer.trim()) consumeFrame(buffer);
  if (blocks.length === 0) throw new Error("沙箱未返回有效回复，请重试。");
  return {
    text: reply,
    blocks,
    ...(latestUsage ? { usage: latestUsage } : {}),
  };
}

async function sandboxJson(
  sessionId: string,
  action: string,
  {
    method = "GET",
    body,
    options = {},
    fallback,
  }: {
    method?: "GET" | "POST" | "PUT";
    body?: unknown;
    options?: SandboxRequestOptions;
    fallback: string;
  },
): Promise<unknown> {
  if (!sessionId) throw new Error("缺少要操作的 AgentKit Session。");
  const response = await fetch(
    withAuth(`${SANDBOX_API}/${encodeURIComponent(sessionId)}/${action}`),
    {
      method,
      headers: sandboxHeaders(
        body === undefined ? undefined : { "Content-Type": "application/json" },
      ),
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: requestSignal(options.signal, SETTINGS_TIMEOUT_MS),
    },
  );
  if (!response.ok) throw await responseError(response, fallback);
  return response.json();
}

export const sandboxClient: AgentKitSandboxClient = {
  async listSessions(options = {}) {
    const response = await fetch(withAuth(SANDBOX_API), {
      method: "GET",
      headers: sandboxHeaders(),
      signal: requestSignal(options.signal, LIST_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw await responseError(response, "无法读取 Codex 智能体，请稍后重试。");
    }
    const data = (await response.json()) as ListSessionsResponse;
    if (!Array.isArray(data.sessions)) {
      throw new Error("AgentKit 沙箱返回了无效的 Session 列表。");
    }
    if (data.snapshots !== undefined && !Array.isArray(data.snapshots)) {
      throw new Error("AgentKit 沙箱返回了无效的 Snapshot 列表。");
    }
    return [
      ...data.sessions.map((session) => parseSession(session)),
      ...(data.snapshots ?? []).map((snapshot) => parseSnapshot(snapshot)),
    ];
  },

  async startSession(options = {}) {
    const response = await fetch(withAuth(SANDBOX_API), {
      method: "POST",
      headers: sandboxHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        displayName: options.displayName?.trim() ?? "",
        persistent: options.persistent ?? true,
      }),
      signal: requestSignal(options.signal, START_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw await responseError(response, "无法启动 AgentKit 沙箱，请稍后重试。");
    }
    return parseSession((await response.json()) as SessionResponse);
  },

  async listAgentSessions(kind, options = {}) {
    const response = await fetch(withAuth(`/web/${kind}/sessions`), {
      method: "GET",
      headers: sandboxHeaders(),
      signal: requestSignal(options.signal, LIST_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw await responseError(response, `无法读取 ${kind} 智能体，请稍后重试。`);
    }
    const data = (await response.json()) as ListSessionsResponse;
    if (!Array.isArray(data.sessions)) {
      throw new Error(`AgentKit 返回了无效的 ${kind} Session 列表。`);
    }
    if (data.snapshots !== undefined && !Array.isArray(data.snapshots)) {
      throw new Error(`AgentKit 返回了无效的 ${kind} Snapshot 列表。`);
    }
    return [
      ...data.sessions.map((session) => parseSession(session, kind)),
      ...(data.snapshots ?? []).map((snapshot) => parseSnapshot(snapshot, kind)),
    ];
  },

  async startAgentSession(kind, options = {}) {
    const response = await fetch(withAuth(`/web/${kind}/sessions`), {
      method: "POST",
      headers: sandboxHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        displayName: options.displayName?.trim() ?? "",
        persistent: options.persistent ?? true,
      }),
      signal: requestSignal(options.signal, START_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw await responseError(response, `无法创建 ${kind} 智能体，请稍后重试。`);
    }
    return parseSession((await response.json()) as SessionResponse, kind);
  },

  async openAgentSession(kind, sessionId, options = {}) {
    if (!sessionId) throw new Error("缺少要打开的 AgentKit Session。");
    const response = await fetch(
      withAuth(`/web/${kind}/sessions/${encodeURIComponent(sessionId)}/open`),
      {
        method: "POST",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, SETTINGS_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, `无法打开 ${kind} 智能体。`);
    }
    const value = (await response.json()) as SessionResponse & {
      webuiUrl?: unknown;
    };
    if (typeof value.webuiUrl !== "string" || !value.webuiUrl.startsWith("/")) {
      throw new Error(`${kind} 智能体返回了无效的主页面地址。`);
    }
    return {
      session: parseSession(value, kind),
      kind,
      webuiUrl: withAuth(value.webuiUrl),
    };
  },

  async launchAgentTerminal(kind, sessionId, options = {}) {
    if (!sessionId) throw new Error("缺少要打开 Terminal 的 AgentKit Session。");
    const response = await fetch(
      withAuth(`/web/${kind}/sessions/${encodeURIComponent(sessionId)}/terminal`),
      {
        method: "POST",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, SETTINGS_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, `无法打开 ${kind} Terminal。`);
    }
    const value = (await response.json()) as {
      url?: unknown;
      shellSessionId?: unknown;
    };
    const terminalUrl = sandboxToolUrl(value.url, `${kind} Terminal`);
    return {
      url: terminalUrl,
      ...(typeof value.shellSessionId === "string"
        ? { shellSessionId: value.shellSessionId }
        : {}),
    };
  },

  async deleteAgentSession(kind, sessionId, options = {}) {
    if (!sessionId) return;
    const response = await fetch(
      withAuth(`/web/${kind}/sessions/${encodeURIComponent(sessionId)}`),
      {
        method: "DELETE",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, CLOSE_TIMEOUT_MS),
      },
    );
    if (!response.ok && response.status !== 404) {
      throw await responseError(response, `无法删除 ${kind} 智能体。`);
    }
  },

  async resumeSnapshot(kind, snapshotId, options = {}) {
    if (!snapshotId) throw new Error("缺少要唤醒的 AgentKit Snapshot。");
    const base = kind === "codex" ? "/web/sandbox" : `/web/${kind}`;
    const response = await fetch(
      withAuth(`${base}/snapshots/${encodeURIComponent(snapshotId)}/resume`),
      {
        method: "POST",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, START_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法从快照唤醒智能体，请稍后重试。");
    }
    return parseSession((await response.json()) as SessionResponse, kind);
  },

  async deleteSnapshot(kind, snapshotId, options = {}) {
    if (!snapshotId) return;
    const base = kind === "codex" ? "/web/sandbox" : `/web/${kind}`;
    const response = await fetch(
      withAuth(`${base}/snapshots/${encodeURIComponent(snapshotId)}`),
      {
        method: "DELETE",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, CLOSE_TIMEOUT_MS),
      },
    );
    if (!response.ok && response.status !== 404) {
      throw await responseError(response, "无法删除智能体快照。");
    }
  },

  async connectSession(sessionId, options = {}) {
    if (!sessionId) throw new Error("缺少要连接的 AgentKit Session。");
    const response = await fetch(
      withAuth(`${SANDBOX_API}/${encodeURIComponent(sessionId)}/connect`),
      {
        method: "POST",
        headers: sandboxHeaders({ "Content-Type": "application/json" }),
        signal: requestSignal(options.signal, CONNECT_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法连接 Codex 智能体，请稍后重试。");
    }
    const session = parseSession((await response.json()) as SessionResponse);
    if (session.status.toLowerCase() !== "ready") {
      throw new Error(`AgentKit Session 尚未就绪，当前状态：${session.status}。`);
    }
    return session;
  },

  async sendMessage(message, options = {}) {
    if (!message.sessionId || !message.text.trim()) {
      throw new Error("内置智能体会话缺少有效的消息内容。");
    }
    const response = await fetch(
      withAuth(`${SANDBOX_API}/${encodeURIComponent(message.sessionId)}/messages`),
      {
        method: "POST",
        headers: sandboxHeaders({
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({
          message: message.text,
          ...(message.skillIds?.length ? { skillIds: message.skillIds } : {}),
        }),
        signal: requestSignal(options.signal, MESSAGE_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "沙箱对话失败，请稍后重试。");
    }
    return parseSandboxStream(response, options);
  },

  async getStatus(sessionId, options = {}) {
    const value = await sandboxJson(sessionId, "status", {
      options,
      fallback: "无法读取 Codex 状态。",
    });
    const settings = parseSettings(value);
    const data = recordOf(value);
    const threadTotal = parseTokenUsage(data?.threadTotal);
    const context = data?.modelContextWindow;
    return {
      ...settings,
      ...(threadTotal ? { threadTotal } : {}),
      ...(typeof context === "number" &&
        Number.isFinite(context) &&
        context >= 0
        ? { modelContextWindow: Math.trunc(context) }
        : {}),
    };
  },

  async getEndpoint(sessionId, options = {}) {
    const value = recordOf(await sandboxJson(sessionId, "endpoint", {
      options,
      fallback: "无法读取 Sandbox Endpoint。",
    }));
    if (typeof value?.endpoint !== "string" || !value.endpoint.trim()) {
      throw new Error("Sandbox 返回了无效 Endpoint。");
    }
    return {
      endpoint: value.endpoint,
      sessionId:
        typeof value.sessionId === "string" ? value.sessionId : sessionId,
      ...(typeof value.expireAt === "string"
        ? { expireAt: value.expireAt }
        : {}),
    };
  },

  async createCodexProjectHandoffPairing(options = {}) {
    const response = await fetch(
      withAuth(`${CODEX_PROJECT_HANDOFF_API}/pairings`),
      {
        method: "POST",
        headers: sandboxHeaders({
          Accept: "application/json",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({
          ttlSeconds: CODEX_PROJECT_HANDOFF_PAIRING_TTL_SECONDS,
        }),
        signal: requestSignal(
          options.signal,
          CODEX_PROJECT_HANDOFF_TIMEOUT_MS,
        ),
      },
    );
    if (!response.ok) {
      throw await responseError(
        response,
        "无法生成 Codex 云端接力配对码。",
      );
    }
    const value = recordOf(await response.json());
    if (
      typeof value?.pairingCode !== "string" ||
      !value.pairingCode.trim() ||
      typeof value.expireAt !== "string" ||
      !value.expireAt.trim()
    ) {
      throw new Error("Studio 返回了无效的 Codex 云端接力配对码。");
    }
    const studioUrl = typeof value.studioUrl === "string" && value.studioUrl.trim()
      ? value.studioUrl.trim()
      : window.location.origin;
    return {
      pairingCode: value.pairingCode,
      expireAt: value.expireAt,
      studioUrl,
    };
  },

  async getCodexProjectHandoffStatus(pairingCode, options = {}) {
    const response = await fetch(
      withAuth(
        `${CODEX_PROJECT_HANDOFF_API}/pairings/${encodeURIComponent(pairingCode)}`,
      ),
      {
        headers: sandboxHeaders({ Accept: "application/json" }),
        signal: requestSignal(
          options.signal,
          CODEX_PROJECT_HANDOFF_TIMEOUT_MS,
        ),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法读取端云接力状态。");
    }
    const value = recordOf(await response.json());
    const states: ReadonlySet<string> = new Set([
      "issued",
      "creating",
      "session-created",
      "continuing",
      "running",
      "completed",
      "failed",
    ]);
    if (
      typeof value?.state !== "string" ||
      !states.has(value.state) ||
      typeof value.expireAt !== "string" ||
      !value.expireAt.trim()
    ) {
      throw new Error("Studio 返回了无效的端云接力状态。");
    }
    return {
      state: value.state as CodexProjectHandoffState,
      expireAt: value.expireAt,
      ...(typeof value.projectName === "string"
        ? { projectName: value.projectName }
        : {}),
      ...(typeof value.agentName === "string"
        ? { agentName: value.agentName }
        : {}),
      ...(typeof value.sessionId === "string"
        ? { sessionId: value.sessionId }
        : {}),
      ...(typeof value.error === "string" ? { error: value.error } : {}),
      ...(value.failedStage === "creating-session" ||
      value.failedStage === "continuing-task"
        ? { failedStage: value.failedStage }
        : {}),
    };
  },

  async listModels(sessionId, options = {}) {
    const value = recordOf(await sandboxJson(sessionId, "models", {
      options,
      fallback: "无法读取 Codex 模型列表。",
    }));
    if (!Array.isArray(value?.models)) {
      throw new Error("Sandbox 返回了无效模型列表。");
    }
    return value.models.flatMap((model) => {
      const parsed = parseModel(model);
      return parsed ? [parsed] : [];
    });
  },

  async setModel(sessionId, model, options = {}) {
    const value = recordOf(await sandboxJson(sessionId, "model", {
      method: "PUT",
      body: { model },
      options,
      fallback: "无法切换 Codex 模型。",
    }));
    if (typeof value?.model !== "string" || !value.model) {
      throw new Error("Sandbox 返回了无效模型。");
    }
    return value.model;
  },

  async listSkills(sessionId, forceReload = false, options = {}) {
    const query = forceReload ? "?force_reload=true" : "";
    const value = recordOf(await sandboxJson(sessionId, `skills${query}`, {
      options,
      fallback: "无法读取 Codex Skills。",
    }));
    if (!Array.isArray(value?.skills)) {
      throw new Error("Sandbox 返回了无效 Skill 列表。");
    }
    return value.skills.flatMap((skill) => {
      const parsed = parseSkill(skill);
      return parsed ? [parsed] : [];
    });
  },

  async listThreads(sessionId, query = {}, options = {}) {
    const search = new URLSearchParams();
    if (query.cursor) search.set("cursor", query.cursor);
    if (query.search) search.set("search", query.search);
    if (query.archived) search.set("archived", "true");
    const suffix = search.size ? `?${search}` : "";
    const value = recordOf(await sandboxJson(sessionId, `threads${suffix}`, {
      options,
      fallback: "无法读取 Codex Thread 列表。",
    }));
    if (!Array.isArray(value?.threads)) {
      throw new Error("Sandbox 返回了无效 Thread 列表。");
    }
    return {
      threads: value.threads.flatMap((thread) => {
        const parsed = parseThreadSummary(thread);
        return parsed ? [parsed] : [];
      }),
      ...(typeof value.nextCursor === "string"
        ? { nextCursor: value.nextCursor }
        : {}),
    };
  },

  async newThread(sessionId, options = {}) {
    return parseThreadSnapshot(await sandboxJson(sessionId, "threads/new", {
      method: "POST",
      options,
      fallback: "无法创建新的 Codex Thread。",
    }));
  },

  async readThread(sessionId, threadId, options = {}) {
    if (!threadId) throw new Error("缺少要读取的 Codex Thread。");
    return parseThreadSnapshot(
      await sandboxJson(
        sessionId,
        `threads/${encodeURIComponent(threadId)}`,
        {
          options,
          fallback: "无法读取 Codex 历史消息。",
        },
      ),
    );
  },

  async resumeThread(sessionId, threadId, options = {}) {
    return parseThreadSnapshot(
      await sandboxJson(sessionId, "threads/resume", {
        method: "POST",
        body: { threadId },
        options,
        fallback: "无法恢复 Codex Thread。",
      }),
    );
  },

  async forkThread(sessionId, options = {}) {
    return parseThreadSnapshot(await sandboxJson(sessionId, "threads/fork", {
      method: "POST",
      options,
      fallback: "无法分叉 Codex Thread。",
    }));
  },

  async archiveThread(sessionId, threadId, options = {}) {
    const value = recordOf(
      await sandboxJson(sessionId, "threads/archive", {
        method: "POST",
        body: { threadId },
        options,
        fallback: "无法归档 Codex Thread。",
      }),
    );
    if (value?.archived !== true) {
      throw new Error("Sandbox 返回了无效归档结果。");
    }
    return {
      archived: true,
      ...(value.thread ? { snapshot: parseThreadSnapshot(value) } : {}),
    };
  },

  async deleteThread(sessionId, threadId, options = {}) {
    const value = recordOf(
      await sandboxJson(sessionId, "threads/delete", {
        method: "POST",
        body: { threadId },
        options,
        fallback: "无法删除 Codex Thread。",
      }),
    );
    if (value?.deleted !== true) {
      throw new Error("Sandbox 返回了无效删除结果。");
    }
    return {
      deleted: true,
      ...(value.thread ? { snapshot: parseThreadSnapshot(value) } : {}),
    };
  },

  async compactThread(sessionId, options = {}) {
    await sandboxJson(sessionId, "threads/compact", {
      method: "POST",
      options,
      fallback: "无法压缩 Codex Thread。",
    });
  },

  async getSettings(sessionId, options = {}) {
    const response = await fetch(
      withAuth(`${SANDBOX_API}/${encodeURIComponent(sessionId)}/settings`),
      {
        method: "GET",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, SETTINGS_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法读取 Codex 权限与工作空间。");
    }
    return parseSettings(await response.json());
  },

  async updatePermissions(sessionId, permissions, options = {}) {
    const response = await fetch(
      withAuth(`${SANDBOX_API}/${encodeURIComponent(sessionId)}/permissions`),
      {
        method: "PUT",
        headers: sandboxHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(permissions),
        signal: requestSignal(options.signal, SETTINGS_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法更新 Codex 权限。");
    }
    const value = (await response.json()) as { permissions?: unknown };
    return parsePermissions(value.permissions);
  },

  async updateWorkspace(sessionId, cwd, options = {}) {
    const response = await fetch(
      withAuth(`${SANDBOX_API}/${encodeURIComponent(sessionId)}/workspace`),
      {
        method: "PUT",
        headers: sandboxHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ cwd }),
        signal: requestSignal(options.signal, SETTINGS_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法更新 Codex 工作空间。");
    }
    const value = (await response.json()) as { cwd?: unknown };
    if (typeof value.cwd !== "string" || !value.cwd) {
      throw new Error("Sandbox 返回了无效工作目录。");
    }
    return value.cwd;
  },

  async listDirectories(sessionId, path, options = {}) {
    const query = new URLSearchParams({ path });
    const response = await fetch(
      withAuth(
        `${SANDBOX_API}/${encodeURIComponent(sessionId)}/directories?${query}`,
      ),
      {
        method: "GET",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, SETTINGS_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法读取 Sandbox 目录。");
    }
    const value = (await response.json()) as Partial<SandboxDirectoryListing>;
    if (
      typeof value.path !== "string" ||
      !Array.isArray(value.directories) ||
      value.directories.some(
        (entry) =>
          !entry ||
          typeof entry.name !== "string" ||
          typeof entry.path !== "string",
      )
    ) {
      throw new Error("Sandbox 返回了无效目录列表。");
    }
    return {
      path: value.path,
      ...(typeof value.parent === "string" ? { parent: value.parent } : {}),
      directories: value.directories,
    };
  },

  async resolveApproval(
    sessionId,
    approvalId,
    decision,
    options = {},
  ) {
    const response = await fetch(
      withAuth(
        `${SANDBOX_API}/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(approvalId)}`,
      ),
      {
        method: "POST",
        headers: sandboxHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ decision }),
        signal: requestSignal(options.signal, SETTINGS_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法提交 Codex 审批决定。");
    }
  },

  async launchTerminal(sessionId, options = {}) {
    return launchSandboxTool(sessionId, "terminal", options);
  },

  async launchBrowser(sessionId, options = {}) {
    return launchSandboxTool(sessionId, "browser", options);
  },

  async uploadFile(sessionId, file, options = {}) {
    const form = new FormData();
    form.set("file", file, file.name);
    const response = await fetch(
      withAuth(`${SANDBOX_API}/${encodeURIComponent(sessionId)}/files`),
      {
        method: "POST",
        headers: sandboxHeaders(),
        body: form,
        signal: requestSignal(options.signal, UPLOAD_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "无法上传文件到 Sandbox。");
    }
    const value = (await response.json()) as Partial<SandboxUploadedFile>;
    if (
      typeof value.id !== "string" ||
      typeof value.path !== "string" ||
      typeof value.name !== "string" ||
      typeof value.mimeType !== "string" ||
      typeof value.sizeBytes !== "number"
    ) {
      throw new Error("Sandbox 返回了无效上传结果。");
    }
    return value as SandboxUploadedFile;
  },

  async closeSession(sessionId, options = {}) {
    if (!sessionId) return;
    const response = await fetch(
      withAuth(
        `${SANDBOX_API}/${encodeURIComponent(sessionId)}/disconnect`,
      ),
      {
        method: "POST",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, CLOSE_TIMEOUT_MS),
      },
    );
    if (!response.ok && response.status !== 404) {
      throw await responseError(response, "无法断开 Codex 智能体连接。");
    }
  },

  async deleteSession(sessionId, options = {}) {
    if (!sessionId) return;
    const response = await fetch(
      withAuth(`${SANDBOX_API}/${encodeURIComponent(sessionId)}`),
      {
        method: "DELETE",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, CLOSE_TIMEOUT_MS),
      },
    );
    if (!response.ok && response.status !== 404) {
      throw await responseError(response, "无法删除 Codex 智能体。");
    }
  },
};

async function launchSandboxTool(
  sessionId: string,
  tool: "terminal" | "browser",
  options: SandboxRequestOptions,
): Promise<SandboxToolLaunch> {
  const response = await fetch(
    withAuth(`${SANDBOX_API}/${encodeURIComponent(sessionId)}/${tool}`),
    {
      method: "POST",
      headers: sandboxHeaders(),
      signal: requestSignal(options.signal, SETTINGS_TIMEOUT_MS),
    },
  );
  if (!response.ok) {
    throw await responseError(
      response,
      tool === "terminal"
        ? "无法打开 Sandbox Terminal。"
        : "无法打开 Sandbox Browser。",
    );
  }
  const value = (await response.json()) as {
    url?: unknown;
    shellSessionId?: unknown;
  };
  const toolUrl = sandboxToolUrl(value.url, "Sandbox 工具");
  return {
    url: toolUrl,
    ...(typeof value.shellSessionId === "string"
      ? { shellSessionId: value.shellSessionId }
      : {}),
  };
}

function sandboxToolUrl(value: unknown, label: string): string {
  if (typeof value !== "string") {
    throw new Error(`${label} 返回了无效地址。`);
  }
  if (value.startsWith("/")) return withAuth(value);
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${label} 返回了无效地址。`);
  }
  const allowsHttp =
    parsed.protocol === "http:" && window.location.protocol === "http:";
  if (parsed.protocol !== "https:" && !allowsHttp) {
    throw new Error(`${label} 返回了不安全的地址。`);
  }
  return parsed.toString();
}
