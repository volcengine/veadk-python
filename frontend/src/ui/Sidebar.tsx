import {
  type CSSProperties,
  type SVGProps,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  Box,
  Info,
  LogOut,
  MoreHorizontal,
  Plus,
  Trash2,
} from "lucide-react";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { BookWrench } from "@openai/apps-sdk-ui/components/Icon";
import { Clock } from "@openai/apps-sdk-ui/components/Icon";
import { MarkerCode } from "@openai/apps-sdk-ui/components/Icon";
import { LoadingIndicator } from "@openai/apps-sdk-ui/components/Indicator";
import { Tooltip } from "@openai/apps-sdk-ui/components/Tooltip";
import type {
  AdkSession,
  SiteBranding,
  StudioAccess,
  UiFeatures,
} from "../adk/client";
import type { SandboxThreadSummary } from "../adk/sandbox";
import { sessionTitle } from "../blocks";
import { displayName, profilePictureUrl } from "../adk/identity";
import { SearchButton } from "./Search";
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

function ScrollableHistoryTitle({ title }: { title: string }) {
  const viewportRef = useRef<HTMLSpanElement>(null);
  const contentRef = useRef<HTMLSpanElement>(null);
  const [overflowDistance, setOverflowDistance] = useState(0);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const content = contentRef.current;
    if (!viewport || !content) return undefined;
    const updateOverflowDistance = () => {
      const next = Math.max(0, Math.ceil(content.scrollWidth - viewport.clientWidth));
      setOverflowDistance((current) => (current === next ? current : next));
    };
    updateOverflowDistance();
    const observer = new ResizeObserver(updateOverflowDistance);
    observer.observe(viewport);
    observer.observe(content);
    return () => observer.disconnect();
  }, [title]);

  const scrollDuration = Math.min(12, Math.max(4.8, 3.6 + overflowDistance / 36));
  const titleStyle = {
    "--history-title-translate": `-${overflowDistance}px`,
    "--history-title-duration": `${scrollDuration.toFixed(2)}s`,
  } as CSSProperties;

  return (
    <span
      ref={viewportRef}
      className={`history-title${overflowDistance > 0 ? " is-overflowing" : ""}`}
      style={titleStyle}
    >
      <span ref={contentRef} className="history-title-text">{title}</span>
    </span>
  );
}

export type SidebarPage =
  | "new-chat"
  | "agents"
  | "workspaces"
  | "environments"
  | "library"
  | "applications"
  | "cronjobs"
  | "search"
  | "developer-resources"
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
  /** Session ids that are currently streaming a reply. */
  streamingSids?: Set<string>;
  /** Session ids whose latest reply is currently being evaluated. */
  evaluatingSids?: Set<string>;
  sandboxHistory?: SidebarSandboxHistory;
  onNewChat: () => void;
  onSearch: () => void;
  onQuickCreate: () => void;
  onLibrary: () => void;
  onAddAgent: () => void;
  onMyAgents: () => void;
  onWorkspace: () => void;
  onApplications: () => void;
  onCronJobs: () => void;
  onAgentKitCli: () => void;
  onDeveloperResources: () => void;
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

/** Account block pinned at the bottom of the sidebar: avatar + name, with a
 *  popover (opening upward) holding the full identity and account actions. */
