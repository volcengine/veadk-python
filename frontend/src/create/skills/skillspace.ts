// AgentKit SkillSpace client. These hit the new /web/skill-spaces* backend
// routes, which sign requests server-side with the server's Volcengine AK/SK
// (the browser never sees credentials) and are gated by SSO when enabled.

import type { ProjectFile } from "../project";
import { DEFAULT_REQUEST_TIMEOUT_MS, requestSignal } from "../../adk/timeout";
import type { SkillHit } from "./types";

export interface SkillSpaceRef {
  id: string;
  name: string;
  description: string;
  status: string;
  region?: string;
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
  bucketName: string;
  tosPath: string;
}

async function jfetch<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { accept: "application/json" },
    signal: requestSignal(undefined, DEFAULT_REQUEST_TIMEOUT_MS),
  });
  if (res.status === 409) {
    throw new Error("服务端未配置 Volcengine AK/SK，无法访问 SkillSpace");
  }
  if (res.status === 401) {
    throw new Error("请先登录以访问 SkillSpace");
  }
  if (res.status === 404) {
    throw new Error("技能不存在或无 SKILL.md 内容");
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

export async function listSkillSpaces(): Promise<SkillSpaceRef[]> {
  const data = await jfetch<{ items: SkillSpaceRef[] }>("/web/skill-spaces?region=all");
  return data.items || [];
}

export async function listSkillsInSpace(spaceId: string, region?: string): Promise<SkillSpaceSkill[]> {
  const q = region ? `?region=${encodeURIComponent(region)}` : "";
  const data = await jfetch<{ items: SkillSpaceSkill[] }>(
    `/web/skill-spaces/${encodeURIComponent(spaceId)}/skills${q}`,
  );
  return data.items || [];
}

export async function getSkillDetail(
  spaceId: string,
  skillId: string,
  version?: string,
  region?: string,
): Promise<SkillDetail> {
  const params: string[] = [];
  if (version) params.push(`version=${encodeURIComponent(version)}`);
  if (region) params.push(`region=${encodeURIComponent(region)}`);
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

/** Download a SkillSpace skill's SKILL.md into a ProjectFile. v1: only the
 *  SKILL.md (SkillMd); TOS zip (scripts/assets) is a follow-up. */
export async function downloadSkillSpaceSkill(
  spaceId: string,
  skillId: string,
  version: string | undefined,
  folder: string,
  region?: string,
): Promise<ProjectFile[]> {
  const d = await getSkillDetail(spaceId, skillId, version, region);
  return [{ path: `skills/${folder}/SKILL.md`, content: d.skillMd }];
}

/** Get the Volcengine console URL for a SkillSpace. */
export function getSkillSpaceConsoleUrl(spaceId: string, region?: string): string {
  const r = region || "cn-beijing";
  const consoleRegion = r === "cn-beijing" ? "cn" : "cn-shanghai";
  return `https://console.volcengine.com/agentkit/${consoleRegion}/skillspace/detail/${encodeURIComponent(spaceId)}`;
}
