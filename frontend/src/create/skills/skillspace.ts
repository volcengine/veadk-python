// AgentKit SkillSpace client. These hit the new /web/skill-spaces* backend
// routes, which sign requests server-side with the server's Volcengine AK/SK
// (the browser never sees credentials) and are gated by SSO when enabled.

import type { ProjectFile } from "../project";
import type { SkillHit } from "./types";

export interface SkillSpaceRef {
  id: string;
  name: string;
  description: string;
  status: string;
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
  const res = await fetch(url, { headers: { accept: "application/json" } });
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
  const data = await jfetch<{ items: SkillSpaceRef[] }>("/web/skill-spaces");
  return data.items || [];
}

export async function listSkillsInSpace(spaceId: string): Promise<SkillSpaceSkill[]> {
  const data = await jfetch<{ items: SkillSpaceSkill[] }>(
    `/web/skill-spaces/${encodeURIComponent(spaceId)}/skills`,
  );
  return data.items || [];
}

export async function getSkillDetail(
  spaceId: string,
  skillId: string,
  version?: string,
): Promise<SkillDetail> {
  const q = version ? `?version=${encodeURIComponent(version)}` : "";
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
): Promise<ProjectFile[]> {
  const d = await getSkillDetail(spaceId, skillId, version);
  return [{ path: `skills/${folder}/SKILL.md`, content: d.skillMd }];
}
