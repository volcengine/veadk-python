import type { AdkEndpoint } from "./client";

export interface MpaRuntime { runtimeId: string; region: string; name: string }
export interface MpaCronTask {
  id: string;
  name: string;
  enabled: boolean;
  schedule: Record<string, unknown> & { type: string };
  nextRunAt?: string | null;
  lastRunStatus?: string | null;
}
export interface MpaCronTaskPage {
  items: MpaCronTask[]; total: number; hasMore: boolean; nextOffset: number | null;
}
type Request = (path: string, init: RequestInit, endpoint: AdkEndpoint) => Promise<Response>;

export async function fetchMpaCronTasks(
  request: Request, runtime: MpaRuntime, offset: number, jwt: string, signal?: AbortSignal,
): Promise<MpaCronTaskPage> {
  const response = await request(
    `/api/v1/esa-cron-tasks?includeDisabled=true&limit=20&offset=${offset}`,
    { headers: jwt.trim() ? { "X-Jwt-Token": jwt.trim() } : {}, signal }, runtime,
  );
  // Do not expose arbitrary upstream bodies, which may contain credentials.
  if (!response.ok) throw new Error(`MPA_HTTP_${response.status}`);
  let data;
  try { data = await response.json(); }
  catch { throw new Error("MPA_INVALID_RESPONSE"); }
  if (!data || !Array.isArray(data.items) || !Number.isInteger(data.total) || data.total < 0
    || typeof data.hasMore !== "boolean"
    || (data.hasMore && (!Number.isInteger(data.nextOffset) || data.nextOffset <= offset))
    || !data.items.every((item: MpaCronTask) => item && typeof item.id === "string"
      && typeof item.name === "string" && typeof item.enabled === "boolean"
      && item.schedule && typeof item.schedule.type === "string"
      && (item.nextRunAt == null || typeof item.nextRunAt === "string")
      && (item.lastRunStatus == null || typeof item.lastRunStatus === "string"))) {
    throw new Error("MPA_INVALID_RESPONSE");
  }
  return data;
}
