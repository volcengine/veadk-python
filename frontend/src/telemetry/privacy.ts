import type {
  ErrorKind,
  StudioTelemetryEventName,
  TelemetryPayload,
  TelemetryValue,
} from "./schema";

export interface ClassifiedTelemetryError {
  errorKind: ErrorKind;
  errorCode?: string;
}

export interface TelemetryErrorContext {
  phase?: string;
}

interface ErrorShape {
  code?: unknown;
  name?: unknown;
  status?: unknown;
}

function stableErrorCode(value: unknown): string | undefined {
  if (typeof value !== "string" && typeof value !== "number") return undefined;
  const code = String(value).trim();
  return /^[A-Za-z0-9_.:-]{1,64}$/.test(code) ? code : undefined;
}

function classifiedTelemetryError(
  errorKind: ErrorKind,
  errorCode?: string,
): ClassifiedTelemetryError {
  return errorCode === undefined ? { errorKind } : { errorKind, errorCode };
}

/** Converts an unknown failure to an approved category without reading its text. */
export function classifyTelemetryError(
  error: unknown,
  context: TelemetryErrorContext = {},
): ClassifiedTelemetryError {
  const shape = error !== null && typeof error === "object"
    ? error as ErrorShape
    : {};
  const declaredErrorCode = stableErrorCode(shape.code);
  const name = typeof shape.name === "string" ? shape.name : "";
  if (name === "RuntimeProbeError") {
    return classifiedTelemetryError("runtime_probe_error", declaredErrorCode);
  }
  if (name === "AbortError") {
    return classifiedTelemetryError("abort", declaredErrorCode);
  }
  if (name === "RuntimeAccessDeniedError" || name === "AuthError") {
    return classifiedTelemetryError("auth", declaredErrorCode);
  }
  if (context.phase === "build") {
    return classifiedTelemetryError("build_failed", declaredErrorCode);
  }
  if (name === "TimeoutError") {
    return classifiedTelemetryError("timeout", declaredErrorCode);
  }
  if (name === "NetworkError" || name === "TypeError") {
    return classifiedTelemetryError("network", declaredErrorCode);
  }
  if (name === "ValidationError") {
    return classifiedTelemetryError("validation", declaredErrorCode);
  }
  if (name === "ServerError") {
    return classifiedTelemetryError("server", declaredErrorCode);
  }

  const status = typeof shape.status === "number" && Number.isInteger(shape.status)
    ? shape.status
    : undefined;
  if (status === undefined || status < 400 || status > 599) {
    return classifiedTelemetryError("unknown", declaredErrorCode);
  }
  const errorCode = String(status);
  if (status === 401 || status === 403) return { errorKind: "auth", errorCode };
  if (status === 400 || status === 409 || status === 422) {
    return { errorKind: "validation", errorCode };
  }
  if (status >= 500) return { errorKind: "server", errorCode };
  return { errorKind: "unknown", errorCode };
}

const COMMON_KEYS = [
  "schema_version",
  "event_id",
  "operation_id",
  "user_pool_id",
  "studio_deploy_id",
  "vefaas_application_id",
  "vefaas_function_id",
  "studio_region",
  "studio_project",
  "studio_version",
  "environment",
  "cloud_provider",
  "account_id",
  "user_role",
  "user_source",
  "page_instance_id",
] as const;

const EVENT_KEYS: Record<StudioTelemetryEventName, readonly string[]> = {
  studio_entry_viewed: ["auth_state"],
  studio_session_started: ["agents_source"],
  studio_agent_deploy: [
    "status",
    "agent_id",
    "deploy_action",
    "deploy_source",
    "create_mode",
    "ai_assisted",
    "deploy_region",
    "runtime_network_type",
    "feishu_enabled",
    "runtime_id",
    "duration_ms",
    "failed_phase",
    "error_kind",
    "error_code",
  ],
  studio_sandbox_create: [
    "status",
    "sandbox_kind",
    "sandbox_source",
    "sandbox_id",
    "duration_ms",
    "error_kind",
    "error_code",
  ],
  studio_agent_debug: [
    "status",
    "agent_id",
    "variant_type",
    "debug_run_id",
    "duration_ms",
    "failed_phase",
    "error_kind",
    "error_code",
  ],
  studio_agent_connect: [
    "status",
    "target_id",
    "agent_kind",
    "connect_source",
    "runtime_region",
    "runtime_is_mine",
    "sandbox_status",
    "duration_ms",
    "error_kind",
    "error_code",
  ],
  studio_agent_message: [
    "status",
    "agent_id",
    "agent_kind",
    "message_source",
    "session_state",
    "session_id",
    "duration_ms",
    "failed_phase",
    "error_kind",
    "error_code",
  ],
  studio_agent_source_download: [
    "status",
    "agent_id",
    "deploy_action",
    "deploy_source",
    "create_mode",
    "ai_assisted",
    "duration_ms",
    "file_count",
    "zip_size_bytes",
    "error_kind",
    "error_code",
  ],
};

function isTelemetryValue(value: unknown): value is TelemetryValue {
  return (
    typeof value === "string" ||
    (typeof value === "number" && Number.isFinite(value))
  );
}

export function sanitizeTelemetryPayload(
  name: StudioTelemetryEventName,
  input: Record<string, unknown>,
): TelemetryPayload {
  const allowed = new Set<string>([...COMMON_KEYS, ...EVENT_KEYS[name]]);
  const payload: TelemetryPayload = {};
  for (const [key, value] of Object.entries(input)) {
    if (!allowed.has(key) || !isTelemetryValue(value)) continue;
    payload[key] = typeof value === "string" ? value.slice(0, 256) : value;
  }
  return payload;
}
