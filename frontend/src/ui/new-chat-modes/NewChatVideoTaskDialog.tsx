import { useEffect, useId, useRef, useState, type SVGProps } from "react";
import { createPortal } from "react-dom";
import {
  currentVideoTaskStatus,
  formatVideoTaskElapsed,
  videoTaskModeLabel,
  videoTaskSteps,
  type VideoGenerationTask,
} from "./video-task";
import { TextShimmer } from "../text-shimmer/TextShimmer";
import "./new-chat-video-task-dialog.css";

export interface NewChatVideoTaskDialogProps {
  open: boolean;
  task: VideoGenerationTask | null;
  onClose: () => void;
  onRetry: () => void;
  onDownload: () => void;
}

function CloseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m7 7 10 10M17 7 7 17" />
    </svg>
  );
}

function DownloadIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M12 3.5v11m-4-4 4 4 4-4" />
      <path d="M5 19.5h14" />
    </svg>
  );
}

function LoadingIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <circle
        cx="8"
        cy="8"
        r="5.5"
        stroke="currentColor"
        strokeWidth="1.5"
        opacity="0.22"
      />
      <path
        d="M8 2.5A5.5 5.5 0 0 1 13.5 8"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function NewChatVideoTaskDialog({
  open,
  task,
  onClose,
  onRetry,
  onDownload,
}: NewChatVideoTaskDialogProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [clockMs, setClockMs] = useState(() => Date.now());
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open || !task) return;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() =>
      titleRef.current?.focus(),
    );
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], video[controls], [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (document.activeElement === titleRef.current) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocusRef.current?.isConnected)
        previousFocusRef.current.focus();
    };
  }, [open, task?.localId]);

  useEffect(() => {
    if (
      !open
      || task?.status !== "generating"
      || task.generationStartedAt === null
    ) return;
    const tick = () => setClockMs(Date.now());
    tick();
    const timer = window.setInterval(tick, 1_000);
    return () => window.clearInterval(timer);
  }, [open, task?.localId, task?.runId, task?.status, task?.generationStartedAt]);

  if (!open || !task) return null;

  const steps = videoTaskSteps(task);
  const running = task.status === "optimizing" || task.status === "generating";
  const retryLabel =
    task.errorStage === "optimization" ? "重试提示词优化" : "重试视频生成";
  const taskLabel = videoTaskModeLabel(task.resolvedMode ?? task.requestedMode);
  const requiresModelActivation = task.error.includes("尚未开通");
  const activeStatus = currentVideoTaskStatus(task);
  const elapsed = task.generationStartedAt === null
    ? ""
    : formatVideoTaskElapsed(clockMs - task.generationStartedAt);
  const providerPhase = task.providerStatus === "queued"
    ? "等待模型调度"
    : task.providerStatus === "running"
      ? "模型生成中"
      : "正在提交任务";
  const generationHint = task.providerStatus === "queued"
    ? "任务已提交，模型开始处理后状态会自动更新"
    : "这可能持续数分钟，完成后将在这里显示视频预览";

  return createPortal(
    <div
      className="new-chat-video-task-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className={`new-chat-video-task-dialog is-${task.status}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-busy={running || undefined}
      >
        <header className="new-chat-video-task-dialog__head">
          <div>
            <h2 ref={titleRef} id={titleId} tabIndex={-1}>
              视频生成任务
            </h2>
            <p>
              {taskLabel} · {task.generationModel}
            </p>
          </div>
          <button
            type="button"
            className="new-chat-video-task-dialog__close"
            onClick={onClose}
            aria-label="关闭视频生成任务弹窗"
          >
            <CloseIcon />
          </button>
        </header>

        <div className="new-chat-video-task-dialog__body">
          <ol
            className="new-chat-video-task-steps"
            aria-label="视频生成进度"
            aria-live="polite"
            aria-atomic="true"
          >
            {steps.map((step) => (
              <li key={step.id} className={`is-${step.status}`}>
                <span className="new-chat-video-task-step__label">
                  {step.status === "active" ? (
                    <LoadingIcon className="new-chat-video-task-step__loading" />
                  ) : null}
                  <span>{step.label}</span>
                </span>
              </li>
            ))}
          </ol>

          {task.error ? (
            <div className="new-chat-video-task-error" role="alert">
              <p>{task.error}</p>
            </div>
          ) : null}

          {task.optimizedPrompt ? (
            <section
              className="new-chat-video-task-prompt"
              aria-labelledby={`${titleId}-prompt`}
            >
              <h3 id={`${titleId}-prompt`}>优化后的提示词</h3>
              <p>{task.optimizedPrompt}</p>
            </section>
          ) : null}

          {task.status === "generating" ? (
            <div className="new-chat-video-task-preview is-loading">
              <LoadingIcon className="new-chat-video-task-preview__loading" />
              <TextShimmer
                as="strong"
                duration={2.2}
                spread={18}
                aria-live="polite"
              >
                {activeStatus}
              </TextShimmer>
              <div
                className="new-chat-video-task-progress"
                role="progressbar"
                aria-label={`${taskLabel}处理进度`}
                aria-valuetext={`${activeStatus}${elapsed ? `，已等待${elapsed}` : ""}`}
              >
                <span aria-hidden="true" />
              </div>
              <div className="new-chat-video-task-progress__meta">
                <span>{providerPhase}</span>
                {elapsed ? <span>已等待 {elapsed}</span> : null}
              </div>
              <span>{generationHint}</span>
            </div>
          ) : task.output ? (
            <div className="new-chat-video-task-preview">
              <video
                src={task.output.previewUrl}
                controls
                playsInline
                preload="metadata"
                aria-label="生成结果预览"
              />
            </div>
          ) : null}
        </div>

        <footer className="new-chat-video-task-dialog__actions">
          <p>
            {running
              ? "可以关闭弹窗，任务会继续在后台运行"
              : task.status === "success"
                ? "视频已生成，可预览或下载"
                : requiresModelActivation
                  ? "请先在模型控制台开通服务，再重试生成"
                  : "修正问题后可重试当前步骤"}
          </p>
          <div>
            <button
              type="button"
              className="new-chat-video-task-button"
              onClick={onClose}
            >
              关闭
            </button>
            {task.status === "error" ? (
              <button
                type="button"
                className="new-chat-video-task-button is-primary"
                onClick={onRetry}
              >
                {retryLabel}
              </button>
            ) : task.output ? (
              <button
                type="button"
                className="new-chat-video-task-button is-primary"
                onClick={onDownload}
              >
                <DownloadIcon />
                下载视频
              </button>
            ) : null}
          </div>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
