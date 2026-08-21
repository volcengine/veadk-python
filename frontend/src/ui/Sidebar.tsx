import {
  type CSSProperties,
  type SVGProps,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Info,
  LogOut,
  MoreHorizontal,
  Plus,
  Trash2,
} from "lucide-react";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Clock } from "@openai/apps-sdk-ui/components/Icon";
import type {
  AdkSession,
  SiteBranding,
  StudioAccess,
  UiFeatures,
} from "../adk/client";
import type { SandboxSession, SandboxThreadSummary } from "../adk/sandbox";
import { sessionTitle } from "../blocks";
import { displayName, profilePictureUrl } from "../adk/identity";
import { SearchButton } from "./Search";
import { AgentKitPromoCard } from "./AgentKitPromoCard";
import { IssueFeedbackIcon } from "./icons/FeedbackIcons";
import {
  NewChatIcon,
  ResourceLibraryIcon,
  SidebarAgentIcon,
  SidebarCollapseIcon,
  SidebarExpandIcon,
} from "./icons/SidebarIcons";
import defaultSiteLogo from "../assets/logo.svg";
import byteplusLogo from "../assets/byteplus.svg";
import "./Sidebar.css";

const SIDEBAR_AUTO_COLLAPSE_QUERY = "(max-width: 860px)";

export type SidebarPage =
  | "new-chat"
  | "agents"
  | "library"
  | "applications"
  | "cronjobs"
  | "search"
  | "feedback"
  | null;

export interface SidebarSandboxHistory {
  threads: SandboxThreadSummary[];
  currentThreadId: string;
  loading: boolean;
  error: string;
  hasMore: boolean;
  busyThreadId: string;
  newDisabled: boolean;
  onNew: () => void;
  onSelect: (threadId: string) => void;
  onLoadMore: () => void;
  onDelete: (thread: SandboxThreadSummary) => void;
}

export interface SidebarIntelligentHistory {
  sessions: SandboxSession[];
  currentSessionId: string;
  loading: boolean;
  error: string;
  busySessionId: string;
  openingSessionId: string;
  onSelect: (session: SandboxSession) => void;
  onDelete: (session: SandboxSession) => void;
}

type SidebarHistoryItem =
  | {
      kind: "agent";
      id: string;
      title: string;
      createdAt: number;
      session: AdkSession;
    }
  | {
      kind: "intelligent";
      id: string;
      title: string;
      createdAt: number;
      session: SandboxSession;
    };

function ApplicationsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      aria-hidden="true"
      {...props}
    >
      <circle cx="7" cy="7" r="2.25" />
      <circle cx="17" cy="7" r="2.25" />
      <circle cx="7" cy="17" r="2.25" />
      <circle cx="17" cy="17" r="2.25" />
    </svg>
  );
}

export interface SidebarProps {
  branding: SiteBranding;
  cloudProvider: "volcengine" | "byteplus";
  sessions: AdkSession[];
  currentSessionId: string;
  activePage: SidebarPage;
  /** Per-module feature gates; omitted modules default to shown. */
  features?: UiFeatures;
  /** Server-derived role and capabilities. */
  access: StudioAccess;
  /** Session ids that are currently streaming a reply (shows a live dot). */
  streamingSids?: Set<string>;
  /** Session ids whose latest reply is currently being evaluated. */
  evaluatingSids?: Set<string>;
  sandboxHistory?: SidebarSandboxHistory;
  intelligentHistory?: SidebarIntelligentHistory;
  onNewChat: () => void;
  onSearch: () => void;
  onQuickCreate: () => void;
  onLibrary: () => void;
  onAddAgent: () => void;
  onMyAgents: () => void;
  onApplications: () => void;
  onCronJobs: () => void;
  onSystemInfo: () => void;
  onIssueFeedback: () => void;
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

/** Account block pinned at the bottom of the sidebar: avatar + name, with a
 *  popover (opening upward) holding the full identity and account actions. */
function SidebarUser({
  access,
  userInfo,
  onSystemInfo,
  onIssueFeedback,
  onLogout,
}: Pick<
  SidebarProps,
  "access" | "userInfo" | "onSystemInfo" | "onIssueFeedback" | "onLogout"
>) {
  const [open, setOpen] = useState(false);
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
                onSystemInfo();
              }}
            >
              <Info className="icon" /> 系统信息
            </button>
            <button
              type="button"
              className="account-action"
              onClick={() => {
                setOpen(false);
                onIssueFeedback();
              }}
            >
              <IssueFeedbackIcon className="icon" /> 问题反馈
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
    </div>
  );
}

