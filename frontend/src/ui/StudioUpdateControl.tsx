import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  getStudioUpdateStatus,
  getStudioUpdatePermissions,
  startStudioUpdate,
  type StudioUpdateProgressStage,
  type StudioUpdatePermissionStatus,
  type StudioUpdateStatus,
} from "../adk/client";
import { splitReleaseNotes } from "./releaseNotes";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./StudioUpdateControl.css";

const CHECK_INTERVAL_MS = 3 * 60 * 1000;
const RELEASE_POLL_INTERVAL_MS = 3_000;
const RELEASE_TIMEOUT_MS = 10 * 60 * 1000;
const COMPLETION_LOG_SETTLE_TIMEOUT_MS = 45_000;
const STUDIO_UPDATE_STORAGE_KEY = "veadk.studio.pending-update";
const STUDIO_UPDATE_HANDOFF_KEY = "veadk.studio.update-handoff";

type UpdatePhase =
  | "idle"
  | "confirm"
  | "checking-permissions"
  | "permission"
  | "submitting"
  | "published"
  | "error";
type PendingStudioUpdate = { targetVersion: string; startedAt: number };
type LogCopyState = "idle" | "copied" | "error";
type VisibleUpdateStage = Exclude<
  StudioUpdateProgressStage,
  "idle" | "complete" | "error"
>;

const UPDATE_STAGES: VisibleUpdateStage[] = [
  "permissions",
  "resolving",
  "downloading",
  "preparing",
  "provisioning",
  "scheduler",
  "submitting",
  "publishing",
];

function updateStageLabel(stage: string, t: TFunction, detailed = false): string {
  const key = detailed && UPDATE_STAGES.includes(stage as VisibleUpdateStage)
    ? `studioUpdate.steps.${stage}`
    : `studioUpdate.stages.${stage}`;
  return t(key, { defaultValue: stage || t("studioUpdate.stages.unknown") });
}

function formatElapsed(seconds: number, t: TFunction) {
  if (seconds < 60) return t("studioUpdate.duration.seconds", { count: seconds });
  return t("studioUpdate.duration.minutesSeconds", {
    minutes: Math.floor(seconds / 60),
    seconds: seconds % 60,
  });
}

function releaseReached(current: string, target: string) {
  if (current === target) return true;
  return /^\d{14}$/.test(current) && /^\d{14}$/.test(target) && current > target;
}

function deploymentLogComplete(lines: string[] | undefined) {
  return Boolean(
    lines?.some(
      (line) =>
        line.includes("部署应用成功") ||
        line.toLowerCase().includes("application deployed successfully"),
    ),
  );
}

function loadPendingUpdate(): PendingStudioUpdate | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STUDIO_UPDATE_STORAGE_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PendingStudioUpdate>;
    if (typeof value.targetVersion === "string" && typeof value.startedAt === "number") {
      return { targetVersion: value.targetVersion, startedAt: value.startedAt };
    }
  } catch {
    // Remove malformed state so it cannot keep the update control stuck.
  }
  window.localStorage.removeItem(STUDIO_UPDATE_STORAGE_KEY);
  return null;
}

function persistPendingUpdate(targetVersion: string, startedAt: number) {
  window.localStorage.setItem(
    STUDIO_UPDATE_STORAGE_KEY,
    JSON.stringify({ targetVersion, startedAt }),
  );
}

function clearPendingUpdate() {
  window.localStorage.removeItem(STUDIO_UPDATE_STORAGE_KEY);
}

function loadUpdateHandoff() {
  if (typeof window === "undefined") return "";
  return window.sessionStorage.getItem(STUDIO_UPDATE_HANDOFF_KEY) ?? "";
}

function persistUpdateHandoff(targetVersion: string) {
  window.sessionStorage.setItem(STUDIO_UPDATE_HANDOFF_KEY, targetVersion);
}

function clearUpdateHandoff() {
  window.sessionStorage.removeItem(STUDIO_UPDATE_HANDOFF_KEY);
}

function StudioUpdateIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M19.2 8.3A8 8 0 1 0 20 13" />
      <path d="M19.2 4.8v3.5h-3.5" />
      <path d="M12 7.8v7.7" />
      <path d="m9.2 12.7 2.8 2.8 2.8-2.8" />
    </svg>
  );
}

function VersionChevronIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="m4 6 4 4 4-4" />
    </svg>
  );
}

function VersionCheckIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="m3.5 8.2 2.8 2.8 6.2-6" />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M6.25 3.75H3.5v8.75h8.75V9.75" />
      <path d="M8.5 3.5h4v4" />
      <path d="m7.25 8.75 5-5" />
    </svg>
  );
}

function StudioUpdateLogPermissionNotice({ href }: { href: string }) {
  const { t } = useTranslation("ui");
  return (
    <div className="studio-update-permission-notice" role="status">
      <p>
        {t("studioUpdate.logPermissionPrefix")}
        <code>vefaas:GetApplicationRevisionLog</code>
        {t("studioUpdate.logPermissionSuffix")}
      </p>
      <a href={href} target="_blank" rel="noreferrer">
        {t("studioUpdate.openIamConsole")}
        <ExternalLinkIcon />
      </a>
    </div>
  );
}

function StudioUpdateLog({
  lines,
  phase,
  copyState,
  onCopy,
}: {
  lines: string[];
  phase: "active" | "complete" | "error";
  copyState: LogCopyState;
  onCopy: (lines: string[]) => void;
}) {
  const { t } = useTranslation("ui");
  const scrollRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);
  const [visibleLines, setVisibleLines] = useState(lines);

  useEffect(() => {
    if (lines.length) setVisibleLines(lines);
  }, [lines]);

  useEffect(() => {
    const root = scrollRef.current;
    if (root && followRef.current) root.scrollTop = root.scrollHeight;
  }, [visibleLines]);

  return (
    <section className="studio-update-live-log" aria-label={t("studioUpdate.deploymentProgress")}>
      <div className="studio-update-log-header">
        <span>
          <i className={`is-${phase}`} aria-hidden />
          {t("studioUpdate.deploymentProgress")}
          <small>{phase === "active" ? t("studioUpdate.live") : phase === "complete" ? t("studioUpdate.completed") : t("studioUpdate.stopped")}</small>
        </span>
        <button
          type="button"
          onClick={() => onCopy(visibleLines)}
          disabled={!visibleLines.length}
        >
          {copyState === "copied"
            ? t("studioUpdate.copied")
            : copyState === "error"
              ? t("studioUpdate.copyFailed")
              : t("studioUpdate.copyLog")}
        </button>
      </div>
      <div
        ref={scrollRef}
        className="studio-update-log-lines"
        role="log"
        aria-live="off"
        aria-busy={phase === "active"}
        tabIndex={0}
        onScroll={(event) => {
          const root = event.currentTarget;
          followRef.current =
            root.scrollHeight - root.scrollTop - root.clientHeight < 24;
        }}
      >
        {visibleLines.length ? (
          visibleLines.map((line, index) => <div key={`${index}-${line}`}>{line}</div>)
        ) : (
          <p>{phase === "active" ? t("studioUpdate.waitingForLogs") : t("studioUpdate.noLogs")}</p>
        )}
      </div>
    </section>
  );
}

