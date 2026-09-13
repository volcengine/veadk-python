import { type ComponentPropsWithoutRef, type CSSProperties, type ReactNode, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Button } from "../../primitives/Button";
import { Label } from "../../primitives/Label";
import { Loading } from "../../primitives/Loading";
import { ScrollArea } from "../../primitives/ScrollArea";
import "../../tokens/glass-surface.css";
import "./LongRunningState.css";

export type LongRunningStep = {
  /** 稳定且唯一的步骤标识 */
  id: string;
  /** 步骤名称，支持动态更新 */
  title: string;
  /** 步骤的最新详情或完成记录，支持正文或无行号 CodeBlock 等 React 内容；完成后由调用方保留记录 */
  details?: ReactNode;
};

export type LongRunningStateProps = Omit<ComponentPropsWithoutRef<"div">, "children"> & {
  /** 按执行顺序展示的步骤 */
  steps: readonly LongRunningStep[];
  /** 当前执行步骤的 id；null 表示没有正在执行的步骤 */
  currentStep: string | null;
  /** 已完成步骤的 id；不传时将当前步骤之前的步骤视为已完成，全部结束时请显式传入 */
  completedSteps?: readonly string[];
  /** 当前查看的历史步骤，null 跟随正在执行的步骤；不传时组件内部管理 */
  selectedStep?: string | null;
  /** 切换详情时触发，返回 null 表示恢复跟随当前进度，不会改变 currentStep */
  onSelectedStepChange?: (stepId: string | null) => void;
  /** 左侧任务标题，可传 null 隐藏 */
  heading?: ReactNode;
  /** 右侧详情的最大高度，超过后使用 ScrollArea 滚动，默认 360px */
  detailsMaxHeight?: CSSProperties["maxHeight"];
};

const ease = [0.22, 1, 0.36, 1] as const;
const markerSpring = { type: "spring", bounce: 0, duration: 0.32 } as const;

function StepDetails({ children, reducedMotion }: { children: ReactNode; reducedMotion: boolean }) {
  return (
    <motion.div
      className="studio-long-running-state__details-content"
      initial={{ opacity: reducedMotion ? 1 : 0.7 }}
      animate={{ opacity: 1 }}
      transition={{ duration: reducedMotion ? 0 : 0.16, ease }}
    >
      {children}
    </motion.div>
  );
}

function StepMarker({ running, completed, reducedMotion }: { running: boolean; completed: boolean; reducedMotion: boolean }) {
  const [keepLoading, setKeepLoading] = useState(running);
  useEffect(() => { if (running) setKeepLoading(true); }, [running]);

  return <span className="studio-long-running-state__marker-content">
    <svg className="studio-long-running-state__marker-shape" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <motion.circle cx="12" cy="12" fill="currentColor"
        initial={false}
        animate={{ r: completed ? 10 : 4, opacity: running ? 0 : 1 }}
        transition={reducedMotion ? { duration: 0 } : { ...markerSpring, opacity: { duration: 0.14 } }}
      />
      <motion.path d="m7.5 12 3 3 6-6" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
        initial={false}
        animate={{ pathLength: completed ? 1 : 0, opacity: completed ? 1 : 0 }}
        transition={{ duration: reducedMotion ? 0 : 0.2, delay: !reducedMotion && completed ? 0.08 : 0, ease }}
      />
    </svg>
    <motion.span className="studio-long-running-state__marker-loading"
      initial={false}
      animate={{ opacity: running ? 1 : 0, scale: reducedMotion || running ? 1 : 0.92 }}
      transition={reducedMotion ? { duration: 0 } : { ...markerSpring, opacity: { duration: 0.14 } }}
      onAnimationComplete={() => { if (!running) setKeepLoading(false); }}
    >
      {(running || keepLoading) && <Loading size={40} decorative />}
    </motion.span>
  </span>;
}

