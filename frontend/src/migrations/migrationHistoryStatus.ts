import type {
  MigrationEvaluationState,
  MigrationTask,
  MigrationTaskState,
} from "../adk/migrations";

export type MigrationHistoryStatusTone =
  | "neutral"
  | "active"
  | "success"
  | "warning"
  | "error";

export interface MigrationHistoryStatus {
  labelKey: string;
  tone: MigrationHistoryStatusTone;
}

const SUCCESSFUL_MIGRATION_STATES = new Set<MigrationTaskState>([
  "succeeded",
  "succeeded_with_warnings",
  "partial",
]);

const RUNNING_EVALUATION_STATES = new Set<MigrationEvaluationState>([
  "preparing",
  "deploying",
  "executing",
  "judging",
  "aggregating",
]);

const MIGRATION_STATUS: Record<MigrationTaskState, MigrationHistoryStatus> = {
  awaiting_upload: { labelKey: "state.awaitingUpload", tone: "neutral" },
  analyzing: { labelKey: "state.analyzing", tone: "active" },
  needs_input: { labelKey: "state.needsInput", tone: "warning" },
  analysis_ready: { labelKey: "state.analysisReady", tone: "warning" },
  migrating: { labelKey: "state.migrating", tone: "active" },
  validating: { labelKey: "state.validating", tone: "active" },
  packaging: { labelKey: "state.packaging", tone: "active" },
  succeeded: { labelKey: "state.succeeded", tone: "success" },
  succeeded_with_warnings: {
    labelKey: "state.succeededWithWarnings",
    tone: "warning",
  },
  partial: { labelKey: "state.partial", tone: "warning" },
  failed: { labelKey: "state.failed", tone: "error" },
  cancelled: { labelKey: "state.cancelled", tone: "neutral" },
  expired: { labelKey: "historyStatus.resultUnavailable", tone: "neutral" },
};

function evaluationStatus(
  state: MigrationEvaluationState,
): MigrationHistoryStatus | null {
  if (state === "disabled" || state === "completed") return null;
  if (state === "pending") {
    return { labelKey: "historyStatus.evaluationPending", tone: "active" };
  }
  if (RUNNING_EVALUATION_STATES.has(state)) {
    return { labelKey: "historyStatus.evaluationRunning", tone: "active" };
  }
  if (state === "waiting_dataset") {
    return { labelKey: "historyStatus.waitingDataset", tone: "warning" };
  }
  if (state === "waiting_environment") {
    return { labelKey: "historyStatus.waitingEnvironment", tone: "warning" };
  }
  if (state === "failed") {
    return { labelKey: "historyStatus.evaluationFailed", tone: "warning" };
  }
  if (state === "blocked") {
    return { labelKey: "historyStatus.evaluationBlocked", tone: "warning" };
  }
  return {
    labelKey: "historyStatus.evaluationCancelled",
    tone: "neutral",
  };
}

export function migrationHistoryStatus(
  task: MigrationTask,
): MigrationHistoryStatus {
  const migrationState =
    task.state === "expired" && task.persistence?.state === "saved"
      ? "succeeded"
      : task.state;
  const migrationStatus = MIGRATION_STATUS[migrationState];
  if (!SUCCESSFUL_MIGRATION_STATES.has(migrationState)) {
    return migrationStatus;
  }
  if (!task.evaluation?.enabled) return migrationStatus;
  return evaluationStatus(task.evaluation.state) ?? migrationStatus;
}

export function isMigrationEnvironmentExpired(
  task: MigrationTask,
  now: number,
): boolean {
  if (task.state === "expired") return true;
  const expiresAt = Date.parse(task.expiresAt);
  return Number.isFinite(expiresAt) && now >= expiresAt;
}
