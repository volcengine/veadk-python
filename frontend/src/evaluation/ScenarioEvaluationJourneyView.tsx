import type { ReactNode } from "react";
import type {
  JourneyActionId,
  JourneyStepId,
  JourneyStepState,
  ScenarioEvaluationJourney,
} from "./scenarioEvaluationJourney";

const stateLabels: Record<JourneyStepState, string> = {
  not_started: "未开始",
  active: "当前步骤",
  complete: "已完成",
  needs_attention: "需处理",
};

export interface ScenarioEvaluationJourneyViewProps {
  journey: ScenarioEvaluationJourney;
  selectedStepId: JourneyStepId;
  onSelectStep: (stepId: JourneyStepId) => void;
  onPrevious: () => void;
  onPrimaryAction: (action: JourneyActionId) => void;
  primaryActionDisabled?: boolean;
  primaryActionReason?: string;
  children: ReactNode;
}

function stepMarker(
  state: JourneyStepState,
  number: number,
): string {
  if (state === "complete") return "✓";
  if (state === "needs_attention") return "!";
  return String(number);
}

export function ScenarioEvaluationJourneyView({
  journey,
  selectedStepId,
  onSelectStep,
  onPrevious,
  onPrimaryAction,
  primaryActionDisabled = false,
  primaryActionReason,
  children,
}: ScenarioEvaluationJourneyViewProps) {
  const selectedStep = journey.steps.find((step) => step.id === selectedStepId)
    ?? journey.steps[journey.currentStepNumber - 1];
  const viewingCurrentStep = selectedStep.id === journey.currentStepId;

  return (
    <section className="se-wizard" aria-label="场景评测流程">
      <nav className="se-wizard-nav" aria-label="场景评测步骤">
        <header>
          <span>发布前质量检查</span>
          <h2>场景评测</h2>
          <p>共 {journey.totalSteps} 步</p>
        </header>
        <ol>
          {journey.steps.map((step) => {
            const isCurrent = step.id === journey.currentStepId;
            const selected = step.id === selectedStep.id;
            return (
              <li
                key={step.id}
                className={`se-wizard-step is-${step.state}${selected ? " is-selected" : ""}`}
              >
                <button
                  type="button"
                  aria-current={isCurrent ? "step" : undefined}
                  aria-pressed={selected}
                  aria-disabled={step.locked}
                  disabled={step.locked}
                  onClick={() => onSelectStep(step.id)}
                >
                  <span className="se-wizard-marker" aria-hidden="true">
                    {stepMarker(step.state, step.number)}
                  </span>
                  <span className="se-wizard-step-copy">
                    <strong>{step.label}</strong>
                    <small>{step.summary}</small>
                  </span>
                  <em>{stateLabels[step.state]}</em>
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      <main className="se-wizard-main">
        <header className="se-wizard-heading">
          <span>第 {selectedStep.number} 步，共 {journey.totalSteps} 步</span>
          <h2>{selectedStep.label}</h2>
          <p>{selectedStep.goal}</p>
        </header>

        <aside className="se-wizard-guide" aria-label="本步说明">
          <div>
            <strong>为什么要做</strong>
            <p>{selectedStep.why}</p>
          </div>
          <div>
            <strong>完成本步需要</strong>
            <ul>
              {selectedStep.requirements.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </aside>

        <div className="se-wizard-content" data-step-content aria-live="off">
          {children}
        </div>

        <footer className="se-wizard-actions">
          <button
            type="button"
            disabled={selectedStep.number === 1}
            onClick={onPrevious}
          >
            上一步
          </button>
          <div>
            {(primaryActionReason || journey.nextAction.disabledReason) && (
              <small>{primaryActionReason ?? journey.nextAction.disabledReason}</small>
            )}
            {viewingCurrentStep ? (
              <button
                type="button"
                className="is-primary"
                disabled={primaryActionDisabled}
                onClick={() => onPrimaryAction(journey.nextAction.id)}
              >
                {journey.nextAction.label}
              </button>
            ) : (
              <button
                type="button"
                className="is-primary"
                onClick={() => onSelectStep(journey.currentStepId)}
              >
                返回第 {journey.currentStepNumber} 步
              </button>
            )}
          </div>
        </footer>
      </main>
    </section>
  );
}
