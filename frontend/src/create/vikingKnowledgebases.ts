// VikingDB KnowledgeBase client. The browser calls /web/viking-knowledgebases;
// the server signs requests with server-side cloud credentials.

import { DEFAULT_REQUEST_TIMEOUT_MS, requestSignal } from "../adk/timeout";
import { createT } from "./i18n";

export interface VikingKnowledgebaseRef {
  id: string;
  name: string;
  description: string;
  projectName: string;
  region: string;
  sourceKind?: "agentkit" | "knowledge" | "vector";
  sourceLabel?: string;
  docCount?: number | null;
  indexCount?: number | null;
  updatedAt?: string;
  resourceId?: string;
  agentkitKnowledgeId?: string;
  providerKnowledgeId?: string;
  providerType?: string;
  status?: string;
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
    throw new Error(createT("helpers.vikingKnowledge.credentialsMissing"));
  }
  if (res.status === 401) {
    throw new Error(createT("helpers.vikingKnowledge.loginRequired"));
  }
  if (!res.ok) {
    let detail = "";
    try {
      const j = (await res.json()) as { detail?: string };
      detail = j.detail || "";
    } catch {
      /* ignore */
    }
    throw new Error(
      createT("helpers.requestFailed", {
        status: res.status,
        detail: detail ? `: ${detail}` : "",
      }),
    );
  }
  return res.json() as Promise<T>;
}

export async function listVikingKnowledgebases(
  options: ListVikingKnowledgebasesOptions = {},
): Promise<VikingKnowledgebaseRef[]> {
  const params = new URLSearchParams();
  if (options.project) params.set("project", options.project);
  if (options.region) params.set("region", options.region);
  const query = params.toString();
  const data = await jfetch<VikingKnowledgebasePage>(
    `/web/viking-knowledgebases${query ? `?${query}` : ""}`,
  );
  return data.items || [];
}
