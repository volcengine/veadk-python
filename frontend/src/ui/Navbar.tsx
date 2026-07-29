import { Fragment, type ReactNode, useState } from "react";
import { ArrowLeftRight, ChevronDown, ChevronRight } from "lucide-react";
import type { RuntimeScope } from "../adk/client";
import { AgentSelector, type SelectedRuntime } from "./AgentSelector";

export interface Crumb {
  label: string;
  /** When set, the crumb is a clickable link; omit for the current (last) crumb. */
  onClick?: () => void;
}

export interface NavbarProps {
  appName: string;
  onAppChange: (app: string) => void;
  /** Map a picker id to its display label (e.g. remote AgentKit apps). */
  agentLabel?: (id: string) => string;
  agentsSource: "local" | "cloud";
  localApps: string[];
  currentRuntime?: SelectedRuntime;
  runtimeScope: RuntimeScope;
  onBrowseAgents?: () => void;
  /** When set, the left side shows this title instead of the agent picker. */
  title?: string;
  /** Optional action rendered immediately before the page title. */
  titleLeading?: ReactNode;
  /** When set, the left side shows a breadcrumb trail (takes priority over title). */
  crumbs?: Crumb[];
  /** Persistent app-level status rendered on the far right. */
  rightContent?: ReactNode;
}

/** Top bar inside the main panel: agent picker / title / breadcrumb on the left.
 *  (The account block lives at the bottom of the sidebar.) */
export function Navbar({
  appName,
  onAppChange,
  agentLabel,
  agentsSource,
  localApps,
  currentRuntime,
  runtimeScope,
  onBrowseAgents,
  title,
  titleLeading,
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
            <div className="navbar-title-group">
              {titleLeading}
              <div className="navbar-title" title={title}>{title}</div>
            </div>
          ) : (
            <div className="navbar-title-group">
              {titleLeading}
              <AgentSelect
                appName={appName}
                onAppChange={onAppChange}
                agentLabel={agentLabel}
                agentsSource={agentsSource}
                localApps={localApps}
                currentRuntime={currentRuntime}
                runtimeScope={runtimeScope}
                onBrowseAgents={onBrowseAgents}
              />
            </div>
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

/** Title-styled trigger backed by the complete Agent picker. */
function AgentSelect({
  appName,
  onAppChange,
  agentLabel,
  agentsSource,
  localApps,
  currentRuntime,
  runtimeScope,
  onBrowseAgents,
}: Pick<
  NavbarProps,
  | "appName"
  | "onAppChange"
  | "agentLabel"
  | "agentsSource"
  | "localApps"
  | "currentRuntime"
  | "runtimeScope"
  | "onBrowseAgents"
>) {
  const [open, setOpen] = useState(false);
  const label = (id: string) => (agentLabel ? agentLabel(id) : id);

  if (agentsSource === "cloud") {
    return (
      <div className="agent-switch">
        <span className="agent-dd-current">
          {appName ? label(appName) : "选择 Agent"}
        </span>
        {appName && onBrowseAgents ? (
          <button
            type="button"
            className="agent-switch-action"
            aria-label="切换智能体"
            title="切换智能体"
            onClick={onBrowseAgents}
          >
            <ArrowLeftRight aria-hidden="true" />
          </button>
        ) : null}
      </div>
    );
  }

  function close() {
    setOpen(false);
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
          <AgentSelector
            open
            variant="navbar"
            agentsSource={agentsSource}
            localApps={localApps}
            currentId={appName}
            currentRuntime={currentRuntime}
            runtimeScope={runtimeScope}
            onSelect={(id) => {
              onAppChange(id);
              close();
            }}
            onClose={close}
          />
        </>
      )}
    </div>
  );
}
