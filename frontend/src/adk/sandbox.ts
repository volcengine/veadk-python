import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { requestSignal } from "./timeout";
import type { Block } from "../blocks";

const SANDBOX_API = "/web/sandbox/sessions";
const START_TIMEOUT_MS = 330_000;
const MESSAGE_TIMEOUT_MS = 600_000;
const CLOSE_TIMEOUT_MS = 15_000;

export interface SandboxRequestOptions {
  signal?: AbortSignal;
  onBlocks?: (blocks: Block[]) => void;
}

export interface SandboxSession {
  id: string;
  toolName: "codex";
  createdAt: string;
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
  startSession(options?: SandboxRequestOptions): Promise<SandboxSession>;
  sendMessage(
    message: SandboxMessage,
    options?: SandboxRequestOptions,
  ): Promise<SandboxReply>;
  closeSession(
    sessionId: string,
    options?: SandboxRequestOptions,
  ): Promise<void>;
}

interface CreateSessionResponse {
  sessionId: string;
  status: string;
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
}

function sandboxHeaders(headers?: HeadersInit): Headers {
  const next = withLocalUser(headers);
  next.set("Accept", "application/json");
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

async function parseSandboxStream(
  response: Response,
  onBlocks?: (blocks: Block[]) => void,
): Promise<SandboxReply> {
  if (!response.body) throw new Error("沙箱对话服务未返回内容。");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let reply = "";
  const blocks: Block[] = [];
  const activityIndexes = new Map<string, number>();

  function emitBlocks(): void {
    onBlocks?.(blocks.map((block) => ({ ...block })));
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
  async startSession(options = {}) {
    const response = await fetch(withAuth(SANDBOX_API), {
      method: "POST",
      headers: sandboxHeaders({ "Content-Type": "application/json" }),
      signal: requestSignal(options.signal, START_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw await responseError(response, "无法启动 AgentKit 沙箱，请稍后重试。");
    }
    const data = (await response.json()) as CreateSessionResponse;
    if (!data.sessionId || data.status !== "ready") {
      throw new Error("AgentKit 沙箱返回了无效的会话信息。");
    }
    return {
      id: data.sessionId,
      toolName: "codex",
      createdAt: new Date().toISOString(),
    };
  },

  async sendMessage(message, options = {}) {
    if (!message.sessionId || !message.text.trim()) {
      throw new Error("临时会话缺少有效的消息内容。");
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
    return parseSandboxStream(response, options.onBlocks);
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
      throw await responseError(response, "无法清理 AgentKit 沙箱会话。");
    }
  },
};
