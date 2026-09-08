import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CopyButton } from "@openai/apps-sdk-ui/components/Button";
import { Check, Copy } from "@openai/apps-sdk-ui/components/Icon";
import { useTranslation } from "react-i18next";
import type { CloudProvider } from "../adk/cloudProvider";
import {
  runtimeConsoleUrl,
  runtimeLogErrorText,
  runtimeLogLevel,
  streamRuntimeLogs,
  type RuntimeLogTarget,
} from "../adk/runtimeLogs";
import {
  SandboxCloseIcon,
  SandboxSpinnerIcon,
  SandboxTerminalIcon,
} from "./icons/SandboxControlIcons";
import "./RuntimeLogsDialog.css";

const MAX_RENDERED_LINES = 1_000;

function ExternalLinkIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14 5h5v5M19 5l-8 8" />
      <path d="M18 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </svg>
  );
}

function RuntimeLogErrorDetails({
  error,
  onRetry,
}: {
  error: string;
  onRetry: () => void;
}) {
  const { t } = useTranslation("conversation");
  return (
    <div className="runtime-logs-error-detail" role="alert">
      <div className="runtime-logs-error-head">
        <strong>{t("runtimeLogs.errorTitle")}</strong>
        <div className="runtime-logs-error-actions">
          <CopyButton
            className="runtime-logs-error-copy"
            copyValue={error}
            color="secondary"
            variant="ghost"
            size="sm"
            uniform
            pill={false}
            title={t("runtimeLogs.copyError")}
            aria-label={t("runtimeLogs.copyError")}
          >
            {({ copied }) => copied ? <Check /> : <Copy />}
          </CopyButton>
          <button className="runtime-logs-error-retry" type="button" onClick={onRetry}>
            {t("runtimeLogs.retry")}
          </button>
        </div>
      </div>
      <pre>{error}</pre>
    </div>
  );
}

