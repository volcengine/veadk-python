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
  message?: unknown;
  name?: unknown;
  status?: unknown;
}

interface TelemetryMessageOptions {
  preserveEnd?: boolean;
}

const DEFAULT_STRING_MAX_LENGTH = 256;
const ERROR_MESSAGE_MAX_LENGTH = 1024;
const REDACTED = "[REDACTED]";

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

function truncateTelemetryString(
  value: string,
  maxLength: number,
  options: TelemetryMessageOptions = {},
): string {
  if (value.length <= maxLength) return value;
  if (options.preserveEnd) {
    const prefix = "[truncated] ...";
    return `${prefix}${value.slice(-Math.max(0, maxLength - prefix.length))}`;
  }
  const suffix = "... [truncated]";
  return `${value.slice(0, Math.max(0, maxLength - suffix.length))}${suffix}`;
}

function redactTelemetryMessage(value: string): string {
  return value
    .replace(
      /\b(Authorization\s*[:=]\s*)(Bearer\s+)?[^\s"',;&]+/gi,
      (_match, prefix: string, bearer: string | undefined) =>
        `${prefix}${bearer ?? ""}${REDACTED}`,
    )
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, `Bearer ${REDACTED}`)
    .replace(
      /\b([\w.-]*(?:token|password|passwd|secret|api[_-]?key|access[_-]?key|secret[_-]?key|cookie)[\w.-]*\s*[:=]\s*)(["']?)[^\s"',;&]+/gi,
      (_match, prefix: string, quote: string) => `${prefix}${quote}${REDACTED}`,
    );
}

/** Returns a compact, redacted error message suitable for product telemetry. */
export function safeTelemetryErrorMessage(
  error: unknown,
  options: TelemetryMessageOptions = {},
): string | undefined {
  const shape = error !== null && typeof error === "object"
    ? error as ErrorShape
    : {};
  const raw = typeof shape.message === "string"
    ? shape.message
    : typeof error === "string" ||
        typeof error === "number" ||
        typeof error === "boolean"
    ? String(error)
    : "";
  const normalized = raw.replace(/\s+/g, " ").trim();
  if (!normalized) return undefined;
  return truncateTelemetryString(
    redactTelemetryMessage(normalized),
    ERROR_MESSAGE_MAX_LENGTH,
    options,
  );
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
  "account_id_resolution_error",
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
    "error_message",
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
    if (typeof value === "string") {
      payload[key] = truncateTelemetryString(
        value,
        key === "error_message"
          ? ERROR_MESSAGE_MAX_LENGTH
          : DEFAULT_STRING_MAX_LENGTH,
      );
    } else {
      payload[key] = value;
    }
  }
  return payload;
}
