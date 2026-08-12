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
  validationRuntimeId: string;
  validationRuntimeStatus: string;
  warnings: string[];
  error: string;
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
    // Fall back to the status text for non-JSON responses.
  }
  return response.statusText || `HTTP ${response.status}`;
}

async function checked<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await errorDetail(response));
  return (await response.json()) as T;
}

export const vibeClient = {
  async create(goal: string): Promise<VibeTask> {
    return checked(
      await apiFetch("/web/vibe/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      }),
    );
  },

  async list(): Promise<VibeTask[]> {
    const payload = await checked<{ tasks: VibeTask[] }>(
      await apiFetch("/web/vibe/tasks"),
    );
    return payload.tasks;
  },

  async get(taskId: string): Promise<VibeTask> {
    return checked(await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}`));
  },

  async credentials(
    taskId: string,
    accessKeyId: string,
    secretAccessKey: string,
  ): Promise<VibeTask> {
    return checked(
      await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}/credentials`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accessKeyId, secretAccessKey }),
      }),
    );
  },

  async intent(taskId: string): Promise<VibeIntentSummary> {
    return checked(
      await apiFetch(
        `/web/vibe/tasks/${encodeURIComponent(taskId)}/intent-summary`,
      ),
    );
  },

  async stop(taskId: string): Promise<VibeTask> {
    return checked(
      await apiFetch(`/web/vibe/tasks/${encodeURIComponent(taskId)}/stop`, {
        method: "POST",
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

export function parseVibeSse(text: string): VibeTaskEvent[] {
  const events: VibeTaskEvent[] = [];
  for (const frame of text.replace(/\r\n/g, "\n").split("\n\n")) {
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (!data) continue;
    try {
      const value = JSON.parse(data) as VibeTaskEvent;
      if (typeof value.sequence === "number" && value.eventType) events.push(value);
    } catch {
      // Ignore incomplete frames; reconnect uses the last valid sequence.
    }
  }
  return events;
}
