import { adkT } from "./i18n";
import zhAdk from "../i18n/resources/zh-CN/adk.json";
import { studioFetch } from "./client";

function projectError(detail: unknown, fallback: string): string {
  if (typeof detail !== "string") return fallback;
  const key = Object.entries(zhAdk.workspaceProjects).find(([, value]) => value === detail)?.[0];
  return key ? adkT(`workspaceProjects.${key}`) : fallback;
}

export interface WorkspacePreview {
  sessionId: string;
  url: string;
  expireAt: string;
  region: string;
}

export async function launchWorkspacePreview(signal: AbortSignal): Promise<WorkspacePreview> {
  const response = await studioFetch("/web/workspace-preview/session", {
    method: "POST",
    signal,
    cache: "no-store",
  }, 180_000);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(projectError(body?.detail, adkT("workspaceProjects.connection")));
  }
  const data = await response.json() as WorkspacePreview;
  const url = new URL(data.url);
  const localPreview = data.region === "local" && url.protocol === "http:"
    && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (!data.sessionId || (url.protocol !== "https:" && !localPreview)) {
    throw new Error(adkT("workspaceProjects.invalidWorkspaceUrl"));
  }
  return data;
}

export interface WorkspaceProject {
  createdAt?: string | null;
  fileCount?: number;
  directoryCount?: number;
  sessionId: string;
  name: string;
  status: string;
  expireAt: string;
  region: string;
}

async function projectRequest(path: string, signal: AbortSignal, name?: string) {
  const response = await studioFetch(`/web/workspace-preview/projects${path}`, {
    method: "POST", signal, cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: name === undefined ? undefined : JSON.stringify({ name }),
  }, 180_000);
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(projectError(data?.detail, adkT("workspaceProjects.operation")));
  const url = new URL(data.url);
  if (url.protocol !== "https:" || !data.sessionId) throw new Error(adkT("workspaceProjects.invalidProjectUrl"));
  return data as WorkspacePreview & WorkspaceProject;
}

export async function listWorkspaceProjects(signal: AbortSignal): Promise<WorkspaceProject[]> {
  const response = await studioFetch("/web/workspace-preview/projects", { signal, cache: "no-store" }, 180_000);
  const data = await response.json().catch(() => null);
  if (!response.ok || !data) throw new Error(projectError(data?.detail, adkT("workspaceProjects.listFallback")));
  return data.projects;
}

export const createWorkspaceProject = (name: string, signal: AbortSignal) => projectRequest("", signal, name);
export const openWorkspaceProject = (id: string, signal: AbortSignal) => projectRequest(`/${encodeURIComponent(id)}/open`, signal);

export async function getWorkspaceState(signal: AbortSignal): Promise<{status: string; sessionId: string; expireAt: string}> {
  const response = await studioFetch("/web/workspace-preview/state", { signal, cache: "no-store" }, 20_000);
  const data = await response.json().catch(() => null);
  if (!response.ok || !data || typeof data.status !== "string") {
    throw new Error(projectError(data?.detail, adkT("workspaceProjects.connectionState")));
  }
  return data;
}
