import type { AdkEndpoint } from "./client";

export interface MpaRuntime {
  runtimeId: string;
  region: string;
  name: string;
}
export interface MpaCronTask {
  id: string;
  name: string;
  enabled: boolean;
  schedule: Record<string, unknown> & { type: string };
  prompt?: string;
  agentId?: string;
  version?: number;
  delivery?: Record<string, unknown>;
  jitterSeconds?: number;
  timeoutSeconds?: number;
  lastRunAt?: string | null;
  runningAt?: string | null;
  createdAt?: string;
  nextRunAt?: string | null;
  lastRunStatus?: string | null;
}
export interface MpaCronTaskPage {
  overview?: { executionCount: number; successRate: number };
  items: MpaCronTask[];
  total: number;
  hasMore: boolean;
  nextOffset: number | null;
}
type Request = (
  path: string,
  init: RequestInit,
  endpoint: AdkEndpoint,
) => Promise<Response>;

function validSchedule(schedule: Record<string, unknown>): boolean {
  if (schedule.timezone != null) {
    if (typeof schedule.timezone !== "string") return false;
    try {
      new Intl.DateTimeFormat("en-US", { timeZone: schedule.timezone });
    } catch {
      return false;
    }
  }
  if (
    schedule.runAt != null &&
    (typeof schedule.runAt !== "string" ||
      !Number.isFinite(Date.parse(schedule.runAt)))
  )
    return false;
  return [schedule.weekdays, schedule.monthDays].every(
    (days) =>
      days == null || (Array.isArray(days) && days.every(Number.isInteger)),
  );
}

export async function fetchMpaCronTasks(
  request: Request,
  runtime: MpaRuntime,
  offset: number,
  query: string,
  signal?: AbortSignal,
): Promise<MpaCronTaskPage> {
  const response = await request(
    `/web/mpa-cron/${encodeURIComponent(runtime.runtimeId)}?region=${encodeURIComponent(runtime.region)}&offset=${offset}&query=${encodeURIComponent(query)}`,
    { signal },
    {},
  );
  // Do not expose arbitrary upstream bodies, which may contain credentials.
  if (!response.ok) throw new Error(`MPA_HTTP_${response.status}`);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("MPA_INVALID_RESPONSE");
  }
  if (
    !data ||
    !Array.isArray(data.items) ||
    !Number.isInteger(data.total) ||
    data.total < 0 ||
    typeof data.hasMore !== "boolean" ||
    (data.hasMore &&
      (!Number.isInteger(data.nextOffset) || data.nextOffset <= offset)) ||
    (data.overview != null &&
      (!Number.isFinite(data.overview.executionCount) ||
        !Number.isFinite(data.overview.successRate))) ||
    !data.items.every(
      (item: MpaCronTask) =>
        item &&
        typeof item.id === "string" &&
        typeof item.name === "string" &&
        typeof item.enabled === "boolean" &&
        (item.prompt == null || typeof item.prompt === "string") &&
        item.schedule &&
        typeof item.schedule.type === "string" &&
        validSchedule(item.schedule) &&
        [item.agentId, item.lastRunAt, item.runningAt, item.createdAt].every(
          (value) => value == null || typeof value === "string",
        ) &&
        (item.nextRunAt == null || typeof item.nextRunAt === "string") &&
        (item.lastRunStatus == null || typeof item.lastRunStatus === "string"),
    )
  ) {
    throw new Error("MPA_INVALID_RESPONSE");
  }
  return data;
}

export interface MpaRun {
  id: string;
  status: string;
  startedAt?: string | null;
  scheduledAt: string;
  durationMs?: number | null;
  errorMessage?: string | null;
  sessionId?: string | null;
}
export interface MpaRunPage {
  items: MpaRun[];
  total: number;
  hasMore: boolean;
  nextOffset: number | null;
}
export type TaskFields = Pick<MpaCronTask, "name" | "schedule" | "enabled"> & {
  agentId?: string;
  prompt: string;
  delivery?: Record<string, unknown>;
  jitterSeconds?: number;
  timeoutSeconds?: number;
};
export async function manageMpaTask(
  request: Request,
  runtime: MpaRuntime,
  method: string,
  suffix: string,
  payload?: unknown,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const response = await request(
    `/web/mpa-cron/${encodeURIComponent(runtime.runtimeId)}${suffix}?region=${encodeURIComponent(runtime.region)}`,
    {
      method,
      signal,
      ...(payload === undefined
        ? {}
        : {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          }),
    },
    {},
  );
  if (!response.ok) throw new Error(`MPA_HTTP_${response.status}`);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("MPA_INVALID_RESPONSE");
  }
  if (!data || typeof data !== "object" || Array.isArray(data))
    throw new Error("MPA_INVALID_RESPONSE");
  return data;
}

export async function fetchMpaRuns(
  request: Request,
  runtime: MpaRuntime,
  taskId: string,
  offset: number,
  signal?: AbortSignal,
): Promise<MpaRunPage> {
  const response = await request(
    `/web/mpa-cron/${encodeURIComponent(runtime.runtimeId)}/${encodeURIComponent(taskId)}/runs?region=${encodeURIComponent(runtime.region)}&offset=${offset}`,
    { signal },
    {},
  );
  if (!response.ok) throw new Error(`MPA_HTTP_${response.status}`);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("MPA_INVALID_RESPONSE");
  }
  if (
    !data ||
    !Array.isArray(data.items) ||
    !Number.isInteger(data.total) ||
    data.total < 0 ||
    typeof data.hasMore !== "boolean" ||
    (data.hasMore &&
      (!Number.isInteger(data.nextOffset) || data.nextOffset <= offset)) ||
    !data.items.every(
      (run: MpaRun) =>
        run &&
        typeof run.id === "string" &&
        typeof run.status === "string" &&
        typeof run.scheduledAt === "string" &&
        [run.startedAt, run.errorMessage, run.sessionId].every(
          (value) => value == null || typeof value === "string",
        ) &&
        (run.durationMs == null ||
          (Number.isFinite(run.durationMs) && run.durationMs >= 0)),
    )
  )
    throw new Error("MPA_INVALID_RESPONSE");
  return data;
}