export function Sidebar({
  branding,
  cloudProvider,
  sessions,
  currentSessionId,
  activePage,
  features,
  access,
  streamingSids,
  evaluatingSids,
  sandboxHistory,
  intelligentHistory,
  onNewChat,
  onSearch,
  onQuickCreate,
  onLibrary,
  onAddAgent,
  onMyAgents,
  onApplications,
  onCronJobs,
  onSystemInfo,
  onIssueFeedback,
  onPickSession,
  onDeleteSession,
  userInfo,
  onLogout,
}: SidebarProps) {
  // Agent creation remains outside the main navigation.
  void onQuickCreate;
  void onAddAgent;
  // Per-module feature gates; a missing flag defaults to shown.
  const show = (k: keyof NonNullable<typeof features>) => features?.[k] !== false;
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const autoCollapsedRef = useRef(
    typeof window !== "undefined" &&
      window.matchMedia(SIDEBAR_AUTO_COLLAPSE_QUERY).matches,
  );
  const [collapsed, setCollapsed] = useState(autoCollapsedRef.current);
  const combinedHistory: SidebarHistoryItem[] = [
    ...sessions.map((session) => ({
      kind: "agent" as const,
      id: session.id,
      title: sessionTitle(session.events),
      createdAt: (session.lastUpdateTime ?? 0) * 1_000,
      session,
    })),
    ...(intelligentHistory?.sessions ?? []).map((session) => ({
      kind: "intelligent" as const,
      id: session.id,
      title: session.displayName || "智能构建",
      createdAt: Date.parse(session.createdAt) || 0,
      session,
    })),
  ].sort((left, right) => right.createdAt - left.createdAt);
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
  const fallbackLogo = cloudProvider === "byteplus" ? byteplusLogo : defaultSiteLogo;
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
              src={branding.logoUrl || fallbackLogo}
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
              <SidebarExpandIcon className="icon" />
            ) : (
              <SidebarCollapseIcon className="icon" />
            )}
          </button>
        </div>
        <nav className="sidebar-nav" aria-label="主导航">
          {show("newChat") && (
            <button
              className={`new-chat new-chat--conversation${
                activePage === "new-chat" ? " is-active" : ""
              }`}
              onClick={onNewChat}
              aria-label="新会话"
              aria-current={activePage === "new-chat" ? "page" : undefined}
              title="新会话"
            >
              <NewChatIcon className="icon" />
              <span className="sidebar-nav-label">新会话</span>
            </button>
          )}
          {show("search") && (
            <SearchButton active={activePage === "search"} onClick={onSearch} />
          )}
          <button
            className={`new-chat new-chat--agents${
              activePage === "agents" ? " is-active" : ""
            }`}
            onClick={onMyAgents}
            aria-label="智能体"
            aria-current={activePage === "agents" ? "page" : undefined}
            title="智能体"
          >
            <SidebarAgentIcon className="icon" />
            <span className="sidebar-nav-label">智能体</span>
          </button>
          <button
            className={`new-chat new-chat--library${
              activePage === "library" ? " is-active" : ""
            }`}
            onClick={onLibrary}
            aria-label="资源库"
            aria-current={activePage === "library" ? "page" : undefined}
            title="资源库"
          >
            <ResourceLibraryIcon className="icon" />
            <span className="sidebar-nav-label">资源库</span>
          </button>
          <button
            className={`new-chat new-chat--cronjobs${
              activePage === "cronjobs" ? " is-active" : ""
            }`}
            onClick={onCronJobs}
            aria-label="定时任务"
            aria-current={activePage === "cronjobs" ? "page" : undefined}
            title="定时任务"
          >
            <Clock className="icon" />
            <span className="sidebar-nav-label">定时任务</span>
            <Badge
              className="sidebar-cronjobs-beta"
              color="discovery"
              variant="soft"
              size="sm"
              pill
            >
              Beta
            </Badge>
          </button>
          <button
            className={`new-chat new-chat--applications${
              activePage === "applications" ? " is-active" : ""
            }`}
            onClick={onApplications}
            aria-label="自动化"
            aria-current={activePage === "applications" ? "page" : undefined}
            title="自动化"
          >
            <ApplicationsIcon className="icon" />
            <span className="sidebar-nav-label">自动化</span>
          </button>
        </nav>
      </div>

      {show("history") && (
        <div className="sidebar-history">
          <div className="history-head">
            <span>历史会话</span>
            {show("newChat") && (
              <button
                type="button"
                className="history-new-chat"
                onClick={sandboxHistory?.onNew ?? onNewChat}
                disabled={sandboxHistory?.newDisabled}
                aria-label="新建会话"
                title="新建会话"
              >
                <Plus className="icon" />
              </button>
            )}
          </div>
          <div className="history-list">
            {sandboxHistory ? (
              <>
                {sandboxHistory.loading && sandboxHistory.threads.length === 0 ? (
                  <div className="history-empty" role="status">
                    正在加载历史会话…
                  </div>
                ) : null}
                {sandboxHistory.error ? (
                  <div className="history-error" role="alert">
                    {sandboxHistory.error}
                  </div>
                ) : null}
                {!sandboxHistory.loading &&
                !sandboxHistory.error &&
                sandboxHistory.threads.length === 0 ? (
                  <div className="history-empty">暂无会话</div>
                ) : null}
                {sandboxHistory.threads.map((thread) => {
                  const active = thread.id === sandboxHistory.currentThreadId;
                  const title =
                    thread.name ||
                    thread.preview ||
                    `Thread ${thread.id.slice(0, 8)}`;
                  const busy = thread.id === sandboxHistory.busyThreadId;
                  return (
                    <div
                      key={thread.id}
                      className={`history-item ${active ? "active" : ""}`}
                    >
                      <button
                        type="button"
                        className="history-item-btn"
                        onClick={() => sandboxHistory.onSelect(thread.id)}
                        aria-current={active ? "page" : undefined}
                        title={title}
                        disabled={busy}
                      >
                        <span className="history-title">{title}</span>
                        {active ? (
                          <span className="history-current-badge">当前</span>
                        ) : null}
                      </button>
                      <button
                        type="button"
                        className="history-more"
                        aria-label={`管理历史会话：${title}`}
                        title="更多"
                        disabled={busy}
                        onClick={() =>
                          setMenuFor((current) =>
                            current === thread.id ? null : thread.id,
                          )
                        }
                      >
                        <MoreHorizontal className="icon" />
                      </button>
                      {menuFor === thread.id ? (
                        <>
                          <div
                            className="menu-scrim"
                            onClick={() => setMenuFor(null)}
                          />
                          <div className="history-menu">
                            <button
                              type="button"
                              className="menu-item menu-item--danger"
                              onClick={() => {
                                setMenuFor(null);
                                sandboxHistory.onDelete(thread);
                              }}
                            >
                              <Trash2 className="icon" /> 删除
                            </button>
                          </div>
                        </>
                      ) : null}
                    </div>
                  );
                })}
                {sandboxHistory.hasMore ? (
                  <button
                    type="button"
                    className="history-load-more"
                    disabled={sandboxHistory.loading}
                    onClick={sandboxHistory.onLoadMore}
                  >
                    {sandboxHistory.loading ? "加载中…" : "加载更多"}
                  </button>
                ) : null}
              </>
            ) : (
              <>
                {intelligentHistory?.loading && combinedHistory.length === 0 ? (
                  <div className="history-empty" role="status">
                    正在加载历史会话…
                  </div>
                ) : null}
                {intelligentHistory?.error ? (
                  <div className="history-error" role="alert">
                    {intelligentHistory.error}
                  </div>
                ) : null}
                {!intelligentHistory?.loading &&
                !intelligentHistory?.error &&
                combinedHistory.length === 0 ? (
                  <div className="history-empty">暂无会话</div>
                ) : null}
                {combinedHistory.map((item) => {
                  const key = `${item.kind}:${item.id}`;
                  const intelligent = item.kind === "intelligent";
                  const active = intelligent
                    ? item.id === intelligentHistory?.currentSessionId
                    : item.id === currentSessionId;
                  const streaming = intelligent
                    ? item.id === intelligentHistory?.busySessionId
                    : streamingSids?.has(item.id) === true;
                  const evaluating = !intelligent && !streaming
                    && evaluatingSids?.has(item.id) === true;
                  const opening = intelligent
                    && item.id === intelligentHistory?.openingSessionId;
                  return (
                    <div
                      key={key}
                      className={`history-item ${active ? "active" : ""}`}
                    >
                      <button
                        className="history-item-btn"
                        onClick={() => item.kind === "intelligent"
                          ? intelligentHistory?.onSelect(item.session)
                          : onPickSession(item.id)}
                        aria-current={active ? "page" : undefined}
                        title={item.title}
                        disabled={opening}
                      >
                        {streaming && (
                          <span
                            className="history-streaming"
                            title={intelligent ? "正在构建…" : "正在生成…"}
                            aria-label={intelligent ? "正在构建" : "正在生成"}
                          />
                        )}
                        <span className="history-title">{item.title}</span>
                        {evaluating && (
                          <span
                            className="history-evaluating-status"
                            title="正在自动评测"
                          >
                            <span
                              className="history-evaluating"
                              aria-hidden="true"
                            />
                            评测中
                          </span>
                        )}
                      </button>
                      <button
                        type="button"
                        className="history-more"
                        aria-label={`管理历史会话：${item.title}`}
                        title="更多"
                        disabled={opening || (intelligent && streaming)}
                        onClick={() =>
                          setMenuFor((current) => current === key ? null : key)
                        }
                      >
                        <MoreHorizontal className="icon" />
                      </button>
                      {menuFor === key && (
                        <>
                          <div
                            className="menu-scrim"
                            onClick={() => setMenuFor(null)}
                          />
                          <div className="history-menu">
                            <button
                              type="button"
                              className="menu-item menu-item--danger"
                              onClick={() => {
                                setMenuFor(null);
                                if (item.kind === "intelligent") {
                                  intelligentHistory?.onDelete(item.session);
                                } else {
                                  onDeleteSession(item.id);
                                }
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
              </>
            )}
          </div>
        </div>
      )}

      <div className="sidebar-footer">
        <AgentKitPromoCard cloudProvider={cloudProvider} />
        <SidebarUser
          access={access}
          userInfo={userInfo}
          onSystemInfo={onSystemInfo}
          onIssueFeedback={onIssueFeedback}
          onLogout={onLogout}
        />
      </div>
    </aside>
  );
}
