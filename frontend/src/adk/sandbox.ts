import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { requestSignal } from "./timeout";
import type { Block } from "../blocks";

const SANDBOX_API = "/web/sandbox/sessions";
const LIST_TIMEOUT_MS = 30_000;
const START_TIMEOUT_MS = 330_000;
const CONNECT_TIMEOUT_MS = 60_000;
const MESSAGE_TIMEOUT_MS = 600_000;
const CLOSE_TIMEOUT_MS = 15_000;
const SETTINGS_TIMEOUT_MS = 60_000;
const UPLOAD_TIMEOUT_MS = 330_000;

export const SANDBOX_DISPLAY_NAME_MAX_LENGTH = 40;

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

export interface SandboxUploadedFile {
  id: string;
  path: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
}

export interface SandboxRequestOptions {
  signal?: AbortSignal;
  onBlocks?: (blocks: Block[]) => void;
  onApproval?: (approval: SandboxApproval) => void;
  onApprovalResolved?: (approvalId: string) => void;
}

export interface SandboxStartOptions extends SandboxRequestOptions {
  displayName?: string;
}

export interface SandboxSession {
  id: string;
  toolName: "codex";
  userSessionId: string;
  displayName: string;
  status: string;
  createdAt: string;
  expireAt: string;
  toolType: string;
  region: string;
  threadId: string;
  cwd: string;
  workspaceLocked: boolean;
  busy: boolean;
  permissions: SandboxPermissions;
}

export interface SandboxMessage {
  sessionId: string;
  text: string;
}

export interface SandboxReply {
  text: string;
  blocks: Block[];
}

export interface AgentKitSandboxClient {
  listSessions(options?: SandboxRequestOptions): Promise<SandboxSession[]>;
  startSession(options?: SandboxStartOptions): Promise<SandboxSession>;
  connectSession(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<SandboxSession>;
  sendMessage(
    message: SandboxMessage,
    options?: SandboxRequestOptions,
  ): Promise<SandboxReply>;
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
}

export interface SandboxSessionSettings {
  threadId: string;
  cwd: string;
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
  toolType?: string;
  region?: string;
  threadId?: string;
  cwd?: string;
  workspaceLocked?: boolean;
  busy?: boolean;
  permissions?: unknown;
}

interface ListSessionsResponse {
  sessions?: SessionResponse[];
}

interface SandboxErrorPayload {
  detail?: unknown;
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
}

function sandboxHeaders(headers?: HeadersInit): Headers {
  const next = withLocalUser(headers);
  if (!next.has("Accept")) next.set("Accept", "application/json");
  return next;
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  let payload: SandboxErrorPayload = {};
  try {
    payload = (await response.json()) as SandboxErrorPayload;
  } catch {
    return new Error(`${fallback}（HTTP ${response.status}）`);
  }
  const nestedDetail = payload.detail;
  const detail =
    nestedDetail && typeof nestedDetail === "object" && "message" in nestedDetail
      ? (nestedDetail as SandboxErrorPayload).message
      : (nestedDetail ?? payload.message);
  return new Error(typeof detail === "string" && detail ? detail : fallback);
}

function parseSession(data: SessionResponse): SandboxSession {
  if (!data.sessionId || !data.status) {
    throw new Error("AgentKit 沙箱返回了无效的 Session 信息。");
  }
  return {
    id: data.sessionId,
    toolName: "codex",
    userSessionId: data.userSessionId ?? "",
    displayName: data.displayName ?? "",
    status: data.status,
    createdAt: data.createdAt ?? "",
    expireAt: data.expireAt ?? "",
    toolType: data.toolType ?? "",
    region: data.region ?? "",
    threadId: data.threadId ?? "",
    cwd: data.cwd ?? "",
    workspaceLocked: data.workspaceLocked === true,
    busy: data.busy === true,
    permissions: parsePermissions(data.permissions),
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
    workspaceLocked: data.workspaceLocked === true,
    busy: data.busy === true,
    permissions: parsePermissions(data.permissions),
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
  return { text: reply, blocks };
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
    return data.sessions.map(parseSession);
  },

  async startSession(options = {}) {
    const response = await fetch(withAuth(SANDBOX_API), {
      method: "POST",
      headers: sandboxHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ displayName: options.displayName?.trim() ?? "" }),
      signal: requestSignal(options.signal, START_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw await responseError(response, "无法启动 AgentKit 沙箱，请稍后重试。");
    }
    return parseSession((await response.json()) as SessionResponse);
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
        body: JSON.stringify({ message: message.text }),
        signal: requestSignal(options.signal, MESSAGE_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw await responseError(response, "沙箱对话失败，请稍后重试。");
    }
    return parseSandboxStream(response, options);
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
      withAuth(`${SANDBOX_API}/${encodeURIComponent(sessionId)}`),
      {
        method: "DELETE",
        headers: sandboxHeaders(),
        signal: requestSignal(options.signal, CLOSE_TIMEOUT_MS),
      },
    );
    if (!response.ok && response.status !== 404) {
      throw await responseError(response, "无法断开 Codex 智能体连接。");
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
  if (typeof value.url !== "string" || !value.url.startsWith("/")) {
    throw new Error("Sandbox 工具返回了无效地址。");
  }
  return {
    url: withAuth(value.url),
    ...(typeof value.shellSessionId === "string"
      ? { shellSessionId: value.shellSessionId }
      : {}),
  };
}
