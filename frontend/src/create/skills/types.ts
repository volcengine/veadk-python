// Shared types for the multi-source skill picker (Skill Hub public marketplace,
// local folder/zip upload, and account-scoped Volcengine AgentKit SkillSpaces).

import type { ProjectFile } from "../project";

/** Discriminator for where a selected skill came from. */
export type SkillSource = "skillhub" | "local" | "skillspace" | "runtime";

/** A selectable hit from any source. Pickers produce these before the user
 *  toggles them into SelectedSkill. */
export interface SkillHit {
  source: SkillSource;
  /** Stable id within that source for dedup + React keys. */
  id: string;
  name: string;
  description: string;
  /** Folder name the skill should land in under skills/. Defaults from the
   *  source-specific id/slug/name if not set. */
  folder?: string;
  // Skill Hub (findskill.com / skills.volces.com) fields
  slug?: string;
  namespace?: string;
  sourceRepo?: string;
  downloadCount?: number;
  // Local upload fields: already-resolved ProjectFiles, prefixed skills/<name>/
  localFiles?: ProjectFile[];
  // SkillSpace (AgentKit account-scoped) fields
  skillSpaceId?: string;
  skillSpaceName?: string;
  skillSpaceRegion?: string;
  skillId?: string;
  version?: string;
}

/** A skill the user has added to the draft. Saved in YAML and materialized
 *  into project files when finish() runs. */
export interface SelectedSkill {
  source: SkillSource;
  /** Folder name used under skills/ in the generated project. */
  folder: string;
  name: string;
  description?: string;
  // Skill Hub
  slug?: string;
  namespace?: string;
  // Local: embedded file snapshot so the selection survives YAML round-trip / reload.
  localFiles?: ProjectFile[];
  // Runtime: opaque Skill already present in the deployed source image. It has
  // no browser-visible file snapshot and is preserved unless explicitly
  // removed or replaced by another source with the same folder.
  // SkillSpace: ids resolved to SKILL.md content at finish() time (SkillMd is
  // fetched live rather than serialized, since it can be large).
  skillSpaceId?: string;
  skillSpaceName?: string;
  skillSpaceRegion?: string;
  skillId?: string;
  version?: string;
}

/** Source-specific downloader signature. Resolves to ProjectFiles to merge
 *  into the generated project under skills/<folder>/. */
export type SkillDownloader = (s: SelectedSkill) => Promise<ProjectFile[]>;
