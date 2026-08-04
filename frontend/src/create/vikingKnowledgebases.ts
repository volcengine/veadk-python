// VikingDB KnowledgeBase client. The browser calls /web/viking-knowledgebases;
// the server signs requests with server-side Volcengine credentials.

import { DEFAULT_REQUEST_TIMEOUT_MS, requestSignal } from "../adk/timeout";

export interface VikingKnowledgebaseRef {
  id: string;
  name: string;
  description: string;
  projectName: string;
  region: string;
  docCount?: number | null;
  updatedAt?: string;
}

export interface VikingKnowledgebasePage {
  items: VikingKnowledgebaseRef[];
  totalCount: number;
}

export interface ListVikingKnowledgebasesOptions {
  region?: string;
  project?: string;
}

async function jfetch<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { accept: "application/json" },
    signal: requestSignal(undefined, DEFAULT_REQUEST_TIMEOUT_MS),
  });
  if (res.status === 409) {
    throw new Error("服务端未配置 Volcengine AK/SK，无法访问 VikingDB 知识库");
  }
  if (res.status === 401) {
    throw new Error("请先登录以访问 VikingDB 知识库");
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

export async function listVikingKnowledgebases(
  options: ListVikingKnowledgebasesOptions = {},
): Promise<VikingKnowledgebaseRef[]> {
  const params = new URLSearchParams({
    region: options.region || "cn-beijing",
    project: options.project || "default",
  });
  const data = await jfetch<VikingKnowledgebasePage>(
    `/web/viking-knowledgebases?${params.toString()}`,
  );
  return data.items || [];
}
