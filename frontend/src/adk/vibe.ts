import { withAuth } from "./auth";
import { withLocalUser } from "./identity";

export type VibeTaskState =
  | "provisioning"
  | "ready"
  | "running"
  | "completed"
  | "partial"
  | "blocked"
  | "failed"
  | "cancelled"
  | "expired";

export interface VibeArtifactInfo {
  revision: number;
  sha256: string;
  size: number;
  filename: string;
}

export interface VibeTask {
  taskId: string;
  displayName: string;
  goal: string;
  state: VibeTaskState;
  stage: string;
  createdAt: string;
  expiresAt: string;
  attempt: number;
  lastSequence: number;
  credentialsConfigured: boolean;
  intentRevision: number;
  sandboxSessionId: string;
  validationRuntimeId: string;
  validationRuntimeStatus: string;
  artifact: VibeArtifactInfo | null;
  warnings: string[];
  error: string;
}

export interface VibeCapabilities {
  enabled: boolean;
  reason?: string;
  sandboxTtlSeconds: number;
  maxCloudAttempts: number;
  intentSummaryPath: string;
  evaluationEnabled: boolean;
  stateSource: string;
}

export interface VibeIntentSummary {
  revision: number;
  goal: string;
  confirmedRequirements: string[];
  constraints: string[];
  assumptions: string[];
  openQuestions: string[];
  successCriteria: string[];
  architectureSummary: Record<string, unknown>;
  currentStatus: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  updatedAt: string;
}

export interface VibeTaskEvent {
  sequence: number;
  eventType: string;
  stage: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

const TERMINAL_STATES = new Set<VibeTaskState>([
  "completed",
  "partial",
  "blocked",
  "failed",
  "cancelled",
  "expired",
]);

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(withAuth(path), {
    ...init,
    headers: withLocalUser(init.headers),
  });
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const value = (await response.json()) as { detail?: unknown };
    if (typeof value.detail === "string") return value.detail;
    if (value.detail && typeof value.detail === "object") {
      const message = (value.detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
  } catch {
    // Fall back to the HTTP metadata for non-JSON responses.
  }
  const contentType = response.headers.get("content-type") || "unknown content type";
  return `${response.statusText || `HTTP ${response.status}`} (${contentType})`;
}

async function checked<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await errorDetail(response));
  return (await response.json()) as T;
}

function jsonHeaders(): HeadersInit {
  return { "Content-Type": "application/json", Accept: "application/json" };
}

export const vibeClient = {
  async capabilities(signal?: AbortSignal): Promise<VibeCapabilities> {
    return checked(await apiFetch("/web/vibe/capabilities", { signal }));
  },

  async create(goal: string, requestId = crypto.randomUUID()): Promise<VibeTask> {
    return checked(
      await apiFetch("/web/vibe/tasks", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ goal, requestId }),
      }),
    );
  },

  async list(signal?: AbortSignal): Promise<VibeTask[]> {
    const payload = await checked<{ tasks: VibeTask[] }>(
      await apiFetch("/web/vibe/tasks", { signal }),
    );
    return payload.tasks;
  },

  async get(taskId: string, signal?: AbortSignal): Promise<VibeTask> {
    return checked(
      await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}`, { signal }),
    );
  },

  async credentials(
    taskId: string,
    accessKeyId: string,
    secretAccessKey: string,
    sessionToken = "",
    commandId = crypto.randomUUID(),
  ): Promise<VibeTask> {
    return checked(
      await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}/credentials`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          commandId,
          accessKeyId,
          secretAccessKey,
          ...(sessionToken ? { sessionToken } : {}),
        }),
      }),
    );
  },

  async intent(taskId: string, signal?: AbortSignal): Promise<VibeIntentSummary> {
    return checked(
      await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}/intent-summary`, {
        signal,
      }),
    );
  },

  async updateIntent(
    taskId: string,
    summary: VibeIntentSummary,
    expectedRevision = summary.revision,
    commandId = crypto.randomUUID(),
  ): Promise<VibeIntentSummary> {
    return checked(
      await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}/intent-summary`, {
        method: "PUT",
        headers: jsonHeaders(),
        body: JSON.stringify({ commandId, expectedRevision, summary }),
      }),
    );
  },

  async stop(
    taskId: string,
    reason = "",
    commandId = crypto.randomUUID(),
  ): Promise<VibeTask> {
    return checked(
      await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}/stop`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ commandId, reason }),
      }),
    );
  },

  async remove(taskId: string): Promise<void> {
    const response = await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(await errorDetail(response));
  },
};

function parseFrame(frame: string): VibeTaskEvent | null {
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (data.length === 0) return null;
  try {
    const value = JSON.parse(data.join("\n")) as VibeTaskEvent;
    return typeof value.sequence === "number" && typeof value.eventType === "string"
      ? value
      : null;
  } catch {
    return null;
  }
}

export function consumeVibeSse(
  chunk: string,
  remainder = "",
): { events: VibeTaskEvent[]; remainder: string } {
  const normalized = (remainder + chunk).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const frames = normalized.split("\n\n");
  const nextRemainder = frames.pop() ?? "";
  return {
    events: frames.map(parseFrame).filter((event): event is VibeTaskEvent => event !== null),
    remainder: nextRemainder,
  };
}

export function parseVibeSse(text: string): VibeTaskEvent[] {
  const parsed = consumeVibeSse(`${text}\n\n`);
  return parsed.events;
}

function reconnectDelay(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, 750);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

export async function* streamVibeEvents(
  taskId: string,
  options: { after?: number; signal: AbortSignal },
): AsyncGenerator<VibeTaskEvent> {
  let lastSequence = Math.max(0, options.after ?? 0);
  while (!options.signal.aborted) {
    const response = await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}/events`, {
      headers: { Accept: "text/event-stream", "Last-Event-ID": String(lastSequence) },
      signal: options.signal,
    });
    if (!response.ok) throw new Error(await errorDetail(response));
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.toLowerCase().includes("text/event-stream")) {
      throw new Error(`事件流返回了非 SSE 响应（${contentType || "Content-Type 缺失"}）`);
    }
    if (!response.body) throw new Error("事件流响应没有可读取的内容。");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let remainder = "";
    try {
      while (!options.signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;
        const parsed = consumeVibeSse(decoder.decode(value, { stream: true }), remainder);
        remainder = parsed.remainder;
        for (const event of parsed.events) {
          if (event.sequence <= lastSequence) continue;
          lastSequence = event.sequence;
          yield event;
        }
      }
    } finally {
      reader.releaseLock();
    }

    const status = await vibeClient.get(taskId, options.signal);
    if (TERMINAL_STATES.has(status.state)) return;
    await reconnectDelay(options.signal);
  }
}
