import { useEffect, useId, useRef, useState, type SVGProps } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
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
  const { t, i18n } = useTranslation("newChat");
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

  const locale = i18n.resolvedLanguage ?? i18n.language;
  const steps = videoTaskSteps(task, locale);
  const running = task.status === "optimizing" || task.status === "generating";
  const retryLabel =
    task.errorStage === "optimization"
      ? t("video.task.retryOptimization")
      : t("video.task.retryGeneration");
  const taskLabel = videoTaskModeLabel(
    task.resolvedMode ?? task.requestedMode,
    locale,
  );
  const requiresModelActivation = task.error.includes("尚未开通");
  const activeStatus = currentVideoTaskStatus(task, locale);
  const elapsed = task.generationStartedAt === null
    ? ""
    : formatVideoTaskElapsed(clockMs - task.generationStartedAt, locale);
  const providerPhase = task.providerStatus === "queued"
    ? t("video.task.providerQueued")
    : task.providerStatus === "running"
      ? t("video.task.providerRunning")
      : t("video.task.providerSubmitting");
  const generationHint = task.providerStatus === "queued"
    ? t("video.task.queuedHint")
    : t("video.task.runningHint");

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
              {t("video.task.title")}
            </h2>
            <p>
              {taskLabel} · {task.generationModel}
            </p>
          </div>
          <button
            type="button"
            className="new-chat-video-task-dialog__close"
            onClick={onClose}
            aria-label={t("video.task.closeAria")}
          >
            <CloseIcon />
          </button>
        </header>

        <div className="new-chat-video-task-dialog__body">
          <ol
            className="new-chat-video-task-steps"
            aria-label={t("video.task.progressAria")}
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
              <h3 id={`${titleId}-prompt`}>{t("video.task.optimizedPrompt")}</h3>
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
                aria-label={t("video.task.processingAria", { task: taskLabel })}
                aria-valuetext={elapsed
                  ? t("video.task.waitingAria", { status: activeStatus, elapsed })
                  : activeStatus}
              >
                <span aria-hidden="true" />
              </div>
              <div className="new-chat-video-task-progress__meta">
                <span>{providerPhase}</span>
                {elapsed ? <span>{t("video.task.elapsed", { elapsed })}</span> : null}
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
                aria-label={t("video.task.previewAria")}
              />
            </div>
          ) : null}
        </div>

        <footer className="new-chat-video-task-dialog__actions">
          <p>
            {running
              ? t("video.task.backgroundHint")
              : task.status === "success"
                ? t("video.task.successHint")
                : requiresModelActivation
                  ? t("video.task.activationHint")
                  : t("video.task.retryHint")}
          </p>
          <div>
            <button
              type="button"
              className="new-chat-video-task-button"
              onClick={onClose}
            >
              {t("video.task.close")}
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
                {t("video.task.download")}
              </button>
            ) : null}
          </div>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
