import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { withLocaleHeaders } from "./i18n";
import { requestSignal, DEFAULT_REQUEST_TIMEOUT_MS } from "./timeout";

export interface MpaCreationInput {
  requestId: string;
  name?: string;
  agentId?: string;
  description: string;
  maxInstance?: number;
  region: string;
  runtimeImage?: string;
  workerImage?: string;
  pgHost?: string;
  pgPort?: string;
  openvikingUrl?: string;
  openvikingResourceId?: string;
  openvikingMode?: "manual" | "auto";
  businessWorkspaceMode?: "shared" | "per-agent";
  businessDatabaseName?: "aidb";
  tosBucket?: string;
}
export interface MpaCreationRequest extends MpaCreationInput {
  openvikingApiKey?: string;
}
export interface MpaCreationTask
  extends MpaCreationInput {
  taskId: string;
  state: "running" | "cancelling" | "succeeded" | "failed" | "cancelled";
  stage: string;
  error?: string;
  latestDiagnostic?: {
    stage: string;
    operation: string;
    category: string;
    attempt: number;
    outcome: string;
    errorCode?: string;
    requestId?: string;
  };
  images?: { runtimeImage?: string; workerImage?: string };
  result?: {
    runtime_id?: string;
    skill_space_id?: string;
    gateway_id?: string;
  };
}
export interface MpaCreationConfig {
  configured: boolean;
  region: string;
  error?: string;
  runtimeImage?: string;
  workerImage?: string;
  pgHost?: string;
  pgPort?: string;
  postgresMode?: "auto";
  businessWorkspaceMode?: "per-agent";
  businessDatabaseName?: "aidb";
  openvikingMode?: "auto";
  postgresMigrationRequired?: boolean;
  postgresLayout?: "split-workspaces";
  adminWorkspaceName?: string;
  adminDatabaseName?: string;
}

export class MpaCreationRequestError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code?: string,
  ) {
    super(message);
    this.name = "MpaCreationRequestError";
  }
}

async function request<T>(
  path: string,
  signal: AbortSignal,
  body?: unknown,
): Promise<T> {
  const response = await fetch(withAuth(`/web/mpa-creation/${path}`), {
    method: body === undefined ? "GET" : "POST",
    headers: withLocaleHeaders(
      withLocalUser({ "Content-Type": "application/json" }),
    ),
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: requestSignal(signal, DEFAULT_REQUEST_TIMEOUT_MS),
  });
  if (!response.ok) {
    const value = await response.json().catch(() => ({}));
    throw new MpaCreationRequestError(
      response.status,
      typeof value.detail === "string"
        ? value.detail
        : `HTTP ${response.status}`,
      typeof value.detail?.code === "string" ? value.detail.code : undefined,
    );
  }
  return response.json() as Promise<T>;
}
export const getMpaCreationConfig = (region: string, signal: AbortSignal) =>
  request<MpaCreationConfig>(
    `config?region=${encodeURIComponent(region)}`,
    signal,
  );
export const startMpaCreation = (
  input: MpaCreationRequest,
  signal: AbortSignal,
) => request<MpaCreationTask>("tasks", signal, input);
export const listMpaCreations = (region: string, signal: AbortSignal) =>
  request<{ tasks: MpaCreationTask[] }>(
    `tasks?region=${encodeURIComponent(region)}`,
    signal,
  );
export const checkMpaCreationName = (
  input: Pick<MpaCreationInput, "requestId" | "name" | "agentId" | "region">,
  signal: AbortSignal,
) => request<{ available: boolean }>("name-check", signal, input);
export const getMpaCreation = (id: string, signal: AbortSignal) =>
  request<MpaCreationTask>(`tasks/${encodeURIComponent(id)}`, signal);
export const cancelMpaCreation = (id: string, signal: AbortSignal) =>
  request<MpaCreationTask>(
    `tasks/${encodeURIComponent(id)}/cancel`,
    signal,
    {},
  );
