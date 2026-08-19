// VikingDB Memory client. The browser calls /web/viking-memories; the server
// signs requests with server-side cloud credentials.

import { DEFAULT_REQUEST_TIMEOUT_MS, requestSignal } from "../adk/timeout";

export interface VikingMemoryRef {
  id: string;
  name: string;
  description: string;
  projectName: string;
  region: string;
  resourceId?: string;
  updatedAt?: string;
  memoryTypes?: string[];
}

export interface VikingMemoryPage {
  items: VikingMemoryRef[];
  totalCount: number;
}

export interface ListVikingMemoriesOptions {
  region?: string;
  project?: string;
}

async function jfetch<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { accept: "application/json" },
    signal: requestSignal(undefined, DEFAULT_REQUEST_TIMEOUT_MS),
  });
  if (res.status === 409) {
    throw new Error("服务端未配置云厂商 AK/SK，无法访问 VikingDB 记忆库");
  }
  if (res.status === 401) {
    throw new Error("请先登录以访问 VikingDB 记忆库");
  }
  if (!res.ok) {
    let detail = "";
    try {
      const j = (await res.json()) as { detail?: string };
      detail = j.detail || "";
    } catch {
      /* ignore */
    }
    throw new Error(`请求失败 (${res.status})${detail ? ": " + detail : ""}`);
  }
  return res.json() as Promise<T>;
}

export async function listVikingMemories(
  options: ListVikingMemoriesOptions = {},
): Promise<VikingMemoryRef[]> {
  const params = new URLSearchParams();
  if (options.project) params.set("project", options.project);
  if (options.region) params.set("region", options.region);
  const query = params.toString();
  const data = await jfetch<VikingMemoryPage>(
    `/web/viking-memories${query ? `?${query}` : ""}`,
  );
  return data.items || [];
}
