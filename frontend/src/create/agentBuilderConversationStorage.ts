import type { Block } from "../blocks";
import type { AgentBuilderChatMessage } from "./AgentBuilderChatPanel";

const STORAGE_VERSION = 1;
const MAX_STORED_MESSAGES = 100;
const MAX_STORED_TEXT_LENGTH = 20_000;

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface StoredAgentBuilderConversation {
  messages: AgentBuilderChatMessage[];
  conversationId?: string;
  expiresAt?: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function redactSensitiveText(value: string): string {
  return value
    .slice(0, MAX_STORED_TEXT_LENGTH)
    .replace(/\bBearer\s+[^\s,;]+/gi, "Bearer [已脱敏]")
    .replace(/\bAKLT[A-Za-z0-9_-]{6,}\b/g, "[已脱敏]")
    .replace(
      /((?:access[_-]?key(?:[_-]?id)?|secret(?:[_-]?(?:access)?[_-]?key)?|session[_-]?token|security[_-]?token|client[_-]?secret|api[_-]?key|authorization|cookie|[a-z0-9_-]*(?:password|secret|token)|credential|ak|sk)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&]+)/gi,
      "$1[已脱敏]",
    );
}

function sanitizeBlock(value: unknown): Block | null {
  if (!isRecord(value) || typeof value.kind !== "string") return null;
  switch (value.kind) {
    case "text":
    case "progress":
      return typeof value.text === "string"
        ? { kind: value.kind, text: redactSensitiveText(value.text) }
        : null;
    case "thinking":
      return typeof value.text === "string"
        ? {
            kind: "thinking",
            text: redactSensitiveText(value.text),
            done: value.done === true,
          }
        : null;
    case "tool":
      return typeof value.name === "string"
        ? {
            kind: "tool",
            name: redactSensitiveText(value.name),
            done: value.done === true,
          }
        : null;
    case "agent-transfer":
      return typeof value.agentName === "string"
        ? {
            kind: "agent-transfer",
            agentName: redactSensitiveText(value.agentName),
            done: value.done === true,
          }
        : null;
    default:
      return null;
  }
}

function sanitizeMessage(value: unknown): AgentBuilderChatMessage | null {
  if (
    !isRecord(value) ||
    typeof value.id !== "string" ||
    (value.role !== "user" && value.role !== "assistant")
  ) {
    return null;
  }
  const blocks = Array.isArray(value.blocks)
    ? value.blocks.flatMap((block) => {
        const sanitized = sanitizeBlock(block);
        return sanitized ? [sanitized] : [];
      })
    : undefined;
  return {
    id: value.id,
    role: value.role,
    text:
      typeof value.text === "string"
        ? redactSensitiveText(value.text)
        : undefined,
    blocks,
    streaming: false,
    error:
      typeof value.error === "string"
        ? redactSensitiveText(value.error)
        : undefined,
  };
}

export function loadAgentBuilderConversation(
  storage: StorageLike,
  key: string,
  nowSeconds = Date.now() / 1000,
): StoredAgentBuilderConversation {
  try {
    const raw = storage.getItem(key);
    if (!raw) return { messages: [] };
    const value = JSON.parse(raw) as unknown;
    if (!isRecord(value) || value.version !== STORAGE_VERSION) {
      return { messages: [] };
    }
    const messages = Array.isArray(value.messages)
      ? value.messages
          .slice(-MAX_STORED_MESSAGES)
          .flatMap((message) => {
            const sanitized = sanitizeMessage(message);
            return sanitized ? [sanitized] : [];
          })
      : [];
    const expiresAt =
      typeof value.expiresAt === "number" ? value.expiresAt : undefined;
    const conversationId =
      typeof value.conversationId === "string" &&
      expiresAt !== undefined &&
      expiresAt > nowSeconds
        ? value.conversationId
        : undefined;
    return {
      messages,
      conversationId,
      expiresAt: conversationId ? expiresAt : undefined,
    };
  } catch {
    return { messages: [] };
  }
}

export function writeAgentBuilderConversation(
  storage: StorageLike,
  key: string,
  value: StoredAgentBuilderConversation,
): void {
  const messages = value.messages
    .slice(-MAX_STORED_MESSAGES)
    .flatMap((message) => {
      const sanitized = sanitizeMessage(message);
      return sanitized ? [sanitized] : [];
    });
  try {
    storage.setItem(
      key,
      JSON.stringify({
        version: STORAGE_VERSION,
        messages,
        conversationId: value.conversationId,
        expiresAt: value.expiresAt,
      }),
    );
  } catch (error) {
    if (
      error instanceof DOMException &&
      (error.name === "QuotaExceededError" ||
        error.name === "NS_ERROR_DOM_QUOTA_REACHED")
    ) {
      throw new Error("浏览器存储空间不足，智能创建对话未保存。");
    }
    throw new Error("浏览器拒绝保存智能创建对话，请检查站点存储权限。");
  }
}
