import { studioFetch } from "./client";
import { adkT } from "./i18n";

export interface WebsiteIntegrationRecord {
  id: string;
  domain: string;
  runtimeId: string;
  runtimeName: string;
  region: string;
  appName: string;
  token: string;
  createdAt: string;
}

export interface CreateWebsiteIntegrationInput {
  domain: string;
  runtimeId: string;
  runtimeName: string;
  region: string;
  appName: string;
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
  const detail = typeof payload?.detail === "string" ? payload.detail : "";
  return new Error(detail || adkT("common.fallbackWithHttpStatus", { fallback, status: response.status }));
}

export async function listWebsiteIntegrations(
  signal?: AbortSignal,
): Promise<WebsiteIntegrationRecord[]> {
  const response = await studioFetch("/web/website-integrations", {
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw await responseError(response, adkT("websiteIntegration.listFailed"));
  const payload = await response.json() as { integrations?: WebsiteIntegrationRecord[] };
  return payload.integrations ?? [];
}

export async function createWebsiteIntegration(
  input: CreateWebsiteIntegrationInput,
): Promise<WebsiteIntegrationRecord> {
  const response = await studioFetch("/web/website-integrations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw await responseError(response, adkT("websiteIntegration.createFailed"));
  return response.json();
}

export async function deleteWebsiteIntegration(id: string): Promise<void> {
  const response = await studioFetch(
    `/web/website-integrations/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw await responseError(response, adkT("websiteIntegration.deleteFailed"));
}
