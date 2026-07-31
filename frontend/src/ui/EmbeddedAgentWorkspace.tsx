import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type SVGProps,
} from "react";

import arkclawLogo from "../assets/builtin-agents/arkclaw.png";
import hermesLogo from "../assets/builtin-agents/hermes.png";
import type {
  EmbeddedAgentSession,
} from "../adk/embeddedAgents";
import {
  SandboxBrowserIcon,
  SandboxTerminalIcon,
} from "./icons/SandboxControlIcons";
import "./EmbeddedAgentWorkspace.css";

type Surface = "webui" | "terminal";

const DETAILS = {
  openclaw: {
    label: "OpenClaw",
    logo: arkclawLogo,
  },
  hermes: {
    label: "Hermes",
    logo: hermesLogo,
  },
} as const;

function CloseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        d="m5.5 5.5 9 9m0-9-9 9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function EmbeddedAgentWorkspace({
  session,
  closing,
  onClose,
}: {
  session: EmbeddedAgentSession;
  closing: boolean;
  onClose: () => void;
}) {
  const detail = DETAILS[session.kind];
  const [surface, setSurface] = useState<Surface>("webui");
  const [visited, setVisited] = useState<Record<Surface, boolean>>({
    webui: true,
    terminal: false,
  });
  const [loading, setLoading] = useState<Record<Surface, boolean>>({
    webui: true,
    terminal: true,
  });
  const webuiTabRef = useRef<HTMLButtonElement>(null);
  const terminalTabRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setSurface("webui");
    setVisited({ webui: true, terminal: false });
    setLoading({ webui: true, terminal: true });
  }, [session.id]);

  const selectSurface = (next: Surface) => {
    setSurface(next);
    setVisited((current) => (
      current[next] ? current : { ...current, [next]: true }
    ));
  };

  const handleTabKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    current: Surface,
  ) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? "webui"
        : event.key === "End"
          ? "terminal"
          : current === "webui" ? "terminal" : "webui";
    selectSurface(next);
    (next === "webui" ? webuiTabRef : terminalTabRef).current?.focus();
  };

  return (
    <section className="embedded-agent-workspace" aria-label={`${detail.label} 工作区`}>
      <header className="embedded-agent-toolbar">
        <div className="embedded-agent-identity">
          <img src={detail.logo} alt="" />
          <div>
            <strong>{detail.label}</strong>
            <span>AgentKit 临时会话</span>
          </div>
        </div>

        <div
          className="embedded-agent-tabs"
          role="tablist"
          aria-label={`${detail.label} 页面`}
        >
          <button
            ref={webuiTabRef}
            type="button"
            role="tab"
            id={`${session.id}-webui-tab`}
            aria-controls={`${session.id}-webui-panel`}
            aria-selected={surface === "webui"}
            tabIndex={surface === "webui" ? 0 : -1}
            className={surface === "webui" ? "is-active" : ""}
            onClick={() => selectSurface("webui")}
            onKeyDown={(event) => handleTabKeyDown(event, "webui")}
          >
            <SandboxBrowserIcon />
            主页面
          </button>
          <button
            ref={terminalTabRef}
            type="button"
            role="tab"
            id={`${session.id}-terminal-tab`}
            aria-controls={`${session.id}-terminal-panel`}
            aria-selected={surface === "terminal"}
            tabIndex={surface === "terminal" ? 0 : -1}
            className={surface === "terminal" ? "is-active" : ""}
            onClick={() => selectSurface("terminal")}
            onKeyDown={(event) => handleTabKeyDown(event, "terminal")}
          >
            <SandboxTerminalIcon />
            Terminal
          </button>
        </div>

        <button
          type="button"
          className="embedded-agent-close"
          disabled={closing}
          aria-label={`关闭 ${detail.label} 工作区`}
          title="关闭工作区"
          onClick={onClose}
        >
          {closing ? <span className="embedded-agent-spinner" /> : <CloseIcon />}
        </button>
      </header>

      <div className="embedded-agent-stage">
        {(["webui", "terminal"] as const).map((item) => {
          if (!visited[item]) return null;
          const active = surface === item;
          const url = item === "webui" ? session.webuiUrl : session.terminalUrl;
          const label = item === "webui" ? "主页面" : "Terminal";
          return (
            <div
              key={item}
              id={`${session.id}-${item}-panel`}
              role="tabpanel"
              aria-labelledby={`${session.id}-${item}-tab`}
              aria-hidden={!active}
              hidden={!active}
              className={`embedded-agent-panel${active ? " is-active" : ""}`}
            >
              {loading[item] && (
                <div className="embedded-agent-loading" role="status">
                  <span className="embedded-agent-spinner" aria-hidden="true" />
                  <span>正在加载 {detail.label} {label}</span>
                </div>
              )}
              <iframe
                src={url}
                title={`${detail.label} ${label}`}
                allow="clipboard-read; clipboard-write; fullscreen"
                sandbox="allow-downloads allow-forms allow-modals allow-popups allow-pointer-lock allow-same-origin allow-scripts"
                onLoad={() => setLoading((current) => ({
                  ...current,
                  [item]: false,
                }))}
              />
            </div>
          );
        })}
      </div>
    </section>
  );
}
