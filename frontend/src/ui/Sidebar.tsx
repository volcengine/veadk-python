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
import { AgentFaceIcon } from "./AgentFaceIcon";
import { IssueFeedbackIcon } from "./icons/FeedbackIcons";
import { SkillSpaceIcon } from "./SkillCenter";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import type { SkillWorkbenchTaskListItem } from "./skill-workbench/types";
import defaultSiteLogo from "../assets/logo.svg";
import byteplusLogo from "../assets/byteplus.svg";

const SIDEBAR_AUTO_COLLAPSE_QUERY = "(max-width: 860px)";

export type SidebarPage =
  | "new-chat"
  | "agents"
  | "applications"
  | "search"
  | "feedback"
  | null;

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
  skillConversations?: SkillWorkbenchTaskListItem[];
  skillConversationsLoading?: boolean;
  skillConversationsError?: string;
  activeSkillConversationId?: string;
  onOpenSkillConversation: (jobId: string) => void;
  onDeleteSkillConversation: (jobId: string) => Promise<void>;
  onRetrySkillConversations: () => void;
  onNewChat: () => void;
  onSearch: () => void;
  onQuickCreate: () => void;
  onSkillCenter: () => void;
  onAddAgent: () => void;
  onMyAgents: () => void;
  onApplications: () => void;
  onIssueFeedback: () => void;
  onPickSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  userInfo?: Record<string, unknown>;
  version: string;
  onLogout: () => void;
}

type SidebarConversation =
  | {
      kind: "session";
      id: string;
      updatedAt: number;
      session: AdkSession;
    }
  | {
      kind: "skill";
      id: string;
      updatedAt: number;
      task: SkillWorkbenchTaskListItem;
    };

export function mergeSidebarConversations(
  sessions: AdkSession[],
  skillConversations: SkillWorkbenchTaskListItem[],
): SidebarConversation[] {
  return [
    ...sessions.map((session): SidebarConversation => ({
      kind: "session",
      id: `session:${session.id}`,
      updatedAt: session.lastUpdateTime ?? 0,
      session,
    })),
    ...skillConversations.map((task): SidebarConversation => ({
      kind: "skill",
      id: `skill:${task.jobId}`,
      updatedAt: task.createdAt,
      task,
    })),
  ].sort((a, b) => b.updatedAt - a.updatedAt);
}

function skillConversationStatus(task: SkillWorkbenchTaskListItem): string {
  if (task.state === "provisioning") return "准备 DevEnv";
  if (task.state === "running") {
    if (task.stage === "validating") return "校验中";
    if (task.stage === "packaging") return "打包中";
    return "生成中";
  }
  if (task.state === "ready" || task.state === "published") return "已完成";
  if (task.state === "failed") return "失败";
  if (task.state === "expired") return "DevEnv 已释放";
  return "已结束";
}