export function StudioUpdateControl({
  variant = "default",
}: {
  variant?: "default" | "feature-link";
}) {
  const { t } = useTranslation("ui");
  const [initialPending] = useState<PendingStudioUpdate | null>(loadPendingUpdate);
  const [status, setStatus] = useState<StudioUpdateStatus | null>(null);
  const [phase, setPhase] = useState<UpdatePhase>(
    initialPending ? "submitting" : "idle",
  );
  const [dialogOpen, setDialogOpen] = useState(Boolean(initialPending));
  const [message, setMessage] = useState("");
  const [permissionStatus, setPermissionStatus] =
    useState<StudioUpdatePermissionStatus | null>(null);
  const [selectedVersion, setSelectedVersion] = useState(
    initialPending?.targetVersion ?? "",
  );
  const [versionMenuOpen, setVersionMenuOpen] = useState(false);
  const [logCopyState, setLogCopyState] = useState<LogCopyState>("idle");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const versionPickerRef = useRef<HTMLDivElement>(null);
  const targetVersionRef = useRef(initialPending?.targetVersion ?? "");
  const startedAtRef = useRef(initialPending?.startedAt ?? 0);
  const handoffTargetRef = useRef(loadUpdateHandoff());
  const completionDetectedAtRef = useRef(0);

  useEffect(() => {
    if (!versionMenuOpen) return;
    const closeMenu = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        !versionPickerRef.current?.contains(event.target)
      ) {
        setVersionMenuOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setVersionMenuOpen(false);
    };
    window.addEventListener("pointerdown", closeMenu);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeMenu);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [versionMenuOpen]);

  const refresh = useCallback(async () => {
    const next = await getStudioUpdateStatus(
      targetVersionRef.current || undefined,
      startedAtRef.current || undefined,
    );
    setStatus(next);
    return next;
  }, []);

  useEffect(() => {
    let active = true;
    const check = () => {
      void refresh().catch(() => {
        if (active) setStatus((current) => current);
      });
    };
    check();
    const timer = window.setInterval(check, CHECK_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  useEffect(() => {
    if (phase !== "submitting") return;
    const timer = window.setInterval(() => {
      void refresh()
        .then((next) => {
          const target = targetVersionRef.current;
          if (
            (target && releaseReached(next.currentVersion, target)) ||
            (!target && !next.available && Boolean(next.latestVersion))
          ) {
            const now = Date.now();
            if (!completionDetectedAtRef.current) {
              completionDetectedAtRef.current = now;
            }
            if (
              next.updateLogsVisible !== false &&
              !deploymentLogComplete(next.updateLogs) &&
              now - completionDetectedAtRef.current < COMPLETION_LOG_SETTLE_TIMEOUT_MS
            ) {
              return;
            }
            window.clearInterval(timer);
            completionDetectedAtRef.current = 0;
            const completedTarget = target || next.latestVersion;
            if (handoffTargetRef.current !== completedTarget) {
              persistUpdateHandoff(completedTarget);
              window.location.reload();
              return;
            }
            clearPendingUpdate();
            clearUpdateHandoff();
            handoffTargetRef.current = "";
            setPhase("published");
            setDialogOpen(true);
            setMessage(t("studioUpdate.messages.updated"));
            return;
          }
          completionDetectedAtRef.current = 0;
          if (next.state === "error") {
            window.clearInterval(timer);
            clearPendingUpdate();
            setPhase("error");
            setMessage(next.message || t("studioUpdate.messages.failed"));
            return;
          }
          if (Date.now() - startedAtRef.current > RELEASE_TIMEOUT_MS) {
            window.clearInterval(timer);
            clearPendingUpdate();
            setPhase("error");
            setMessage(t("studioUpdate.messages.timeout"));
          }
        })
        .catch(() => {
          // Replacing the current Revision may briefly interrupt this request.
        });
    }, RELEASE_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [phase, refresh, t]);

  useEffect(() => {
    if (phase !== "idle" || status?.state !== "updating") return;
    targetVersionRef.current = status.targetVersion;
    startedAtRef.current = status.startedAt || Date.now();
    persistPendingUpdate(status.targetVersion, startedAtRef.current);
    setSelectedVersion(status.targetVersion);
    setPhase("submitting");
  }, [phase, status]);

  useEffect(() => {
    if (phase !== "submitting") {
      setElapsedSeconds(0);
      return;
    }
    const updateElapsed = () => {
      const startedAt = startedAtRef.current || Date.now();
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1_000);
    return () => window.clearInterval(timer);
  }, [phase]);

  if (!status?.enabled) return null;
  const visible = status.available || status.state === "updating" || phase !== "idle";
  if (!visible) return null;
  const releases = status.releases ?? [];
  const targetVersion = selectedVersion || releases[0]?.version || status.latestVersion;
  const targetRelease = releases.find(
    (release) => release.version === targetVersion,
  );
  const targetReleaseNotes = splitReleaseNotes(targetRelease?.changelog ?? []);

  const beginUpdate = async () => {
    clearUpdateHandoff();
    handoffTargetRef.current = "";
    targetVersionRef.current = targetVersion;
    startedAtRef.current = Date.now();
    setPhase("checking-permissions");
    setMessage("");
    setLogCopyState("idle");
    try {
      const permissions = await getStudioUpdatePermissions();
      setPermissionStatus(permissions);
      if (!permissions.ready) {
        clearPendingUpdate();
        setPhase("permission");
        return;
      }
      setPermissionStatus(null);
      persistPendingUpdate(targetVersion, startedAtRef.current);
      setPhase("submitting");
      const result = await startStudioUpdate(targetVersion);
      targetVersionRef.current = result.version;
      persistPendingUpdate(result.version, startedAtRef.current);
      setMessage(t("studioUpdate.messages.submitted"));
    } catch (error) {
      if (
        error instanceof TypeError ||
        (error instanceof Error &&
          (error.name === "TimeoutError" || error.name === "AbortError"))
      ) {
        setMessage(t("studioUpdate.messages.connectionSwitched"));
        return;
      }
      clearPendingUpdate();
      setPhase("error");
      const fallbackMessage = error instanceof Error ? error.message : t("studioUpdate.messages.failed");
      try {
        const next = await refresh();
        setMessage(next.message || fallbackMessage);
      } catch {
        setMessage(fallbackMessage);
      }
    }
  };

  const updateLogs = status.updateLogs?.length
    ? status.updateLogs
    : (status.errorLog || status.progressMessage || message)
        .split("\n")
        .filter(Boolean);
  const updateSteps = UPDATE_STAGES.map((id) => ({
    id,
    label: updateStageLabel(id, t, true),
  }));
  const currentUpdateStepIndex = updateSteps.findIndex((item) => item.id === status.progressStage);
  const unknownProgressStage =
    phase === "submitting" &&
    status.progressStage !== "idle" &&
    currentUpdateStepIndex < 0;

  const copyUpdateLog = async (lines: string[]) => {
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setLogCopyState("copied");
    } catch {
      setLogCopyState("error");
    }
  };

  const retryUpdate = () => {
    setVersionMenuOpen(false);
    setLogCopyState("idle");
    setMessage("");
    setPermissionStatus(null);
    setSelectedVersion(targetVersionRef.current || releases[0]?.version || "");
    setPhase("confirm");
  };

  return (
    <>
      <button
        type="button"
        className={
          variant === "feature-link"
            ? "welcome-feature-link studio-update-trigger--feature"
            : `studio-update-trigger is-${phase}`
        }
        title={
          phase === "checking-permissions"
            ? t("studioUpdate.checkingPermissions")
            : phase === "permission"
              ? t("studioUpdate.authorizationRequired")
              : phase === "submitting"
            ? t("studioUpdate.updating")
            : phase === "published"
              ? t("studioUpdate.updated")
              : t("studioUpdate.updateToVersion", { version: status.latestVersion })
        }
        onClick={() => {
          if (phase === "published") {
            window.location.reload();
          } else if (
            phase === "checking-permissions" ||
            phase === "permission" ||
            phase === "submitting" ||
            phase === "error"
          ) {
            setDialogOpen(true);
          } else {
            setSelectedVersion(releases[0]?.version || status.latestVersion);
            setPhase("confirm");
            setDialogOpen(true);
          }
        }}
      >
        {variant !== "feature-link" && (
          <StudioUpdateIcon className="studio-update-icon" />
        )}
        {phase === "checking-permissions" ? (
          <TextShimmer as="span">{t("studioUpdate.checkPermissions")}</TextShimmer>
        ) : phase === "permission" ? (
          <span>{t("studioUpdate.authorizationNeeded")}</span>
        ) : phase === "submitting" ? (
          <TextShimmer as="span">{t("studioUpdate.updatingShort")}</TextShimmer>
        ) : phase === "published" ? (
          <span>{t("studioUpdate.refreshForNewVersion")}</span>
        ) : phase === "error" ? (
          <span>{t("studioUpdate.updateFailed")}</span>
        ) : variant === "feature-link" ? (
          <span>{t("studioUpdate.updateNow")}</span>
        ) : (
          <span>{t("studioUpdate.newVersionAvailable")}</span>
        )}
      </button>

      {dialogOpen && phase !== "idle" &&
        createPortal(
        <div className="confirm-scrim" role="presentation">
          <section
            className={`confirm-box studio-update-dialog${
              phase === "submitting" || phase === "published" || phase === "error"
                ? " is-progress"
                : ""
            }`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="studio-update-title"
          >
            <div className="studio-update-dialog-mark">
              <StudioUpdateIcon />
            </div>
            <div id="studio-update-title" className="confirm-title">
              {phase === "error"
                ? t("studioUpdate.dialog.failed")
                : phase === "checking-permissions"
                  ? t("studioUpdate.dialog.checkingPermissions")
                  : phase === "permission"
                    ? t("studioUpdate.dialog.authorizationRequired")
                : phase === "submitting"
                  ? t("studioUpdate.dialog.updating")
                  : phase === "published"
                    ? t("studioUpdate.dialog.completed")
                    : t("studioUpdate.dialog.newVersion")}
            </div>
            {phase === "checking-permissions" ? (
              <div className="studio-update-permission-checking" role="status">
                <TextShimmer as="p">{t("studioUpdate.permissionCheck")}</TextShimmer>
                <p>{t("studioUpdate.permissionCheckHint")}</p>
              </div>
            ) : phase === "permission" && permissionStatus ? (
              <div className="studio-update-authorization-panel">
                <p className="confirm-text">
                  {t("studioUpdate.missingPermissionCount", { count: permissionStatus.missingActions.length })}
                </p>
                <dl className="studio-update-authorization-principal">
                  <div>
                    <dt>{t("studioUpdate.functionRole")}</dt>
                    <dd>{permissionStatus.principalName || t("studioUpdate.currentRole")}</dd>
                  </div>
                  {permissionStatus.policyName && (
                    <div>
                      <dt>{t("studioUpdate.policyToUpdate")}</dt>
                      <dd>{permissionStatus.policyName}</dd>
                    </div>
                  )}
                </dl>
                <ol className="studio-update-authorization-steps">
                  <li>{t("studioUpdate.authorizationSteps.open")}</li>
                  <li>{t("studioUpdate.authorizationSteps.debug")}</li>
                  <li>{t("studioUpdate.authorizationSteps.return")}</li>
                </ol>
                <div className="studio-update-missing-actions">
                  <span>{t("studioUpdate.missingPermissions")}</span>
                  <ul>
                    {permissionStatus.missingActions.map((action) => (
                      <li key={action}><code>{action}</code></li>
                    ))}
                  </ul>
                </div>
                <a
                  className="studio-update-authorization-link"
                  href={permissionStatus.authorizationUrl || permissionStatus.iamConsoleUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {permissionStatus.authorizationUrl
                    ? t("studioUpdate.openPrefilledAuthorization")
                    : t("studioUpdate.openIamManually")}
                  <ExternalLinkIcon />
                </a>
                {!permissionStatus.authorizationUrl && (
                  <p className="studio-update-authorization-note">
                    {t("studioUpdate.noSafePolicy")}
                  </p>
                )}
              </div>
            ) : phase === "error" ? (
              <div className="studio-update-error-panel">
                <p className="confirm-text studio-update-error">{message}</p>
                <dl className="studio-update-error-meta">
                  <div>
                    <dt>{t("studioUpdate.failedStage")}</dt>
                    <dd>
                      {updateStageLabel(status.errorStage, t)}
                    </dd>
                  </div>
                  <div>
                    <dt>{t("studioUpdate.errorId")}</dt>
                    <dd>{status.errorId || t("studioUpdate.notGenerated")}</dd>
                  </div>
                </dl>
                {status.updateLogsVisible !== false && (
                  <StudioUpdateLog
                    lines={updateLogs}
                    phase="error"
                    copyState={logCopyState}
                    onCopy={(lines) => void copyUpdateLog(lines)}
                  />
                )}
                {status.updateLogsVisible === false && (
                  <StudioUpdateLogPermissionNotice
                    href={status.permissionConsoleUrl}
                  />
                )}
                {status.consoleUrl && (
                  <a
                    className="studio-update-console-link"
                    href={status.consoleUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t("studioUpdate.openFunctionLogs")}
                    <ExternalLinkIcon />
                  </a>
                )}
              </div>
            ) : phase === "submitting" || phase === "published" ? (
              <div className="studio-update-progress-body">
                <div className="studio-update-progress-summary">
                  <div>
                    <span>{t("studioUpdate.targetVersion")}</span>
                    <strong>{targetVersionRef.current || targetVersion}</strong>
                  </div>
                  <div>
                    <span>{phase === "published" ? t("studioUpdate.updateStatus") : t("studioUpdate.elapsed")}</span>
                    <strong>
                      {phase === "published" ? t("studioUpdate.completed") : formatElapsed(elapsedSeconds, t)}
                    </strong>
                  </div>
                </div>
                <ol className="studio-update-progress" aria-label={t("studioUpdate.progressAriaLabel")}>
                  {unknownProgressStage && (
                    <li className="is-active" aria-current="step">
                      <span className="studio-update-progress-dot" aria-hidden />
                      <div>
                        <span>
                          {updateStageLabel(status.progressStage, t) || t("studioUpdate.processingUpdate")}
                        </span>
                        <TextShimmer as="small">
                          {status.progressMessage || message || t("studioUpdate.processing")}
                        </TextShimmer>
                      </div>
                    </li>
                  )}
                  {updateSteps.map((step, index) => {
                    const completed =
                      phase === "published" || index < currentUpdateStepIndex;
                    const active =
                      phase === "submitting" && step.id === status.progressStage;
                    return (
                      <li
                        key={step.id}
                        className={completed ? "is-complete" : active ? "is-active" : ""}
                        aria-current={active ? "step" : undefined}
                      >
                        <span className="studio-update-progress-dot" aria-hidden />
                        <div>
                          <span>{step.label}</span>
                          {active && (
                            <TextShimmer as="small">
                              {status.progressMessage || message || t("studioUpdate.processing")}
                            </TextShimmer>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
                {status.updateLogsVisible !== false && (
                  <StudioUpdateLog
                    lines={updateLogs}
                    phase={phase === "published" ? "complete" : "active"}
                    copyState={logCopyState}
                    onCopy={(lines) => void copyUpdateLog(lines)}
                  />
                )}
                {status.updateLogsVisible === false && (
                  <StudioUpdateLogPermissionNotice
                    href={status.permissionConsoleUrl}
                  />
                )}
                <p className="studio-update-progress-note">
                  {t("studioUpdate.backgroundHint")}
                </p>
              </div>
            ) : (
              <>
                <p className="confirm-text">
                  {t("studioUpdate.confirmDescription")}
                </p>
                <div className="studio-update-field" ref={versionPickerRef}>
                  <span>{t("studioUpdate.selectVersion")}</span>
                  <button
                    type="button"
                    className="studio-update-version-trigger"
                    aria-label={t("studioUpdate.selectVersion")}
                    aria-haspopup="listbox"
                    aria-expanded={versionMenuOpen}
                    onClick={() => setVersionMenuOpen((open) => !open)}
                    onKeyDown={(event) => {
                      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                        event.preventDefault();
                        setVersionMenuOpen(true);
                      }
                    }}
                  >
                    <span>{targetVersion}</span>
                    <VersionChevronIcon />
                  </button>
                  {versionMenuOpen && (
                    <div
                      className="studio-update-version-menu"
                      role="listbox"
                      aria-label={t("studioUpdate.selectVersion")}
                    >
                      {releases.map((release) => {
                        const selected = release.version === targetVersion;
                        return (
                          <button
                            key={release.version}
                            type="button"
                            role="option"
                            aria-selected={selected}
                            className={`studio-update-version-option${
                              selected ? " is-selected" : ""
                            }`}
                            onClick={() => {
                              setSelectedVersion(release.version);
                              setVersionMenuOpen(false);
                            }}
                          >
                            <span>{release.version}</span>
                            {selected && <VersionCheckIcon />}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
                <dl className="studio-update-versions">
                  <div>
                    <dt>{t("studioUpdate.currentVersion")}</dt>
                    <dd>{status.currentVersion}</dd>
                  </div>
                  <div>
                    <dt>{t("studioUpdate.targetVersion")}</dt>
                    <dd>{targetVersion}</dd>
                  </div>
                  <div>
                    <dt>Commit</dt>
                    <dd>{(targetRelease?.gitSha || status.latestGitSha).slice(0, 8)}</dd>
                  </div>
                </dl>
                <section className="studio-update-changelog" aria-labelledby="studio-update-changelog-title">
                  <div id="studio-update-changelog-title">{t("studioUpdate.changelog")}</div>
                  {targetReleaseNotes.length ? (
                    <ul>
                      {targetReleaseNotes.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>{t("studioUpdate.noChangelog")}</p>
                  )}
                </section>
              </>
            )}
            <div className="confirm-actions">
              <button
                type="button"
                className="confirm-btn"
                onClick={() => {
                  setDialogOpen(false);
                  setVersionMenuOpen(false);
                  if (phase === "confirm") {
                    setPhase("idle");
                    setMessage("");
                  }
                }}
              >
                {phase === "submitting"
                  ? t("studioUpdate.runInBackground")
                  : phase === "confirm"
                    ? t("common.cancel")
                    : t("common.close")}
              </button>
              {phase === "confirm" && (
                <button
                  type="button"
                  className="confirm-btn studio-update-confirm"
                  onClick={() => void beginUpdate()}
                >
                  {t("studioUpdate.updateNow")}
                </button>
              )}
              {phase === "permission" && (
                <button
                  type="button"
                  className="confirm-btn studio-update-confirm"
                  onClick={() => void beginUpdate()}
                >
                  {t("studioUpdate.authorizedRecheck")}
                </button>
              )}
              {phase === "error" && (
                <button
                  type="button"
                  className="confirm-btn studio-update-confirm"
                  onClick={retryUpdate}
                >
                  {t("studioUpdate.tryAgain")}
                </button>
              )}
            </div>
          </section>
        </div>,
          document.body,
        )}
    </>
  );
}
