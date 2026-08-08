import type { CloudRegion } from "../../adk/cloudProvider";

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
  region?: CloudRegion;
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

export interface SkillWorkbenchArtifactFile extends SkillWorkbenchFile {
  content: string;
}

export interface SkillWorkbenchArtifact {
  jobId: string;
  revision: number;
  sha256: string;
  name: string;
  description: string;
  files: SkillWorkbenchArtifactFile[];
}

export interface SkillWorkbenchPublishProgress {
  phase: "preparing" | "uploading" | "registering" | "activating" | "publishing";
  message: string;
}

export interface SkillWorkbenchPublishResult {
  skillId: string;
  version: string;
  skillSpaceIds: string[];
  disposition: "create-new" | "update-source";
  region: CloudRegion;
  projectName: string;
}

export type SkillWorkbenchRecoveryStatus =
  | "pending"
  | "ready"
  | "failed"
  | "unknown";

export interface SkillWorkbenchTask {
  jobId: string;
  operation: SkillWorkbenchOperation;
  intent: string;
  model?: string;
  style?: string;
  requestedName?: string;
  revision: number;
  toolId?: string;
  sessionId?: string;
  sessionTtlSeconds?: number;
  expiresAt?: string;
  recoveryAvailable?: boolean;
  recoveryStatus?: SkillWorkbenchRecoveryStatus;
  recoveredFromSnapshot?: boolean;
  source?: SkillWorkbenchSource | null;
  state: SkillWorkbenchState;
  stage: string;
  activities: SkillWorkbenchActivity[];
  name?: string;
  description?: string;
  skillMd?: string;
  files: SkillWorkbenchFile[];
  validation?: { valid: boolean; errors: string[]; warnings?: string[] };
  publication?: SkillWorkbenchPublishResult & { revision: number };
  error?: string;
}

export interface SkillWorkbenchProvisioningTask {
  jobId: string;
  operation: SkillWorkbenchOperation | null;
  intent: string;
  sourceName?: string;
  revision: 1;
  state: "provisioning";
  stage: "provisioning";
  createdAt: number;
}

export interface SkillWorkbenchTaskSummary {
  jobId: string;
  operation: SkillWorkbenchOperation;
  intent: string;
  revision: number;
  state: SkillWorkbenchState;
  stage: string;
  createdAt: number;
  name?: string;
  sourceName?: string;
  recoveryAvailable?: boolean;
  recoveryStatus?: SkillWorkbenchRecoveryStatus;
}

export type SkillWorkbenchTaskListItem =
  | SkillWorkbenchProvisioningTask
  | SkillWorkbenchTaskSummary;

export interface SkillWorkbenchCapability {
  enabled: boolean;
  reason: string;
  operations: SkillWorkbenchOperation[];
  maxUploadBytes?: number;
  models: Array<{ id: string; label: string }>;
  styles: Record<string, string>;
}

export interface SkillCenterOptimizationSource {
  kind: "skill-center";
  skillId: string;
  version: string;
  region: string;
  projectName?: string;
  skillSpaceId?: string;
  skillSpaceName?: string;
  name: string;
  description?: string;
}
