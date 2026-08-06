export function parseJanusStatus(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  return (value as Record<string, unknown>).available === true;
}

export function parseJanusToolResult(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const result = (value as Record<string, unknown>).result;
  return typeof result === "string" ? result : null;
}

export function parseJanusToolError(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const error = (value as Record<string, unknown>).error;
  return typeof error === "string" && error.trim() ? error : null;
}

function requestJanus<T>(
  type: "janus-studio-status" | "janus-studio-tool",
  payload: Record<string, unknown>,
  parse: (value: unknown) => T,
  fallback: T,
  timeoutMs: number,
): Promise<T> {
  const requestId = crypto.randomUUID();
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value: T) => {
      if (settled) return;
      settled = true;
      window.removeEventListener("message", onMessage);
      window.clearTimeout(timer);
      resolve(value);
    };
    const onMessage = (event: MessageEvent) => {
      if (event.source !== window) return;
      const response = event.data as Record<string, unknown> | null;
      if (response?.type !== `${type}-ack` || response.requestId !== requestId) return;
      finish(parse(response));
    };
    const timer = window.setTimeout(() => finish(fallback), timeoutMs);
    window.addEventListener("message", onMessage);
    window.postMessage({ type, requestId, ...payload }, window.location.origin);
  });
}

export function probeJanusBrowserContext(timeoutMs = 800): Promise<boolean> {
  return requestJanus(
    "janus-studio-status",
    {},
    parseJanusStatus,
    false,
    timeoutMs,
  );
}

export function executeJanusBrowserTool(
  args: Record<string, unknown>,
  timeoutMs = 10_000,
): Promise<string> {
  return requestJanus(
    "janus-studio-tool",
    { args },
    (value) => ({
      result: parseJanusToolResult(value),
      error: parseJanusToolError(value),
    }),
    { result: null, error: "Janus 工具调用超时" },
    timeoutMs,
  ).then(({ result, error }) => {
    if (result === null) throw new Error(error || "Janus 工具调用失败");
    return result;
  });
}
