import {
  comparisonSessionStatus,
  type ComparisonSessionState,
} from "./comparisonSessionState";

export const COMPARISON_SESSION_WARNING_BODY =
  "当前对话、指标和判定来自上一版配置，不能继续用于本轮比较。开启后将清空旧内容，并重新启动全部测试环境。";

const STALE_WARNING_TITLE = "对照配置已变化，请开启新 Session";
const STALE_COMPOSER_PLACEHOLDER = "配置已变化，请先开启新 Session";
const READ_ONLY_CARD_STATUS = "上一 Session · 只读";

export interface ComparisonSessionViewModelOptions {
  problem: string;
  canSendReadySession: boolean;
  readyComposerPlaceholder: string;
}

export interface ComparisonSessionViewModel {
  showAlert: boolean;
  showWarning: boolean;
  warningTitle: string;
  failureTitle: string;
  failureDetail: string;
  actionLabel:
    | "开启 Session"
    | "重新开启 Session"
    | "开启新 Session"
    | "正在开启";
  actionDisabled: boolean;
  actionProblem: string;
  transcriptReadOnly: boolean;
  composerDisabled: boolean;
  composerPlaceholder: string;
  requireConfirmation: boolean;
  cardStatusLabel: string | null;
  sessionReady: boolean;
  sessionStarting: boolean;
  verdictEditable: boolean;
}

export function comparisonSessionViewModel(
  state: ComparisonSessionState,
  options: ComparisonSessionViewModelOptions,
): ComparisonSessionViewModel {
  const status = comparisonSessionStatus(state);
  const hasActiveSession = state.activeSessionRevision !== null;
  const sessionReady = status === "ready";
  const sessionStarting = status === "starting";
  const transcriptReadOnly = hasActiveSession && status !== "ready";
  const showWarning =
    hasActiveSession && (status === "stale" || status === "failed");
  const failureStage =
    state.failure?.stage === "run" ? "启动调试环境" : "创建 ADK Session";

  let actionLabel: ComparisonSessionViewModel["actionLabel"];
  if (status === "starting") {
    actionLabel = "正在开启";
  } else if (!hasActiveSession) {
    actionLabel = "开启 Session";
  } else if (status === "ready") {
    actionLabel = "重新开启 Session";
  } else {
    actionLabel = "开启新 Session";
  }

  let composerPlaceholder = options.readyComposerPlaceholder;
  if (transcriptReadOnly) {
    composerPlaceholder = STALE_COMPOSER_PLACEHOLDER;
  } else if (status === "starting") {
    composerPlaceholder = "正在开启 Session";
  } else if (status !== "ready") {
    composerPlaceholder = "请先开启 Session";
  }

  return {
    showAlert: showWarning || Boolean(state.failure),
    showWarning,
    warningTitle: STALE_WARNING_TITLE,
    failureTitle: state.failure
      ? `开启 Session 失败 · ${state.failure.variantName}`
      : "",
    failureDetail: state.failure
      ? `${failureStage}：${state.failure.message}`
      : "",
    actionLabel,
    actionDisabled: status === "starting" || Boolean(options.problem),
    actionProblem: options.problem,
    transcriptReadOnly,
    composerDisabled:
      status !== "ready" || !options.canSendReadySession,
    composerPlaceholder,
    requireConfirmation: hasActiveSession,
    cardStatusLabel: transcriptReadOnly ? READ_ONLY_CARD_STATUS : null,
    sessionReady,
    sessionStarting,
    verdictEditable: sessionReady,
  };
}
