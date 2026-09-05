import { useState } from "react";
import { useTranslation } from "react-i18next";
import { sandboxStatusLabel, type SandboxAgentResource } from "../adk/sandbox";
import { PageBackButton } from "./PageBackButton";
import "./SandboxAgentDetails.css";

const AGENT_LABELS = {
  codex: "Codex",
  "deepseek-harness": "DeepSeek Harness",
  openclaw: "OpenClaw",
  hermes: "Hermes",
} as const;

function formatDate(value: string, locale: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
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
  session: SandboxAgentResource;
  onBack: () => void;
  onOpen: () => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const { t, i18n } = useTranslation("sandbox");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [opening, setOpening] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const label = AGENT_LABELS[session.toolName];
  const wakeable = session.resourceType === "snapshot";
  const resourceId = wakeable
    ? session.sourceSessionId || session.snapshotId
    : session.id;
  const agentName = session.displayName || t("common.agentFallback", { agent: label });
  const locale = i18n.resolvedLanguage ?? i18n.language;

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
        <PageBackButton label={t("agentDetails.back")} onClick={onBack} />
        <div>
          <h1>{agentName}</h1>
          <p>{t("agentDetails.subtitle", { agent: label })}</p>
        </div>
      </header>

      {error ? <div className="sandbox-agent-detail-error" role="alert">{error}</div> : null}

      <div className="sandbox-agent-detail-panel">
        <dl>
          <div><dt>{t("agentDetails.type")}</dt><dd>{label}</dd></div>
          <div><dt>{t("agentDetails.status")}</dt><dd>{sandboxStatusLabel(session.status)}</dd></div>
          <div><dt>{t("agentDetails.createdBy")}</dt><dd>{session.createdBy?.trim() || t("common.unknownSource")}</dd></div>
          <div>
            <dt>{wakeable ? t("agentDetails.snapshotStatus") : t("agentDetails.toolType")}</dt>
            <dd>{wakeable ? session.snapshotStatus || "—" : session.toolType || "—"}</dd>
          </div>
          <div><dt>{t("agentDetails.createdAt")}</dt><dd>{formatDate(session.createdAt, locale)}</dd></div>
          <div>
            <dt>{wakeable ? t("agentDetails.snapshotReason") : t("agentDetails.expiresAt")}</dt>
            <dd>{wakeable ? session.reason || "—" : formatDate(session.expireAt, locale)}</dd>
          </div>
          <div className="is-wide">
            <dt>{t(wakeable ? "agentDetails.snapshotId" : "agentDetails.sessionId")}</dt>
            <dd>{wakeable ? session.snapshotId : resourceId}</dd>
          </div>
          {wakeable && session.sourceSessionId ? (
            <div className="is-wide"><dt>{t("agentDetails.sourceSessionId")}</dt><dd>{session.sourceSessionId}</dd></div>
          ) : null}
        </dl>
        <footer>
          <button
            type="button"
            className="sandbox-agent-delete"
            disabled={opening || deleting}
            onClick={() => setConfirmDelete(true)}
          >
            {t("agentDetails.delete")}
          </button>
          <button
            type="button"
            className="sandbox-agent-open"
            disabled={opening || deleting}
            aria-busy={opening || undefined}
            onClick={() => void openAgent()}
          >
            {opening
              ? wakeable
                ? t("agentDetails.waking")
                : t("agentDetails.opening")
              : wakeable
                ? t("agentDetails.wake")
                : t("agentDetails.open")}
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
            <div className="confirm-title" id="sandbox-agent-delete-title">
              {t("agentDetails.deleteTitle")}
            </div>
            <div className="confirm-text">
              {t("agentDetails.deleteDescription", {
                name: agentName,
                resource: wakeable ? "Snapshot" : "Session",
              })}
            </div>
            <div className="confirm-actions">
              <button
                type="button"
                className="confirm-btn"
                disabled={deleting}
                onClick={() => setConfirmDelete(false)}
              >
                {t("common.cancel")}
              </button>
              <button
                type="button"
                className="confirm-btn confirm-btn--danger"
                disabled={deleting}
                onClick={() => void deleteAgent()}
              >
                {deleting ? t("agentDetails.deleting") : t("agentDetails.confirmDelete")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
