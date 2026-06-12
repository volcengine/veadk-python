import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight, Cpu, Loader2, LogOut, Wrench } from "lucide-react";
import { getAgentInfo, type AgentInfo } from "../adk/client";
import { displayName } from "../adk/identity";

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
  userInfo?: Record<string, unknown>;
  onLogout: () => void;
  /** When set, the left side shows this title instead of the agent picker. */
  title?: string;
  /** When set, the left side shows a breadcrumb trail (takes priority over title). */
  crumbs?: Crumb[];
}

/** Top bar inside the main panel: agent picker on the left, account on the right. */
export function Navbar({ apps, appName, onAppChange, agentLabel, userInfo, onLogout, title, crumbs }: NavbarProps) {
  return (
    <div className="navbar">
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
        <div className="navbar-title">{title}</div>
      ) : (
        <AgentSelect apps={apps} appName={appName} onAppChange={onAppChange} agentLabel={agentLabel} />
      )}
      <Account userInfo={userInfo} onLogout={onLogout} />
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
  const label = (id: string) => (agentLabel ? agentLabel(id) : id);

  function loadInfo(app: string) {
    setHovered(app);
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
                {hovered === a && <AgentFlyout state={cache[a]} />}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function AgentFlyout({ state }: { state: InfoState }) {
  return (
    <div className="agent-dd-flyout">
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

/** Avatar-only account button; clicking opens a small panel with name + logout. */
function Account({ userInfo, onLogout }: Pick<NavbarProps, "userInfo" | "onLogout">) {
  const [open, setOpen] = useState(false);
  if (!userInfo) return null;
  const name = displayName(userInfo);
  const email = String(userInfo.email ?? userInfo.sub ?? "");
  const initial = (name || "U").slice(0, 1).toUpperCase();
  return (
    <div className="account">
      <button className="account-avatar" title={name} onClick={() => setOpen((o) => !o)}>
        {initial}
      </button>
      {open && (
        <>
          <div className="menu-scrim" onClick={() => setOpen(false)} />
          <div className="account-pop">
            <div className="account-head">
              <div className="account-avatar account-avatar--lg">{initial}</div>
              <div className="account-id">
                <div className="account-name">{name}</div>
                {email && email !== name && <div className="account-sub">{email}</div>}
              </div>
            </div>
            <button
              className="account-logout"
              onClick={() => {
                setOpen(false);
                onLogout();
              }}
            >
              <LogOut className="icon" /> 退出登录
            </button>
          </div>
        </>
      )}
    </div>
  );
}