function skillConversationTitle(task: SkillWorkbenchTaskListItem): string {
  return task.intent ||
    (task.operation === "create" ? "创建 Skill" : "优化 Skill");
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
  cloudProvider,
  sessions,
  currentSessionId,
  activePage,
  features,
  access,
  streamingSids,
  evaluatingSids,
  skillConversations = [],
  skillConversationsLoading = false,
  skillConversationsError = "",
  activeSkillConversationId = "",
  onOpenSkillConversation,
  onDeleteSkillConversation,
  onRetrySkillConversations,
  onNewChat,
  onSearch,
  onQuickCreate,
  onSkillCenter,
  onAddAgent,
  onMyAgents,
  onApplications,
  onIssueFeedback,
  onPickSession,
  onDeleteSession,
  userInfo,
  version,
  onLogout,
}: SidebarProps) {
  // Agent creation still lives outside the #748-style sidebar.
  void onQuickCreate;
  void onAddAgent;
  // Per-module feature gates; a missing flag defaults to shown.
  const show = (k: keyof NonNullable<typeof features>) => features?.[k] !== false;
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [skillDeleteTarget, setSkillDeleteTarget] =
    useState<SkillWorkbenchTaskListItem | null>(null);
  const [deletingSkillConversation, setDeletingSkillConversation] = useState(false);
  const [skillDeleteError, setSkillDeleteError] = useState("");
  const autoCollapsedRef = useRef(
    typeof window !== "undefined" &&
      window.matchMedia(SIDEBAR_AUTO_COLLAPSE_QUERY).matches,
  );
  const [collapsed, setCollapsed] = useState(autoCollapsedRef.current);
  const conversations = mergeSidebarConversations(sessions, skillConversations);
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
              <PanelLeftOpen className="icon" />
            ) : (
              <PanelLeftClose className="icon" />
            )}
          </button>
        </div>
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
            <Plus className="icon" />
            <span className="sidebar-nav-label">新会话</span>
          </button>
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
          <AgentFaceIcon />
          <span className="sidebar-nav-label">智能体</span>
        </button>
        {show("skillCenter") && (
          <button
            className="new-chat new-chat--skills"
            onClick={onSkillCenter}
            aria-label="技能中心"
            title="技能中心"
          >
            <span className="sidebar-skill-icon">
              <SkillSpaceIcon />
            </span>
            <span className="sidebar-nav-label">技能中心</span>
          </button>
        )}
        {show("search") && (
          <SearchButton active={activePage === "search"} onClick={onSearch} />
        )}
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
          <span className="sidebar-beta-badge">Beta</span>
        </button>
      </div>

      {show("history") && (
      <div className="sidebar-history">
        <div className="history-head">
          <span>会话</span>
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
          {conversations.length === 0 && (
            <div className="history-empty">
              {skillConversationsLoading ? "正在读取会话…" : "暂无会话"}
            </div>
          )}
          {conversations.map((conversation) => {
            const isSkill = conversation.kind === "skill";
            const task = isSkill ? conversation.task : null;
            const title = isSkill
              ? skillConversationTitle(conversation.task)
              : sessionTitle(conversation.session.events);
            const active = isSkill
              ? conversation.task.jobId === activeSkillConversationId
              : conversation.session.id === currentSessionId;
            const live = isSkill
              ? conversation.task.state === "running" || conversation.task.state === "provisioning"
              : streamingSids?.has(conversation.session.id);
            const evaluating = !isSkill
              && !live
              && evaluatingSids?.has(conversation.session.id) === true;
            const status = task ? skillConversationStatus(task) : "";
            return (
              <div
                key={conversation.id}
                className={`history-item ${active ? "active" : ""}`}
              >
                <button
                  className="history-item-btn"
                  onClick={() => {
                    if (conversation.kind === "skill") {
                      onOpenSkillConversation(conversation.task.jobId);
                    } else {
                      onPickSession(conversation.session.id);
                    }
                  }}
                  aria-current={active ? "page" : undefined}
                  title={task ? `${title} · ${task.operation === "create" ? "创建" : "优化"} · ${status}` : title}
                >
                  {live && (
                    <span className="history-streaming" title="正在生成…" aria-label="正在生成" />
                  )}
                  <span className="history-title">
                    {title}
                    {task ? <small>{task.operation === "create" ? "创建" : "优化"} · {status}</small> : null}
                  </span>
                  {evaluating && (
                    <span className="history-evaluating-status" title="正在自动评测">
                      <span className="history-evaluating" aria-hidden="true" />
                      评测中
                    </span>
                  )}
                </button>
              <button
                className="history-more"
                title="更多"
                onClick={() => setMenuFor((value) => value === conversation.id ? null : conversation.id)}
              >
                <MoreHorizontal className="icon" />
              </button>
              {menuFor === conversation.id && (
                <>
                  <div className="menu-scrim" onClick={() => setMenuFor(null)} />
                  <div className="history-menu">
                    <button
                      className="menu-item menu-item--danger"
                      onClick={() => {
                        setMenuFor(null);
                        if (conversation.kind === "skill") {
                          setSkillDeleteError("");
                          setSkillDeleteTarget(conversation.task);
                        } else {
                          onDeleteSession(conversation.session.id);
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
          {skillConversationsError ? (
            <div className="history-load-error" role="alert">
              <span>{skillConversationsError}</span>
              <button type="button" onClick={onRetrySkillConversations}>重试</button>
            </div>
          ) : null}
        </div>
      </div>
      )}

      <div className="sidebar-footer">
        <button
          type="button"
          className={`sidebar-feedback${
            activePage === "feedback" ? " is-active" : ""
          }`}
          onClick={onIssueFeedback}
          aria-label="问题反馈"
          aria-current={activePage === "feedback" ? "page" : undefined}
          title="问题反馈"
        >
          <IssueFeedbackIcon className="icon" />
          <span className="sidebar-nav-label">问题反馈</span>
        </button>
        <SidebarUser
          access={access}
          userInfo={userInfo}
          version={version}
          onLogout={onLogout}
        />
      </div>
      {skillDeleteTarget ? (
        <StudioConfirmDialog
          title="删除 Skill 会话？"
          description={skillDeleteError
            ? `删除失败：${skillDeleteError}`
            : "这会删除对应的临时 DevEnv 和会话记录。"}
          confirmLabel={deletingSkillConversation ? "正在删除…" : "删除会话"}
          variant="danger"
          busy={deletingSkillConversation}
          onCancel={() => setSkillDeleteTarget(null)}
          onConfirm={() => {
            setDeletingSkillConversation(true);
            setSkillDeleteError("");
            void onDeleteSkillConversation(skillDeleteTarget.jobId)
              .then(() => setSkillDeleteTarget(null))
              .catch((cause) => {
                setSkillDeleteError(cause instanceof Error ? cause.message : String(cause));
              })
              .finally(() => setDeletingSkillConversation(false));
          }}
        />
      ) : null}
    </aside>
  );
}
