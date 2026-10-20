import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { adkT, withLocaleHeaders } from "./i18n";
import { skillApiErrorFromResponse } from "./skills";
import { DEFAULT_REQUEST_TIMEOUT_MS, requestSignal, TRANSFER_REQUEST_TIMEOUT_MS } from "./timeout";

export interface SkillVersion {
  skillId: string;
  version: string;
  sourceVersion?: string;
  author?: string;
  name: string;
  description: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  error: string;
  isCurrent: boolean;
}

export interface SkillVersionsResult {
  items: SkillVersion[];
  totalCount: number;
  canUpdate: boolean;
}

interface SkillVersionTarget {
  spaceId: string;
  skillId: string;
  region: string;
  signal?: AbortSignal;
}

async function requestVersion<T>(
  target: SkillVersionTarget, init: RequestInit, fallback: string, timeout: number,
): Promise<T> {
  const params = new URLSearchParams({ region: target.region });
  const response = await fetch(withAuth(`/web/skill-management/spaces/${encodeURIComponent(target.spaceId)}/skills/${encodeURIComponent(target.skillId)}/versions?${params}`), {
    ...init,
    headers: withLocaleHeaders(withLocalUser(init.headers)),
    signal: requestSignal(target.signal, timeout),
  });
  if (!response.ok) throw await skillApiErrorFromResponse(response, fallback);
  return response.json() as Promise<T>;
}

export function listSkillVersions(target: SkillVersionTarget): Promise<SkillVersionsResult> {
  return requestVersion(target, {}, adkT("skills.listVersionsFailed"), DEFAULT_REQUEST_TIMEOUT_MS);
}

export function uploadSkillVersion(target: SkillVersionTarget & { file: File }): Promise<{
  skillId: string; name: string; version: string; description: string; skillSpaceId: string;
}> {
  return requestVersion(target, {
    method: "POST", headers: { "Content-Type": "application/zip" }, body: target.file,
  }, adkT("skills.uploadVersionFailed"), TRANSFER_REQUEST_TIMEOUT_MS);
}
