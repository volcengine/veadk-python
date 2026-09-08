// Volcengine Skill Hub client (the backend behind findskill.com /
// skills.volces.com). Search uses a normalized Studio harness endpoint for the
// project-creation Skill picker. Downloads still use `/skillhub` because the
// selected zip is unpacked client-side into the generated project:
//   GET /harness/skills/findskill?query=<q>         -> { items: [...] }
//   GET /skillhub/v1/skills/download/<slug>?namespace=<ns> -> application/zip
//
// Skills are downloaded as a zip and unpacked client-side into project files.

import type { ProjectFile } from "../project";
import {
  DEFAULT_REQUEST_TIMEOUT_MS,
  requestSignal,
  TRANSFER_REQUEST_TIMEOUT_MS,
} from "../../adk/timeout";
import type { SkillHit, SelectedSkill } from "./types";
import { unzip } from "./zip";
import { createT } from "../i18n";

const DOWNLOAD_BASE = "/skillhub/v1/skills";
const SEARCH_BASE = "/harness/skills/findskill";

interface RawSkill {
  slug?: string;
  name?: string;
  description?: string;
  sourceRepo?: string;
  downloadCount?: number;
  version?: string;
}

/** Search the public Skill Hub. */
export async function searchSkills(
  query: string,
  namespace = "public",
): Promise<SkillHit[]> {
  const q = query.trim();
  const params = new URLSearchParams({
    query: q,
    page_number: "1",
    page_size: "20",
  });
  const url = `${SEARCH_BASE}?${params.toString()}`;
  const res = await fetch(url, {
    headers: { accept: "application/json" },
    signal: requestSignal(undefined, DEFAULT_REQUEST_TIMEOUT_MS),
  });
  if (!res.ok) {
    throw new Error(createT("helpers.skills.searchFailed", { status: res.status }));
  }
  const data = (await res.json()) as { items?: RawSkill[] };
  return (data.items ?? []).map((s) => ({
    source: "skillhub" as const,
    id: s.slug ?? s.name ?? "",
    slug: s.slug ?? "",
    name: s.name ?? s.slug ?? "",
    description: s.description ?? "",
    namespace,
    sourceRepo: s.sourceRepo,
    downloadCount: s.downloadCount,
    version: s.version,
  }));
}

/** Download one Skill Hub skill's zip and unpack it into ProjectFiles under
 *  `skills/<folder>/...` (folder defaults to last slug segment). */
export async function downloadSkillHubSkill(
  s: SelectedSkill,
): Promise<ProjectFile[]> {
  const slug = s.slug || "";
  const namespace = s.namespace || "public";
  const url = `${DOWNLOAD_BASE}/download/${slug}?namespace=${encodeURIComponent(namespace)}`;
  const res = await fetch(url, {
    signal: requestSignal(undefined, TRANSFER_REQUEST_TIMEOUT_MS),
  });
  if (!res.ok) {
    throw new Error(createT("helpers.skills.downloadFailed", { status: res.status }));
  }
  const buf = new Uint8Array(await res.arrayBuffer());
  const entries = await unzip(buf);
  const folder = s.folder || slug.split("/").pop() || "skill";
  return entries
    .filter((e) => !e.name.endsWith("/")) // skip directory entries
    .map((e) => ({ path: `skills/${folder}/${e.name}`, content: e.text }));
}