export function RuntimeLogsDialog({
  open,
  provider,
  sessionId,
  target,
  onClose,
}: {
  open: boolean;
  provider: CloudProvider;
  sessionId?: string;
  target: RuntimeLogTarget;
  onClose: () => void;
}) {
  const { t } = useTranslation("conversation");
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const followTailRef = useRef(true);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  const [status, setStatus] = useState<"idle" | "connecting" | "live" | "retrying">("idle");
  const [logs, setLogs] = useState("");
  const [error, setError] = useState("");
  const [retryKey, setRetryKey] = useState(0);
  const [consoleUrl, setConsoleUrl] = useState("");
  const [resolvedInstanceName, setResolvedInstanceName] = useState("");
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      )].filter((item) => item.offsetParent !== null);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
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
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousFocusRef.current?.isConnected) previousFocusRef.current.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    followTailRef.current = true;
    setLogs("");
    setError("");
    setResolvedInstanceName(target.instanceName ?? "");
    if (!target.instanceName && !sessionId) {
      setStatus("idle");
      setConsoleUrl("");
      return;
    }
    const controller = new AbortController();
    setStatus("connecting");
    setConsoleUrl(
      target.instanceName
        ? runtimeConsoleUrl(
          provider,
          target.region,
          target.runtimeId,
          target.instanceName,
        )
        : "",
    );
    void (async () => {
      try {
        for await (const event of streamRuntimeLogs({
          runtimeId: target.runtimeId,
          region: target.region,
          instanceName: target.instanceName,
          sessionId,
          signal: controller.signal,
        })) {
          if (event.type === "context") {
            setResolvedInstanceName(event.instanceName);
            setConsoleUrl(event.consoleUrl);
            setStatus("live");
            setError("");
          } else if (event.type === "logs") {
            setLogs(event.text);
            setStatus("live");
            setError("");
          } else if (event.type === "error") {
            setStatus("retrying");
            setError(runtimeLogErrorText(event));
          }
        }
      } catch (cause) {
        if (controller.signal.aborted) return;
        setStatus("idle");
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    })();
    return () => controller.abort();
  }, [open, provider, retryKey, sessionId, target.instanceName, target.region, target.runtimeId]);

  useEffect(() => {
    const element = logRef.current;
    if (!open || !element || !followTailRef.current) return;
    element.scrollTop = element.scrollHeight;
  }, [logs, open]);

  const lines = useMemo(() => {
    const occurrences = new Map<string, number>();
    return logs.split(/\r?\n/).slice(-MAX_RENDERED_LINES).map((text) => {
      const occurrence = (occurrences.get(text) ?? 0) + 1;
      occurrences.set(text, occurrence);
      return { id: `${text}\u0000${occurrence}`, text };
    });
  }, [logs]);
  const resolvedConsoleUrl = consoleUrl || (
    resolvedInstanceName
      ? runtimeConsoleUrl(provider, target.region, target.runtimeId, resolvedInstanceName)
      : ""
  );
  const statusLabel = t(`runtimeLogs.statuses.${status}`);

  if (!open) return null;
  return createPortal(
    <div
      className="runtime-logs-layer"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <section
        ref={dialogRef}
        className="runtime-logs-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="runtime-logs-head">
          <span className="runtime-logs-head-icon" aria-hidden="true">
            <SandboxTerminalIcon />
          </span>
          <div className="runtime-logs-heading">
            <h2 id={titleId}>{t("runtimeLogs.title")}</h2>
            <p>{t("runtimeLogs.description")}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="runtime-logs-close"
            aria-label={t("runtimeLogs.close")}
            onClick={onClose}
          >
            <SandboxCloseIcon />
          </button>
        </header>

        <div className="runtime-logs-meta">
          <span className={`runtime-logs-status is-${status}`} aria-live="polite">
            <i aria-hidden="true" />
            {statusLabel}
          </span>
          <span className="runtime-logs-instance-label">{t("runtimeLogs.instanceId")}</span>
          {resolvedInstanceName && resolvedConsoleUrl ? (
            <a
              className="runtime-logs-instance-link"
              href={resolvedConsoleUrl}
              target="_blank"
              rel="noreferrer"
              title={resolvedInstanceName}
            >
              <span>{resolvedInstanceName}</span>
              <ExternalLinkIcon />
            </a>
          ) : (
            <span className="runtime-logs-instance-empty">{t("runtimeLogs.waitingInstance")}</span>
          )}
          {target.requestId ? (
            <span className="runtime-logs-request" title={target.requestId}>
              {t("runtimeLogs.request", { id: target.requestId })}
            </span>
          ) : null}
        </div>

        <div
          ref={logRef}
          className="runtime-logs-output"
          role="log"
          aria-label={t("runtimeLogs.ariaLabel")}
          aria-live="off"
          onScroll={(event) => {
            const element = event.currentTarget;
            followTailRef.current =
              element.scrollHeight - element.scrollTop - element.clientHeight <= 32;
          }}
        >
          {!target.instanceName && !sessionId ? (
            <div className="runtime-logs-empty">
              <SandboxTerminalIcon />
              <strong>{t("runtimeLogs.notCapturedTitle")}</strong>
              <span>{t("runtimeLogs.notCapturedDescription")}</span>
            </div>
          ) : status === "connecting" && !logs ? (
            <div className="runtime-logs-empty">
              <SandboxSpinnerIcon className="spin" />
              <strong>{t("runtimeLogs.connectingTitle")}</strong>
              <span>{t("runtimeLogs.connectingDescription")}</span>
            </div>
          ) : error && !logs ? (
            <RuntimeLogErrorDetails
              error={error}
              onRetry={() => setRetryKey((value) => value + 1)}
            />
          ) : lines.length === 0 || (lines.length === 1 && lines[0].text === "") ? (
            <div className="runtime-logs-empty">
              <strong>{t("runtimeLogs.emptyTitle")}</strong>
              <span>{t("runtimeLogs.emptyDescription")}</span>
            </div>
          ) : (
            <>
              {error ? (
                <RuntimeLogErrorDetails
                  error={error}
                  onRetry={() => setRetryKey((value) => value + 1)}
                />
              ) : null}
              <div className="runtime-logs-lines">
                {lines.map((line, index) => (
                  <div
                    key={line.id}
                    className={`runtime-log-line is-${runtimeLogLevel(line.text)}`}
                  >
                    <span className="runtime-log-index" aria-hidden="true">
                      {String(index + 1).padStart(3, "0")}
                    </span>
                    <span className="runtime-log-text">{line.text || " "}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <footer className="runtime-logs-foot">
          <span>{t("runtimeLogs.retention", { count: MAX_RENDERED_LINES })}</span>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
