import { useState } from "react";
import { sandboxStatusLabel, type SandboxSession } from "../adk/sandbox";
import "./SandboxAgentDetails.css";

const AGENT_LABELS = {
  codex: "Codex",
  openclaw: "OpenClaw",
  hermes: "Hermes",
} as const;

function formatDate(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

export function SandboxAgentDetails({
  session,
  onBack,
  onOpen,
  onDelete,
}: {
  session: SandboxSession;
  onBack: () => void;
  onOpen: () => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [opening, setOpening] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const label = AGENT_LABELS[session.toolName];

  const openAgent = async () => {
    if (opening || deleting) return;
    setOpening(true);
    setError("");
    try {
      await onOpen();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setOpening(false);
    }
  };

  const deleteAgent = async () => {
    if (deleting || opening) return;
    setDeleting(true);
    setError("");
    try {
      await onDelete();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setConfirmDelete(false);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <section className="sandbox-agent-details">
      <header className="sandbox-agent-details-header">
        <button type="button" className="sandbox-agent-back" onClick={onBack}>
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="m14.5 6-6 6 6 6"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          返回智能体
        </button>
        <div>
          <h1>{session.displayName || `${label} 智能体`}</h1>
          <p>{label} AgentKit Session 详情</p>
        </div>
      </header>

      {error ? <div className="sandbox-agent-detail-error" role="alert">{error}</div> : null}

      <div className="sandbox-agent-detail-panel">
        <dl>
          <div><dt>智能体类型</dt><dd>{label}</dd></div>
          <div><dt>状态</dt><dd>{sandboxStatusLabel(session.status)}</dd></div>
          <div><dt>创建人</dt><dd>{session.createdBy || "—"}</dd></div>
          <div><dt>工具类型</dt><dd>{session.toolType || "—"}</dd></div>
          <div><dt>创建时间</dt><dd>{formatDate(session.createdAt)}</dd></div>
          <div><dt>过期时间</dt><dd>{formatDate(session.expireAt)}</dd></div>
          <div className="is-wide"><dt>Session ID</dt><dd>{session.id}</dd></div>
        </dl>
        <footer>
          <button
            type="button"
            className="sandbox-agent-delete"
            disabled={opening || deleting}
            onClick={() => setConfirmDelete(true)}
          >
            删除智能体
          </button>
          <button
            type="button"
            className="sandbox-agent-open"
            disabled={opening || deleting}
            aria-busy={opening || undefined}
            onClick={() => void openAgent()}
          >
            {opening ? "打开中…" : "打开智能体"}
          </button>
        </footer>
      </div>

      {confirmDelete ? (
        <div className="confirm-scrim" onClick={() => !deleting && setConfirmDelete(false)}>
          <div
            className="confirm-box"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="sandbox-agent-delete-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="confirm-title" id="sandbox-agent-delete-title">删除智能体？</div>
            <div className="confirm-text">
              将删除“{session.displayName || `${label} 智能体`}”及其 AgentKit Session，此操作无法撤销。
            </div>
            <div className="confirm-actions">
              <button
                type="button"
                className="confirm-btn"
                disabled={deleting}
                onClick={() => setConfirmDelete(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="confirm-btn confirm-btn--danger"
                disabled={deleting}
                onClick={() => void deleteAgent()}
              >
                {deleting ? "删除中…" : "确认删除"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