function SidebarUser({
  activePage,
  access,
  userInfo,
  onAgentKitCli,
  onDeveloperResources,
  onSystemInfo,
  onIssueFeedback,
  onLogout,
}: Pick<
  SidebarProps,
  | "activePage"
  | "access"
  | "userInfo"
  | "onAgentKitCli"
  | "onDeveloperResources"
  | "onSystemInfo"
  | "onIssueFeedback"
  | "onLogout"
>) {
  const [open, setOpen] = useState(false);
  const [failedAvatarUrl, setFailedAvatarUrl] = useState("");
  if (!userInfo) return null;
  const name = displayName(userInfo) || "用户";
  const email = typeof userInfo.email === "string" ? userInfo.email.trim() : "";
  const avatarStyle = smokeAvatarStyle(name);
  const pictureUrl = profilePictureUrl(userInfo);
  const visiblePictureUrl = pictureUrl === failedAvatarUrl ? "" : pictureUrl;
  return (
    <div className="sidebar-user">
      <div className="sidebar-user-row">
        <button
          type="button"
          className="sidebar-user-btn"
          onClick={() => setOpen((o) => !o)}
          title={name}
        >
          <span
            className={`account-avatar${visiblePictureUrl ? " has-image" : ""}`}
            style={avatarStyle}
            aria-hidden="true"
          >
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
            <span className="sidebar-user-name">{name}</span>
          </span>
        </button>
        <div className="sidebar-user-shortcuts" aria-label="快捷入口">
          <Tooltip compact content="体验 AgentKit CLI">
            <button
              type="button"
              className="sidebar-user-shortcut"
              onClick={onAgentKitCli}
              aria-label="体验 AgentKit CLI"
            >
              <MarkerCode className="icon" />
            </button>
          </Tooltip>
          <Tooltip compact content="开发者资源">
            <button
              type="button"
              className={`sidebar-user-shortcut${
                activePage === "developer-resources" ? " is-active" : ""
              }`}
              onClick={onDeveloperResources}
              aria-label="开发者资源"
              aria-current={activePage === "developer-resources" ? "page" : undefined}
            >
              <BookWrench className="icon" />
            </button>
          </Tooltip>
        </div>
      </div>
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
                aria-hidden="true"
              >
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
                  <Badge color="secondary" size="sm" variant="soft" pill>
                    {STUDIO_ROLE_LABELS[access.role]}
                  </Badge>
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
  onNewChat,
  onSearch,
  onQuickCreate,
  onLibrary,
  onAddAgent,
  onMyAgents,
  onWorkspace,
  onApplications,
  onCronJobs,
  onAgentKitCli,
  onDeveloperResources,
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
  const combinedHistory = sessions.map((session) => ({
    id: session.id,
    title: sessionTitle(session.events),
    createdAt: (session.lastUpdateTime ?? 0) * 1_000,
  })).sort((left, right) => right.createdAt - left.createdAt);
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
            className={`new-chat new-chat--workspaces${
              activePage === "workspaces" ? " is-active" : ""
            }`}
            onClick={onWorkspace}
            aria-label="工作区"
            aria-current={activePage === "workspaces" ? "page" : undefined}
            title="工作区"
          >
            <Box className="icon" />
            <span className="sidebar-nav-label">工作区</span>
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
                        <ScrollableHistoryTitle title={title} />
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
                {combinedHistory.length === 0 ? (
                  <div className="history-empty">暂无会话</div>
                ) : null}
                {combinedHistory.map((item) => {
                  const active = item.id === currentSessionId;
                  const streaming = streamingSids?.has(item.id) === true;
                  const evaluating = !streaming
                    && evaluatingSids?.has(item.id) === true;
                  return (
                    <div
                      key={item.id}
                      className={`history-item ${active ? "active" : ""}`}
                    >
                      <button
                        className="history-item-btn"
                        onClick={() => onPickSession(item.id)}
                        aria-current={active ? "page" : undefined}
                        title={item.title}
                      >
                        <ScrollableHistoryTitle title={item.title} />
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
                      <div className="history-action-slot">
                        {streaming ? (
                          <LoadingIndicator
                            className="history-streaming-indicator"
                            size={12}
                            role="status"
                            aria-label="正在生成"
                          />
                        ) : null}
                        <button
                          type="button"
                          className="history-more"
                          aria-label={`管理历史会话：${item.title}`}
                          title="更多"
                          onClick={() =>
                            setMenuFor((current) =>
                              current === item.id ? null : item.id
                            )
                          }
                        >
                          <MoreHorizontal className="icon" />
                        </button>
                      </div>
                      {menuFor === item.id && (
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
                                onDeleteSession(item.id);
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
        <SidebarUser
          activePage={activePage}
          access={access}
          userInfo={userInfo}
          onAgentKitCli={onAgentKitCli}
          onDeveloperResources={onDeveloperResources}
          onSystemInfo={onSystemInfo}
          onIssueFeedback={onIssueFeedback}
          onLogout={onLogout}
        />
      </div>
    </aside>
  );
}
