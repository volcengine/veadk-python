import { Loader2 } from "lucide-react";
import {
  COMPARISON_SESSION_WARNING_BODY,
  type ComparisonSessionViewModel,
} from "./comparisonSessionViewModel";

export interface ComparisonSessionActionSlotProps {
  placement: "toolbar" | "alert";
  viewModel: ComparisonSessionViewModel;
  onStartSession: () => void;
}

function SessionAction({
  viewModel,
  onStartSession,
}: Omit<ComparisonSessionActionSlotProps, "placement">) {
  return (
    <div className="cw-comparison-session-action">
      <button
        type="button"
        className={
          viewModel.sessionReady ? "cw-btn cw-btn-soft" : "cw-btn cw-btn-primary"
        }
        data-comparison-session-action="true"
        disabled={viewModel.actionDisabled}
        title={viewModel.actionProblem || undefined}
        onClick={onStartSession}
      >
        {viewModel.sessionStarting ? (
          <Loader2 className="cw-i cw-spin" />
        ) : null}
        {viewModel.actionLabel}
      </button>
      {viewModel.actionProblem ? <span>{viewModel.actionProblem}</span> : null}
    </div>
  );
}

export function ComparisonSessionActionSlot({
  placement,
  viewModel,
  onStartSession,
}: ComparisonSessionActionSlotProps) {
  const alertOwnsAction = viewModel.showAlert;
  if ((placement === "alert") !== alertOwnsAction) return null;

  if (placement === "toolbar") {
    return (
      <SessionAction
        viewModel={viewModel}
        onStartSession={onStartSession}
      />
    );
  }

  return (
    <div
      id="cw-comparison-session-warning"
      className="cw-comparison-session-alert"
      role="alert"
    >
      <div className="cw-comparison-session-alert-copy">
        {viewModel.showWarning ? (
          <div className="cw-comparison-session-warning-copy">
            <strong>{viewModel.warningTitle}</strong>
            <p>{COMPARISON_SESSION_WARNING_BODY}</p>
          </div>
        ) : null}
        {viewModel.failureTitle ? (
          <div className="cw-comparison-session-failure">
            <strong>{viewModel.failureTitle}</strong>
            <p>{viewModel.failureDetail}</p>
          </div>
        ) : null}
      </div>
      <SessionAction
        viewModel={viewModel}
        onStartSession={onStartSession}
      />
    </div>
  );
}
