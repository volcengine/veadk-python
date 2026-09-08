import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { DEFAULT_REQUEST_TIMEOUT_MS, requestSignal, TRANSFER_REQUEST_TIMEOUT_MS } from "./timeout";
import type { SkillSpacePage, SkillSpaceRef } from "../create/skills/skillspace";
import { adkT, withLocaleHeaders } from "./i18n";

const API_ROOT = "/web/skill-management";

export interface SkillApiOriginalError {
  type?: string;
  message?: string;
  repr?: string;
}

export class SkillManagementApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "SKILL_MANAGEMENT_ERROR",
    readonly statusText = "",
    readonly originalError?: SkillApiOriginalError,
    readonly rawResponse = "",
  ) {
    super(message);
    this.name = "SkillManagementApiError";
  }
}

async function request(path: string, init: RequestInit = {}, timeout = DEFAULT_REQUEST_TIMEOUT_MS) {
  return fetch(withAuth(`${API_ROOT}${path}`), {
    ...init,
    headers: withLocaleHeaders(withLocalUser(init.headers)),
    signal: requestSignal(init.signal, timeout),
  });
}

export async function skillApiErrorFromResponse(
  response: Response,
  fallback: string,
): Promise<SkillManagementApiError> {
  let message = fallback;
  let code = "SKILL_MANAGEMENT_ERROR";
  let originalError: SkillApiOriginalError | undefined;
  const rawResponse = await response.text().catch(() => "");
  try {
    const payload = JSON.parse(rawResponse) as {
      detail?: string | {
        message?: string;
        code?: string;
        originalError?: SkillApiOriginalError;
      };
    };
    if (typeof payload.detail === "string") message = payload.detail;
    else if (payload.detail) {
      message = payload.detail.message || fallback;
      code = payload.detail.code || code;
      originalError = payload.detail.originalError;
    }
  } catch {
    if (rawResponse.trim()) message = adkT("common.fallbackWithDetail", { fallback, detail: rawResponse.trim() });
  }
  return new SkillManagementApiError(
    message,
    response.status,
    code,
    response.statusText,
    originalError,
    rawResponse,
  );
}

async function json<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw await skillApiErrorFromResponse(response, fallback);
  }
  return response.json() as Promise<T>;
}

export async function listManagedSkillSpaces(args: {
  region: string;
  page: number;
  pageSize: number;
  project?: string;
  signal?: AbortSignal;
}): Promise<SkillSpacePage<SkillSpaceRef>> {
  const params = new URLSearchParams({
    region: args.region,
    page: String(args.page),
    page_size: String(args.pageSize),
  });
  if (args.project) params.set("project", args.project);
  return json(
    await request(`/spaces?${params}`, { signal: args.signal }),
    adkT("skills.listSpacesFailed"),
  );
}

export async function createSkillSpace(args: {
  name: string;
  description?: string;
  region: string;
  projectName?: string;
}): Promise<SkillSpaceRef> {
  return json(
    await request("/spaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args),
    }),
    adkT("skills.createSpaceFailed"),
  );
}

export async function updateSkillSpace(args: {
  spaceId: string;
  name: string;
  description?: string;
  region: string;
}): Promise<SkillSpaceRef> {
  return json(
    await request(`/spaces/${encodeURIComponent(args.spaceId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: args.name,
        description: args.description,
        region: args.region,
      }),
    }),
    adkT("skills.updateSpaceFailed"),
  );
}

export async function deleteSkillSpace(args: {
  spaceId: string;
  region: string;
}): Promise<void> {
  const params = new URLSearchParams({ region: args.region });
  await json(
    await request(
      `/spaces/${encodeURIComponent(args.spaceId)}?${params}`,
      { method: "DELETE" },
    ),
    adkT("skills.deleteSpaceFailed"),
  );
}

export async function uploadSkillArchive(args: {
  spaceId: string;
  region: string;
  project?: string;
  file: File;
}): Promise<{ skillId: string; name: string; version: string }> {
  const params = new URLSearchParams({ region: args.region });
  if (args.project) params.set("project", args.project);
  return json(
    await request(
      `/spaces/${encodeURIComponent(args.spaceId)}/skills?${params}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/zip" },
        body: args.file,
      },
      TRANSFER_REQUEST_TIMEOUT_MS,
    ),
    adkT("skills.uploadFailed"),
  );
}

export async function validateSkillArchive(file: File): Promise<{
  valid: true;
  name: string;
  description: string;
  files: Array<{ path: string; size: number }>;
}> {
  return json(
    await request(
      "/validate",
      {
        method: "POST",
        headers: { "Content-Type": "application/zip" },
        body: file,
      },
      TRANSFER_REQUEST_TIMEOUT_MS,
    ),
    adkT("skills.validateFailed"),
  );
}

export async function deleteManagedSkill(args: {
  spaceId: string;
  skillId: string;
  region: string;
}): Promise<void> {
  const params = new URLSearchParams({ region: args.region });
  await json(
    await request(
      `/spaces/${encodeURIComponent(args.spaceId)}/skills/${encodeURIComponent(args.skillId)}?${params}`,
      { method: "DELETE" },
    ),
    adkT("skills.deleteFailed"),
  );
}

export interface ManagedSkillFile {
  path: string;
  size: number;
  mimeType: string;
  kind: "text" | "image" | "binary";
  content?: string;
}

export async function getManagedSkillFiles(args: {
  spaceId: string;
  skillId: string;
  version?: string;
  region: string;
  skillSpaceName?: string;
  skillName?: string;
}): Promise<ManagedSkillFile[]> {
  const params = new URLSearchParams({ region: args.region });
  if (args.version) params.set("version", args.version);
  if (args.skillSpaceName) params.set("skill_space_name", args.skillSpaceName);
  if (args.skillName) params.set("skill_name", args.skillName);
  const result = await json<{ files: ManagedSkillFile[] }>(
    await request(`/spaces/${encodeURIComponent(args.spaceId)}/skills/${encodeURIComponent(args.skillId)}/files?${params}`),
    adkT("skills.listFilesFailed"),
  );
  return Array.isArray(result.files) ? result.files : [];
}

export async function downloadManagedSkillArchive(args: {
  spaceId: string;
  skillId: string;
  version?: string;
  region: string;
  fallbackName: string;
  skillSpaceName?: string;
  skillName?: string;
}): Promise<void> {
  const params = new URLSearchParams({ region: args.region });
  if (args.version) params.set("version", args.version);
  if (args.skillSpaceName) params.set("skill_space_name", args.skillSpaceName);
  if (args.skillName) params.set("skill_name", args.skillName);
  const response = await request(
    `/spaces/${encodeURIComponent(args.spaceId)}/skills/${encodeURIComponent(args.skillId)}/archive?${params}`,
    {},
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
  if (!response.ok) await json(response, adkT("skills.downloadFailed"));
  const disposition = response.headers.get("content-disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `${args.fallbackName}.zip`;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
