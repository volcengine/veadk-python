import { type CSSProperties, useEffect, useRef, useState } from "react";
import {
  Info,
  LogOut,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { createPortal } from "react-dom";
import type {
  AdkSession,
  SiteBranding,
  StudioAccess,
  UiFeatures,
} from "../adk/client";
import { sessionTitle } from "../blocks";
import { displayName, profilePictureUrl } from "../adk/identity";
import { SearchButton } from "./Search";
import volcengineLogo from "../assets/volcengine.svg";

const SIDEBAR_AUTO_COLLAPSE_QUERY = "(max-width: 860px)";

/** A minimal Agent face that stays friendly and legible at sidebar-icon size. */
function ManageAgentsIcon() {
  return (
    <svg
      className="icon sidebar-agent-face"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect x="4.25" y="5.25" width="15.5" height="13.5" rx="4.75" />
      <path className="sidebar-agent-face__eye sidebar-agent-face__eye--left" d="M8.5 10.7v2" />
      <path className="sidebar-agent-face__eye sidebar-agent-face__eye--right" d="M15.5 10.7v2" />
    </svg>
  );
}

export interface SidebarProps {
  branding: SiteBranding;
  sessions: AdkSession[];
  currentSessionId: string;
  /** Per-module feature gates; omitted modules default to shown. */
  features?: UiFeatures;
  /** Server-derived role and capabilities. */
  access: StudioAccess;
  /** Session ids that are currently streaming a reply (shows a live dot). */
  streamingSids?: Set<string>;
  onNewChat: () => void;
  onSearch: () => void;
  onQuickCreate: () => void;
  onSkillCenter: () => void;
  onAddAgent: () => void;
  onMyAgents: () => void;
  onPickSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  userInfo?: Record<string, unknown>;
  version: string;
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

const STUDIO_ROLE_LABELS: Record<StudioAccess["role"], string> = {
  admin: "管理员",
  developer: "开发者",
  user: "普通用户",
};

function StudioRoleBadge({ role }: { role: StudioAccess["role"] }) {
  const label = STUDIO_ROLE_LABELS[role];
  return (
    <span className={`studio-role-badge studio-role-badge--${role}`} title={label}>
      {label}
    </span>
  );
}

function SystemInfoDialog({
  version,
  onClose,
}: {
  version: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return createPortal(
    <div className="confirm-scrim" onMouseDown={onClose}>
      <section
        className="confirm-box system-info-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="system-info-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="system-info-head">
          <h2 id="system-info-title">系统信息</h2>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="关闭系统信息"
            autoFocus
          >
            <X className="icon" aria-hidden="true" />
          </button>
        </header>
        <dl className="system-info-meta">
          <div>
            <dt>当前版本</dt>
            <dd>{version || "—"}</dd>
          </div>
        </dl>
      </section>
    </div>,
    document.body,
  );
}

/** Account block pinned at the bottom of the sidebar: avatar + name, with a
 *  popover (opening upward) holding the full identity and account actions. */
function SidebarUser({
  access,
  userInfo,
  version,
  onLogout,
}: Pick<SidebarProps, "access" | "userInfo" | "version" | "onLogout">) {
  const [open, setOpen] = useState(false);
  const [systemInfoOpen, setSystemInfoOpen] = useState(false);
  const [failedAvatarUrl, setFailedAvatarUrl] = useState("");
  if (!userInfo) return null;
  const name = displayName(userInfo);
  const email = typeof userInfo.email === "string" ? userInfo.email : "";
  const initial = (name || "U").slice(0, 1).toUpperCase();
  const avatarStyle = smokeAvatarStyle(name || email || initial);
  const pictureUrl = profilePictureUrl(userInfo);
  const visiblePictureUrl = pictureUrl === failedAvatarUrl ? "" : pictureUrl;
  return (
    <div className="sidebar-user">
      <button
        className="sidebar-user-btn"
        onClick={() => setOpen((o) => !o)}
        title={email ? `${name}\n${email}` : name}
      >
        <span
          className={`account-avatar${visiblePictureUrl ? " has-image" : ""}`}
          style={avatarStyle}
        >
          {initial}
          {visiblePictureUrl ? (
            <img
              className="account-avatar-image"
              src={visiblePictureUrl}
              alt=""
              aria-hidden="true"
              referrerPolicy="no-referrer"
              onError={() => setFailedAvatarUrl(visiblePictureUrl)}
            />
          ) : null}
        </span>
        <span className="sidebar-user-identity">
          <span className="sidebar-user-primary">
            <span className="sidebar-user-name">{name}</span>
            <StudioRoleBadge role={access.role} />
          </span>
          {email && email !== name && (
            <span className="sidebar-user-email">{email}</span>
          )}
        </span>
      </button>
      {open && (
        <>
          <div className="menu-scrim" onClick={() => setOpen(false)} />
          <div className="account-pop sidebar-user-pop">
            <div className="account-head">
              <span
                className={`account-avatar account-avatar--lg${
                  visiblePictureUrl ? " has-image" : ""
                }`}
                style={avatarStyle}
              >
                {initial}
                {visiblePictureUrl ? (
                  <img
                    className="account-avatar-image"
                    src={visiblePictureUrl}
                    alt=""
                    aria-hidden="true"
                    referrerPolicy="no-referrer"
                    onError={() => setFailedAvatarUrl(visiblePictureUrl)}
                  />
                ) : null}
              </span>
              <div className="account-id">
                <div className="account-name-row">
                  <div className="account-name">{name}</div>
                  <StudioRoleBadge role={access.role} />
                </div>
                {email && email !== name && <div className="account-sub">{email}</div>}
              </div>
            </div>
            <button
              type="button"
              className="account-action"
              onClick={() => {
                setOpen(false);
                setSystemInfoOpen(true);
              }}
            >
              <Info className="icon" /> 系统信息
            </button>
            <button
              type="button"
              className="account-action"
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
      {systemInfoOpen ? (
        <SystemInfoDialog version={version} onClose={() => setSystemInfoOpen(false)} />
      ) : null}
    </div>
  );
}

export function Sidebar({
  branding,
  sessions,
  currentSessionId,
  features,
  access,
  streamingSids,
  onNewChat,
  onSearch,
  onQuickCreate,
  onSkillCenter,
  onAddAgent,
  onMyAgents,
  onPickSession,
  onDeleteSession,
  userInfo,
  version,
  onLogout,
}: SidebarProps) {
  // Creation and Skill Center live outside the #748-style sidebar.
  void onQuickCreate;
  void onSkillCenter;
  void onAddAgent;
  // Per-module feature gates; a missing flag defaults to shown.
  const show = (k: keyof NonNullable<typeof features>) => features?.[k] !== false;
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const autoCollapsedRef = useRef(
    typeof window !== "undefined" &&
      window.matchMedia(SIDEBAR_AUTO_COLLAPSE_QUERY).matches,
  );
  const [collapsed, setCollapsed] = useState(autoCollapsedRef.current);
  const sorted = [...sessions].sort(
    (a, b) => (b.lastUpdateTime ?? 0) - (a.lastUpdateTime ?? 0),
  );
  const toggleCollapsed = () => {
    autoCollapsedRef.current = false;
    setCollapsed((value) => !value);
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
          <button
            type="button"
            className="brand"
            onClick={onNewChat}
            aria-label="返回首页"
            title="返回首页"
          >
            <img
              className="brand-logo"
              src={branding.logoUrl || volcengineLogo}
              width={20}
              height={20}
              alt=""
              aria-hidden
            />
            <span className="brand-title">{branding.title}</span>
          </button>
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
        {show("newChat") && (
          <button
            className="new-chat new-chat--conversation"
            onClick={onNewChat}
            aria-label="新会话"
            title="新会话"
          >
            <Plus className="icon" />
            <span className="sidebar-nav-label">新会话</span>
          </button>
        )}
        <button
          className="new-chat new-chat--agents"
          onClick={onMyAgents}
          aria-label="智能体"
          title="智能体"
        >
          <ManageAgentsIcon />
          <span className="sidebar-nav-label">智能体</span>
        </button>
        {show("search") && <SearchButton onClick={onSearch} />}
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
          {sorted.map((s) => {
            const title = sessionTitle(s.events);
            return (
              <div
                key={s.id}
                className={`history-item ${s.id === currentSessionId ? "active" : ""}`}
              >
                <button
                  className="history-item-btn"
                  onClick={() => onPickSession(s.id)}
                  title={title}
                >
                  {streamingSids?.has(s.id) && (
                    <span className="history-streaming" title="正在生成…" aria-label="正在生成" />
                  )}
                  <span className="history-title">{title}</span>
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
            );
          })}
        </div>
      </div>
      )}

      <SidebarUser access={access}
        userInfo={userInfo}
        version={version}
        onLogout={onLogout}
      />
    </aside>
  );
}
