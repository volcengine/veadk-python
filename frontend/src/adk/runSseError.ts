const SESSION_NOT_FOUND_PATTERN = /\brun_sse\s*failed\s*:\s*404\b/i;
const SESSION_DETAIL_PATTERN = /session not found/i;
const ROUTE_NOT_FOUND_PATTERN = /(?:^|[：:\s])not found\s*$/i;
const TOOL_ARGUMENT_JSON_PATTERN =
  /Expecting (?:'[^']+'|\w+)(?: delimiter)?: line \d+ column \d+ \(char \d+\)/i;

const PERSISTENT_MEMORY_HINT =
  "提示：会话已不存在。使用 in-memory 或 SQLite 短期记忆时，多实例、进程重启或滚动发布都可能导致会话丢失；建议改用基于数据库的持久化短期记忆存储。";
const UNSUPPORTED_ROUTE_HINT =
  "提示：该 Runtime 未提供会话能力运行接口，可能是 Runtime 版本与当前 Studio 不兼容。";
const TOOL_ARGUMENT_JSON_HINT =
  "提示：模型生成的工具参数格式不完整，请重新发送一次。";

/** Preserve the upstream error and add guidance only when its cause is known. */
export function formatRunSseError(error: unknown): string {
  const message = String(error);
  if (TOOL_ARGUMENT_JSON_PATTERN.test(message)) {
    return message.includes(TOOL_ARGUMENT_JSON_HINT)
      ? message
      : `${message}\n\n${TOOL_ARGUMENT_JSON_HINT}`;
  }
  if (!SESSION_NOT_FOUND_PATTERN.test(message)) {
    return message;
  }
  if (SESSION_DETAIL_PATTERN.test(message)) {
    return message.includes(PERSISTENT_MEMORY_HINT)
      ? message
      : `${message}\n\n${PERSISTENT_MEMORY_HINT}`;
  }
  if (ROUTE_NOT_FOUND_PATTERN.test(message)) {
    return message.includes(UNSUPPORTED_ROUTE_HINT)
      ? message
      : `${message}\n\n${UNSUPPORTED_ROUTE_HINT}`;
  }
  return message;
}
