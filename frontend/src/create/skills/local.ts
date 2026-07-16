// Local skill upload: read a browser folder (via <input webkitdirectory>) or a
// .zip file into SkillHit entries. Each skill directory must contain a
// SKILL.md (case-insensitive) with valid frontmatter. Validation mirrors what
// ADK's skill loader requires (so skills actually load at runtime):
//   - SKILL.md starts with a closed `--- ... ---` frontmatter block
//   - `name`: required, <=64 chars, matches [a-z0-9-]+ (kebab-case)
//   - `description`: required, <=1024 chars, no XML tags
//   - quoted name/description values are accepted (quotes stripped) — real YAML
//     parsers handle them fine, and the platform's line-based parser only
//     applies to pushed skills, not locally-uploaded ones.
//
// Resulting ProjectFiles are rooted at `skills/<frontmatter-name>/...` so they
// merge cleanly with the existing Skill Hub download layout. Zip-slip paths
// are rejected.

import type { ProjectFile } from "../project";
import type { SkillHit } from "./types";
import { unzip } from "./zip";

export interface LocalReadResult {
  hits: SkillHit[];
  errors: string[];
}

interface RawEntry {
  /** Path inside the upload, using '/' separators (zip style). */
  path: string;
  text: string;
}

const SKILL_MD_RE = /(^|\/)skill\.md$/i;

/** Validation error: carries a human-readable message. */
class SkillValidationError extends Error {}

/** Parse a YAML "key: value" line the same way the agentkit validator does
 *  (simple line-based, no full YAML parser, rejects quoted name/description).
 *  Returns { name, description } on success, throws on any violation. */
function parseAndValidateSkillMd(text: string, where: string): {
  name: string;
  description: string;
} {
  const lines = (text ?? "").replace(/\r\n?/g, "\n").split("\n");
  if (!lines.length || lines[0].trim() !== "---") {
    throw new SkillValidationError(
      `${where} 的 SKILL.md 必须以 YAML frontmatter (--- ... ---) 开头`,
    );
  }
  let endIdx = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === "---") {
      endIdx = i;
      break;
    }
  }
  if (endIdx < 0) {
    throw new SkillValidationError(
      `${where} 的 SKILL.md frontmatter 未闭合（缺少结束 ---）`,
    );
  }
  const meta: Record<string, string> = {};
  for (let i = 1; i < endIdx; i++) {
    const s = lines[i].trim();
    if (!s || s.startsWith("#")) continue;
    const colon = s.indexOf(":");
    if (colon < 0) continue;
    const key = s.slice(0, colon).trim();
    let val = s.slice(colon + 1).trim();
    // Strip surrounding quotes (ADK's frontmatter parser accepts quoted YAML
    // strings, so we normalize them rather than reject — user intent is clear).
    if (isQuoted(val)) val = val.slice(1, -1);
    meta[key] = val;
  }

  const name = (meta.name || "").trim();
  const description = (meta.description || "").trim();
  validateName(name, where);
  validateDescription(description, where);
  return { name, description };
}

function isQuoted(v: string): boolean {
  return v.length >= 2 && ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'")));
}

function validateName(name: string, where: string) {
  if (!name) {
    throw new SkillValidationError(`${where} 的 SKILL.md 缺少必填的 name frontmatter`);
  }
  if (name.length > 64) {
    throw new SkillValidationError(`${where} 的 name 长度超过 64 个字符`);
  }
  if (!/^[a-z0-9-]+$/.test(name)) {
    throw new SkillValidationError(
      `${where} 的 name 必须匹配 [a-z0-9-]+（小写字母、数字、短横线）`,
    );
  }
}

function validateDescription(desc: string, where: string) {
  if (!desc) {
    throw new SkillValidationError(
      `${where} 的 SKILL.md 缺少必填的 description frontmatter`,
    );
  }
  if (desc.length > 1024) {
    throw new SkillValidationError(`${where} 的 description 长度超过 1024 个字符`);
  }
  if (/<[^>]+>/.test(desc)) {
    throw new SkillValidationError(`${where} 的 description 不能包含 XML 标签`);
  }
}

/** Normalize path separators and strip a single common wrapper folder if the
 *  upload has one (typical when someone zips a single folder named after the
 *  skill). Returns paths relative to the logical root. */
