import type { EvaluatorTrialReport } from "./types";

export type MutationFeedback = {
  kind: "success" | "error";
  message: string;
  publishedVersion?: number;
};

export type PublishActionTone = "idle" | "running" | "success" | "error";

export interface PublishActionPresentation {
  label: string;
  disabled: boolean;
  status: string | null;
  tone: PublishActionTone;
}

export function latestVersionForDraft(
  versions: Array<{ version: number; sourceDraftRevision: number }>,
  draftRevision: number,
): number | null {
  return versions.reduce<number | null>(
    (latest, item) =>
      item.sourceDraftRevision === draftRevision
        ? Math.max(latest ?? item.version, item.version)
        : latest,
    null,
  );
}

export function buildPublishActionPresentation({
  isRunning,
  publishedVersion,
  feedback,
}: {
  isRunning: boolean;
  publishedVersion: number | null;
  feedback: MutationFeedback | null;
}): PublishActionPresentation {
  if (isRunning) {
    return {
      label: "正在发布…",
      disabled: true,
      status: "正在发布版本",
      tone: "running",
    };
  }
  const effectivePublishedVersion = publishedVersion
    ?? (feedback?.kind === "success" ? feedback.publishedVersion ?? null : null);
  if (effectivePublishedVersion !== null) {
    return {
      label: `已发布 v${effectivePublishedVersion}`,
      disabled: true,
      status: feedback?.kind === "success"
        ? feedback.message
        : `已发布 v${effectivePublishedVersion}`,
      tone: "success",
    };
  }
  if (feedback?.kind === "error") {
    return {
      label: "重新发布",
      disabled: false,
      status: `发布失败：${feedback.message}`,
      tone: "error",
    };
  }
  if (feedback?.kind === "success") {
    return {
      label: "已发布",
      disabled: true,
      status: feedback.message,
      tone: "success",
    };
  }
  return {
    label: "发布版本",
    disabled: false,
    status: null,
    tone: "idle",
  };
}

type EvaluatorTrialResult = EvaluatorTrialReport["results"][number];

export type CalibrationTone = "accurate" | "inaccurate" | "unavailable";

export interface CalibrationPresentation {
  humanJudgment: string;
  evaluatorJudgment: string;
  verdict: string;
  explanation: string;
  tone: CalibrationTone;
}

function businessJudgment(outcome: "pass" | "fail"): string {
  return outcome === "pass" ? "通过" : "不通过";
}

export function buildCalibrationPresentation(
  result: EvaluatorTrialResult,
): CalibrationPresentation {
  const humanJudgment = businessJudgment(result.expectedOutcome);
  const explanation = result.errorMessage || result.reason || "未提供判断理由";

  if (result.outcome === "infra_error" || result.outcome === "cancelled") {
    return {
      humanJudgment,
      evaluatorJudgment: result.outcome === "infra_error" ? "执行异常" : "已取消",
      verdict: "本次校准未完成，暂时无法判断准确性",
      explanation,
      tone: "unavailable",
    };
  }

  if (result.matchesExpectation) {
    return {
      humanJudgment,
      evaluatorJudgment: businessJudgment(result.outcome),
      verdict: "判断一致，评估器本次判断准确",
      explanation,
      tone: "accurate",
    };
  }

  return {
    humanJudgment,
    evaluatorJudgment: businessJudgment(result.outcome),
    verdict: "判断不一致，评估器本次存在误判",
    explanation,
    tone: "inaccurate",
  };
}
