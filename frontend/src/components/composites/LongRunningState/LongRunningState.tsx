import { type ComponentPropsWithoutRef, type ReactNode, useId } from "react";
import { AnimatePresence, motion, useIsPresent, useReducedMotion } from "motion/react";
import { Loading } from "../../primitives/Loading";
import "./LongRunningState.css";

export type LongRunningStep = {
  /** 稳定且唯一的步骤标识 */
  id: string;
  /** 步骤名称，支持动态更新 */
  title: string;
  /** 在右侧面板显示当前步骤的细节，支持文字、进度信息或 React 内容 */
  details?: ReactNode;
};

export type LongRunningStateProps = Omit<ComponentPropsWithoutRef<"div">, "children"> & {
  /** 按执行顺序展示的步骤 */
  steps: readonly LongRunningStep[];
  /** 当前执行步骤的 id；null 表示没有正在执行的步骤 */
  currentStep: string | null;
};

const ease = [0.22, 1, 0.36, 1] as const;

function StepDetails({ children, reducedMotion, labelledBy }: { children: ReactNode; reducedMotion: boolean; labelledBy: string }) {
  const isPresent = useIsPresent();
  return (
    <motion.div
      className="studio-long-running-state__details-content"
      data-exiting={!isPresent || undefined}
      layout={reducedMotion ? false : "position"}
      initial={{ opacity: 0, filter: reducedMotion ? "none" : "blur(3px)", y: reducedMotion ? 0 : 3 }}
      animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
      exit={{ opacity: 0, filter: reducedMotion ? "none" : "blur(3px)", y: reducedMotion ? 0 : -3 }}
      transition={{ duration: reducedMotion ? 0 : 0.24, ease }}
      role="region"
      aria-labelledby={labelledBy}
      aria-hidden={!isPresent || undefined}
      inert={!isPresent || undefined}
    >
      {children}
    </motion.div>
  );
}

export function LongRunningState({ steps, currentStep, className = "", ...props }: LongRunningStateProps) {
  const instanceId = useId();
  const reducedMotion = Boolean(useReducedMotion());
  const activeStep = steps.find(step => step.id === currentStep);

  return (
    <div {...props} className={`studio-long-running-state ${className}`.trim()}>
      <div className="studio-long-running-state__layout">
        <ol className="studio-long-running-state__steps" aria-label={props["aria-label"] ?? "执行步骤"}>
          {steps.map(step => {
            const isCurrent = step.id === currentStep;
            const titleId = `${instanceId}-${step.id}-title`;
            return (
              <li
                key={step.id}
                className="studio-long-running-state__step"
                data-current={isCurrent || undefined}
                aria-current={isCurrent ? "step" : undefined}
              >
                <div className="studio-long-running-state__header">
                  <span className="studio-long-running-state__marker" aria-hidden="true">
                    <AnimatePresence initial={false}>
                      <motion.span
                        key={isCurrent ? "loading" : "dot"}
                        className="studio-long-running-state__marker-content"
                        initial={{ opacity: 0, scale: reducedMotion ? 1 : 0.75 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: reducedMotion ? 1 : 0.75 }}
                        transition={{ duration: reducedMotion ? 0 : 0.18, ease }}
                      >
                        {isCurrent ? <Loading size={32} decorative /> : <span className="studio-long-running-state__dot" />}
                      </motion.span>
                    </AnimatePresence>
                  </span>
                  <span id={titleId} className="studio-long-running-state__title">
                    <AnimatePresence initial={false} mode="popLayout">
                      <motion.span
                        key={`${step.title}-${isCurrent ? "current" : "idle"}`}
                        className="studio-long-running-state__title-text"
                        initial={{ opacity: 0, filter: reducedMotion ? "none" : "blur(2px)", y: reducedMotion ? 0 : 2 }}
                        animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
                        exit={{ opacity: 0, filter: reducedMotion ? "none" : "blur(2px)", y: reducedMotion ? 0 : -2 }}
                        transition={{ duration: reducedMotion ? 0 : 0.24, ease }}
                      >
                        {step.title}
                      </motion.span>
                    </AnimatePresence>
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
        <motion.div
          className="studio-long-running-state__details"
          layout={reducedMotion ? false : "size"}
          transition={{ layout: { duration: reducedMotion ? 0 : 0.28, ease } }}
        >
          <div className="studio-long-running-state__details-stage">
            <AnimatePresence initial={false}>
              {activeStep && activeStep.details != null && (
                <StepDetails key={activeStep.id} reducedMotion={reducedMotion} labelledBy={`${instanceId}-${activeStep.id}-title`}>
                  {activeStep.details}
                </StepDetails>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
      <span className="studio-long-running-state__announcement" role="status" aria-live="polite" aria-atomic="true">
        {activeStep ? `正在执行：${activeStep.title}` : "没有进行中的步骤"}
      </span>
    </div>
  );
}
