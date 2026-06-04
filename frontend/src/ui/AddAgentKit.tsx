import { useState } from "react";
import { Loader2 } from "lucide-react";
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
  return (
    <button className="new-chat" onClick={onClick}>
      <AddAgentKitIcon />
      添加 AgentKit 智能体
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
      const conn = await addConnection(name, url, apiKey);
      if (conn.apps.length === 0) {
        setError("连接成功，但该地址未发现任何 Agent（/list-apps 为空）。");
        setBusy(false);
        return;
      }
      onAdded(remoteAppId(conn.id, conn.apps[0]));
    } catch (e) {
      setError(`连接失败：${String(e)}。请检查 URL、API Key，以及该网关是否允许跨域。`);
      setBusy(false);
    }
  }

  return (
    <div className="addagent">
      <div className="addagent-card">
        <h2 className="addagent-title">添加 AgentKit 智能体</h2>
        <p className="addagent-sub">
          填入 AgentKit 部署的访问地址与 API Key，将通过 ADK 协议连接，连接成功后其
          Agent 会出现在左上角的下拉中。
        </p>

        <label className="addagent-field">
          <span className="addagent-label">访问地址 URL</span>
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
            placeholder="以 Authorization: Bearer 方式连接"
          />
        </label>

        <label className="addagent-field">
          <span className="addagent-label">显示名称（可选）</span>
          <input
            className="addagent-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="默认取 URL 的主机名"
          />
        </label>

        {error && <div className="addagent-error">{error}</div>}

        <div className="addagent-actions">
          <button className="addagent-btn addagent-btn--ghost" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button className="addagent-btn addagent-btn--primary" onClick={submit} disabled={!canSubmit}>
            {busy ? <Loader2 className="icon spin" /> : null}
            {busy ? "连接中…" : "连接并添加"}
          </button>
        </div>
      </div>
    </div>
  );
}
