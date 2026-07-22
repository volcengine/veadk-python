export const SKILL_MODELS = [
  "doubao-seed-2-0-pro-260215",
  "deepseek-v4-flash-260425",
] as const;

export type SkillModel = (typeof SKILL_MODELS)[number];

export type SkillCandidateStatus = "queued" | "running" | "succeeded" | "failed";

export type SkillCandidateStage =
  | "provisioning"
  | "generating"
  | "validating"
  | "packaging"
  | "completed"
  | "failed";

export interface SkillFile {
  path: string;
  size: number;
}

export interface SkillValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface SkillCandidate {
  id: string;
  model: string;
  modelLabel: string;
  status: SkillCandidateStatus;
  stage: SkillCandidateStage;
  name?: string;
  description?: string;
  skillMd?: string;
  files: SkillFile[];
  validation?: SkillValidation;
  durationMs?: number;
  error?: string;
  published?: boolean;
  skillId?: string;
  version?: string;
}

export interface SkillCreationJob {
  id: string;
  prompt: string;
  status: "running" | "completed";
  candidates: SkillCandidate[];
}

export interface PublishedSkill {
  skillId: string;
  name?: string;
  version?: string;
  skillSpaceIds: string[];
  message?: string;
}

export interface PublishSkillOptions {
  skillSpaceIds: string[];
  projectName?: string;
  skillId?: string;
}
