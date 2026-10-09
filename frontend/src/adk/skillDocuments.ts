import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { withLocaleHeaders } from "./i18n";
import {
  requestSignal,
  DEFAULT_REQUEST_TIMEOUT_MS,
  TRANSFER_REQUEST_TIMEOUT_MS,
} from "./timeout";
import { skillApiErrorFromResponse } from "./skills";

export interface SkillDocumentTarget {
  spaceId: string;
  skillId: string;
  region: string;
  name: string;
}
export interface SkillDocument {
  content: string;
  baseVersion: string;
  canUpdate: boolean;
}
async function request<T>(
  target: SkillDocumentTarget & { signal?: AbortSignal },
  init: RequestInit,
  timeout: number,
): Promise<T> {
  const params = new URLSearchParams({ region: target.region });
  const response = await fetch(
    withAuth(
      `/web/skill-management/spaces/${encodeURIComponent(target.spaceId)}/skills/${encodeURIComponent(target.skillId)}/document?${params}`,
    ),
    {
      ...init,
      headers: withLocaleHeaders(withLocalUser(init.headers)),
      signal: requestSignal(target.signal, timeout),
    },
  );
  if (!response.ok)
    throw await skillApiErrorFromResponse(
      response,
      "SKILL_DOCUMENT_REQUEST_FAILED",
    );
  return response.json() as Promise<T>;
}
export function getSkillDocument(
  target: SkillDocumentTarget & { signal?: AbortSignal },
): Promise<SkillDocument> {
  return request(target, {}, DEFAULT_REQUEST_TIMEOUT_MS);
}
export function saveSkillDocument(
  target: SkillDocumentTarget & {
    content: string;
    baseVersion: string;
    signal?: AbortSignal;
  },
): Promise<{ version: string }> {
  return request(
    target,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: target.content,
        baseVersion: target.baseVersion,
      }),
    },
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
}
