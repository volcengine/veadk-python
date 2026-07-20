// Remote AgentKit connections: a URL + API key whose apps are reachable over
// the ADK protocol (browser-direct, with `Authorization: Bearer <key>`). Stored
// in localStorage and registered into the client's routing table on load.

import {
  clearRemoteApps,
  fetchRemoteApps,
  probeRuntimeApps,
  registerRemoteApp,
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
  apps: string[];
  /** Optional app ID -> friendly name mapping (e.g., "a_1" -> "a_1-4zkzsezc") */
  appLabels?: Record<string, string>;
}

/** An entry in the agent picker — a local app or one remote AgentKit app. */
export interface AgentEntry {
  id: string; // selection id passed to the ADK client
  label: string; // shown in the dropdown
  app: string; // real ADK app name
  remote: boolean;
  host?: string; // remote host, for display
}

const STORAGE_KEY = "veadk_agentkit_connections";

export function loadConnections(): RemoteConnection[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as RemoteConnection[]) : [];
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
    for (const app of c.apps) {
      registerRemoteApp(
        remoteAppId(c.id, app),
        c.runtimeId
          ? { app, runtimeId: c.runtimeId, region: c.region }
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
): RemoteConnection {
  const conn: RemoteConnection = {
    id: `rt_${runtimeId}`,
    name: name || runtimeId,
    runtimeId,
    region,
    apps,
    appLabels,
  };
  const list = [...loadConnections().filter((c) => c.runtimeId !== runtimeId), conn];
  persist(list);
  registerConnections(list);
  return conn;
}

/** Probe, persist, and register one AgentKit runtime, returning its first app id. */
export async function connectRuntime(
  runtimeId: string,
  name: string,
  region: string,
): Promise<string> {
  const apps = await probeRuntimeApps(runtimeId, region);
  if (!apps || apps.length === 0) {
    throw new Error("该 Runtime 暂不支持连接，请确认服务已正常运行。");
  }
  const labels = Object.fromEntries(apps.map((app) => [app, name]));
  const connection = addRuntimeConnection(runtimeId, name, region, apps, labels);
  return remoteAppId(connection.id, apps[0]);
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
      };
    }),
  );
  return [...local, ...remote];
}
