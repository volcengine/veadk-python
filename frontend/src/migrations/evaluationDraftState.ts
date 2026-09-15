import type { MigrationTaskState } from "../adk/migrations";

export function needsEvaluationDraftHydration(
  taskId: string,
  evaluationEnabled: boolean,
  draftTaskId: string,
): boolean {
  return evaluationEnabled && taskId !== draftTaskId;
}

export function evaluationSettingsAreLocked(
  taskState: MigrationTaskState,
  hasSavedDataset: boolean,
  datasetSaveFailed: boolean,
): boolean {
  if (hasSavedDataset) return true;
  if (datasetSaveFailed) return false;
  return taskState !== "awaiting_upload";
}
