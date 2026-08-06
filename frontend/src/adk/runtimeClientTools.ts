export const CLIENT_TOOLS_PROTOCOL_VERSION = 1;

const DEFAULT_CACHE_TTL_MS = 5 * 60 * 1000;
const DEFAULT_PROBE_TIMEOUT_MS = 5_000;

interface CachedSupport {
  value?: boolean;
  expiresAt?: number;
  promise?: Promise<boolean>;
}

export type RuntimeClientToolsFetcher = (
  url: string,
  init?: RequestInit,
) => Promise<Response>;

interface ProbeOptions {
  fetcher?: RuntimeClientToolsFetcher;
  force?: boolean;
  signal?: AbortSignal;
  timeoutMs?: number;
  cacheTtlMs?: number;
}

const supportCache = new Map<string, CachedSupport>();

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function declaresClientToolsProtocol(value: unknown): boolean {
  if (!isRecord(value) || !isRecord(value.protocols)) return false;
  const clientTools = value.protocols.client_tools;
  return (
    isRecord(clientTools) &&
    clientTools.version === CLIENT_TOOLS_PROTOCOL_VERSION
  );
}

function decodePointerToken(value: string): string {
  return value.replace(/~1/g, "/").replace(/~0/g, "~");
}

function resolveLocalRef(document: unknown, reference: string): unknown {
  if (!reference.startsWith("#/")) return null;
  return reference
    .slice(2)
    .split("/")
    .map(decodePointerToken)
    .reduce<unknown>((current, key) => {
      if (!isRecord(current)) return null;
      return current[key];
    }, document);
}

function resolveSchema(document: unknown, schema: unknown): unknown {
  let current = schema;
  const visited = new Set<string>();
  while (isRecord(current) && typeof current.$ref === "string") {
    if (visited.has(current.$ref)) return null;
    visited.add(current.$ref);
    current = resolveLocalRef(document, current.$ref);
  }
  return current;
}

function schemaHasClientTools(document: unknown, schema: unknown): boolean {
  const resolved = resolveSchema(document, schema);
  if (!isRecord(resolved)) return false;
  if (isRecord(resolved.properties) && "client_tools" in resolved.properties) {
    return true;
  }
  for (const key of ["allOf", "anyOf", "oneOf"]) {
    const variants = resolved[key];
    if (
      Array.isArray(variants) &&
      variants.some((variant) => schemaHasClientTools(document, variant))
    ) {
      return true;
    }
  }
  return false;
}

/** Strict compatibility fallback for runtimes predating /harness/capabilities. */
export function openApiSupportsClientTools(value: unknown): boolean {
  if (!isRecord(value) || !isRecord(value.paths)) return false;
  const harnessPath = value.paths["/harness/run_sse"];
  if (!isRecord(harnessPath) || !isRecord(harnessPath.post)) return false;
  const requestBody = resolveSchema(value, harnessPath.post.requestBody);
  if (!isRecord(requestBody) || !isRecord(requestBody.content)) return false;
  const jsonBody = requestBody.content["application/json"];
  return isRecord(jsonBody) && schemaHasClientTools(value, jsonBody.schema);
}

function runtimeProxyUrl(
  runtimeId: string,
  region: string,
  path: string,
): string {
  const params = new URLSearchParams({ region });
  return `/web/runtime-proxy/${encodeURIComponent(runtimeId)}/${path}?${params.toString()}`;
}

async function fetchJson(
  fetcher: RuntimeClientToolsFetcher,
  url: string,
  signal: AbortSignal,
): Promise<{ status: number; value: unknown }> {
  const response = await fetcher(url, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) return { status: response.status, value: null };
  return { status: response.status, value: await response.json() };
}

async function runProbe(
  runtimeId: string,
  region: string,
  fetcher: RuntimeClientToolsFetcher,
  signal: AbortSignal,
): Promise<boolean> {
  const capability = await fetchJson(
    fetcher,
    runtimeProxyUrl(runtimeId, region, "harness/capabilities"),
    signal,
  );
  if (capability.status === 200) {
    return declaresClientToolsProtocol(capability.value);
  }
  if (capability.status !== 404) return false;

  const openApi = await fetchJson(
    fetcher,
    runtimeProxyUrl(runtimeId, region, "openapi.json"),
    signal,
  );
  return openApi.status === 200 && openApiSupportsClientTools(openApi.value);
}

/**
 * Detect whether one selected Runtime can dynamically mount Studio client tools.
 * Failures are treated as unsupported so UI never advertises an unusable tool.
 */
export async function probeRuntimeClientToolsSupport(
  runtimeId: string,
  region: string,
  options: ProbeOptions = {},
): Promise<boolean> {
  if (!runtimeId.trim() || !region.trim()) return false;
  const key = `${region}\u0001${runtimeId}`;
  const now = Date.now();
  const cached = supportCache.get(key);
  if (!options.force && cached?.value !== undefined && (cached.expiresAt ?? 0) > now) {
    return cached.value;
  }
  if (!options.force && cached?.promise) return cached.promise;

  const timeoutController = new AbortController();
  const forwardAbort = () => timeoutController.abort(options.signal?.reason);
  if (options.signal?.aborted) forwardAbort();
  else options.signal?.addEventListener("abort", forwardAbort, { once: true });
  const timeout = window.setTimeout(
    () => timeoutController.abort(),
    options.timeoutMs ?? DEFAULT_PROBE_TIMEOUT_MS,
  );
  const promise = runProbe(
    runtimeId,
    region,
    options.fetcher ?? fetch,
    timeoutController.signal,
  )
    .then((value) => {
      if (!timeoutController.signal.aborted) {
        supportCache.set(key, {
          value,
          expiresAt: Date.now() + (options.cacheTtlMs ?? DEFAULT_CACHE_TTL_MS),
        });
      }
      return value;
    })
    .catch(() => false)
    .finally(() => {
      window.clearTimeout(timeout);
      options.signal?.removeEventListener("abort", forwardAbort);
      const current = supportCache.get(key);
      if (current?.promise === promise) supportCache.delete(key);
    });
  supportCache.set(key, { promise });
  return promise;
}

export function clearRuntimeClientToolsSupportCache(): void {
  supportCache.clear();
}
