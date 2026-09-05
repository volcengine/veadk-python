import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type {
  SandboxApproval,
  SandboxApprovalDecision,
  SandboxDirectoryListing,
  SandboxPermissions,
  SandboxThreadSummary,
  SandboxToolLaunch,
} from "../adk/sandbox";
import {
  SandboxBrowserIcon,
  SandboxChevronIcon,
  SandboxCloseIcon,
  SandboxHistoryIcon,
  SandboxPermissionsIcon,
  SandboxSpinnerIcon,
  SandboxTerminalIcon,
  SandboxWorkspaceIcon,
} from "./icons/SandboxControlIcons";
import "./SandboxControls.css";

interface DialogShellProps {
  open: boolean;
  keepMounted?: boolean;
  title: string;
  subtitle?: string;
  icon: ReactNode;
  className?: string;
  onClose: () => void;
  children: ReactNode;
}

export function DialogShell({
  open,
  keepMounted = false,
  title,
  subtitle,
  icon,
  className = "",
  onClose,
  children,
}: DialogShellProps) {
  const { t } = useTranslation("sandbox");
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = closeRef.current?.closest<HTMLElement>("[role=dialog]");
      const focusable = Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), iframe, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
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
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [open]);

  if (!open && !keepMounted) return null;
  return createPortal(
    <div
      className="sandbox-control-backdrop"
      hidden={!open}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className={`sandbox-control-dialog ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="sandbox-control-head">
          <span className="sandbox-control-head-icon" aria-hidden="true">
            {icon}
          </span>
          <div>
            <h2 id={titleId}>{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button
            ref={closeRef}
            type="button"
            className="sandbox-control-close"
            aria-label={t("common.closeDialog", { title })}
            onClick={onClose}
          >
            <SandboxCloseIcon />
          </button>
        </header>
        {children}
      </section>
    </div>,
    document.body,
  );
}

export interface SandboxToolDialogProps {
  open: boolean;
  kind: "terminal" | "browser";
  launch: SandboxToolLaunch | null;
  loading: boolean;
  error: string;
  onReload: () => void;
  onClose: () => void;
}

export function SandboxToolDialog({
  open,
  kind,
  launch,
  loading,
  error,
  onReload,
  onClose,
}: SandboxToolDialogProps) {
  const { t } = useTranslation("sandbox");
  const terminal = kind === "terminal";
  const title = terminal ? t("tool.terminalTitle") : t("tool.browserTitle");

  return (
    <DialogShell
      open={open}
      title={title}
      subtitle={
        terminal
          ? t("tool.terminalSubtitle")
          : t("tool.browserSubtitle")
      }
      icon={terminal ? <SandboxTerminalIcon /> : <SandboxBrowserIcon />}
      className={`sandbox-tool-dialog sandbox-tool-dialog--${kind}`}
      onClose={onClose}
    >
      <div className="sandbox-tool-toolbar">
        <span>
          <i className={loading ? "is-loading" : launch ? "is-ready" : ""} />
          {loading
            ? t("tool.connecting")
            : launch
              ? t("tool.connected")
              : t("tool.notConnected")}
        </span>
      </div>
      <div className="sandbox-tool-surface">
        {loading ? (
          <div className="sandbox-control-state">
            <SandboxSpinnerIcon className="spin" />
            <strong>{t("tool.opening", { title })}</strong>
            <span>{t("tool.connectingSession")}</span>
          </div>
        ) : error ? (
          <div className="sandbox-control-state is-error">
            <strong>{t("tool.openFailed", { title })}</strong>
            <span>{error}</span>
            <button type="button" onClick={onReload}>{t("common.retry")}</button>
          </div>
        ) : launch ? (
          <iframe
            src={launch.url}
            title={title}
            allow="clipboard-read; clipboard-write"
            sandbox="allow-downloads allow-forms allow-modals allow-popups allow-pointer-lock allow-same-origin allow-scripts"
          />
        ) : null}
      </div>
    </DialogShell>
  );
}

export interface SandboxThreadsDialogProps {
  open: boolean;
  threads: SandboxThreadSummary[];
  currentThreadId: string;
  loading: boolean;
  error: string;
  onSelect: (threadId: string) => void;
  onClose: () => void;
}

export function SandboxThreadsDialog({
  open,
  threads,
  currentThreadId,
  loading,
  error,
  onSelect,
  onClose,
}: SandboxThreadsDialogProps) {
  const { t, i18n } = useTranslation("sandbox");
  return (
    <DialogShell
      open={open}
      title={t("threads.title")}
      subtitle={t("threads.subtitle")}
      icon={<SandboxHistoryIcon />}
      className="sandbox-threads-dialog"
      onClose={onClose}
    >
      <div className="sandbox-thread-list">
        {loading ? (
          <div className="sandbox-control-state">
            <SandboxSpinnerIcon className="spin" />
            <strong>{t("threads.loading")}</strong>
          </div>
        ) : error ? (
          <div className="sandbox-control-state is-error">
            <strong>{t("threads.loadFailed")}</strong>
            <span>{error}</span>
          </div>
        ) : threads.length === 0 ? (
          <div className="sandbox-control-state">
            <strong>{t("threads.empty")}</strong>
          </div>
        ) : (
          threads.map((thread) => {
            const active = thread.id === currentThreadId;
            const title =
              thread.name || thread.preview || `Thread ${thread.id.slice(0, 8)}`;
            return (
              <button
                key={thread.id}
                type="button"
                className={active ? "is-active" : ""}
                disabled={active}
                onClick={() => onSelect(thread.id)}
              >
                <span>
                  <strong>{title}</strong>
                  <small>{thread.preview || thread.cwd || thread.id}</small>
                </span>
                <time>
                  {thread.updatedAt
                    ? new Date(thread.updatedAt * 1_000).toLocaleString(
                        i18n.resolvedLanguage ?? i18n.language,
                      )
                    : ""}
                </time>
                <SandboxChevronIcon />
              </button>
            );
          })
        )}
      </div>
    </DialogShell>
  );
}

const SANDBOX_CHOICES = [
  {
    value: "read-only",
    labelKey: "permissions.sandboxChoices.readOnly.label",
    detailKey: "permissions.sandboxChoices.readOnly.detail",
  },
  {
    value: "workspace-write",
    labelKey: "permissions.sandboxChoices.workspaceWrite.label",
    detailKey: "permissions.sandboxChoices.workspaceWrite.detail",
  },
  {
    value: "danger-full-access",
    labelKey: "permissions.sandboxChoices.fullAccess.label",
    detailKey: "permissions.sandboxChoices.fullAccess.detail",
    danger: true,
  },
] as const;

const APPROVAL_CHOICES = [
  {
    value: "untrusted",
    labelKey: "permissions.approvalChoices.untrusted.label",
    detailKey: "permissions.approvalChoices.untrusted.detail",
  },
  {
    value: "on-request",
    labelKey: "permissions.approvalChoices.onRequest.label",
    detailKey: "permissions.approvalChoices.onRequest.detail",
  },
  {
    value: "never",
    labelKey: "permissions.approvalChoices.never.label",
    detailKey: "permissions.approvalChoices.never.detail",
    danger: true,
  },
] as const;

const REVIEWER_CHOICES = [
  {
    value: "user",
    labelKey: "permissions.reviewerChoices.user.label",
    detailKey: "permissions.reviewerChoices.user.detail",
  },
  {
    value: "auto_review",
    labelKey: "permissions.reviewerChoices.autoReview.label",
    detailKey: "permissions.reviewerChoices.autoReview.detail",
  },
] as const;

export interface SandboxPermissionsDialogProps {
  open: boolean;
  value: SandboxPermissions;
  busy: boolean;
  error: string;
  onSave: (value: SandboxPermissions) => void;
  onClose: () => void;
}

export function SandboxPermissionsDialog({
  open,
  value,
  busy,
  error,
  onSave,
  onClose,
}: SandboxPermissionsDialogProps) {
  const { t } = useTranslation("sandbox");
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    if (open) setDraft(value);
  }, [open, value]);

  return (
    <DialogShell
      open={open}
      title={t("permissions.title")}
      subtitle={t("permissions.subtitle")}
      icon={<SandboxPermissionsIcon />}
      className="sandbox-settings-dialog"
      onClose={onClose}
    >
      <div className="sandbox-control-body">
        <ChoiceGroup
          label={t("permissions.sandboxMode")}
          choices={SANDBOX_CHOICES.map((choice) => ({
            ...choice,
            label: t(choice.labelKey),
            detail: t(choice.detailKey),
          }))}
          value={draft.sandboxMode}
          disabled={busy}
          onChange={(sandboxMode) =>
            setDraft((current) => ({
              ...current,
              sandboxMode,
              networkAccess:
                sandboxMode === "danger-full-access"
                  ? true
                  : current.networkAccess,
            }))
          }
        />
        <ChoiceGroup
          label={t("permissions.approvalPolicy")}
          choices={APPROVAL_CHOICES.map((choice) => ({
            ...choice,
            label: t(choice.labelKey),
            detail: t(choice.detailKey),
          }))}
          value={draft.approvalPolicy}
          disabled={busy}
          onChange={(approvalPolicy) =>
            setDraft((current) => ({ ...current, approvalPolicy }))
          }
        />
        <ChoiceGroup
          label={t("permissions.approvalMethod")}
          choices={REVIEWER_CHOICES.map((choice) => ({
            ...choice,
            label: t(choice.labelKey),
            detail: t(choice.detailKey),
          }))}
          value={draft.approvalsReviewer}
          disabled={busy}
          onChange={(approvalsReviewer) =>
            setDraft((current) => ({ ...current, approvalsReviewer }))
          }
        />
        <label
          className={`sandbox-network-toggle${
            draft.sandboxMode === "danger-full-access" ? " is-disabled" : ""
          }`}
        >
          <span>
            <strong>{t("permissions.networkAccess")}</strong>
            <small>{t("permissions.networkAccessHelp")}</small>
          </span>
          <input
            type="checkbox"
            checked={draft.networkAccess}
            disabled={busy || draft.sandboxMode === "danger-full-access"}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                networkAccess: event.target.checked,
              }))
            }
          />
        </label>
        {draft.sandboxMode === "danger-full-access" ? (
          <div className="sandbox-control-note is-danger">
            {t("permissions.fullAccessWarning")}
          </div>
        ) : null}
        {error ? <div className="sandbox-control-error">{error}</div> : null}
      </div>
      <footer className="sandbox-control-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          {t("common.cancel")}
        </button>
        <button
          type="button"
          className="is-primary"
          disabled={busy}
          onClick={() => onSave(draft)}
        >
          {busy ? <SandboxSpinnerIcon className="spin" /> : null}
          {t("permissions.save")}
        </button>
      </footer>
    </DialogShell>
  );
}

interface Choice {
  value: string;
  label: string;
  detail: string;
  danger?: boolean;
}

function ChoiceGroup<T extends string>({
  label,
  choices,
  value,
  disabled,
  onChange,
}: {
  label: string;
  choices: readonly (Choice & { value: T })[];
  value: T;
  disabled: boolean;
  onChange: (value: T) => void;
}) {
  return (
    <fieldset
      className="sandbox-choice-group"
      disabled={disabled}
      role="radiogroup"
      aria-label={label}
    >
      <legend>{label}</legend>
      <div className="sandbox-choice-list">
        {choices.map((choice) => (
          <button
            key={choice.value}
            type="button"
            role="radio"
            className={`${value === choice.value ? "is-active" : ""}${
              choice.danger ? " is-danger" : ""
            }`.trim()}
            aria-checked={value === choice.value}
            onClick={() => onChange(choice.value)}
            onKeyDown={(event) => {
              const currentIndex = choices.findIndex(
                (item) => item.value === choice.value,
              );
              let nextIndex = currentIndex;
              if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                nextIndex = (currentIndex + 1) % choices.length;
              } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                nextIndex = (currentIndex - 1 + choices.length) % choices.length;
              } else if (event.key === "Home") {
                nextIndex = 0;
              } else if (event.key === "End") {
                nextIndex = choices.length - 1;
              } else {
                return;
              }
              event.preventDefault();
              onChange(choices[nextIndex].value);
              const radios = event.currentTarget.parentElement
                ?.querySelectorAll<HTMLButtonElement>('[role="radio"]');
              radios?.[nextIndex]?.focus();
            }}
          >
            <i />
            <span>
              <strong>{choice.label}</strong>
              <small>{choice.detail}</small>
            </span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export interface SandboxWorkspaceDialogProps {
  open: boolean;
  cwd: string;
  locked: boolean;
  busy: boolean;
  error: string;
  browse: (path: string) => Promise<SandboxDirectoryListing>;
  onSave: (cwd: string) => void;
  onClose: () => void;
}

export function SandboxWorkspaceDialog({
  open,
  cwd,
  locked,
  busy,
  error,
  browse,
  onSave,
  onClose,
}: SandboxWorkspaceDialogProps) {
  const { t } = useTranslation("sandbox");
  const [path, setPath] = useState(cwd || "/");
  const [listing, setListing] = useState<SandboxDirectoryListing | null>(null);
  const [loading, setLoading] = useState(false);
  const [browseError, setBrowseError] = useState("");

  useEffect(() => {
    if (!open) return;
    const next = cwd || "/";
    setPath(next);
    void load(next);
    // `browse` is supplied as a stable callback by App.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cwd, open]);

  async function load(nextPath: string) {
    setLoading(true);
    setBrowseError("");
    try {
      const next = await browse(nextPath);
      setListing(next);
      setPath(next.path);
    } catch (cause) {
      setBrowseError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }

  return (
    <DialogShell
      open={open}
      title={t("workspace.title")}
      subtitle={t("workspace.subtitle")}
      icon={<SandboxWorkspaceIcon />}
      className="sandbox-workspace-dialog"
      onClose={onClose}
    >
      <div className="sandbox-control-body">
        <label className="sandbox-workspace-input">
          <span>{t("workspace.absolutePath")}</span>
          <div>
            <input
              value={path}
              disabled={busy || locked}
              spellCheck={false}
              onChange={(event) => setPath(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && path.startsWith("/")) {
                  event.preventDefault();
                  void load(path);
                }
              }}
            />
            <button
              type="button"
              disabled={busy || loading || !path.startsWith("/")}
              onClick={() => void load(path)}
            >
              {t("workspace.browse")}
            </button>
          </div>
        </label>
        <div className="sandbox-directory-browser">
          <div className="sandbox-directory-head">
            <span title={listing?.path}>{listing?.path ?? path}</span>
            {loading ? <SandboxSpinnerIcon className="spin" /> : null}
          </div>
          <div className="sandbox-directory-list">
            {listing?.parent ? (
              <button
                type="button"
                disabled={loading}
                onClick={() => void load(listing.parent ?? "/")}
              >
                <SandboxWorkspaceIcon />
                <span>{t("workspace.parent")}</span>
                <small>{listing.parent}</small>
                <SandboxChevronIcon />
              </button>
            ) : null}
            {listing?.directories.map((directory) => (
              <button
                type="button"
                key={directory.path}
                disabled={loading}
                onClick={() => void load(directory.path)}
              >
                <SandboxWorkspaceIcon />
                <span>{directory.name}</span>
                <SandboxChevronIcon />
              </button>
            ))}
            {!loading && listing?.directories.length === 0 ? (
              <div className="sandbox-directory-empty">{t("workspace.empty")}</div>
            ) : null}
          </div>
        </div>
        {locked ? (
          <div className="sandbox-control-note">
            {t("workspace.locked")}
          </div>
        ) : null}
        {browseError || error ? (
          <div className="sandbox-control-error">{browseError || error}</div>
        ) : null}
      </div>
      <footer className="sandbox-control-actions">
        <button type="button" onClick={onClose} disabled={busy}>
          {t("common.cancel")}
        </button>
        <button
          type="button"
          className="is-primary"
          disabled={busy || locked || !path.startsWith("/")}
          onClick={() => onSave(path)}
        >
          {busy ? <SandboxSpinnerIcon className="spin" /> : null}
          {t("workspace.useDirectory")}
        </button>
      </footer>
    </DialogShell>
  );
}

export interface SandboxApprovalDialogProps {
  approval: SandboxApproval | null;
  busy: boolean;
  error: string;
  onDecision: (decision: SandboxApprovalDecision) => void;
}

export function SandboxApprovalDialog({
  approval,
  busy,
  error,
  onDecision,
}: SandboxApprovalDialogProps) {
  const { t } = useTranslation("sandbox");
  const command = approval?.command?.trim();
  const changes = approval?.changes === undefined
    ? ""
    : JSON.stringify(approval.changes, null, 2);
  return (
    <DialogShell
      open={approval !== null}
      title={approval?.kind === "file"
        ? t("approval.fileTitle")
        : t("approval.commandTitle")}
      subtitle={t("approval.subtitle")}
      icon={<SandboxPermissionsIcon />}
      className="sandbox-approval-dialog"
      onClose={() => {
        if (!busy) onDecision("cancel");
      }}
    >
      <div className="sandbox-control-body">
        {approval?.reason ? (
          <div className="sandbox-approval-reason">{approval.reason}</div>
        ) : null}
        {command ? <pre>{command}</pre> : null}
        {changes ? <pre>{changes}</pre> : null}
        {approval?.cwd ? (
          <div className="sandbox-approval-meta">
            {t("approval.workingDirectory")} <code>{approval.cwd}</code>
          </div>
        ) : null}
        {error ? <div className="sandbox-control-error">{error}</div> : null}
      </div>
      <footer className="sandbox-control-actions sandbox-approval-actions">
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecision("decline")}
        >
          {t("approval.decline")}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecision("accept")}
        >
          {t("approval.acceptOnce")}
        </button>
        <button
          type="button"
          className="is-primary"
          disabled={busy}
          onClick={() => onDecision("acceptForSession")}
        >
          {busy ? <SandboxSpinnerIcon className="spin" /> : null}
          {t("approval.acceptSession")}
        </button>
      </footer>
    </DialogShell>
  );
}
