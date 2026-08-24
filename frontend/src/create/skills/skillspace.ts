// AgentKit SkillSpace client. These hit the new /web/skill-spaces* backend
// routes, which sign requests server-side with the server's cloud AK/SK
// (the browser never sees credentials) and are gated by SSO when enabled.

import type { ProjectFile } from "../project";
import { skillApiErrorFromResponse } from "../../adk/skills";
import { DEFAULT_REQUEST_TIMEOUT_MS, requestSignal } from "../../adk/timeout";
import type { SkillHit } from "./types";

export interface SkillSpaceRef {
  id: string;
  name: string;
  description: string;
  status: string;
  region?: string;
  projectName?: string;
  updatedAt?: string;
  skillCount?: number;
}
export interface SkillSpaceSkill {
  skillId: string;
  skillName: string;
  skillDescription: string;
  version: string;
  skillStatus: string;
}
export interface SkillDetail {
  skillId: string;
  skillSpaceId: string;
  name: string;
  description: string;
  version: string;
  skillMd: string;
  files?: ProjectFile[];
  bucketName: string;
  tosPath: string;
}

export interface SkillSpacePage<T> {
  items: T[];
  totalCount: number;
  page: number;
  pageSize: number;
}

export interface SkillSpacePageOptions {
  region: string;
  page: number;
  pageSize: number;
  project?: string;
}

async function jfetch<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { accept: "application/json" },
    signal: requestSignal(undefined, DEFAULT_REQUEST_TIMEOUT_MS),
  });
  if (!res.ok) {
    throw await skillApiErrorFromResponse(res, "AgentKit Skills 请求失败");
  }
  return res.json() as Promise<T>;
}

export async function listSkillSpaces(): Promise<SkillSpaceRef[]> {
  const data = await jfetch<{ items: SkillSpaceRef[] }>("/web/skill-spaces?region=all");
  return data.items || [];
}

export async function listSkillSpacesPage(
  options: SkillSpacePageOptions,
): Promise<SkillSpacePage<SkillSpaceRef>> {
  const params = new URLSearchParams({
    region: options.region,
    page: String(options.page),
    page_size: String(options.pageSize),
  });
  if (options.project) params.set("project", options.project);
  return jfetch<SkillSpacePage<SkillSpaceRef>>(`/web/skill-spaces?${params.toString()}`);
}

export async function listSkillsInSpace(spaceId: string, region?: string): Promise<SkillSpaceSkill[]> {
  const q = region ? `?region=${encodeURIComponent(region)}` : "";
  const data = await jfetch<{ items: SkillSpaceSkill[] }>(
    `/web/skill-spaces/${encodeURIComponent(spaceId)}/skills${q}`,
  );
  return data.items || [];
}

export async function listSkillsInSpacePage(
  spaceId: string,
  options: SkillSpacePageOptions,
): Promise<SkillSpacePage<SkillSpaceSkill>> {
  const params = new URLSearchParams({
    region: options.region,
    page: String(options.page),
    page_size: String(options.pageSize),
  });
  if (options.project) params.set("project", options.project);
  return jfetch<SkillSpacePage<SkillSpaceSkill>>(
    `/web/skill-spaces/${encodeURIComponent(spaceId)}/skills?${params.toString()}`,
  );
}

export async function getSkillDetail(
  spaceId: string,
  skillId: string,
  version?: string,
  region?: string,
  project?: string,
  skillName?: string,
  skillSpaceName?: string,
): Promise<SkillDetail> {
  const params: string[] = [];
  if (version) params.push(`version=${encodeURIComponent(version)}`);
  if (region) params.push(`region=${encodeURIComponent(region)}`);
  if (project) params.push(`project=${encodeURIComponent(project)}`);
  if (skillName) params.push(`skill_name=${encodeURIComponent(skillName)}`);
  if (skillSpaceName) params.push(`skill_space_name=${encodeURIComponent(skillSpaceName)}`);
  const q = params.length > 0 ? `?${params.join("&")}` : "";
  return jfetch<SkillDetail>(
    `/web/skill-spaces/${encodeURIComponent(spaceId)}/skills/${encodeURIComponent(skillId)}${q}`,
  );
}

/** Convert a raw space skill listing into a selectable SkillHit. */
export function toHit(space: SkillSpaceRef, s: SkillSpaceSkill): SkillHit {
  return {
    source: "skillspace",
    id: `ss:${space.id}/${s.skillId}/${s.version}`,
    name: s.skillName,
    description: s.skillDescription,
    folder: s.skillName,
    skillSpaceId: space.id,
    skillSpaceName: space.name,
    skillSpaceRegion: space.region,
    skillId: s.skillId,
    version: s.version,
  };
}

/** Download a SkillSpace skill package into ProjectFiles. The backend returns
 *  full package files when the cloud version exposes a TOS zip, and falls back
 *  to SKILL.md-only for older metadata-only responses. */
export async function downloadSkillSpaceSkill(
  spaceId: string,
  skillId: string,
  version: string | undefined,
  folder: string,
  region?: string,
): Promise<ProjectFile[]> {
  const d = await getSkillDetail(spaceId, skillId, version, region);
  if (Array.isArray(d.files) && d.files.length > 0) return d.files;
  return [{ path: `skills/${folder}/SKILL.md`, content: d.skillMd }];
}

/** Get the cloud console URL for a SkillSpace when the provider exposes one. */
export function getSkillSpaceConsoleUrl(
  spaceId: string,
  region?: string,
  provider: "volcengine" | "byteplus" = "volcengine",
): string {
  if (provider === "byteplus") return "";
  const r = region || "cn-beijing";
  const consoleRegion = r === "cn-beijing" ? "cn" : "cn-shanghai";
  return `https://console.volcengine.com/agentkit/${consoleRegion}/skillspace/detail/${encodeURIComponent(spaceId)}`;
}
