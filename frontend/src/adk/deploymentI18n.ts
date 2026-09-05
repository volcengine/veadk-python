import { activeLocale, adkT } from "./i18n";

export interface LocalizableDeployStage {
  phase?: string;
  message?: string;
  messageCode?: string;
  buildLog?: {
    status?: "running" | "complete" | "error" | string;
  };
}

const HAN_TEXT = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/u;

const MESSAGE_CODE_KEYS: Record<string, string> = {
  "deploy.build.logs_syncing": "client.deploymentProgress.buildLogsSyncing",
  "deploy.build.logs_complete": "client.deploymentProgress.buildLogsComplete",
  "deploy.build.failed_logs_synced": "client.deploymentProgress.buildFailedLogsSynced",
  "deploy.build.logs_unavailable": "client.deploymentProgress.buildLogsUnavailable",
  "deploy.build.final_logs_unavailable": "client.deploymentProgress.finalBuildLogsUnavailable",
};

const PHASE_KEYS: Record<string, string> = {
  prepare: "client.deploymentProgress.preparing",
  upload: "client.deploymentProgress.uploading",
  build: "client.deploymentProgress.building",
  deploy: "client.deploymentProgress.deploying",
  publish: "client.deploymentProgress.publishing",
  evaluation: "client.deploymentProgress.evaluating",
  update: "client.deploymentProgress.updating",
  complete: "client.deploymentProgress.completing",
  github: "client.deploymentProgress.github",
};

/** Resolve deployment progress from stable codes or phases across all locales. */
export function localizeDeployStageMessage(
  stage: LocalizableDeployStage,
): string {
  const original = stage.message?.trim() ?? "";
  const codedKey = stage.messageCode
    ? MESSAGE_CODE_KEYS[stage.messageCode]
    : undefined;
  if (codedKey) return adkT(codedKey);

  // Preserve provider detail that is already in the active language. Older
  // Studio servers send Chinese-only prose, so non-Chinese locales fall back
  // to the stable phase instead of exposing the server implementation locale.
  if (
    original &&
    (activeLocale().toLowerCase() === "zh-cn" || !HAN_TEXT.test(original))
  ) {
    return original;
  }

  if (stage.phase === "build" && stage.buildLog?.status) {
    const buildLogKey = {
      running: "client.deploymentProgress.buildLogsSyncing",
      complete: "client.deploymentProgress.buildLogsComplete",
      error: "client.deploymentProgress.buildLogsUnavailable",
    }[stage.buildLog.status];
    if (buildLogKey) return adkT(buildLogKey);
  }

  const phaseKey = stage.phase ? PHASE_KEYS[stage.phase] : undefined;
  if (phaseKey) return adkT(phaseKey);
  return original || adkT("client.deploymentProgress.inProgress");
}
