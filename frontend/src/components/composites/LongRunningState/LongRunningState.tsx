import { type ComponentPropsWithoutRef, type CSSProperties, type ReactNode, useId, useLayoutEffect, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ScrollArea } from "../../primitives/ScrollArea";
import "./LongRunningState.css";

export type LongRunningStep = {
  /** 稳定且唯一的步骤标识 */
  id: string;
  /** 当前进度名称，支持动态更新 */
  title: string;
  /** 当前步骤的具体内容，支持文字或 React 内容 */
  details?: ReactNode;
};

export type LongRunningStateProps = Omit<ComponentPropsWithoutRef<"div">, "children"> & {
  /** 按执行顺序提供的步骤 */
  steps: readonly LongRunningStep[];
  /** 当前执行步骤的 id；null 表示没有正在执行的步骤 */
  currentStep: string | null;
  /** 已完成步骤的 id；任务结束时显式传入全部步骤，以显示完成状态并保留最终内容 */
  completedSteps?: readonly string[];
  /** 内容区最大高度，超过后使用 ScrollArea 滚动，默认 240px */
  detailsMaxHeight?: CSSProperties["maxHeight"];
};

const ease = [0.22, 1, 0.36, 1] as const;

export function LongRunningState({ steps, currentStep, completedSteps = [], detailsMaxHeight = 240, className = "", ...props }: LongRunningStateProps) {
  const titleId = `${useId()}-title`;
  const reducedMotion = Boolean(useReducedMotion());
  const detailsRef = useRef<HTMLDivElement>(null);
  const activeStep = steps.find(step => step.id === currentStep);
  const completedIds = new Set(completedSteps);
  const completed = steps.filter(step => completedIds.has(step.id));
  const complete = !activeStep && steps.length > 0 && completed.length === steps.length;
  const displayedStep = activeStep ?? completed[completed.length - 1];
  const title = activeStep?.title ?? (complete ? "任务已完成" : completed.length ? "等待下一步" : "等待任务开始");
  const state = activeStep ? "running" : complete ? "complete" : "idle";

  useLayoutEffect(() => {
    if (detailsRef.current) detailsRef.current.scrollTop = 0;
  }, [displayedStep?.id]);

  return (
    <div {...props} className={`studio-long-running-state ${className}`.trim()} data-state={state}>
      <div id={titleId} className="studio-long-running-state__title" role="status" aria-live="polite" aria-atomic="true">
        <AnimatePresence initial={false} mode="wait">
          <motion.span
            key={`${state}:${activeStep?.id ?? ""}:${title}`}
            className="studio-long-running-state__title-text"
            title={title}
            initial={{ opacity: reducedMotion ? 1 : 0, y: reducedMotion ? 0 : 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: reducedMotion ? 1 : 0, y: reducedMotion ? 0 : -12 }}
            transition={{ duration: reducedMotion ? 0 : 0.2, ease }}
          >{title}</motion.span>
        </AnimatePresence>
      </div>
      <div
        className="studio-long-running-state__bar"
        role="progressbar"
        aria-label="任务执行进度"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={activeStep ? undefined : complete ? 100 : 0}
        aria-valuetext={title}
      >
        <span className="studio-long-running-state__bar-indicator" />
      </div>
      <ScrollArea
        ref={detailsRef}
        className="studio-long-running-state__details"
        maxHeight={detailsMaxHeight}
        tabIndex={0}
        role="region"
        aria-labelledby={titleId}
      >
        <div className="studio-long-running-state__details-content">{displayedStep?.details}</div>
      </ScrollArea>
    </div>
  );
}
