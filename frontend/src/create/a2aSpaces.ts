// AgentKit A2A Space client. The browser calls the local /web/a2a-spaces
// route; the server signs ListA2aSpaces with its cloud credential chain.

import { DEFAULT_REQUEST_TIMEOUT_MS, requestSignal } from "../adk/timeout";
import { createT } from "./i18n";

export interface A2aSpaceTag {
  key: string;
  value: string;
}

export interface A2aSpaceRef {
  id: string;
  name: string;
  intentEnabled: boolean;
  projectName: string;
  tags: A2aSpaceTag[];
  isDefault: boolean;
  region: string;
}

export interface A2aSpacePage {
  items: A2aSpaceRef[];
  totalCount: number;
  page: number;
  pageSize: number;
}

export interface ListA2aSpacesOptions {
  region?: string;
  pageSize?: number;
  project?: string;
}

async function jfetch<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { accept: "application/json" },
    signal: requestSignal(undefined, DEFAULT_REQUEST_TIMEOUT_MS),
  });
  if (res.status === 409) {
    throw new Error(createT("helpers.a2aSpaces.credentialsMissing"));
  }
  if (res.status === 401) {
    throw new Error(createT("helpers.a2aSpaces.loginRequired"));
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

export async function listA2aSpaces(
  options: ListA2aSpacesOptions = {},
): Promise<A2aSpaceRef[]> {
  const params = new URLSearchParams({
    page_size: String(options.pageSize ?? 100),
    project: options.project || "default",
  });
  if (options.region) params.set("region", options.region);
  const data = await jfetch<A2aSpacePage>(`/web/a2a-spaces?${params.toString()}`);
  return data.items || [];
}