export function LongRunningState({ steps, currentStep, completedSteps, selectedStep, onSelectedStepChange, heading = "任务执行进度", detailsMaxHeight = 360, className = "", ...props }: LongRunningStateProps) {
  const instanceId = useId();
  const reducedMotion = Boolean(useReducedMotion());
  const [historyStep, setHistoryStep] = useState<string | null>(null);
  const currentIndex = steps.findIndex(step => step.id === currentStep);
  const activeStep = steps[currentIndex];
  const completedIds = new Set(completedSteps ?? steps.slice(0, Math.max(0, currentIndex)).map(step => step.id));
  const completed = steps.filter(step => step.id !== currentStep && completedIds.has(step.id));
  const historyIsAvailable = steps.some(step => step.id === historyStep && completedIds.has(step.id));
  const requestedStep = selectedStep === undefined ? historyStep : selectedStep;
  const viewedStep = steps.find(step => step.id === requestedStep && (step.id === currentStep || completedIds.has(step.id)))
    ?? activeStep ?? completed[completed.length - 1];
  const isHistory = Boolean(viewedStep && viewedStep.id !== currentStep);
  const canReturnToCurrent = isHistory && Boolean(activeStep);
  const detailsId = `${instanceId}-details`;
  const detailsTitleId = `${instanceId}-details-title`;
  const detailsRef = useRef<HTMLDivElement>(null);
  const currentButtonRef = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => {
    if (detailsRef.current) detailsRef.current.scrollTop = 0;
  }, [viewedStep?.id]);
  useEffect(() => {
    if (selectedStep === undefined && historyStep !== null && (!historyIsAvailable || historyStep === currentStep)) setHistoryStep(null);
  }, [selectedStep, historyStep, historyIsAvailable, currentStep]);

  function selectStep(stepId: string) {
    const next = stepId === currentStep ? null : stepId;
    if (selectedStep === undefined) setHistoryStep(next);
    onSelectedStepChange?.(next);
  }

  return (
    <div {...props} className={`studio-long-running-state ${className}`.trim()}>
      <div className="studio-long-running-state__layout">
        <div className="studio-long-running-state__navigation">
          <header className="studio-long-running-state__overview">
            {heading != null && <h3 className="studio-long-running-state__heading">{heading}</h3>}
            <span className="studio-long-running-state__progress">已完成 {completed.length} / {steps.length}</span>
            <span className="studio-long-running-state__progress-track" aria-hidden="true">
              <motion.span
                initial={false}
                animate={{ scaleX: steps.length ? completed.length / steps.length : 0 }}
                transition={reducedMotion ? { duration: 0 } : markerSpring}
              />
            </span>
          </header>
          <ol className="studio-long-running-state__steps" aria-label={props["aria-label"] ?? "执行步骤"}>
            {steps.map((step, index) => {
              const isCurrent = step.id === currentStep;
              const isCompleted = !isCurrent && completedIds.has(step.id);
              const isSelected = step.id === viewedStep?.id;
              const status = isCurrent ? "进行中" : isCompleted ? "已完成" : "待执行";
              const titleId = `${instanceId}-${step.id}-title`;
              return (
                <li
                  key={step.id}
                  className="studio-long-running-state__step"
                  data-current={isCurrent || undefined}
                  data-completed={isCompleted || undefined}
                  data-selected={isSelected || undefined}
                  aria-current={isCurrent ? "step" : undefined}
                >
                  {index < steps.length - 1 && <span className="studio-long-running-state__connector" aria-hidden="true">
                    <motion.span initial={false} animate={{ scaleY: isCompleted ? 1 : 0 }} transition={reducedMotion ? { duration: 0 } : markerSpring} />
                  </span>}
                  <button
                    ref={isCurrent ? currentButtonRef : undefined}
                    type="button"
                    className="studio-long-running-state__header"
                    disabled={!isCurrent && !isCompleted}
                    aria-pressed={isSelected}
                    aria-controls={detailsId}
                    aria-label={`${step.title}，${status}`}
                    onClick={() => selectStep(step.id)}
                  >
                    {isSelected && <motion.span
                      className="studio-long-running-state__selection"
                      layoutId={`${instanceId}-selection`}
                      initial={false}
                      transition={reducedMotion ? { duration: 0 } : markerSpring}
                      aria-hidden="true"
                    />}
                    <span className="studio-long-running-state__marker" aria-hidden="true">
                      <StepMarker running={isCurrent} completed={isCompleted} reducedMotion={reducedMotion} />
                    </span>
                    <span id={titleId} className="studio-long-running-state__title">
                      <AnimatePresence initial={false}>
                        <motion.span
                          key={step.title}
                          className="studio-long-running-state__title-text"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: reducedMotion ? 0 : 0.16, ease }}
                        >
                          {step.title}
                        </motion.span>
                      </AnimatePresence>
                    </span>
                    <svg className="studio-long-running-state__step-chevron" width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <path d="m6 4 4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
        <motion.div
          className="studio-long-running-state__details studio-glass-surface"
          data-surface="glass"
          data-history={isHistory || undefined}
          initial={reducedMotion ? false : { opacity: 0, scale: 0.985 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={reducedMotion ? { duration: 0 } : { type: "spring", bounce: 0, duration: 0.4 }}
        >
          <div className="studio-long-running-state__details-header">
            <div className="studio-long-running-state__details-heading">
              <h4 id={detailsTitleId} title={viewedStep?.title}>{viewedStep?.title ?? "等待任务开始"}</h4>
              {viewedStep && <Label variant="status" className="studio-long-running-state__status">{isHistory ? "已完成" : "进行中"}</Label>}
            </div>
            <Button
              variant="ghost"
              className="studio-long-running-state__return"
              data-visible={canReturnToCurrent || undefined}
              aria-hidden={!canReturnToCurrent || undefined}
              disabled={!canReturnToCurrent}
              tabIndex={canReturnToCurrent ? undefined : -1}
              onClick={() => {
                if (activeStep) {
                  selectStep(activeStep.id);
                  currentButtonRef.current?.focus({ preventScroll: true });
                }
              }}
            >返回当前步骤</Button>
          </div>
          <ScrollArea ref={detailsRef} id={detailsId} className="studio-long-running-state__details-scroll" maxHeight={detailsMaxHeight} tabIndex={0} role="region" aria-labelledby={detailsTitleId}>
            <div className="studio-long-running-state__details-stage">
              {viewedStep && viewedStep.details != null && (
                <StepDetails key={viewedStep.id} reducedMotion={reducedMotion}>
                  {viewedStep.details}
                </StepDetails>
              )}
            </div>
          </ScrollArea>
        </motion.div>
      </div>
      <span className="studio-long-running-state__announcement" role="status" aria-live="polite" aria-atomic="true">
        {activeStep ? `正在执行：${activeStep.title}` : completed.length === steps.length && steps.length > 0 ? "所有步骤已完成" : "没有进行中的步骤"}
      </span>
    </div>
  );
}
