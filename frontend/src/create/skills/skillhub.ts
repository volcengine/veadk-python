// Volcengine Skill Hub client (the backend behind findskill.com /
// skills.volces.com). Endpoints are proxied via vite `/skillhub` to dodge the
// missing CORS headers:
//   GET /v1/skills?query=<q>&namespace=public      -> { Skills: [...] }
//   GET /v1/skills/download/<slug>?namespace=<ns>   -> application/zip
//
// Skills are downloaded as a zip and unpacked client-side into project files.

import type { ProjectFile } from "../project";
import type { SkillHit, SelectedSkill } from "./types";
import { unzip } from "./zip";

const BASE = "/skillhub/v1/skills";

interface RawSkill {
  Id?: string;
  Slug?: string;
  Name?: string;
  Description?: string;
  Namespace?: string;
  SourceRepo?: string;
  DownloadCount?: number;
  Metadata?: { DisplayDescription?: string };
}

/** Search the public Skill Hub. */
export async function searchSkills(
  query: string,
  namespace = "public",
): Promise<SkillHit[]> {
  const q = query.trim();
  const url = `${BASE}?query=${encodeURIComponent(q)}&namespace=${encodeURIComponent(namespace)}`;
  const res = await fetch(url, { headers: { accept: "application/json" } });
  if (!res.ok) throw new Error(`搜索失败 (${res.status})`);
  const data = (await res.json()) as { Skills?: RawSkill[] };
  return (data.Skills ?? []).map((s) => ({
    source: "skillhub" as const,
    id: s.Id ?? s.Slug ?? "",
    slug: s.Slug ?? "",
    name: s.Name ?? s.Slug ?? "",
    description: s.Metadata?.DisplayDescription || s.Description || "",
    namespace: s.Namespace ?? namespace,
    sourceRepo: s.SourceRepo,
    downloadCount: s.DownloadCount,
  }));
}

/** Download one Skill Hub skill's zip and unpack it into ProjectFiles under
 *  `skills/<folder>/...` (folder defaults to last slug segment). */
export async function downloadSkillHubSkill(
  s: SelectedSkill,
): Promise<ProjectFile[]> {
  const slug = s.slug || "";
  const namespace = s.namespace || "public";
  const url = `${BASE}/download/${slug}?namespace=${encodeURIComponent(namespace)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`下载技能失败 (${res.status})`);
  const buf = new Uint8Array(await res.arrayBuffer());
  const entries = await unzip(buf);
  const folder = s.folder || slug.split("/").pop() || "skill";
  return entries
    .filter((e) => !e.name.endsWith("/")) // skip directory entries
    .map((e) => ({ path: `skills/${folder}/${e.name}`, content: e.text }));
}
