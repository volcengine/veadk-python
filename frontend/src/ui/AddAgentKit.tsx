import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { addConnection, remoteAppId } from "../adk/connections";

/** Hand-drawn "connect remote agent" mark: a small node-link graph. */
function AddAgentKitIcon() {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="6" cy="12" r="2.4" />
      <circle cx="18" cy="6" r="2.4" />
      <circle cx="18" cy="18" r="2.4" />
      <path d="M8.1 10.9 15.9 7.1M8.1 13.1 15.9 16.9" />
    </svg>
  );
}

/** Sidebar entry that opens the "add AgentKit agent" form in the main panel. */
export function AddAgentKitButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation("conversation");
  return (
    <button className="new-chat" onClick={onClick}>
      <AddAgentKitIcon />
      {t("addAgentKit.title")}
    </button>
  );
}

export interface AddAgentKitViewProps {
  /** Called with the new agent's selection id after a successful add. */
  onAdded: (entryId: string) => void;
  onCancel: () => void;
}

/** Form to register a remote AgentKit agent by URL + API key. On submit it
 *  enumerates the endpoint's apps over the ADK protocol and adds them. */
export function AddAgentKitView({ onAdded, onCancel }: AddAgentKitViewProps) {
  const { t } = useTranslation("conversation");
  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const canSubmit = url.trim().length > 0 && apiKey.trim().length > 0 && !busy;

  async function submit() {
    if (!canSubmit) return;
    setBusy(true);
    setError("");
    try {
      const conn = await addConnection(name, url, apiKey, name);
      if (conn.apps.length === 0) {
        setError(t("addAgentKit.noAgents"));
        setBusy(false);
        return;
      }
      onAdded(remoteAppId(conn.id, conn.apps[0]));
    } catch (e) {
      setError(t("addAgentKit.connectionFailed", { error: String(e) }));
      setBusy(false);
    }
  }

  return (
    <div className="addagent">
      <div className="addagent-card">
        <h2 className="addagent-title">{t("addAgentKit.title")}</h2>
        <p className="addagent-sub">{t("addAgentKit.description")}</p>

        <label className="addagent-field">
          <span className="addagent-label">{t("addAgentKit.url")}</span>
          <input
            className="addagent-input"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://xxxxx.apigateway-cn-beijing.volceapi.com"
            autoFocus
          />
        </label>

        <label className="addagent-field">
          <span className="addagent-label">API Key</span>
          <input
            className="addagent-input"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={t("addAgentKit.apiKeyHint")}
          />
        </label>

        <label className="addagent-field">
          <span className="addagent-label">{t("addAgentKit.displayName")}</span>
          <input
            className="addagent-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("addAgentKit.displayNameHint")}
          />
        </label>

        {error && <div className="addagent-error">{error}</div>}

        <div className="addagent-actions">
          <button className="addagent-btn addagent-btn--ghost" onClick={onCancel} disabled={busy}>
            {t("addAgentKit.cancel")}
          </button>
          <button className="addagent-btn addagent-btn--primary" onClick={submit} disabled={!canSubmit}>
            {busy ? <Loader2 className="icon spin" /> : null}
            {busy ? t("addAgentKit.connecting") : t("addAgentKit.connect")}
          </button>
        </div>
      </div>
    </div>
  );
}
