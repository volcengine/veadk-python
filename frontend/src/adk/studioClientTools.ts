const STUDIO_CLIENT_TOOL_NAMES = [
  "ppt_generate",
  "image_generate",
  "image_edit",
  "video_generate",
  "video_task_query",
] as const;

const EXECUTION_TIMEOUT_MS = 21 * 60 * 1_000;
const CAPABILITY_TIMEOUT_MS = 5_000;

interface ClientToolDownload {
  filename: string;
  mimeType: string;
  data: string;
}

interface ClientToolExecutionResponse {
  result: unknown;
  downloads: ClientToolDownload[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseStudioClientToolCapabilities(value: unknown): boolean {
  if (!isRecord(value) || !Array.isArray(value.tools)) return false;
  const available = new Set(value.tools.filter((name): name is string => typeof name === "string"));
  return STUDIO_CLIENT_TOOL_NAMES.every((name) => available.has(name));
}

function parseDownload(value: unknown): ClientToolDownload | null {
  if (!isRecord(value)) return null;
  const { filename, mimeType, data } = value;
  if (
    typeof filename !== "string" ||
    typeof mimeType !== "string" ||
    typeof data !== "string"
  ) return null;
  return { filename, mimeType, data };
}

export function parseStudioClientToolExecution(
  value: unknown,
): ClientToolExecutionResponse | null {
  if (!isRecord(value) || !("result" in value)) return null;
  if (value.downloads !== undefined && !Array.isArray(value.downloads)) return null;
  const downloads = (value.downloads ?? []).map(parseDownload);
  if (downloads.some((download) => download === null)) return null;
  return {
    result: value.result,
    downloads: downloads as ClientToolDownload[],
  };
}

export function sanitizeDownloadFilename(filename: string): string {
  const basename = filename.replace(/\\/g, "/").split("/").pop()?.trim();
  return basename || "download";
}

function triggerDownload(download: ClientToolDownload): void {
  const binary = atob(download.data);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: download.mimeType }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = sanitizeDownloadFilename(download.filename);
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(url);
  }
}

async function responseError(response: Response): Promise<Error> {
  let detail = "";
  try {
    const value = await response.json();
    if (isRecord(value) && typeof value.detail === "string") detail = value.detail;
  } catch {
    // The status code remains actionable when the response is not JSON.
  }
  return new Error(
    `Studio 客户端工具请求失败（HTTP ${response.status}）${detail ? `：${detail}` : ""}`,
  );
}

export async function probeStudioClientTools(): Promise<boolean> {
  try {
    const response = await fetch("/web/client-tools/capabilities", {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(CAPABILITY_TIMEOUT_MS),
    });
    return response.ok && parseStudioClientToolCapabilities(await response.json());
  } catch {
    return false;
  }
}

export async function executeStudioClientTool(
  name: string,
  args: Record<string, unknown>,
): Promise<unknown> {
  const response = await fetch("/web/client-tools/execute", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name, arguments: args }),
    signal: AbortSignal.timeout(EXECUTION_TIMEOUT_MS),
  });
  if (!response.ok) throw await responseError(response);
  const execution = parseStudioClientToolExecution(await response.json());
  if (!execution) throw new Error("Studio 客户端工具返回了无效响应");
  execution.downloads.forEach(triggerDownload);
  return execution.result;
}
