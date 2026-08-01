import { useState } from "react";
import {
  ArrowLeft,
  ExternalLink,
  Globe2,
  Loader2,
  RefreshCw,
} from "lucide-react";

import type {
  SandboxAgentWorkspace as SandboxAgentWorkspaceInfo,
  SandboxToolLaunch,
} from "../adk/sandbox";
import openClawLogo from "../assets/builtin-agents/arkclaw.png";
import hermesLogo from "../assets/builtin-agents/hermes.png";
import { SandboxTerminalIcon } from "./icons/SandboxControlIcons";
import "./SandboxAgentWorkspace.css";

type WorkspaceView = "webui" | "terminal";

export function SandboxAgentWorkspace({
  workspace,
  onBack,
  onRequestTerminal,
}: {
  workspace: SandboxAgentWorkspaceInfo;
  onBack: () => void;
  onRequestTerminal: () => Promise<SandboxToolLaunch>;
}) {
  const [view, setView] = useState<WorkspaceView>("webui");
  const [terminal, setTerminal] = useState<SandboxToolLaunch | null>(null);
  const [terminalLoading, setTerminalLoading] = useState(false);
  const [terminalError, setTerminalError] = useState("");
  const [loadedUrl, setLoadedUrl] = useState("");
  const [frameRevision, setFrameRevision] = useState(0);
  const label = workspace.kind === "openclaw" ? "OpenClaw" : "Hermes";
  const logo = workspace.kind === "openclaw" ? openClawLogo : hermesLogo;
  const activeUrl = view === "webui" ? workspace.webuiUrl : terminal?.url ?? "";
  const loaded = !!activeUrl && loadedUrl === `${view}:${activeUrl}:${frameRevision}`;

  async function selectView(nextView: WorkspaceView) {
    if (nextView === "terminal" && !terminal && !terminalLoading) {
      setTerminalLoading(true);
      setTerminalError("");
      try {
        setTerminal(await onRequestTerminal());
      } catch (error) {
        setTerminalError(error instanceof Error ? error.message : String(error));
      } finally {
        setTerminalLoading(false);
      }
    }
    setView(nextView);
  }

  function refresh() {
    setLoadedUrl("");
    if (view === "terminal" && terminalError) {
      setTerminal(null);
      setTerminalError("");
      void selectView("terminal");
      return;
    }
    setFrameRevision((value) => value + 1);
  }

  return (
    <section className="sandbox-agent-workspace">
      <header className="sandbox-agent-workspace__header">
        <div className="sandbox-agent-workspace__identity">
          <button type="button" className="sandbox-agent-workspace__back" onClick={onBack}>
            <ArrowLeft aria-hidden />
            返回列表
          </button>
          <span className="sandbox-agent-workspace__divider" aria-hidden />
          <img src={logo} alt="" />
          <strong>{workspace.session.displayName || label}</strong>
          <span>{label} Session</span>
        </div>
        <div className="sandbox-agent-workspace__controls">
          <div role="tablist" aria-label={`${label} Session 视图`}>
            <button
              type="button"
              role="tab"
              aria-selected={view === "webui"}
              onClick={() => void selectView("webui")}
            >
              <Globe2 aria-hidden />
              主页面
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "terminal"}
              onClick={() => void selectView("terminal")}
            >
              <SandboxTerminalIcon />
              Terminal
            </button>
          </div>
          <button type="button" title="重新加载" aria-label="重新加载" onClick={refresh}>
            <RefreshCw aria-hidden />
          </button>
          {activeUrl && (
            <a href={activeUrl} target="_blank" rel="noreferrer" title="在新窗口打开">
              <ExternalLink aria-hidden />
            </a>
          )}
        </div>
      </header>

      <div className="sandbox-agent-workspace__surface">
        {terminalError && view === "terminal" ? (
          <div className="sandbox-agent-workspace__state" role="alert">
            <p>{terminalError}</p>
            <button type="button" onClick={refresh}>重新尝试</button>
          </div>
        ) : !activeUrl || terminalLoading ? (
          <div className="sandbox-agent-workspace__state" role="status">
            <Loader2 className="spin" aria-hidden />
            正在打开 {view === "webui" ? `${label} 主页面` : "Terminal"}…
          </div>
        ) : (
          <>
            {!loaded && (
              <div className="sandbox-agent-workspace__state" role="status">
                <Loader2 className="spin" aria-hidden />
                正在载入 {view === "webui" ? `${label} 主页面` : "Terminal"}…
              </div>
            )}
            <iframe
              key={`${view}:${frameRevision}`}
              src={activeUrl}
              title={view === "webui" ? `${label} 主页面` : `${label} Terminal`}
              allow="clipboard-read; clipboard-write"
              onLoad={() => setLoadedUrl(`${view}:${activeUrl}:${frameRevision}`)}
            />
          </>
        )}
      </div>
    </section>
  );
}
