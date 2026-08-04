export type SkillWorkbenchOperation = "create" | "optimize";
export type SkillWorkbenchState =
  | "running"
  | "ready"
  | "failed"
  | "cancelled"
  | "expired"
  | "published";

export interface SkillWorkbenchSource {
  kind: "skill-center" | "upload";
  name?: string;
  skillId?: string;
  version?: string;
  region?: string;
  projectName?: string;
  skillSpaceId?: string;
  sha256?: string;
}

export type SkillWorkbenchActivity =
  | {
      id: string;
      kind: "status" | "thinking" | "message";
      status: "running" | "done";
      text: string;
    }
  | {
      id: string;
      kind: "tool";
      status: "running" | "done";
      name: string;
      args?: unknown;
      response?: unknown;
    };

export interface SkillWorkbenchFile {
  path: string;
  size: number;
}

export interface SkillWorkbenchTask {
  jobId: string;
  operation: SkillWorkbenchOperation;
  intent: string;
  revision: number;
  source?: SkillWorkbenchSource | null;
  state: SkillWorkbenchState;
  stage: string;
  activities: SkillWorkbenchActivity[];
  name?: string;
  description?: string;
  skillMd?: string;
  files: SkillWorkbenchFile[];
  validation?: { valid: boolean; errors: string[]; warnings?: string[] };
  error?: string;
}

export interface SkillWorkbenchCapability {
  enabled: boolean;
  reason: string;
  operations: SkillWorkbenchOperation[];
  maxUploadBytes?: number;
}

export interface SkillCenterOptimizationSource {
  kind: "skill-center";
  skillId: string;
  version: string;
  region: string;
  projectName?: string;
  skillSpaceId?: string;
  name: string;
  description?: string;
}
