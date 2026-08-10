// Remote AgentKit connections: a URL + API key whose apps are reachable over
// the ADK protocol (browser-direct, with `Authorization: Bearer <key>`). Stored
// in localStorage and registered into the client's routing table on load.

import {
  clearRemoteApps,
  fetchRemoteApps,
  probeRuntimeApps,
  registerRemoteApp,
  RuntimeAccessDeniedError,
  RuntimeProbeError,
} from "./client";

export interface RemoteConnection {
  id: string;
  name: string;
  /** Legacy browser-direct AgentKit endpoint (apikey held in the browser). */
  base?: string;
  apiKey?: string;
  /** Preferred: an AgentKit runtime routed through the server-side proxy. When
   *  set, `base`/`apiKey` are unused and the apikey stays server-side. */
  runtimeId?: string;
  region?: string;
  currentVersion?: number | null;
  apps: string[];
  /** Optional app ID -> friendly name mapping (e.g., "a_1" -> "a_1-4zkzsezc") */
  appLabels?: Record<string, string>;
}

/** An entry in the agent picker — a local app or one remote AgentKit app. */
export interface AgentEntry {
  id: string; // selection id passed to the ADK client
  label: string; // shown in the dropdown
  app: string; // real ADK app name
  runtimeApp?: string; // known Runtime app name, when already connected
  remote: boolean;
  host?: string; // remote host, for display
  runtimeId?: string;
  region?: string;
  currentVersion?: number | null;
  /** Server-authorized permission for Studio-managed Runtime deletion. */
  canDelete?: boolean;
}

const STORAGE_KEY = "veadk_agentkit_connections";
const RUNTIME_REGION_FALLBACKS = ["cn-beijing", "cn-shanghai"] as const;
const DEPLOYED_RUNTIME_CONNECT_INTERVAL_MS = 3_000;
const DEPLOYED_RUNTIME_CONNECT_TIMEOUT_MS = 60_000;

interface ConnectRuntimeOptions {
  waitForReady?: boolean;
}

function runtimeRegionCandidates(region: string): string[] {
  const primary = region || "cn-beijing";
  if (!RUNTIME_REGION_FALLBACKS.includes(primary as (typeof RUNTIME_REGION_FALLBACKS)[number])) {
    return [primary];
  }
  return [
    primary,
    ...RUNTIME_REGION_FALLBACKS.filter((candidate) => candidate !== primary),
  ];
}

export function loadConnections(): RemoteConnection[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as RemoteConnection[]) : [];
    return parsed.filter((connection) => !connection.runtimeId || !!connection.region);
  } catch {
    return [];
  }
}

function persist(list: RemoteConnection[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    /* storage unavailable */
  }
}

/** Dropdown id for one remote app (kept distinct from local app names). */
export function remoteAppId(connId: string, app: string): string {
  return `agentkit:${connId}:${app}`;
}

function hostOf(base: string): string {
  try {
    return new URL(base).host;
  } catch {
    return base;
  }
}

/** Register all stored connections' apps into the client routing table. */
export function registerConnections(conns: RemoteConnection[]): void {
  clearRemoteApps();
  for (const c of conns) {
    if (c.runtimeId && !c.region) continue;
    for (const app of c.apps) {
      registerRemoteApp(
        remoteAppId(c.id, app),
        c.runtimeId
          ? { app, runtimeId: c.runtimeId, region: c.region! }
          : { app, base: c.base, apiKey: c.apiKey },
      );
    }
  }
}

/** Persist + register an AgentKit runtime (proxy-routed; apikey server-side)
 *  and return the connection. Reuses any existing entry for the same runtime.
 *  The connection id is derived from the runtime id so picker ids are stable
 *  across reloads. */
export function addRuntimeConnection(
  runtimeId: string,
  name: string,
  region: string,
  apps: string[],
  appLabels?: Record<string, string>,
  currentVersion?: number | null,
): RemoteConnection {
  const conn: RemoteConnection = {
    id: `rt_${runtimeId}`,
    name: name || runtimeId,
    runtimeId,
    region,
    apps,
    appLabels,
    currentVersion,
  };
  const list = loadConnections();
  const existingIndex = list.findIndex((item) => item.runtimeId === runtimeId);
  if (existingIndex === -1) list.push(conn);
  else list[existingIndex] = conn;
  persist(list);
  registerConnections(list);
  return conn;
}

