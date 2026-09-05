import { useEffect, useState } from "react";
import { SegmentedControl } from "@openai/apps-sdk-ui/components/SegmentedControl";
import { useTranslation } from "react-i18next";
import {
  sandboxClient,
  sandboxStatusLabel,
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
  const { t } = useTranslation("sandbox");
  const [surface, setSurface] = useState<"main" | "terminal">("main");
  const [terminalUrl, setTerminalUrl] = useState("");
  const [terminalLoading, setTerminalLoading] = useState(false);
  const [terminalError, setTerminalError] = useState("");
  const label = workspace.kind === "deepseek-harness"
    ? "DeepSeek Harness"
    : workspace.kind === "openclaw" ? "OpenClaw" : "Hermes";
  const agentName = workspace.session.displayName ||
    t("common.agentFallback", { agent: label });

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
          <button type="button" onClick={onBack} aria-label={t("agentWorkspace.back")}>
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
            <h1>{agentName}</h1>
            <p>
              <span>
                {t("agentWorkspace.createdBy", {
                  creator: workspace.session.createdBy?.trim() || t("common.unknownSource"),
                })}
              </span>
              <span
                className="sandbox-agent-workspace-status"
                data-ready={
                  workspace.session.status.toLowerCase() === "ready" || undefined
                }
              >
                {sandboxStatusLabel(workspace.session.status)}
              </span>
            </p>
          </div>
        </div>
        <SegmentedControl
          className="sandbox-agent-workspace-tabs"
          value={surface}
          size="lg"
          gutterSize="lg"
          block
          pill={false}
          aria-label={t("agentWorkspace.ariaLabel")}
          onChange={(nextSurface) => {
            if (nextSurface === "terminal") void openTerminal();
            else setSurface("main");
          }}
        >
          <SegmentedControl.Option value="main">
            {t("agentWorkspace.main")}
          </SegmentedControl.Option>
          <SegmentedControl.Option value="terminal">
            {t("agentWorkspace.terminal")}
          </SegmentedControl.Option>
        </SegmentedControl>
      </header>

      <div className="sandbox-agent-workspace-surface">
        {surface === "main" ? (
          <iframe
            src={workspace.webuiUrl}
            title={t("agentWorkspace.mainTitle", { agent: label })}
            allow="clipboard-read; clipboard-write"
          />
        ) : terminalLoading ? (
          <div className="sandbox-agent-workspace-state" role="status">
            {t("agentWorkspace.openingTerminal")}
          </div>
        ) : terminalError ? (
          <div className="sandbox-agent-workspace-state is-error" role="alert">
            <p>{terminalError}</p>
            <button type="button" onClick={() => void openTerminal()}>
              {t("common.tryAgain")}
            </button>
          </div>
        ) : terminalUrl ? (
          <iframe
            src={terminalUrl}
            title={t("agentWorkspace.terminalTitle", { agent: label })}
          />
        ) : null}
      </div>
    </section>
  );
}
