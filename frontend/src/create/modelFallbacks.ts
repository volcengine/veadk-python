import type { ModelFallbackDraft, ModelFallbackEndpointDraft } from "./types";

const ENV_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

function trimString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function isModelFallbackEndpoint(
  value: ModelFallbackDraft | unknown,
): value is ModelFallbackEndpointDraft {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    typeof (value as Partial<ModelFallbackEndpointDraft>).modelName === "string"
  );
}

export function modelFallbackName(value: ModelFallbackDraft): string {
  return typeof value === "string" ? value : value.modelName;
}

export function modelFallbackIsSameProvider(value: ModelFallbackDraft): boolean {
  return (
    typeof value === "string" ||
    (!value.modelProvider?.trim() &&
      !value.modelApiBase?.trim() &&
      !value.modelApiKeyEnv?.trim())
  );
}

export function defaultModelFallbackApiKeyEnv(
  agentName: string | null | undefined,
  index: number,
): string {
  const segment =
    (agentName ?? "")
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "") ||
    "AGENT";
  return `FALLBACK_MODEL_${segment}_${index + 1}_API_KEY`;
}

export function isValidModelFallbackApiKeyEnv(value: string): boolean {
  return ENV_NAME_RE.test(value);
}

export function nextModelFallbackApiKeyEnv(
  agentName: string | null | undefined,
  index: number,
  values: readonly unknown[] | null | undefined,
): string {
  const used = new Set(
    (values ?? [])
      .map((value) =>
        isModelFallbackEndpoint(value) ? value.modelApiKeyEnv?.trim() : "",
      )
      .filter((value): value is string => Boolean(value)),
  );
  const base = defaultModelFallbackApiKeyEnv(agentName, index);
  if (!used.has(base)) return base;
  let suffix = 2;
  while (used.has(`${base}_${suffix}`)) suffix += 1;
  return `${base}_${suffix}`;
}

export function modelFallbackApiKeyEnv(
  agentName: string | null | undefined,
  index: number,
  values: readonly unknown[] | null | undefined,
  endpoint: ModelFallbackEndpointDraft,
): string {
  const existing = endpoint.modelApiKeyEnv?.trim() ?? "";
  if (existing && isValidModelFallbackApiKeyEnv(existing)) return existing;
  return nextModelFallbackApiKeyEnv(agentName, index, values);
}

export function normalizeModelFallbacks(
  primaryModelName: string | null | undefined,
  values: readonly unknown[] | null | undefined,
): ModelFallbackDraft[] {
  const primary = (primaryModelName ?? "").trim();
  const seen = new Set<string>();
  if (primary) seen.add(`same:${primary}`);

  const fallbacks: ModelFallbackDraft[] = [];
  for (const rawValue of values ?? []) {
    const normalized = normalizeRawModelFallback(rawValue);
    if (!normalized) continue;
    const modelName = modelFallbackName(normalized).trim();
    const sameProvider = modelFallbackIsSameProvider(normalized);
    if (!modelName) continue;
    if (sameProvider && modelName === primary) continue;
    const key =
      typeof normalized === "string"
        ? `same:${modelName}`
        : [
            "endpoint",
            modelName,
            normalized.modelProvider?.trim() ?? "",
            normalized.modelApiBase?.trim() ?? "",
            normalized.modelApiKeyEnv?.trim() ?? "",
          ].join("\u0000");
    if (seen.has(key)) continue;
    seen.add(key);
    fallbacks.push(normalized);
  }
  return fallbacks;
}

function normalizeRawModelFallback(value: unknown): ModelFallbackDraft | null {
  if (typeof value === "string") {
    const modelName = value.trim();
    return modelName || null;
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const modelName = trimString(raw.modelName ?? raw.model_name ?? raw.model);
  if (!modelName) return null;
  const endpoint: ModelFallbackEndpointDraft = {
    modelName,
  };
  const modelProvider = trimString(
    raw.modelProvider ?? raw.model_provider ?? raw.provider,
  );
  const modelApiBase = trimString(
    raw.modelApiBase ??
      raw.model_api_base ??
      raw.apiBase ??
      raw.api_base ??
      raw.baseUrl ??
      raw.base_url,
  );
  const modelApiKeyEnv = trimString(
    raw.modelApiKeyEnv ?? raw.model_api_key_env ?? raw.apiKeyEnv ?? raw.api_key_env,
  );
  if (modelProvider) endpoint.modelProvider = modelProvider;
  if (modelApiBase) endpoint.modelApiBase = modelApiBase;
  if (modelApiKeyEnv && isValidModelFallbackApiKeyEnv(modelApiKeyEnv)) {
    endpoint.modelApiKeyEnv = modelApiKeyEnv;
  }
  return modelFallbackIsSameProvider(endpoint) ? modelName : endpoint;
}

export function sameProviderModelFallbacks(
  primaryModelName: string | null | undefined,
  values: readonly unknown[] | null | undefined,
): string[] {
  return normalizeModelFallbacks(primaryModelName, values).filter(
    (value): value is string => typeof value === "string",
  );
}

export function normalizeDraftModelNames(rawModelName: unknown, rawFallbacks: unknown) {
  const modelNames = Array.isArray(rawModelName) ? rawModelName : [rawModelName];
  const primaryModelName =
    typeof modelNames[0] === "string" ? modelNames[0].trim() : "";
  return {
    modelName: primaryModelName,
    modelFallbacks: normalizeModelFallbacks(primaryModelName, [
      ...modelNames.slice(1),
      ...(Array.isArray(rawFallbacks) ? rawFallbacks : []),
    ]),
  };
}