async function connectRuntimeOnce(
  runtimeId: string,
  name: string,
  region: string,
  currentVersion?: number | null,
): Promise<string> {
  let apps: string[] | null = null;
  let resolvedRegion = region || "cn-beijing";
  let unsupportedError: RuntimeProbeError | null = null;
  for (const candidate of runtimeRegionCandidates(region)) {
    try {
      const probedApps = await probeRuntimeApps(runtimeId, candidate, {
        retryProbe: true,
      });
      if (probedApps && probedApps.length > 0) {
        apps = probedApps;
        resolvedRegion = candidate;
        break;
      }
    } catch (error) {
      if (error instanceof RuntimeAccessDeniedError) {
        removeRuntimeConnection(runtimeId);
        throw error;
      }
      if (error instanceof RuntimeProbeError && error.unsupported) {
        unsupportedError = error;
        continue;
      }
      throw error;
    }
  }
  if (!apps || apps.length === 0) {
    removeRuntimeConnection(runtimeId);
    if (unsupportedError) throw unsupportedError;
    throw new RuntimeProbeError(
      "该 Runtime 暂不支持连接，请确认服务已正常运行。",
      true,
      true,
    );
  }
  const labels = Object.fromEntries(apps.map((app) => [app, name]));
  const connection = addRuntimeConnection(
    runtimeId,
    name,
    resolvedRegion,
    apps,
    labels,
    currentVersion,
  );
  return remoteAppId(connection.id, apps[0]);
}

function waitForRuntimeProbe(delayMs: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, delayMs));
}

/** Probe, persist, and register one AgentKit runtime, returning its first app id. */
export async function connectRuntime(
  runtimeId: string,
  name: string,
  region: string,
  currentVersion?: number | null,
  options: ConnectRuntimeOptions = {},
): Promise<string> {
  const startedAt = Date.now();
  while (true) {
    try {
      return await connectRuntimeOnce(runtimeId, name, region, currentVersion);
    } catch (error) {
      const elapsedMs = Date.now() - startedAt;
      if (
        !options.waitForReady ||
        !(error instanceof RuntimeProbeError) ||
        !error.retryable ||
        elapsedMs >= DEPLOYED_RUNTIME_CONNECT_TIMEOUT_MS
      ) {
        throw error;
      }
      const delayMs = Math.min(
        DEPLOYED_RUNTIME_CONNECT_INTERVAL_MS,
        DEPLOYED_RUNTIME_CONNECT_TIMEOUT_MS - elapsedMs,
      );
      await waitForRuntimeProbe(delayMs);
    }
  }
}

/** Validate a remote AgentKit endpoint and persist it. Throws on bad URL/key. */
export async function addConnection(
  name: string,
  base: string,
  apiKey: string,
  appLabel?: string,
): Promise<RemoteConnection> {
  const normBase = base.trim().replace(/\/+$/, "");
  const apps = await fetchRemoteApps(normBase, apiKey.trim());
  const conn: RemoteConnection = {
    id: Date.now().toString(36),
    name: name.trim() || hostOf(normBase),
    base: normBase,
    apiKey: apiKey.trim(),
    apps,
    appLabels: appLabel && apps.length > 0 ? { [apps[0]]: appLabel } : undefined,
  };
  const list = [...loadConnections().filter((c) => c.base !== normBase), conn];
  persist(list);
  registerConnections(list);
  return conn;
}

export function removeConnection(id: string): RemoteConnection[] {
  const list = loadConnections().filter((c) => c.id !== id);
  persist(list);
  registerConnections(list);
  return list;
}

/** Forget a cached runtime connection after the server rejects its owner. */
export function removeRuntimeConnection(runtimeId: string): RemoteConnection[] {
  const list = loadConnections().filter((c) => c.runtimeId !== runtimeId);
  persist(list);
  registerConnections(list);
  return list;
}

/** Build the full agent-picker list: local apps first, then remote apps. */
export function buildAgentEntries(
  localApps: string[],
  conns: RemoteConnection[],
): AgentEntry[] {
  const local: AgentEntry[] = localApps.map((app) => ({
    id: app,
    label: app,
    app,
    remote: false,
  }));
  const remote: AgentEntry[] = conns.flatMap((c) =>
    c.apps.map((app) => {
      const label = c.appLabels?.[app] ?? app;
      return {
        id: remoteAppId(c.id, app),
        label,
        app,
        remote: true,
        host: c.runtimeId ? c.name : hostOf(c.base ?? ""),
        runtimeId: c.runtimeId,
        region: c.region,
        currentVersion: c.currentVersion,
      };
    }),
  );
  return [...local, ...remote];
}