function normalizeEntries(raw: RawEntry[]): RawEntry[] {
  const cleaned = raw
    .map((e) => ({
      path: e.path.replace(/\\/g, "/").replace(/^\.\//, ""),
      text: e.text,
    }))
    .filter((e) => e.path.length > 0 && !e.path.endsWith("/"));

  const firstSegs = new Set(cleaned.map((p) => p.path.split("/")[0]));
  if (firstSegs.size === 1 && cleaned.every((p) => p.path.includes("/"))) {
    const prefix = [...firstSegs][0] + "/";
    return cleaned.map((p) => ({ path: p.path.slice(prefix.length), text: p.text }));
  }
  return cleaned;
}

/** Group entries by their nearest enclosing skill directory (the folder
 *  containing a SKILL.md). The folder "" represents a root-level SKILL.md. */
function groupBySkillFolder(entries: RawEntry[]): Map<string, RawEntry[]> {
  const groups = new Map<string, RawEntry[]>();
  const skillFolders = new Set<string>();
  for (const e of entries) {
    if (SKILL_MD_RE.test("/" + e.path)) {
      const parts = e.path.split("/");
      skillFolders.add(parts.slice(0, -1).join("/"));
    }
  }

  for (const e of entries) {
    const parts = e.path.split("/");
    let assigned = "";
    for (let d = parts.length - 1; d >= 0; d--) {
      const candidate = parts.slice(0, d).join("/");
      if (skillFolders.has(candidate)) {
        assigned = candidate;
        break;
      }
    }
    const isSkillMdItself = SKILL_MD_RE.test("/" + e.path);
    if (!assigned && !isSkillMdItself && !skillFolders.has("")) continue;
    if (!skillFolders.has(assigned) && !isSkillMdItself) continue;
    const relPath = assigned ? e.path.slice(assigned.length + 1) : e.path;
    const arr = groups.get(assigned) || [];
    arr.push({ path: relPath, text: e.text });
    groups.set(assigned, arr);
  }
  return groups;
}

function materializeHit(
  folderKey: string,
  files: RawEntry[],
  sourceLabel: string,
): { hit: SkillHit | null; error: string | null } {
  const where = `${sourceLabel}${folderKey ? "/" + folderKey : ""}`;
  const md = files.find((e) => SKILL_MD_RE.test("/" + e.path));
  if (!md) {
    return { hit: null, error: `${where} 缺少 SKILL.md` };
  }
  let fm: { name: string; description: string };
  try {
    fm = parseAndValidateSkillMd(md.text, where);
  } catch (e) {
    return {
      hit: null,
      error: e instanceof Error ? e.message : String(e),
    };
  }
  const folder = fm.name;
  const projectFiles: ProjectFile[] = [];
  for (const e of files) {
    // Zip-slip guard: reject paths containing '..' or that would escape
    // skills/<folder>/ after normalization.
    const parts = e.path.split("/");
    if (parts.some((p) => p === "..")) {
      return { hit: null, error: `${where} 包含非法路径（..）：${e.path}` };
    }
    const target = `skills/${folder}/${e.path}`;
    if (!target.startsWith(`skills/${folder}/`)) {
      return { hit: null, error: `${where} 包含非法路径：${e.path}` };
    }
    projectFiles.push({ path: target, content: e.text });
  }
  return {
    hit: {
      source: "local",
      id: `local:${folder}:${files.length}`,
      name: fm.name,
      description: fm.description,
      folder,
      localFiles: projectFiles,
    },
    error: null,
  };
}

/** Read a .zip File into zero or more SkillHits. */
export async function readZipSkills(file: File): Promise<LocalReadResult> {
  const buf = new Uint8Array(await file.arrayBuffer());
  const zipEntries = await unzip(buf);
  const raw: RawEntry[] = zipEntries.map((e) => ({ path: e.name, text: e.text }));
  return collectHits(normalizeEntries(raw), file.name);
}

/** Read a FileList produced by <input webkitdirectory>. */
export async function readFolderSkills(fileList: FileList): Promise<LocalReadResult> {
  const raw: RawEntry[] = [];
  for (let i = 0; i < fileList.length; i++) {
    const f = fileList[i];
    const rel =
      (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
    // Decode bytes as UTF-8. Binary assets are out of v1 scope.
    const text = await f.text();
    raw.push({ path: rel, text });
  }
  return collectHits(normalizeEntries(raw), "文件夹");
}

function collectHits(entries: RawEntry[], sourceLabel: string): LocalReadResult {
  const groups = groupBySkillFolder(entries);
  const hits: SkillHit[] = [];
  const errors: string[] = [];
  for (const [folderKey, files] of groups) {
    const { hit, error } = materializeHit(folderKey, files, sourceLabel);
    if (error) errors.push(error);
    if (hit) hits.push(hit);
  }
  if (hits.length === 0 && errors.length === 0) {
    errors.push(`${sourceLabel} 中未发现 SKILL.md`);
  }
  return { hits, errors };
}
