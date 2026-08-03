import { useEffect, useState } from "react";
import {
  sandboxClient,
  type SandboxAgentWorkspace as SandboxAgentWorkspaceData,
} from "../adk/sandbox";
import "./SandboxAgentWorkspace.css";

export function SandboxAgentWorkspace({
  workspace,
  onBack,
}: {
  workspace: SandboxAgentWorkspaceData;
  onBack: () => void;
}) {
  const [surface, setSurface] = useState<"main" | "terminal">("main");
  const [terminalUrl, setTerminalUrl] = useState("");
  const [terminalLoading, setTerminalLoading] = useState(false);
  const [terminalError, setTerminalError] = useState("");
  const label = workspace.kind === "openclaw" ? "OpenClaw" : "Hermes";

  useEffect(() => {
    setSurface("main");
    setTerminalUrl("");
    setTerminalError("");
    setTerminalLoading(false);
  }, [workspace.session.id]);

  const openTerminal = async () => {
    setSurface("terminal");
    if (terminalUrl || terminalLoading) return;
    setTerminalLoading(true);
    setTerminalError("");
    try {
      const launch = await sandboxClient.launchAgentTerminal(
        workspace.kind,
        workspace.session.id,
      );
      setTerminalUrl(launch.url);
    } catch (cause) {
      setTerminalError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setTerminalLoading(false);
    }
  };

  return (
    <section className="sandbox-agent-workspace">
      <header>
        <div className="sandbox-agent-workspace-title">
          <button type="button" onClick={onBack} aria-label="返回智能体列表">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="m14.5 6-6 6 6 6"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <div>
            <h1>{workspace.session.displayName || `${label} 智能体`}</h1>
            <p>{workspace.session.region || "未知地域"} · {workspace.session.status}</p>
          </div>
        </div>
        <nav aria-label="智能体工作区">
          <button
            type="button"
            className={surface === "main" ? "is-active" : ""}
            aria-pressed={surface === "main"}
            onClick={() => setSurface("main")}
          >
            主界面
          </button>
          <button
            type="button"
            className={surface === "terminal" ? "is-active" : ""}
            aria-pressed={surface === "terminal"}
            onClick={() => void openTerminal()}
          >
            Terminal
          </button>
        </nav>
      </header>

      <div className="sandbox-agent-workspace-surface">
        {surface === "main" ? (
          <iframe
            src={workspace.webuiUrl}
            title={`${label} 主界面`}
            allow="clipboard-read; clipboard-write"
          />
        ) : terminalLoading ? (
          <div className="sandbox-agent-workspace-state" role="status">
            正在打开 Terminal…
          </div>
        ) : terminalError ? (
          <div className="sandbox-agent-workspace-state is-error" role="alert">
            <p>{terminalError}</p>
            <button type="button" onClick={() => void openTerminal()}>重新尝试</button>
          </div>
        ) : terminalUrl ? (
          <iframe src={terminalUrl} title={`${label} Terminal`} />
        ) : null}
      </div>
    </section>
  );
}
