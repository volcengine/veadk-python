import type {
  EvaluatorDraft,
  EvaluatorTrialReport,
  EvaluatorVersion,
  ScenarioEvaluationWorkspaceData,
} from "./types";

export interface SceneEvaluatorGroup {
  sceneVersionId: string;
  sceneName: string;
  drafts: EvaluatorDraft[];
  versions: EvaluatorVersion[];
  latestPublishedVersionIds: string[];
  ordinaryCheckCount: number;
  severeCheckCount: number;
  calibrationState: "not_started" | "accurate" | "inaccurate" | "unavailable";
  calibrationBlockReason: string | null;
  publishState: "draft" | "partial" | "published";
}

export interface CombinedCalibrationPresentation {
  humanJudgment: string;
  evaluatorJudgment: string;
  verdict: string;
  explanation: string;
  tone: "accurate" | "inaccurate" | "unavailable";
  hardFailure: boolean;
}

function latestCurrentVersion(
  draft: EvaluatorDraft,
  versions: EvaluatorVersion[],
): EvaluatorVersion | null {
  return versions
    .filter((version) =>
      version.evaluatorId === draft.evaluatorId
      && version.sourceDraftRevision === draft.revision)
    .sort((left, right) => right.version - left.version)[0] ?? null;
}

function calibrationStateForTrials(
  trials: Array<EvaluatorTrialReport | null>,
): SceneEvaluatorGroup["calibrationState"] {
  if (trials.some((trial) => !trial)) return "not_started";
  const current = trials.filter((trial): trial is EvaluatorTrialReport => Boolean(trial));
  if (current.some((trial) => trial.results.some((result) =>
    result.outcome === "infra_error" || result.outcome === "cancelled"))) {
    return "unavailable";
  }
  if (new Set(current.map((trial) => trial.datasetVersionId)).size !== 1) {
    return "unavailable";
  }
  const sampleIds = current.map((trial) =>
    trial.results.map((result) => result.sampleId).sort());
  if (
    sampleIds.length === 0
    || sampleIds[0].length === 0
    || sampleIds.some((ids) => ids.join("\n") !== sampleIds[0].join("\n"))
  ) {
    return "unavailable";
  }
  for (const sampleId of sampleIds[0]) {
    const results = current.map((trial) =>
      trial.results.find((result) => result.sampleId === sampleId));
    if (results.some((result) => !result)) return "unavailable";
    const complete = results.filter(
      (result): result is EvaluatorTrialReport["results"][number] => Boolean(result),
    );
    const expectedOutcomes = new Set(complete.map((result) => result.expectedOutcome));
    if (expectedOutcomes.size !== 1) return "unavailable";
    const combinedOutcome = complete.some((result) => result.outcome === "fail")
      ? "fail"
      : "pass";
    if (combinedOutcome !== [...expectedOutcomes][0]) return "inaccurate";
  }
  return "accurate";
}

export function buildSceneEvaluatorGroups(
  workspace: ScenarioEvaluationWorkspaceData,
): SceneEvaluatorGroup[] {
  return workspace.scenes.map((scene) => {
    const drafts = workspace.evaluatorDrafts.filter(
      (draft) => draft.sceneVersionId === scene.sceneVersionId,
    );
    const versions = workspace.evaluators.filter(
      (version) => version.sceneVersionId === scene.sceneVersionId,
    );
    const latestPublishedVersionIds = drafts
      .map((draft) => ({
        evaluatorId: draft.evaluatorId,
        version: latestCurrentVersion(draft, versions),
      }))
      .filter((item): item is { evaluatorId: string; version: EvaluatorVersion } =>
        Boolean(item.version))
      .sort((left, right) => left.evaluatorId.localeCompare(right.evaluatorId))
      .map((item) => item.version.evaluatorVersionId);
    const currentTrials = drafts.map((draft) =>
      workspace.evaluatorTrials
        .filter((trial) =>
          trial.evaluatorId === draft.evaluatorId
          && trial.evaluatorRevision === draft.revision)
        .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))[0]
        ?? null);
    const calibrationState = drafts.length === 0
      ? "not_started"
      : calibrationStateForTrials(currentTrials);
    const missingTrialCount = currentTrials.filter((trial) => !trial).length;
    const calibrationBlockReason = drafts.length === 0
      ? "尚未配置检查，请先添加或生成至少一项检查"
      : calibrationState === "not_started"
        ? `还有 ${missingTrialCount} 项检查未完成本轮校准`
      : calibrationState === "inaccurate"
        ? "场景评估器综合判断与人工判断不一致，请调整检查项后重新试跑"
        : calibrationState === "unavailable"
          ? "本轮校准未完成，请修复执行问题后重新试跑"
          : null;

    return {
      sceneVersionId: scene.sceneVersionId,
      sceneName: scene.name,
      drafts,
      versions,
      latestPublishedVersionIds,
      ordinaryCheckCount: drafts.filter((draft) => !draft.hardFailure).length,
      severeCheckCount: drafts.filter((draft) => draft.hardFailure).length,
      calibrationState,
      calibrationBlockReason,
      publishState: latestPublishedVersionIds.length === 0
        ? "draft"
        : latestPublishedVersionIds.length === drafts.length
          ? "published"
          : "partial",
    };
  });
}

export function unpublishedEvaluatorDrafts(
  group: SceneEvaluatorGroup,
): EvaluatorDraft[] {
  return group.drafts.filter(
    (draft) => !latestCurrentVersion(draft, group.versions),
  );
}

export function combineSceneEvaluatorTrialResults(
  expectedOutcome: "pass" | "fail",
  checks: Array<{
    label: string;
    hardFailure: boolean;
    result: EvaluatorTrialReport["results"][number];
  }>,
): CombinedCalibrationPresentation {
  const unavailableChecks = checks.filter(({ result }) =>
    result.outcome === "infra_error" || result.outcome === "cancelled");
  if (unavailableChecks.length > 0) {
    return {
      humanJudgment: expectedOutcome === "pass" ? "通过" : "不通过",
      evaluatorJudgment: "执行异常",
      verdict: "本次校准未完成，暂时无法判断准确性",
      explanation: unavailableChecks
        .map(({ label, result }) =>
          `${label}：${result.errorMessage || result.reason || "检查未完成"}`)
        .join("；"),
      tone: "unavailable",
      hardFailure: false,
    };
  }
  const failedChecks = checks.filter(({ result }) => result.outcome === "fail");
  const hardFailure = failedChecks.some(({ hardFailure: severe }) => severe);
  const combinedOutcome = failedChecks.length > 0 ? "fail" : "pass";
  const matchesExpectation = combinedOutcome === expectedOutcome;
  const decisiveChecks = hardFailure
    ? failedChecks.filter(({ hardFailure: severe }) => severe)
    : failedChecks;

  return {
    humanJudgment: expectedOutcome === "pass" ? "通过" : "不通过",
    evaluatorJudgment: combinedOutcome === "pass" ? "通过" : "不通过",
    verdict: matchesExpectation
      ? "判断一致，场景评估器本次判断准确"
      : "判断不一致，场景评估器本次存在误判",
    explanation: decisiveChecks
      .map(({ label, result }) => `${label}：${result.reason || "不符合标准"}`)
      .join("；") || "全部检查均符合标准",
    tone: matchesExpectation ? "accurate" : "inaccurate",
    hardFailure,
  };
}
