import { type CSSProperties, useEffect, useRef, useState } from "react";
import {
  ChevronRight,
  LogOut,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Trash2,
} from "lucide-react";
import type { AdkSession, SiteBranding, UiFeatures } from "../adk/client";
import { sessionTitle } from "../blocks";
import { displayName } from "../adk/identity";
import { SkillCenterButton } from "./SkillCenter";
import { SearchButton } from "./Search";
import { AgentSelector, type SelectedRuntime } from "./AgentSelector";
import { AgentIdentityIcon } from "./AgentIdentityIcon";
import volcengineLogo from "../assets/volcengine.svg";

const SIDEBAR_AUTO_COLLAPSE_QUERY = "(max-width: 860px)";

/** Hand-drawn "quick create" mark: a lightning bolt (speed) with a spark. */
function QuickCreateIcon() {
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
      <path d="M12.5 3 5.5 13h5l-1 8 8-11h-5l.5-7z" fill="currentColor" stroke="none" />
      <path d="M19 4.5v3M17.5 6h3" opacity="0.85" />
    </svg>
  );
}

/** Agent roster with two compact tuning rails — management without a generic cube. */
function ManageAgentsIcon() {
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
      <circle cx="8.25" cy="7.75" r="3.15" />
      <path d="M2.9 19.2c.45-3.45 2.48-5.35 5.35-5.35 2.4 0 4.2 1.28 4.98 3.66" />
      <path d="M17.4 4.5v15M14.8 9h5.2M14.8 15.3h5.2" />
      <circle cx="17.4" cy="9" r="1.15" fill="currentColor" stroke="none" />
      <circle cx="17.4" cy="15.3" r="1.15" fill="currentColor" stroke="none" />
    </svg>
  );
}

export interface SidebarProps {
  branding: SiteBranding;
  sessions: AdkSession[];
  currentSessionId: string;
  /** Per-module feature gates; omitted modules default to shown. */
  features?: UiFeatures;
  /** Session ids that are currently streaming a reply (shows a live dot). */
  streamingSids?: Set<string>;
  /** Agent picker: source, local app list, current selection + label. */
  agentsSource?: "local" | "cloud";
  localApps?: string[];
  currentAgentId?: string;
  currentAgentLabel?: string;
  /** The connected runtime (drives the picker's detail panel). */
  currentRuntime?: SelectedRuntime;
  /** Identity used to badge the user's own runtimes in the cloud picker. */
  author?: string;
  onSelectAgent?: (id: string) => void;
  onNewChat: () => void;
  onSearch: () => void;
  onQuickCreate: () => void;
  onSkillCenter: () => void;
  onAddAgent: () => void;
  onManageAgents: () => void;
  onPickSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  userInfo?: Record<string, unknown>;
  onLogout: () => void;
}

/** Stable per-user blue/cyan smoke palette so avatars feel individual without flicker. */
function smokeAvatarStyle(seed: string): CSSProperties {
  let hash = 2166136261;
  for (const char of seed) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  const value = hash >>> 0;
  return {
    "--avatar-hue-a": 194 + (value % 22),
    "--avatar-hue-b": 214 + ((value >>> 6) % 25),
    "--avatar-hue-c": 176 + ((value >>> 12) % 25),
    "--avatar-x": `${22 + ((value >>> 18) % 55)}%`,
    "--avatar-y": `${18 + ((value >>> 24) % 58)}%`,
  } as CSSProperties;
}

/** Account block pinned at the bottom of the sidebar: avatar + name, with a
 *  popover (opening upward) holding the full identity + logout. */
