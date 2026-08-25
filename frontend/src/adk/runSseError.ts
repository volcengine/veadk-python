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
export const RUN_SSE_NETWORK_CONFIGURATION_HINT =
  "提示：请检查共享公网出口等网络配置，然后重试。";
const RAW_RESPONSE_LABEL = "原始响应：";

function appendHint(message: string, hint: string): string {
  return message.includes(hint) ? message : `${message}\n\n${hint}`;
}

/** Preserve the upstream error before appending diagnosis and recovery guidance. */
export function formatRunSseError(error: unknown): string {
  const message = String(error);
  let formatted = message.includes(RAW_RESPONSE_LABEL)
    ? message
    : `${RAW_RESPONSE_LABEL}${message}`;
  if (TOOL_ARGUMENT_JSON_PATTERN.test(message)) {
    formatted = appendHint(formatted, TOOL_ARGUMENT_JSON_HINT);
  } else if (SESSION_NOT_FOUND_PATTERN.test(message)) {
    if (SESSION_DETAIL_PATTERN.test(message)) {
      formatted = appendHint(formatted, PERSISTENT_MEMORY_HINT);
    } else if (ROUTE_NOT_FOUND_PATTERN.test(message)) {
      formatted = appendHint(formatted, UNSUPPORTED_ROUTE_HINT);
    }
  }
  return appendHint(formatted, RUN_SSE_NETWORK_CONFIGURATION_HINT);
}
