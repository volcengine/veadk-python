import {
  ChevronRight,
  History,
  Loader2,
  X,
} from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
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
  SandboxPermissionsIcon,
  SandboxTerminalIcon,
  SandboxWorkspaceIcon,
} from "./icons/SandboxControlIcons";
import "./SandboxControls.css";

interface DialogShellProps {
  open: boolean;
  title: string;
  subtitle: string;
  icon: ReactNode;
  className?: string;
  onClose: () => void;
  children: ReactNode;
}

function DialogShell({
  open,
  title,
  subtitle,
  icon,
  className = "",
  onClose,
  children,
}: DialogShellProps) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, open]);

  if (!open) return null;
  return createPortal(
    <div
      className="sandbox-control-backdrop"
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
            <p>{subtitle}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="sandbox-control-close"
            aria-label={`关闭${title}`}
            onClick={onClose}
          >
            <X />
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
  const terminal = kind === "terminal";
  const title = terminal ? "Terminal" : "Sandbox Browser";

  return (
    <DialogShell
      open={open}
      title={title}
      subtitle={
        terminal
          ? "连接当前 AgentKit Session 的交互式终端"
          : "在当前 AgentKit Session 中查看与操作浏览器"
      }
      icon={terminal ? <SandboxTerminalIcon /> : <SandboxBrowserIcon />}
      className={`sandbox-tool-dialog sandbox-tool-dialog--${kind}`}
      onClose={onClose}
    >
      <div className="sandbox-tool-toolbar">
        <span>
          <i className={loading ? "is-loading" : launch ? "is-ready" : ""} />
          {loading ? "正在连接…" : launch ? "已连接" : "尚未连接"}
        </span>
      </div>
      <div className="sandbox-tool-surface">
        {loading ? (
          <div className="sandbox-control-state">
            <Loader2 className="spin" />
            <strong>正在打开 {title}</strong>
            <span>工具将通过 Studio 的安全代理连接到当前沙箱。</span>
          </div>
        ) : error ? (
          <div className="sandbox-control-state is-error">
            <strong>{title} 打开失败</strong>
            <span>{error}</span>
            <button type="button" onClick={onReload}>重试</button>
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
  return (
    <DialogShell
      open={open}
      title="恢复 Codex 对话"
      subtitle="选择当前 Sandbox Session 中最近更新的 Thread"
      icon={<History />}
      className="sandbox-threads-dialog"
      onClose={onClose}
    >
      <div className="sandbox-thread-list">
        {loading ? (
          <div className="sandbox-control-state">
            <Loader2 className="spin" />
            <strong>正在读取历史对话</strong>
          </div>
        ) : error ? (
          <div className="sandbox-control-state is-error">
            <strong>历史对话读取失败</strong>
            <span>{error}</span>
          </div>
        ) : threads.length === 0 ? (
          <div className="sandbox-control-state">
            <strong>暂无可恢复的对话</strong>
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
                    ? new Date(thread.updatedAt * 1_000).toLocaleString()
                    : ""}
                </time>
                <ChevronRight />
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
    label: "只读",
    detail: "允许读取文件，不允许写入工作空间。",
  },
  {
    value: "workspace-write",
    label: "工作区写入",
    detail: "允许在当前工作空间内读取与修改文件。",
  },
  {
    value: "danger-full-access",
    label: "完全访问",
    detail: "不启用沙箱隔离，适合明确可信的任务。",
    danger: true,
  },
] as const;

const APPROVAL_CHOICES = [
  {
    value: "untrusted",
    label: "仅不可信命令",
    detail: "只对 Codex 判断为不可信的操作发起审批。",
  },
  {
    value: "on-request",
    label: "按需审批",
    detail: "Codex 可在必要时请求你确认命令或文件修改。",
  },
  {
    value: "never",
    label: "不审批",
    detail: "Codex 不会暂停并请求人工批准。",
    danger: true,
  },
] as const;

const REVIEWER_CHOICES = [
  {
    value: "user",
    label: "由我审批",
    detail: "审批请求会显示在 Studio 中，由你决定。",
  },
  {
    value: "auto_review",
    label: "自动审查",
    detail: "使用 Codex 自动审查流程处理审批请求。",
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
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    if (open) setDraft(value);
  }, [open, value]);

  return (
    <DialogShell
      open={open}
      title="Codex 权限"
      subtitle="设置会保存到当前 Sandbox Session，并同步到其中的所有 Thread"
      icon={<SandboxPermissionsIcon />}
      className="sandbox-settings-dialog"
      onClose={onClose}
    >
      <div className="sandbox-control-body">
        <ChoiceGroup
          label="沙箱模式"
          choices={SANDBOX_CHOICES}
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
          label="审批策略"
          choices={APPROVAL_CHOICES}
          value={draft.approvalPolicy}
          disabled={busy}
          onChange={(approvalPolicy) =>
            setDraft((current) => ({ ...current, approvalPolicy }))
          }
        />
        <ChoiceGroup
          label="审批方式"
          choices={REVIEWER_CHOICES}
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
            <strong>允许网络访问</strong>
            <small>控制 workspace-write 与只读模式中的外部网络访问。</small>
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
            完全访问会关闭文件系统与网络隔离，请只在可信任务中使用。
          </div>
        ) : null}
        {error ? <div className="sandbox-control-error">{error}</div> : null}
      </div>
      <footer className="sandbox-control-actions">
        <button type="button" onClick={onClose} disabled={busy}>取消</button>
        <button
          type="button"
          className="is-primary"
          disabled={busy}
          onClick={() => onSave(draft)}
        >
          {busy ? <Loader2 className="spin" /> : null}
          保存权限
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
    <fieldset className="sandbox-choice-group" disabled={disabled}>
      <legend>{label}</legend>
      <div className="sandbox-choice-list">
        {choices.map((choice) => (
          <button
            key={choice.value}
            type="button"
            className={`${value === choice.value ? "is-active" : ""}${
              choice.danger ? " is-danger" : ""
            }`.trim()}
            aria-pressed={value === choice.value}
            onClick={() => onChange(choice.value)}
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
      title="工作空间"
      subtitle="选择当前 Codex Thread 执行命令与修改文件的目录"
      icon={<SandboxWorkspaceIcon />}
      className="sandbox-workspace-dialog"
      onClose={onClose}
    >
      <div className="sandbox-control-body">
        <label className="sandbox-workspace-input">
          <span>绝对路径</span>
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
              浏览
            </button>
          </div>
        </label>
        <div className="sandbox-directory-browser">
          <div className="sandbox-directory-head">
            <span title={listing?.path}>{listing?.path ?? path}</span>
            {loading ? <Loader2 className="spin" /> : null}
          </div>
          <div className="sandbox-directory-list">
            {listing?.parent ? (
              <button
                type="button"
                disabled={loading}
                onClick={() => void load(listing.parent ?? "/")}
              >
                <SandboxWorkspaceIcon />
                <span>上一级</span>
                <small>{listing.parent}</small>
                <ChevronRight />
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
                <ChevronRight />
              </button>
            ))}
            {!loading && listing?.directories.length === 0 ? (
              <div className="sandbox-directory-empty">当前目录没有子目录</div>
            ) : null}
          </div>
        </div>
        {locked ? (
          <div className="sandbox-control-note">
            当前对话已经开始，工作空间已锁定。新建 Sandbox 会话后可重新选择。
          </div>
        ) : null}
        {browseError || error ? (
          <div className="sandbox-control-error">{browseError || error}</div>
        ) : null}
      </div>
      <footer className="sandbox-control-actions">
        <button type="button" onClick={onClose} disabled={busy}>取消</button>
        <button
          type="button"
          className="is-primary"
          disabled={busy || locked || !path.startsWith("/")}
          onClick={() => onSave(path)}
        >
          {busy ? <Loader2 className="spin" /> : null}
          使用此目录
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
  const command = approval?.command?.trim();
  const changes = approval?.changes === undefined
    ? ""
    : JSON.stringify(approval.changes, null, 2);
  return (
    <DialogShell
      open={approval !== null}
      title={approval?.kind === "file" ? "允许修改文件？" : "允许执行命令？"}
      subtitle="Codex 正在等待你的决定"
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
            执行目录 <code>{approval.cwd}</code>
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
          拒绝
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecision("accept")}
        >
          仅本次允许
        </button>
        <button
          type="button"
          className="is-primary"
          disabled={busy}
          onClick={() => onDecision("acceptForSession")}
        >
          {busy ? <Loader2 className="spin" /> : null}
          本会话允许
        </button>
      </footer>
    </DialogShell>
  );
}
