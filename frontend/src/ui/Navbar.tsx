import { Fragment, type ReactNode, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Cpu, Loader2, Wrench } from "lucide-react";
import { getAgentInfo, type AgentInfo } from "../adk/client";

export interface Crumb {
  label: string;
  /** When set, the crumb is a clickable link; omit for the current (last) crumb. */
  onClick?: () => void;
}

export interface NavbarProps {
  apps: string[];
  appName: string;
  onAppChange: (app: string) => void;
  /** Map a picker id to its display label (e.g. remote AgentKit apps). */
  agentLabel?: (id: string) => string;
  /** When set, the left side shows this title instead of the agent picker. */
  title?: string;
  /** When set, the left side shows a breadcrumb trail (takes priority over title). */
  crumbs?: Crumb[];
  /** Persistent app-level status rendered on the far right. */
  rightContent?: ReactNode;
}

/** Top bar inside the main panel: agent picker / title / breadcrumb on the left.
 *  (The account block lives at the bottom of the sidebar.) */
export function Navbar({
  apps,
  appName,
  onAppChange,
  agentLabel,
  title,
  crumbs,
  rightContent,
}: NavbarProps) {
  return (
    <div className="navbar">
      <div className="navbar-left">
        <div className="navbar-default">
          {crumbs && crumbs.length > 0 ? (
            <nav className="navbar-crumbs" aria-label="面包屑">
              {crumbs.map((c, i) => (
                <Fragment key={i}>
                  {i > 0 && <ChevronRight className="crumb-sep" />}
                  {c.onClick ? (
                    <button className="crumb crumb-link" onClick={c.onClick}>
                      {c.label}
                    </button>
                  ) : (
                    <span className="crumb crumb-current">{c.label}</span>
                  )}
                </Fragment>
              ))}
            </nav>
          ) : title ? (
            <div className="navbar-title" title={title}>{title}</div>
          ) : (
            <AgentSelect
              apps={apps}
              appName={appName}
              onAppChange={onAppChange}
              agentLabel={agentLabel}
            />
          )}
        </div>
        <div id="veadk-page-header-left" className="navbar-portal-slot" />
      </div>
      <div className="navbar-right">
        <div id="veadk-page-header-actions" className="navbar-portal-actions" />
        {rightContent}
      </div>
    </div>
  );
}

type InfoState = AgentInfo | "loading" | "error" | undefined;

/** ChatGPT-style dropdown: a heading trigger that opens a popover of agents.
 *  Hovering a row reveals a flyout with that agent's model + tools. */
function AgentSelect({
  apps,
  appName,
  onAppChange,
  agentLabel,
}: Pick<NavbarProps, "apps" | "appName" | "onAppChange" | "agentLabel">) {
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, InfoState>>({});
  const [flyoutTop, setFlyoutTop] = useState<number>(0);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const label = (id: string) => (agentLabel ? agentLabel(id) : id);

  function loadInfo(app: string) {
    setHovered(app);
    const rowEl = rowRefs.current[app];
    if (rowEl) {
      const rect = rowEl.getBoundingClientRect();
      const ddEl = rowEl.closest('.agent-dd');
      if (ddEl) {
        const ddRect = ddEl.getBoundingClientRect();
        // Position relative to .agent-dd container, accounting for menu's top offset
        setFlyoutTop(rect.top - ddRect.top);
      }
    }
    if (cache[app] !== undefined) return;
    setCache((c) => ({ ...c, [app]: "loading" }));
    getAgentInfo(app)
      .then((info) => setCache((c) => ({ ...c, [app]: info })))
      .catch(() => setCache((c) => ({ ...c, [app]: "error" })));
  }

  function close() {
    setOpen(false);
    setHovered(null);
  }

  return (
    <div className="agent-dd">
      <button className="agent-dd-trigger" onClick={() => setOpen((o) => !o)}>
        <span className="agent-dd-current">{appName ? label(appName) : "选择 Agent"}</span>
        <ChevronDown className={`agent-dd-chev ${open ? "open" : ""}`} />
      </button>
      {open && (
        <>
          <div className="menu-scrim" onClick={close} />
          <div className="agent-dd-menu">
            {apps.map((a) => (
              <div
                key={a}
                ref={(el) => (rowRefs.current[a] = el)}
                className="agent-dd-row"
                onMouseEnter={() => loadInfo(a)}
                onMouseLeave={() => setHovered((h) => (h === a ? null : h))}
              >
                <button
                  className={`agent-dd-item ${a === appName ? "active" : ""}`}
                  onClick={() => {
                    onAppChange(a);
                    close();
                  }}
                >
                  <span className="agent-dd-item-name">{label(a)}</span>
                  {a === appName && <span className="agent-dd-item-dot" aria-label="当前" />}
                </button>
              </div>
            ))}
          </div>
          {hovered && <AgentFlyout state={cache[hovered]} top={flyoutTop} />}
        </>
      )}
    </div>
  );
}

function AgentFlyout({ state, top }: { state: InfoState; top: number }) {
  return (
    <div className="agent-dd-flyout" style={{ top: `${top}px` }}>
      {state === undefined || state === "loading" ? (
        <div className="agent-dd-fly-loading">
          <Loader2 className="icon spin" /> 加载中…
        </div>
      ) : state === "error" ? (
        <div className="agent-dd-fly-loading">读取信息失败</div>
      ) : (
        <>
          <div className="agent-dd-fly-name">{state.name}</div>
          {state.description && (
            <div className="agent-dd-fly-desc">{state.description}</div>
          )}
          <div className="agent-dd-fly-field">
            <Cpu className="icon" />
            <span className="agent-dd-fly-model">{state.model}</span>
          </div>
          {state.tools.length > 0 && (
            <div className="agent-dd-fly-field agent-dd-fly-field--tools">
              <Wrench className="icon" />
              <div className="agent-dd-fly-chips">
                {state.tools.map((t) => (
                  <span key={t} className="agent-dd-chip">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
          {state.subAgents.length > 0 && (
            <div className="agent-dd-fly-field">
              <span className="agent-dd-fly-label">子 Agent</span>
              <span className="agent-dd-fly-model">{state.subAgents.join("、")}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
