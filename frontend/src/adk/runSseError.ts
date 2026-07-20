const SESSION_NOT_FOUND_PATTERN = /\brun_sse\s*failed\s*:\s*404\b/i;

const PERSISTENT_MEMORY_HINT =
  "提示：该 404 可能是多实例部署使用 in-memory 或 SQLite 短期记忆导致的：" +
  "请求落到不同实例后，会话无法找到。请改用基于数据库的持久化短期记忆存储。";

/** Preserve a run error and append guidance for the common cross-instance 404. */
export function formatRunSseError(error: unknown): string {
  const message = String(error);
  if (!SESSION_NOT_FOUND_PATTERN.test(message) || message.includes(PERSISTENT_MEMORY_HINT)) {
    return message;
  }
  return `${message}\n\n${PERSISTENT_MEMORY_HINT}`;
}