function SidebarUser({
  userInfo,
  onLogout,
}: Pick<SidebarProps, "userInfo" | "onLogout">) {
  const [open, setOpen] = useState(false);
  if (!userInfo) return null;
  const name = displayName(userInfo);
  const email = String(userInfo.email ?? userInfo.sub ?? "");
  const initial = (name || "U").slice(0, 1).toUpperCase();
  const avatarStyle = smokeAvatarStyle(name || email || initial);
  return (
    <div className="sidebar-user">
      <button
        className="sidebar-user-btn"
        onClick={() => setOpen((o) => !o)}
        title={name}
      >
        <span className="account-avatar" style={avatarStyle}>{initial}</span>
        <span className="sidebar-user-name">{name}</span>
      </button>
      {open && (
        <>
          <div className="menu-scrim" onClick={() => setOpen(false)} />
          <div className="account-pop sidebar-user-pop">
            <div className="account-head">
              <div className="account-avatar account-avatar--lg" style={avatarStyle}>
                {initial}
              </div>
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

export function Sidebar({
  branding,
  sessions,
  currentSessionId,
  features,
  streamingSids,
  agentsSource = "local",
  localApps = [],
  currentAgentId = "",
  currentAgentLabel = "",
  currentRuntime,
  author = "",
  onSelectAgent,
  onNewChat,
  onSearch,
  onQuickCreate,
  onSkillCenter,
  onAddAgent,
  onManageAgents,
  onPickSession,
  onDeleteSession,
  userInfo,
  onLogout,
}: SidebarProps) {
  // onAddAgent is now reached through the "添加 Agent" chooser, not a direct
  // sidebar button; kept in the props contract for the App-level handler.
  void onAddAgent;
  // Per-module feature gates; a missing flag defaults to shown.
  const show = (k: keyof NonNullable<typeof features>) => features?.[k] !== false;
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const autoCollapsedRef = useRef(
    typeof window !== "undefined" &&
      window.matchMedia(SIDEBAR_AUTO_COLLAPSE_QUERY).matches,
  );
  const [collapsed, setCollapsed] = useState(autoCollapsedRef.current);
  const [anchorTop, setAnchorTop] = useState(0);
  const rowRef = useRef<HTMLButtonElement>(null);
  const toggleSelector = () => {
    // Align the drawer's top with the picker row (its offsetParent is .sidebar).
    if (rowRef.current) setAnchorTop(rowRef.current.offsetTop);
    setSelectorOpen((o) => !o);
  };
  const sorted = [...sessions].sort(
    (a, b) => (b.lastUpdateTime ?? 0) - (a.lastUpdateTime ?? 0),
  );
  const toggleCollapsed = () => {
    autoCollapsedRef.current = false;
    setCollapsed((value) => !value);
    setSelectorOpen(false);
    setMenuFor(null);
  };
  useEffect(() => {
    const query = window.matchMedia(SIDEBAR_AUTO_COLLAPSE_QUERY);
    const handleViewportChange = (event: MediaQueryListEvent) => {
      if (event.matches) {
        setCollapsed((current) => {
          if (current) return current;
          autoCollapsedRef.current = true;
          return true;
        });
      } else if (autoCollapsedRef.current) {
        autoCollapsedRef.current = false;
        setCollapsed(false);
      }
    };

    query.addEventListener("change", handleViewportChange);
    return () => query.removeEventListener("change", handleViewportChange);
  }, []);
  return (
    <aside className={`sidebar ${collapsed ? "is-collapsed" : ""}`}>
      <div className="sidebar-top">
        <div className="sidebar-brand-row">
          <div className="brand">
            <img
              className="brand-logo"
              src={branding.logoUrl || volcengineLogo}
              width={20}
              height={20}
              alt=""
              aria-hidden
            />
            <span className="brand-title">{branding.title}</span>
          </div>
          <button
            type="button"
            className="sidebar-collapse-toggle"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
            title={collapsed ? "展开侧边栏" : "收起侧边栏"}
          >
            {collapsed ? (
              <PanelLeftOpen className="icon" />
            ) : (
              <PanelLeftClose className="icon" />
            )}
          </button>
        </div>
        {onSelectAgent &&
          (() => {
            // Cloud mode with nothing connected: a red prompt so the default
            // isn't mistaken for a real agent.
            const needsPick = agentsSource === "cloud" && !currentAgentId;
            const selectedRegion =
              agentsSource === "cloud" && !needsPick && currentRuntime?.region
                ? currentRuntime.region === "cn-beijing"
                  ? "北京"
                  : currentRuntime.region === "cn-shanghai"
                    ? "上海"
                    : currentRuntime.region
                : "";
            return (
              <button
                ref={rowRef}
                className={`agent-row ${needsPick ? "agent-row--empty" : ""}`}
                onClick={toggleSelector}
                aria-label={needsPick ? "请选择 Agent" : currentAgentLabel || "选择 Agent"}
                title="切换 Agent"
              >
                <AgentIdentityIcon className="icon agent-row-lead" />
                <span className="agent-row-name">
                  {needsPick ? "请选择 Agent" : currentAgentLabel || "选择 Agent"}
                </span>
                {selectedRegion && (
                  <span className="agent-row-region">{selectedRegion}</span>
                )}
                <ChevronRight className={`icon agent-row-chev ${selectorOpen ? "open" : ""}`} />
              </button>
            );
          })()}
        {onSelectAgent && (
          <AgentSelector
            open={selectorOpen}
            onClose={() => setSelectorOpen(false)}
            anchorTop={anchorTop}
            agentsSource={agentsSource}
            localApps={localApps}
            currentId={currentAgentId}
            currentRuntime={currentRuntime}
            author={author}
            onSelect={onSelectAgent}
          />
        )}
        {show("newChat") && (
          <button
            className="new-chat"
            onClick={onNewChat}
            aria-label="新会话"
            title="新会话"
          >
            <Plus className="icon" />
            <span className="sidebar-nav-label">新会话</span>
          </button>
        )}
        {show("search") && <SearchButton onClick={onSearch} />}
        {show("skillCenter") && <SkillCenterButton onClick={onSkillCenter} />}
        {show("addAgent") && (
          <button
            className="new-chat"
            onClick={onQuickCreate}
            aria-label="添加 Agent"
            title="添加 Agent"
          >
            <QuickCreateIcon />
            <span className="sidebar-nav-label">添加 Agent</span>
          </button>
        )}
        {show("manageAgents") && (
          <button
            className="new-chat"
            onClick={onManageAgents}
            aria-label="管理 Agent"
            title="管理 Agent"
          >
            <ManageAgentsIcon />
            <span className="sidebar-nav-label">管理 Agent</span>
          </button>
        )}
      </div>

      {show("history") && (
      <div className="sidebar-history">
        <div className="history-head">
          <span>历史会话</span>
          {show("newChat") && (
            <button
              type="button"
              className="history-new-chat"
              onClick={onNewChat}
              aria-label="新建会话"
              title="新建会话"
            >
              <Plus className="icon" />
            </button>
          )}
        </div>
        <div className="history-list">
          {sorted.length === 0 && (
            <div className="history-empty">暂无会话</div>
          )}
          {sorted.map((s) => (
            <div
              key={s.id}
              className={`history-item ${s.id === currentSessionId ? "active" : ""}`}
            >
              <button
                className="history-item-btn"
                onClick={() => onPickSession(s.id)}
                title={s.id}
              >
                {streamingSids?.has(s.id) && (
                  <span className="history-streaming" title="正在生成…" aria-label="正在生成" />
                )}
                <span className="history-title">{sessionTitle(s.events)}</span>
              </button>
              <button
                className="history-more"
                title="更多"
                onClick={() => setMenuFor((m) => (m === s.id ? null : s.id))}
              >
                <MoreHorizontal className="icon" />
              </button>
              {menuFor === s.id && (
                <>
                  <div className="menu-scrim" onClick={() => setMenuFor(null)} />
                  <div className="history-menu">
                    <button
                      className="menu-item menu-item--danger"
                      onClick={() => {
                        setMenuFor(null);
                        onDeleteSession(s.id);
                      }}
                    >
                      <Trash2 className="icon" /> 删除
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
      )}

      <SidebarUser userInfo={userInfo} onLogout={onLogout} />
    </aside>
  );
}
