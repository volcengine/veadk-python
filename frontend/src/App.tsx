import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type WheelEvent,
} from "react";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  CircleX,
  Copy,
  CornerDownRight,
  ListTodo,
  Loader2,
} from "lucide-react";
import { motion } from "motion/react";
import {
  cancelAgentkitDeployment,
  addSessionCapability,
  clearMessageFeedbackCache,
  createSession,
  DEFAULT_STUDIO_ACCESS,
  DEFAULT_SITE_BRANDING,
  deleteRuntime,
  deleteMedia,
  deleteSessionMedia,
  deleteSession,
  getAgentInfo,
  getSessionCapabilities,
  getSession,
  getStudioAccess,
  getRuntimes,
  listApps,
  listSessionBuiltinTools,
  listSessions,
  removeSessionCapability,
  runSSE,
  submitMessageFeedback,
  uploadMedia,
  getUiConfig,
  type AdkEvent,
  type AgentInfo,
  type AgentNode,
  type AgentTarget,
  type AgentFeedbackCase,
  type AdkSession,
  type AddSessionCapability,
  type Attachment,
  type FrontendInvocation,
  type CloudRuntime,
  type MessageFeedbackRating,
  type SiteBranding,
  type SessionCapabilities,
  type StudioAccess,
  type UiFeatures,
} from "./adk/client";
import {
  applyEvent,
  emptyAcc,
  eventsToTurns,
  type Block,
  type Turn,
} from "./blocks";
import { Sidebar } from "./ui/Sidebar";
import { Navbar } from "./ui/Navbar";
import { AgentInfoDrawer, AgentInfoPanel } from "./ui/AgentTopology";
import { AgentIdentityIcon } from "./ui/AgentIdentityIcon";
import { SkillCenterView } from "./ui/SkillCenter";
import { AddAgentKitView } from "./ui/AddAgentKit";
import {
  AgentWorkspace,
  type WorkspaceAgentDraft,
} from "./ui/AgentWorkspace";
import { MyAgents, type MyAgentCardData } from "./ui/MyAgents";
import { SearchView } from "./ui/Search";
import {
  buildAgentEntries,
  connectRuntime,
  loadConnections,
  registerConnections,
  removeRuntimeConnection,
  remoteAppId,
  type AgentEntry,
  type RemoteConnection,
} from "./adk/connections";
import { Blocks, ThinkingPlaceholder } from "./ui/Blocks";
import { Composer } from "./ui/Composer";
import { InvocationChips } from "./ui/InvocationChips";
import { MediaGroup } from "./ui/Media";
import { QuickCreate, type QuickCreateKind } from "./ui/QuickCreate";
import { StackCards } from "./ui/AddAgentMenu";
import { IntelligentCreate } from "./create/IntelligentCreate";
import { CustomCreate } from "./create/CustomCreate";
import { TemplateCreate } from "./create/TemplateCreate";
import { WorkflowCreate } from "./create/WorkflowCreate";
import { CodePackageCreate } from "./create/CodePackageCreate";
import { FileArchive } from "lucide-react";
import type { AgentDraft } from "./create/types";
import type { DeployResult, DeploymentTaskUpdate } from "./ui/ProjectPreview";
import { DeploymentErrorMessage } from "./ui/DeploymentErrorMessage";
import { TextShimmer } from "./ui/text-shimmer/TextShimmer";
import { StudioUpdateControl } from "./ui/StudioUpdateControl";
import { createSkillJob, deleteSkillJob } from "./ui/skill-create/api";
import { SkillCreateWorkspace } from "./ui/skill-create/SkillCreateWorkspace";
import { SKILL_MODELS, type SkillCreationJob } from "./ui/skill-create/types";
import type { NewChatMode } from "./ui/new-chat-modes/types";
import {
  sandboxClient,
  type SandboxSession as SandboxSessionInfo,
} from "./adk/sandbox";
import {
  getSandboxCapability,
  getSkillCreatorCapability,
} from "./adk/newChatCapabilities";
import {
  SandboxLaunchDialog,
  type SandboxLaunchState,
} from "./ui/SandboxLaunchDialog";
import {
  SandboxSessionWarning,
} from "./ui/SandboxSession";
import defaultSiteLogo from "./assets/volcengine.svg";
import {
  FeedbackDownIcon,
  FeedbackUpIcon,
} from "./ui/icons/FeedbackIcons";

// Breadcrumb root label for the create flow and the per-mode leaf labels.
const CREATE_ROOT = "创建 Agent";
type CreateMode = QuickCreateKind | "package";

const MODE_LABEL: Record<CreateMode, string> = {
  intelligent: "智能模式",
  custom: "自定义",
  template: "从模板新建",
  workflow: "工作流",
  package: "代码包部署",
};

type CreateView = "menu" | CreateMode | null;

// Persist the last view so a page refresh restores where the user was.
const LS = { app: "veadk.appName", view: "veadk.view", session: "veadk.sessionId" } as const;
const EMPTY_STRING_SET: Set<string> = new Set<string>();
const EMPTY_STRING_ARR: string[] = [];

function emptyInvocation(): FrontendInvocation {
  return { skills: [] };
}

function workspaceDraftsKey(userId: string): string {
  return `veadk.agentDrafts.${encodeURIComponent(userId)}`;
}

function activeWorkspaceDraftKey(userId: string): string {
  return `${workspaceDraftsKey(userId)}.active`;
}

function workspaceAgentOrderKey(userId: string): string {
  return `veadk.agentOrder.${encodeURIComponent(userId)}`;
}

function loadWorkspaceDrafts(userId: string): WorkspaceAgentDraft[] {
  if (!userId) return [];
  try {
    const value = JSON.parse(localStorage.getItem(workspaceDraftsKey(userId)) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function loadWorkspaceAgentOrder(userId: string): string[] {
  if (!userId) return [];
  try {
    const value = JSON.parse(localStorage.getItem(workspaceAgentOrderKey(userId)) || "[]");
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function findAgentNode(node: AgentNode, name: string): AgentNode | undefined {
  if (node.name === name || node.id === name) return node;
  for (const child of node.children) {
    const found = findAgentNode(child, name);
    if (found) return found;
  }
  return undefined;
}

function mentionableDescendants(node: AgentNode): AgentTarget[] {
  const targets: AgentTarget[] = [];
  for (const child of node.children) {
    if (!child.mentionable) continue;
    targets.push({
      name: child.name,
      description: child.description,
      type: child.type,
      path: child.path,
    });
    targets.push(...mentionableDescendants(child));
  }
  return targets;
}

function loadView(): CreateView {
  const v = typeof localStorage !== "undefined" ? localStorage.getItem(LS.view) : null;
  return v === "menu" || v === "intelligent" || v === "custom" || v === "template" || v === "workflow"
    ? v
    : null;
}
import { TraceDrawer } from "./ui/TraceDrawer";
import { LoginPage } from "./ui/LoginPage";
import { AuthExpiredDialog } from "./ui/AuthExpiredDialog";
import { Markdown } from "./ui/Markdown";
import {
  clearLocalUser,
  logout,
  openLoginWindow,
  resolveIdentity,
  setLocalUser,
  type AuthStatus,
} from "./adk/identity";
import {
  AUTHENTICATION_REQUIRED_EVENT,
  authenticationRestored,
  isAuthenticationPending,
} from "./adk/authSession";
import type { A2uiAction, A2uiComponent } from "./a2ui/types";
import { buildSurfaces } from "./a2ui/Surface";

/** Hand-drawn "from zero" mark: a "0" ring with a creativity spark inside. */
function ScratchIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <ellipse cx="12" cy="12" rx="6.6" ry="8.2" />
      <path d="M12 8.2l1.05 2.75 2.75 1.05-2.75 1.05L12 15.8l-1.05-2.75L8.2 12l2.75-1.05z" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Hand-drawn "tracing / observability" icon (stacked spans). */
function TraceIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <rect x="3" y="4" width="14" height="3.2" rx="1.2" fill="currentColor" stroke="none" />
      <rect x="6" y="10.4" width="13" height="3.2" rx="1.2" fill="currentColor" stroke="none" opacity="0.7" />
      <rect x="9" y="16.8" width="9" height="3.2" rx="1.2" fill="currentColor" stroke="none" opacity="0.45" />
    </svg>
  );
}

/** Format an epoch-seconds timestamp as Beijing (Asia/Shanghai) time. */
function fmtTime(ts?: number): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function fmtMeta(meta?: { tokens?: number; ts?: number }): string {
  if (!meta) return "";
  const parts: string[] = [];
  if (meta.ts) parts.push(fmtTime(meta.ts));
  if (meta.tokens != null) parts.push(`${meta.tokens.toLocaleString()} tokens`);
  return parts.join(" · ");
}

/** Plain-text content of a turn (answer text only), for copying. */
function turnText(turn: Turn): string {
  return turn.blocks
    .map((b) => (b.kind === "text" ? b.text : ""))
    .join("")
    .trim();
}

const A2UI_TOOL_NAME = "send_a2ui_json_to_client";

/** Whether a finalized assistant turn has anything visible to render — non-empty
 *  text, media, a renderable A2UI surface, or a non-A2UI tool. Thinking, the hidden
 *  (done) A2UI tool, and empty A2UI surfaces don't count, so a reply that was
 *  ONLY thinking + an empty surface returns false (→ we show a fallback). */
function turnHasVisibleContent(turn: Turn): boolean {
  return turn.blocks.some((b) => {
    if (b.kind === "text") return b.text.trim().length > 0;
    if (b.kind === "attachment") return b.files.length > 0;
    if (b.kind === "tool") return !(b.name === A2UI_TOOL_NAME && b.done);
    if (b.kind === "agent-transfer") return false;
    if (b.kind === "a2ui") return buildSurfaces(b.messages).some((s) => s.components[s.rootId]);
    if (b.kind === "auth") return true; // the OAuth card counts as content
    return false; // thinking is not an answer
  });
}

/** True while a turn is paused on an unresolved OAuth card — like streaming, we
 *  hide the actions/timestamp row until authorization completes. */
function turnAwaitingAuth(turn: Turn): boolean {
  return turn.blocks.some((b) => b.kind === "auth" && !b.done);
}

/** Open the OAuth authorize URL in a popup and resolve with the full callback
 *  URL. Auto-captures when the provider redirects back to our origin (poll +
 *  postMessage); if the popup closes without capture (cross-origin redirect),
 *  falls back to asking the user to paste the callback URL. */
function runOAuthPopup(authUri: string): Promise<string> {
  return new Promise((resolve, reject) => {
    let protocol = "";
    try {
      protocol = new URL(authUri, window.location.href).protocol;
    } catch {
      // Invalid URLs are rejected with unsupported schemes below.
    }
    if (protocol !== "http:" && protocol !== "https:") {
      reject(new Error("授权链接不是 http/https 地址，已阻止打开。"));
      return;
    }
    const popup = window.open(authUri, "veadk_oauth", "width=520,height=720");
    if (!popup) {
      reject(new Error("弹窗被拦截，请允许弹窗后重试。"));
      return;
    }
    let done = false;
    const cleanup = () => {
      clearInterval(timer);
      window.removeEventListener("message", onMsg);
    };
    const finish = (url: string) => {
      if (done) return;
      done = true;
      cleanup();
      try {
        popup.close();
      } catch {
        /* ignore */
      }
      resolve(url);
    };
    const onMsg = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
      const d = e.data as { veadkOAuth?: boolean; url?: string } | null;
      if (d && d.veadkOAuth && typeof d.url === "string") finish(d.url);
    };
    window.addEventListener("message", onMsg);
    const timer = setInterval(() => {
      if (done) return;
      if (popup.closed) {
        cleanup();
        const pasted = window.prompt(
          "授权完成后，请粘贴回调页面（浏览器地址栏）的完整 URL：",
        );
        if (pasted && pasted.trim()) {
          done = true;
          resolve(pasted.trim());
        } else {
          reject(new Error("授权已取消。"));
        }
        return;
      }
      try {
        const href = popup.location.href; // throws while cross-origin
        if (
          href &&
          href !== "about:blank" &&
          new URL(href).origin === window.location.origin &&
          /[?&](code|state|error)=/.test(href)
        ) {
          finish(href);
        }
      } catch {
        /* still on the provider's origin — keep polling */
      }
    }, 500);
  });
}

/** Clone an ADK AuthConfig and set the OAuth2 callback URL, so ADK can exchange
 *  the code for a token when we send it back as the credential response. */
function withAuthResponseUri(authConfig: unknown, callbackUrl: string): unknown {
  const cfg = JSON.parse(JSON.stringify(authConfig ?? {})) as Record<string, any>;
  const cred = cfg.exchangedAuthCredential ?? cfg.exchanged_auth_credential ?? {};
  const o = cred.oauth2 ?? {};
  o.authResponseUri = callbackUrl;
  o.auth_response_uri = callbackUrl;
  cred.oauth2 = o;
  cfg.exchangedAuthCredential = cred;
  return cfg;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="icon-btn"
      title={copied ? "已复制" : "复制"}
      disabled={!text}
      onClick={async () => {
        if (!text) return;
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard unavailable */
        }
      }}
    >
      {copied ? <Check className="icon" /> : <Copy className="icon" />}
    </button>
  );
}

function deployRegionLabel(region: string): string {
  if (region === "cn-beijing") return "华北 2（北京）";
  if (region === "cn-shanghai") return "华东 2（上海）";
  return region || "未指定";
}

function DeploymentTaskStatus({
  tasks,
  onCancel,
}: {
  tasks: DeploymentTaskUpdate[];
  onCancel: (task: DeploymentTaskUpdate) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const runningCount = tasks.filter((task) => task.status === "running").length;
  const latest = tasks[0];
  const summaryStatus = runningCount > 0 ? "running" : latest?.status ?? "idle";
  const summary =
    runningCount > 0
      ? `${runningCount} 个部署任务进行中`
      : latest?.status === "success"
        ? "最近部署已完成"
        : latest?.status === "error"
          ? "最近部署失败"
          : latest?.status === "cancelled"
            ? "最近部署已取消"
            : "部署任务";

  const cancelTask = (task: DeploymentTaskUpdate) => {
    setCancellingId(task.id);
    void onCancel(task).finally(() => setCancellingId(null));
  };

  return (
    <div className="global-deploy-center">
      <button
        type="button"
        className={`global-deploy-task is-${summaryStatus}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((current) => !current)}
      >
        {summaryStatus === "running" ? (
          <Loader2 className="global-deploy-task-icon spin" />
        ) : summaryStatus === "success" ? (
          <CircleCheck className="global-deploy-task-icon" />
        ) : summaryStatus === "error" ? (
          <CircleAlert className="global-deploy-task-icon" />
        ) : summaryStatus === "cancelled" ? (
          <CircleX className="global-deploy-task-icon" />
        ) : (
          <ListTodo className="global-deploy-task-icon" />
        )}
        <span className="global-deploy-task-detail">{summary}</span>
        <ChevronDown
          className={`global-deploy-task-chevron${open ? " is-open" : ""}`}
        />
      </button>

      {open && (
        <>
          <button
            type="button"
            className="global-deploy-task-scrim"
            aria-label="关闭部署任务"
            onClick={() => setOpen(false)}
          />
          <section
            className="global-deploy-popover"
            role="dialog"
            aria-label="部署任务"
          >
            <header className="global-deploy-popover-head">
              <span>部署任务</span>
              <span>{tasks.length}</span>
            </header>
            <div className="global-deploy-list">
              {tasks.length === 0 ? (
                <div className="global-deploy-empty">暂无部署任务</div>
              ) : tasks.map((task) => {
                const detail = `${task.label}${
                  task.status === "running" && typeof task.pct === "number"
                    ? ` ${Math.round(task.pct)}%`
                    : ""
                }`;
                return (
                  <article
                    key={task.id}
                    className={`global-deploy-item is-${task.status}`}
                  >
                    <div className="global-deploy-item-head">
                      <span className="global-deploy-runtime-name">
                        {task.runtimeName}
                      </span>
                      <span className="global-deploy-status">{detail}</span>
                    </div>
                    <dl className="global-deploy-meta">
                      <div>
                        <dt>Runtime 名称</dt>
                        <dd>{task.runtimeName}</dd>
                      </div>
                      <div>
                        <dt>部署地域</dt>
                        <dd>{deployRegionLabel(task.region)}</dd>
                      </div>
                      {task.runtimeId && (
                        <div>
                          <dt>Runtime ID</dt>
                          <dd>{task.runtimeId}</dd>
                        </div>
                      )}
                    </dl>
                    {task.message && task.status === "error" ? (
                      <DeploymentErrorMessage
                        className="global-deploy-error"
                        message={task.message}
                        onRetry={task.retry}
                      />
                    ) : task.message ? (
                      <p className="global-deploy-message">{task.message}</p>
                    ) : null}
                    {task.status === "running" && (
                      <>
                        <div className="global-deploy-progress" aria-hidden>
                          <span
                            style={{
                              width: `${Math.max(6, Math.min(100, task.pct ?? 6))}%`,
                            }}
                          />
                        </div>
                        <div className="global-deploy-item-actions">
                          <button
                            type="button"
                            disabled={cancellingId === task.id}
                            onClick={() => cancelTask(task)}
                          >
                            {cancellingId === task.id ? "取消中…" : "取消部署"}
                          </button>
                        </div>
                      </>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
// Side-effect import: registers all A2UI components under a2ui/components/*.
import "./a2ui/components";


const GREETINGS = [
  "今天想做点什么？",
  "有什么可以帮你的？",
  "需要我帮你查点什么吗？",
  "有问题尽管问我",
  "嗨，我们开始吧",
  "开始一段新对话吧",
  "今天想先解决哪件事？",
  "把你的想法告诉我吧",
  "我们从哪里开始？",
  "有什么任务交给我？",
  "准备好一起推进了吗？",
  "说说你现在最关心的问题",
  "今天也一起把事情做好",
  "我在，随时可以开始",
];
const pickGreeting = () => GREETINGS[Math.floor(Math.random() * GREETINGS.length)];

function releaseAttachmentPreviews(items: Attachment[]) {
  for (const item of items) {
    if (item.previewUrl?.startsWith("blob:")) URL.revokeObjectURL(item.previewUrl);
  }
}

function attachmentDraftId() {
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function browserMimeType(file: File) {
  if (file.type) return file.type;
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension === "md" || extension === "markdown") return "text/markdown";
  if (extension === "txt") return "text/plain";
  return "application/octet-stream";
}

export default function App() {
  const [apps, setApps] = useState<string[]>([]);
  const [appName, setAppName] = useState("");
  const [sessions, setSessions] = useState<AdkSession[]>([]);
  const [sessionId, setSessionId] = useState("");
  const creatingSessionRef = useRef<Promise<string> | null>(null);
  const [initializingSession, setInitializingSession] = useState(false);
  const [pendingTurns, setPendingTurns] = useState<Turn[]>([]);
  const [sandboxSession, setSandboxSession] =
    useState<SandboxSessionInfo | null>(null);
  const [sandboxTurns, setSandboxTurns] = useState<Turn[]>([]);
  const [sandboxBusy, setSandboxBusy] = useState(false);
  const [sandboxLaunchOpen, setSandboxLaunchOpen] = useState(false);
  const [sandboxLaunchState, setSandboxLaunchState] =
    useState<SandboxLaunchState>("confirm");
  const [sandboxLaunchError, setSandboxLaunchError] = useState("");
  const sandboxLaunchAbortRef = useRef<AbortController | null>(null);
  const sandboxMessageAbortRef = useRef<AbortController | null>(null);
  // Turns are stored PER SESSION, so a background stream can keep updating its
  // own session's transcript while you view another one — no cross-session
  // leak, no data loss, and no re-fetch when you switch back (its entry is
  // already live). The view shows the active session's entry.
  const [turnsBySession, setTurnsBySession] = useState<Record<string, Turn[]>>(
    {},
  );
  const persistentTurns = sessionId
    ? turnsBySession[sessionId] ?? []
    : pendingTurns;
  const turns = sandboxSession ? sandboxTurns : persistentTurns;
  const setTurnsFor = (
    sid: string,
    updater: Turn[] | ((prev: Turn[]) => Turn[]),
  ) =>
    setTurnsBySession((m) => ({
      ...m,
      [sid]: typeof updater === "function" ? updater(m[sid] ?? []) : updater,
    }));
  const [input, setInput] = useState("");
  const [newChatMode, setNewChatMode] = useState<NewChatMode>("agent");
  const [newChatCapabilities, setNewChatCapabilities] = useState<{
    temporaryEnabled?: boolean;
    skillCreateEnabled?: boolean;
  }>({});
  const [skillJob, setSkillJob] = useState<SkillCreationJob | null>(null);
  const [skillCreating, setSkillCreating] = useState(false);
  const skillCreationRunRef = useRef(0);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [invocation, setInvocation] = useState<FrontendInvocation>(emptyInvocation);
  const [agentInfo, setAgentInfo] = useState<AgentInfo | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);
  const [sessionCapabilities, setSessionCapabilities] =
    useState<SessionCapabilities | null>(null);
  const [sessionCapabilitiesLoading, setSessionCapabilitiesLoading] =
    useState(false);
  const [sessionBuiltinTools, setSessionBuiltinTools] = useState<string[]>([]);
  const [sessionCapabilityMutating, setSessionCapabilityMutating] =
    useState(false);
  const removedAttachmentIdsRef = useRef<Set<string>>(new Set());
  // Streaming state is PER SESSION so multiple sessions can stream at once
  // (each /run_sse is an independent request). `streamingSids` = which sessions
  // are currently streaming; the AbortControllers let unmount / delete cancel
  // a specific session's stream. A normal switch does NOT abort — the stream
  // keeps running and persisting.
  const [streamingSids, setStreamingSids] = useState<Set<string>>(
    () => new Set(),
  );
  const [streamPresentationSids, setStreamPresentationSids] = useState<Set<string>>(
    () => new Set(),
  );
  const streamAbortsRef = useRef<Map<string, AbortController>>(new Map());
  const streamPresentationTimersRef = useRef<Map<string, number>>(new Map());
  const setStreaming = (sid: string, on: boolean) =>
    setStreamingSids((s) => {
      const n = new Set(s);
      if (on) n.add(sid);
      else n.delete(sid);
      return n;
    });
  const startStreamPresentation = (sid: string) => {
    const timer = streamPresentationTimersRef.current.get(sid);
    if (timer !== undefined) window.clearTimeout(timer);
    streamPresentationTimersRef.current.delete(sid);
    setStreamPresentationSids((current) => new Set(current).add(sid));
  };
  const finishStreamPresentation = (sid: string) => {
    const previousTimer = streamPresentationTimersRef.current.get(sid);
    if (previousTimer !== undefined) window.clearTimeout(previousTimer);
    const timer = window.setTimeout(() => {
      streamPresentationTimersRef.current.delete(sid);
      setStreamPresentationSids((current) => {
        const next = new Set(current);
        next.delete(sid);
        return next;
      });
    }, 2400);
    streamPresentationTimersRef.current.set(sid, timer);
  };
  // The session currently on screen — used to gate the single global error
  // banner (per-session transcripts/topology don't need it).
  const viewSidRef = useRef("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const toastTimerRef = useRef<number | null>(null);
  useEffect(() => () => {
    if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
  }, []);
  const [feedbackPendingIds, setFeedbackPendingIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [traceOpen, setTraceOpen] = useState(false);
  const [agentInfoOpen, setAgentInfoOpen] = useState(false);
  const agentInfoTriggerRef = useRef<HTMLButtonElement>(null);
  const closeAgentInfo = useCallback(() => setAgentInfoOpen(false), []);
  const [greeting, setGreeting] = useState(pickGreeting);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [authExpired, setAuthExpired] = useState(false);
  const [authRecoveryChecking, setAuthRecoveryChecking] = useState(false);
  const [authRecoveryError, setAuthRecoveryError] = useState("");
  const authRecoveryActiveRef = useRef(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [userId, setUserId] = useState("");
  const [userInfo, setUserInfo] = useState<Record<string, unknown> | undefined>();
  // Null while the server-derived role is unresolved. Privileged UI remains
  // hidden until this has loaded; failures fall back to the ordinary user.
  const [access, setAccess] = useState<StudioAccess | null>(null);
  // Per-module feature gates (studio mode disables chat-centric modules).
  // Defaults to all-enabled until /web/ui-config resolves.
  const [features, setFeatures] = useState<UiFeatures>({
    newChat: true,
    search: true,
    skillCenter: true,
    history: true,
    addAgent: true,
    manageAgents: true,
    addAgentkit: true,
  });
  const [agentsSource, setAgentsSource] = useState<"local" | "cloud">("cloud");
  const [siteBranding, setSiteBranding] = useState<SiteBranding>(DEFAULT_SITE_BRANDING);
  const [version, setVersion] = useState("");
  const [defaultView, setDefaultView] = useState<"chat" | "addAgent">("chat");
  const [uiConfigLoaded, setUiConfigLoaded] = useState(false);
  const [localMode, setLocalMode] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  // The executing sub-agent (ADK event.author) and everyone who emitted this
  // turn — PER SESSION, so each session's topology highlights its own stream.
  const [activeAgentBySession, setActiveAgentBySession] = useState<
    Record<string, string>
  >({});
  const [seenAgentsBySession, setSeenAgentsBySession] = useState<
    Record<string, Set<string>>
  >({});
  // The current delegation chain (root → … → executing agent) per session,
  // built from event.actions.transfer_to_agent / end_of_agent.
  const [execPathBySession, setExecPathBySession] = useState<
    Record<string, string[]>
  >({});

  // Everything the view needs for the ACTIVE session, derived from the
  // per-session maps above.
  const busy = streamingSids.has(sessionId);
  const presentingStream = streamPresentationSids.has(sessionId);
  const conversationBusy = busy || initializingSession;
  const sessionConfigurationBusy = !!sessionId && sessionCapabilitiesLoading;
  const activeConversationBusy = sandboxSession
    ? sandboxBusy
    : conversationBusy;
  const activeConversationPresenting =
    activeConversationBusy || (!sandboxSession && presentingStream);
  const activeAgent = activeAgentBySession[sessionId] ?? "";
  const seenAgents = seenAgentsBySession[sessionId] ?? EMPTY_STRING_SET;
  const execPath = execPathBySession[sessionId] ?? EMPTY_STRING_ARR;
  const rootCapabilityNode = agentInfo?.graph;
  const rootAgentNames = [
    agentInfo?.name,
    rootCapabilityNode?.name,
    rootCapabilityNode?.id,
  ].filter((name): name is string => Boolean(name));
  const skillCapabilityNode = invocation.targetAgent && rootCapabilityNode
    ? findAgentNode(rootCapabilityNode, invocation.targetAgent.name)
    : rootCapabilityNode;
  const availableSkills = skillCapabilityNode?.skills ??
    (invocation.targetAgent ? [] : agentInfo?.skills ?? []);
  const availableAgents = rootCapabilityNode
    ? mentionableDescendants(rootCapabilityNode)
    : [];

  function discardDraftAttachments(items: Attachment[]) {
    releaseAttachmentPreviews(items);
    for (const item of items) {
      if (item.status === "uploading") {
        removedAttachmentIdsRef.current.add(item.id);
      } else if (item.uri) {
        void deleteMedia(appName, item.uri).catch((e) => setError(String(e)));
      }
    }
  }

  function discardSkillCreation() {
    skillCreationRunRef.current += 1;
    const job = skillJob;
    setSkillJob(null);
    setSkillCreating(false);
    if (job && !job.id.startsWith("pending-")) {
      void deleteSkillJob(job.id).catch((cause) => {
        setError(cause instanceof Error ? cause.message : String(cause));
      });
    }
  }

  async function abandonDraftSession(sid: string) {
    try {
      await deleteSessionMedia(appName, userId, sid);
      await deleteSession(appName, userId, sid);
      setSessions((current) => current.filter((session) => session.id !== sid));
      setTurnsBySession((current) => {
        const { [sid]: _drop, ...rest } = current;
        return rest;
      });
    } catch (e) {
      setError(String(e));
    }
  }

  function removeDraftAttachment(id: string) {
    const removed = attachments.find((item) => item.id === id);
    if (!removed) return;
    const remaining = attachments.filter((item) => item.id !== id);
    releaseAttachmentPreviews([removed]);
    if (removed.status === "uploading") {
      removedAttachmentIdsRef.current.add(id);
    }
    setAttachments(remaining);

    const shouldAbandonSession =
      remaining.length === 0 && !input.trim() && !!sessionId && turns.length === 0;
    if (shouldAbandonSession) {
      viewSidRef.current = "";
      setSessionId("");
      void abandonDraftSession(sessionId);
    } else if (removed.uri) {
      void deleteMedia(appName, removed.uri).catch((e) => setError(String(e)));
    }
  }

  // Apply a stream event's control-flow signals to a session's live state:
  // author = who's executing now; transfer_to_agent pushes the delegation
  // chain; end_of_agent / escalate pops it. `author` always wins for highlight.
  const applyStreamSignals = (sid: string, ev: AdkEvent) => {
    const who = ev.author && ev.author !== "user" ? ev.author : undefined;
    if (who) {
      setActiveAgentBySession((m) => ({ ...m, [sid]: who }));
      setSeenAgentsBySession((m) => ({
        ...m,
        [sid]: new Set(m[sid] ?? []).add(who),
      }));
      // Seed the path with the entry (root) agent on the first event.
      setExecPathBySession((m) =>
        m[sid]?.length ? m : { ...m, [sid]: [who] },
      );
    }
    const transferTo =
      ev.actions?.transferToAgent ?? ev.actions?.transfer_to_agent;
    if (transferTo) {
      setExecPathBySession((m) => {
        const cur = m[sid] ?? [];
        return cur[cur.length - 1] === transferTo
          ? m
          : { ...m, [sid]: [...cur, transferTo] };
      });
    }
    const ended =
      ev.actions?.endOfAgent ?? ev.actions?.end_of_agent ?? ev.actions?.escalate;
    if (ended) {
      setExecPathBySession((m) => {
        const cur = m[sid] ?? [];
        return cur.length <= 1 ? m : { ...m, [sid]: cur.slice(0, -1) };
      });
    }
  };
  const [createView, setCreateView] = useState<CreateView>(loadView);
  const [deploymentTasks, setDeploymentTasks] = useState<
    DeploymentTaskUpdate[]
  >([]);
  const updateDeploymentTask = useCallback((task: DeploymentTaskUpdate) => {
    setDeploymentTasks((current) => {
      const existingIndex = current.findIndex((item) => item.id === task.id);
      if (existingIndex === -1) return [task, ...current];
      const next = [...current];
      next[existingIndex] = { ...next[existingIndex], ...task };
      return next;
    });
  }, []);
  const cancelDeploymentTask = useCallback(
    async (task: DeploymentTaskUpdate) => {
      try {
        await cancelAgentkitDeployment(task.id);
        setDeploymentTasks((current) =>
          current.map((item) =>
            item.id === task.id
              ? {
                  ...item,
                  status: "cancelled",
                  label: "已取消",
                  message: "部署已取消，相关 Runtime 资源已请求销毁。",
                }
              : item,
          ),
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setDeploymentTasks((current) =>
          current.map((item) =>
            item.id === task.id
              ? { ...item, message: `取消失败：${message}` }
              : item,
          ),
        );
      }
    },
    [],
  );
  // Whether the server has Volcengine AK/SK. The agent-creation workbench needs
  // them; assume present until the runtime-config check says otherwise (avoids
  // flashing the notice in the common, configured case).
  const [hasCreds, setHasCreds] = useState(true);
  const [skillCenter, setSkillCenter] = useState(false);
  const [addAgent, setAddAgent] = useState(false);
  // The "添加 Agent" chooser (two cards: AgentKit / 从 0 快速创建).
  const [addMenu, setAddMenu] = useState(false);
  // A draft imported from YAML, used to pre-fill the custom wizard once.
  const [importedDraft, setImportedDraft] = useState<AgentDraft | null>(null);
  const [savedAgentDrafts, setSavedAgentDrafts] = useState<WorkspaceAgentDraft[]>([]);
  const [workspaceAgentOrder, setWorkspaceAgentOrder] = useState<string[]>([]);
  const [editingDraftId, setEditingDraftId] = useState("");
  const editingDraftBaselineRef = useRef<WorkspaceAgentDraft | null>(null);
  const [searchView, setSearchView] = useState(false);
  // The #748 Agent workspace: library, evaluation groups, and draft management.
  const [manageAgents, setManageAgents] = useState(false);
  const [feedbackCaseReturnAgentId, setFeedbackCaseReturnAgentId] = useState("");
  const [feedbackCaseReturnKind, setFeedbackCaseReturnKind] =
    useState<"good" | "bad">("good");
  const [focusedWorkspaceAgentSection, setFocusedWorkspaceAgentSection] =
    useState<"basic" | "evaluations">("basic");
  const [focusedWorkspaceCaseKind, setFocusedWorkspaceCaseKind] =
    useState<"good" | "bad">("good");
  const [feedbackTargetEventId, setFeedbackTargetEventId] = useState("");
  const [myAgents, setMyAgents] = useState(false);
  // A search result may belong to a different agent; remember it so the
  // agent-switch effect opens it instead of resetting to a fresh chat.
  const pendingOpenRef = useRef<{ app: string; sid: string } | null>(null);
  // Remote AgentKit connections (persisted); register them into the ADK client
  // routing table once, synchronously, so remote app ids resolve immediately.
  const [connections, setConnections] = useState<RemoteConnection[]>(() => {
    const c = loadConnections();
    registerConnections(c);
    return c;
  });
  const [agentLibraryLoading, setAgentLibraryLoading] = useState(false);
  const [agentLibraryError, setAgentLibraryError] = useState("");
  const [libraryRuntimeIds, setLibraryRuntimeIds] = useState<Set<string> | null>(
    null,
  );
  const [libraryRuntimePermissions, setLibraryRuntimePermissions] = useState<
    Record<string, { canDelete: boolean }>
  >({});
  const [runtimeUpdateTarget, setRuntimeUpdateTarget] = useState<{
    runtimeId: string;
    name: string;
    region: string;
    currentVersion?: number | null;
  } | null>(null);
  const [focusedDeploymentTaskId, setFocusedDeploymentTaskId] = useState("");
  const [focusedWorkspaceAgentId, setFocusedWorkspaceAgentId] = useState("");
  const [agentDetailTarget, setAgentDetailTarget] =
    useState<MyAgentCardData | null>(null);
  // Shown when the user clicks the breadcrumb root to leave a create mode;
  // warns that the in-progress draft will be discarded.
  const [confirmLeave, setConfirmLeave] = useState(false);
  // Restore the previously-open session only once, after apps/user resolve.
  const restoredRef = useRef(false);
  const defaultViewAppliedRef = useRef(false);

  const saveWorkspaceDraft = useCallback(
    (
      id: string,
      draft: AgentDraft,
      deploymentTarget?: WorkspaceAgentDraft["deploymentTarget"],
    ) => {
      if (!id || !userId) return;
      setSavedAgentDrafts((current) => {
        const nextItem: WorkspaceAgentDraft = {
          id,
          draft,
          updatedAt: Date.now(),
          deploymentTarget,
        };
        const next = [nextItem, ...current.filter((item) => item.id !== id)];
        localStorage.setItem(workspaceDraftsKey(userId), JSON.stringify(next));
        return next;
      });
    },
    [userId],
  );

  const removeWorkspaceDraft = useCallback((id: string) => {
    if (!id || !userId) return;
    setSavedAgentDrafts((current) => {
      const next = current.filter((item) => item.id !== id);
      localStorage.setItem(workspaceDraftsKey(userId), JSON.stringify(next));
      return next;
    });
  }, [userId]);

  const deleteWorkspaceDrafts = useCallback((draftsToDelete: WorkspaceAgentDraft[]) => {
    if (!userId || draftsToDelete.length === 0) return;
    const deletedDraftIds = new Set(draftsToDelete.map((item) => item.id));
    setSavedAgentDrafts((current) => {
      const next = current.filter((item) => !deletedDraftIds.has(item.id));
      localStorage.setItem(workspaceDraftsKey(userId), JSON.stringify(next));
      return next;
    });
    if (deletedDraftIds.has(editingDraftId)) {
      setEditingDraftId("");
      setImportedDraft(null);
      setRuntimeUpdateTarget(null);
      editingDraftBaselineRef.current = null;
      localStorage.removeItem(activeWorkspaceDraftKey(userId));
    }
  }, [editingDraftId, userId]);

  const restoreWorkspaceDraftBaseline = useCallback((id: string) => {
    if (!id || !userId) return;
    const baseline = editingDraftBaselineRef.current;
    setSavedAgentDrafts((current) => {
      const remaining = current.filter((item) => item.id !== id);
      const next = baseline?.id === id ? [baseline, ...remaining] : remaining;
      localStorage.setItem(workspaceDraftsKey(userId), JSON.stringify(next));
      return next;
    });
  }, [userId]);

  useEffect(() => {
    if (!userId) {
      setSavedAgentDrafts([]);
      setWorkspaceAgentOrder([]);
      setEditingDraftId("");
      editingDraftBaselineRef.current = null;
      return;
    }
    const nextDrafts = loadWorkspaceDrafts(userId);
    setSavedAgentDrafts(nextDrafts);
    setWorkspaceAgentOrder(loadWorkspaceAgentOrder(userId));
    const activeId = localStorage.getItem(activeWorkspaceDraftKey(userId)) || "";
    const activeDraft = nextDrafts.find((item) => item.id === activeId);
    editingDraftBaselineRef.current = activeDraft ?? null;
    if (createView === "custom" && activeDraft) {
      setEditingDraftId(activeDraft.id);
      setImportedDraft(activeDraft.draft);
      setRuntimeUpdateTarget(activeDraft.deploymentTarget ?? null);
    }
    // Restore only when identity changes; later edits are already in state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    const key = activeWorkspaceDraftKey(userId);
    if (createView === "custom" && editingDraftId) {
      localStorage.setItem(key, editingDraftId);
    } else {
      localStorage.removeItem(key);
    }
  }, [createView, editingDraftId, userId]);

  const saveWorkspaceAgentOrder = useCallback((nextOrder: string[]) => {
    if (!userId) return;
    const deduped = [...new Set(nextOrder.filter(Boolean))];
    setWorkspaceAgentOrder(deduped);
    localStorage.setItem(workspaceAgentOrderKey(userId), JSON.stringify(deduped));
  }, [userId]);

  const deleteWorkspaceAgents = useCallback(async (agentsToDelete: AgentEntry[]) => {
    const targets = agentsToDelete.filter(
      (agent): agent is AgentEntry & { runtimeId: string } =>
        Boolean(agent.runtimeId) && agent.canDelete === true,
    );
    if (targets.length === 0) return;

    const deletedRuntimeIds = new Set<string>();
    const deletedAgentIds = new Set<string>();
    const failures: string[] = [];
    for (const agent of targets) {
      try {
        await deleteRuntime(agent.runtimeId, agent.region ?? "cn-beijing");
        removeRuntimeConnection(agent.runtimeId);
        deletedRuntimeIds.add(agent.runtimeId);
        deletedAgentIds.add(agent.id);
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : String(cause);
        failures.push(`${agent.label}: ${message}`);
      }
    }

    if (deletedRuntimeIds.size > 0) {
      setConnections(loadConnections());
      setLibraryRuntimeIds((current) => {
        if (!current) return current;
        const next = new Set(current);
        for (const runtimeId of deletedRuntimeIds) next.delete(runtimeId);
        return next;
      });
      setLibraryRuntimePermissions((current) =>
        Object.fromEntries(
          Object.entries(current).filter(([runtimeId]) => !deletedRuntimeIds.has(runtimeId)),
        ),
      );
      setWorkspaceAgentOrder((current) => {
        const next = current.filter((id) => !deletedAgentIds.has(id));
        if (userId) {
          localStorage.setItem(workspaceAgentOrderKey(userId), JSON.stringify(next));
        }
        return next;
      });
      setSavedAgentDrafts((current) => {
        const next = current.filter(
          (item) =>
            !item.deploymentTarget?.runtimeId ||
            !deletedRuntimeIds.has(item.deploymentTarget.runtimeId),
        );
        if (userId) {
          localStorage.setItem(workspaceDraftsKey(userId), JSON.stringify(next));
        }
        return next;
      });
      if (targets.some((agent) => agent.id === appName)) {
        viewSidRef.current = "";
        setSessionId("");
        setAppName("");
      }
    }

    if (failures.length > 0) {
      const shown = failures.slice(0, 3).join("；");
      const suffix = failures.length > 3 ? `；另有 ${failures.length - 3} 个失败` : "";
      throw new Error(`${failures.length} 个 Agent 删除失败：${shown}${suffix}`);
    }
  }, [appName, userId]);

  const refreshAgentLibrary = useCallback(async () => {
    setAgentLibraryLoading(true);
    setAgentLibraryError("");
    try {
      const runtimes: CloudRuntime[] = [];
      let nextToken = "";
      do {
        const page = await getRuntimes({
          scope: "mine",
          region: "all",
          pageSize: 100,
          nextToken,
        });
        runtimes.push(...page.runtimes);
        nextToken = page.nextToken;
      } while (nextToken && runtimes.length < 2000);

      setLibraryRuntimeIds(new Set(runtimes.map((runtime) => runtime.runtimeId)));
      setLibraryRuntimePermissions(
        Object.fromEntries(
          runtimes.map((runtime) => [
            runtime.runtimeId,
            { canDelete: runtime.canDelete },
          ]),
        ),
      );
      const failures: string[] = [];
      for (const runtime of runtimes) {
        try {
          await connectRuntime(
            runtime.runtimeId,
            runtime.name,
            runtime.region,
            runtime.currentVersion,
          );
        } catch {
          failures.push(runtime.name);
        }
      }
      setConnections(loadConnections());
      if (failures.length > 0) {
        setAgentLibraryError(
          `${failures.length} 个 Runtime 暂时无法读取，请稍后重试。`,
        );
      }
    } catch (cause) {
      setAgentLibraryError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAgentLibraryLoading(false);
    }
  }, []);

  // Placeholder: persisting/registering the created agent is a follow-up.
  function onCreate(draft: AgentDraft) {
    console.log("create agent draft:", draft);
    setCreateView(null);
    startNewChat();
  }

  // Navigate to a newly added agent: switch app, close create view, start fresh chat.
  function onAgentAdded(agentId: string, agentName: string) {
    console.log("Agent added, navigating to:", agentId, agentName);
    setConnections(loadConnections()); // Refresh connections to pick up the new agent
    setLibraryRuntimeIds(null);
    removeWorkspaceDraft(editingDraftId);
    setEditingDraftId("");
    editingDraftBaselineRef.current = null;
    setRuntimeUpdateTarget(null);
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId(agentId);
    setFocusedWorkspaceAgentSection("basic");
    setCreateView(null);
    setManageAgents(true);
    setAppName(agentId);
    // startNewChat will be called automatically by the appName change effect
  }

  const openDeploymentDetail = useCallback((task: DeploymentTaskUpdate) => {
    setCreateView(null);
    setAddMenu(false);
    setAgentDetailTarget(null);
    setManageAgents(true);
    setFocusedWorkspaceAgentId("");
    setFocusedWorkspaceAgentSection("basic");
    setFocusedDeploymentTaskId(task.id);
    setError("");
  }, []);

  const finishDeployment = useCallback(
    async (result: DeployResult) => {
      if (!result.runtimeId) throw new Error("部署完成，但未返回 Runtime ID。");
      const fallbackRegion = runtimeUpdateTarget?.region ?? "cn-beijing";
      const agentId = await connectRuntime(
        result.runtimeId,
        result.agentName,
        result.region ?? fallbackRegion,
        result.version,
      );
      setConnections(loadConnections());
      setLibraryRuntimeIds((current) => {
        const next = new Set(current ?? []);
        next.add(result.runtimeId!);
        return next;
      });
      setRuntimeUpdateTarget(null);
      removeWorkspaceDraft(editingDraftId);
      setEditingDraftId("");
      editingDraftBaselineRef.current = null;
      setFocusedWorkspaceAgentId(agentId);
      setFocusedWorkspaceAgentSection("basic");
      setCreateView(null);
      setManageAgents(true);
      setAppName(agentId);
    },
    [editingDraftId, removeWorkspaceDraft, runtimeUpdateTarget],
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const turnNodeRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const conversationAutoFollowRef = useRef(true);
  const conversationSmoothScrollRef = useRef(false);
  const conversationSmoothTimerRef = useRef<number | null>(null);
  const conversationScrollStateRef = useRef({ key: "", turnCount: 0 });
  const conversationScrollKey = sandboxSession?.id ?? sessionId;
  useLayoutEffect(() => {
    const el = scrollRef.current;
    const previous = conversationScrollStateRef.current;
    const conversationChanged = previous.key !== conversationScrollKey;
    const turnAppended = !conversationChanged && turns.length > previous.turnCount;
    conversationScrollStateRef.current = {
      key: conversationScrollKey,
      turnCount: turns.length,
    };
    if (!el || turns.length === 0 || (!conversationChanged && !turnAppended)) return;

    conversationAutoFollowRef.current = true;
    conversationSmoothScrollRef.current = false;
    if (conversationSmoothTimerRef.current !== null) {
      window.clearTimeout(conversationSmoothTimerRef.current);
      conversationSmoothTimerRef.current = null;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (conversationChanged || reduceMotion) {
      el.scrollTop = el.scrollHeight;
      return;
    }

    conversationSmoothScrollRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    conversationSmoothTimerRef.current = window.setTimeout(() => {
      conversationSmoothScrollRef.current = false;
      conversationSmoothTimerRef.current = null;
    }, 450);
  }, [conversationScrollKey, turns.length]);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (
      !el ||
      !conversationAutoFollowRef.current ||
      conversationSmoothScrollRef.current
    ) return;
    el.scrollTop = el.scrollHeight;
  }, [activeConversationBusy, turns]);
  useEffect(() => {
    if (!feedbackTargetEventId || manageAgents || turns.length === 0) return;
    const node = turnNodeRefs.current.get(feedbackTargetEventId);
    if (!node) return;
    conversationAutoFollowRef.current = false;
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = window.setTimeout(() => {
      setFeedbackTargetEventId("");
    }, 2600);
    return () => window.clearTimeout(timer);
  }, [feedbackTargetEventId, manageAgents, turns]);
  useEffect(() => () => {
    if (conversationSmoothTimerRef.current !== null) {
      window.clearTimeout(conversationSmoothTimerRef.current);
    }
  }, []);
  const onConversationScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || conversationSmoothScrollRef.current) return;
    conversationAutoFollowRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 32;
  }, []);
  const onConversationWheel = useCallback((event: WheelEvent<HTMLDivElement>) => {
    if (event.deltaY < 0) {
      conversationSmoothScrollRef.current = false;
      conversationAutoFollowRef.current = false;
    }
  }, []);
  const onConversationTouchMove = useCallback(() => {
    conversationSmoothScrollRef.current = false;
    conversationAutoFollowRef.current = false;
  }, []);
  const followConversationStreamFrame = useCallback(() => {
    const el = scrollRef.current;
    if (
      !el ||
      !conversationAutoFollowRef.current ||
      conversationSmoothScrollRef.current
    ) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  // Resolve SSO identity first; it provides the ADK user_id.
  const resolveAuth = useCallback(() => {
    setAuthError(null);
    resolveIdentity()
      .then((id) => {
        setUserId(id.userId);
        setUserInfo(id.info);
        setLocalMode(!!id.local);
        setAuthStatus(id.status);
        if (id.status === "authenticated") {
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(false);
          setMyAgents(true);
        }
      })
      .catch((error) => {
        setAuthError(error instanceof Error ? error.message : String(error));
      });
  }, []);
  useEffect(() => {
    resolveAuth();
  }, [resolveAuth]);

  useEffect(() => {
    const showExpiredDialog = () => {
      setAuthRecoveryError("");
      setAuthExpired(true);
    };
    window.addEventListener(AUTHENTICATION_REQUIRED_EVENT, showExpiredDialog);
    if (isAuthenticationPending()) showExpiredDialog();
    return () =>
      window.removeEventListener(
        AUTHENTICATION_REQUIRED_EVENT,
        showExpiredDialog,
      );
  }, []);

  const recoverAuthentication = useCallback(async () => {
    if (authRecoveryActiveRef.current) return;
    authRecoveryActiveRef.current = true;
    const loginWindow = openLoginWindow();
    if (!loginWindow) {
      authRecoveryActiveRef.current = false;
      setAuthRecoveryError("登录窗口被浏览器拦截，请允许弹出窗口后重试。");
      return;
    }
    setAuthRecoveryChecking(true);
    setAuthRecoveryError("");
    try {
      while (true) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        try {
          const identity = await resolveIdentity();
          if (identity.status === "authenticated") {
            setUserId(identity.userId);
            setUserInfo(identity.info);
            setLocalMode(!!identity.local);
            setAuthStatus(identity.status);
            setAuthExpired(false);
            authenticationRestored();
            loginWindow.close();
            return;
          }
        } catch {
          // The gateway may return its login page until the popup completes.
        }
        if (loginWindow.closed) {
          setAuthRecoveryError("登录窗口已关闭，请重新登录以继续当前操作。");
          return;
        }
      }
    } finally {
      authRecoveryActiveRef.current = false;
      setAuthRecoveryChecking(false);
    }
  }, []);

  useEffect(() => {
    if (localMode && userId) setLocalUser(userId);
  }, [localMode, userId]);

  useEffect(() => {
    if (authStatus !== "authenticated" || !userId) {
      setNewChatCapabilities({});
      return;
    }
    let cancelled = false;
    void Promise.allSettled([
      getSandboxCapability(),
      getSkillCreatorCapability(),
    ]).then(([sandboxResult, skillResult]) => {
      if (cancelled) return;
      setNewChatCapabilities({
        temporaryEnabled:
          sandboxResult.status === "fulfilled" && sandboxResult.value.enabled,
        skillCreateEnabled:
          skillResult.status === "fulfilled" && skillResult.value.enabled,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [authStatus, userId]);

  useEffect(() => {
    if (authStatus !== "authenticated" || !userId) {
      setAccess(null);
      return;
    }
    let cancelled = false;
    setAccess(null);
    getStudioAccess()
      .then((next) => {
        if (!cancelled) setAccess(next);
      })
      .catch((error) => {
        console.warn("[app] /web/access failed; using ordinary-user access:", error);
        if (!cancelled) setAccess(DEFAULT_STUDIO_ACCESS);
      });
    return () => {
      cancelled = true;
    };
  }, [authStatus, userId]);

  // Load per-module feature gates. The configured landing page is applied only
  // after role resolution so an ordinary user never sees a privileged view.
  useEffect(() => {
    getUiConfig().then((cfg) => {
      setFeatures(cfg.features);
      setAgentsSource(cfg.agentsSource);
      setSiteBranding(cfg.branding);
      setVersion(cfg.version);
      setDefaultView(cfg.defaultView);
      setUiConfigLoaded(true);
    });
  }, []);

  useEffect(() => {
    if (!access || !uiConfigLoaded || defaultViewAppliedRef.current || myAgents) return;
    defaultViewAppliedRef.current = true;
    if (defaultView === "addAgent" && access.capabilities.createAgents) {
      setCreateView(null);
      setSkillCenter(false);
      setSearchView(false);
      setManageAgents(false);
      setAddAgent(false);
      setAddMenu(true);
    }
  }, [access, defaultView, myAgents, uiConfigLoaded]);

  useEffect(() => {
    if (!access) return;
    if (!access.capabilities.createAgents) {
      setCreateView(null);
      setImportedDraft(null);
      setAddAgent(false);
      setAddMenu(false);
      setDeploymentTasks([]);
    }
    if (!access.capabilities.manageAgents) setManageAgents(false);
  }, [access]);

  useEffect(() => {
    if (authStatus !== "authenticated" || agentsSource !== "cloud" || !uiConfigLoaded) {
      return;
    }
    void refreshAgentLibrary();
  }, [agentsSource, authStatus, refreshAgentLibrary, uiConfigLoaded]);

  useEffect(() => {
    document.title = siteBranding.title;
    let favicon = document.querySelector<HTMLLinkElement>('link[rel~="icon"]');
    if (!favicon) {
      favicon = document.createElement("link");
      favicon.rel = "icon";
      document.head.appendChild(favicon);
    }
    favicon.removeAttribute("type");
    favicon.href = siteBranding.logoUrl || defaultSiteLogo;
  }, [siteBranding]);

  // Check whether the server has Volcengine AK/SK (needed by the workbench).
  useEffect(() => {
    fetch("/web/runtime-config", { signal: AbortSignal.timeout(10_000) })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) setHasCreds(!!d.credentials);
      })
      .catch((error) => {
        console.warn("[app] /web/runtime-config probe failed; workbench stays hidden:", error);
      });
  }, []);

  function onUsername(name: string) {
    setLocalUser(name);
    // A completed login is a fresh entry into the app. Do not reveal a create
    // or management view that was persisted before the login page appeared.
    restoredRef.current = true;
    defaultViewAppliedRef.current = false;
    setAccess(null);
    setCreateView(null);
    setImportedDraft(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    startNewChat();
    setMyAgents(true);
    setUserId(name);
    setUserInfo({ name });
    setLocalMode(true);
    setAuthStatus("authenticated");
  }

  function onLogout() {
    defaultViewAppliedRef.current = false;
    setAccess(null);
    if (localMode) {
      clearLocalUser();
      setUserId("");
      setUserInfo(undefined);
      setAuthStatus("unauthenticated");
    } else {
      logout();
    }
  }

  useEffect(() => {
    if (authStatus === "unauthenticated") return; // login page is shown instead
    listApps()
      .then((list) => {
        setApps(list);
        // Restore the last-used agent; otherwise land on a known-good default
        // (prefer a servable, conversational agent — numbered examples like
        // 01_quickstart are standalone scripts with no root_agent and can't load).
        if (agentsSource === "cloud") {
          const saved = localStorage.getItem(LS.app);
          const remoteIds = connections.flatMap((c) =>
            c.apps.map((a) => remoteAppId(c.id, a)),
          );
          setAppName((current) => {
            if (current && remoteIds.includes(current)) return current;
            if (saved && remoteIds.includes(saved)) return saved;
            return remoteIds[0] ?? "";
          });
          return;
        }
        // Local mode: restore the last-used agent, else a known-good default
        // (prefer a servable, conversational agent — numbered examples like
        // 01_quickstart are standalone scripts with no root_agent and can't load).
        const saved = localStorage.getItem(LS.app);
        const remoteIds = connections.flatMap((c) => c.apps.map((a) => remoteAppId(c.id, a)));
        const valid = saved && (list.includes(saved) || remoteIds.includes(saved));
        const fallback =
          ["web_search_agent", "web_demo"].find((a) => list.includes(a)) ??
          list.find((a) => !/^\d/.test(a)) ??
          list[0];
        setAppName(valid ? saved : fallback || "");
      })
      .catch((e) => setError(String(e)));
  }, [authStatus, agentsSource, connections]);

  // Persist the current view/agent/session so a refresh restores them.
  useEffect(() => {
    if (appName) localStorage.setItem(LS.app, appName);
  }, [appName]);
  useEffect(() => {
    let cancelled = false;
    setSessionCapabilities(null);
    setSessionBuiltinTools([]);
    if (!appName || !userId || !sessionId) {
      setSessionCapabilitiesLoading(false);
      return;
    }
    setSessionCapabilitiesLoading(true);
    getSessionCapabilities(appName, userId, sessionId)
      .then((capabilities) => {
        if (cancelled) return;
        setSessionCapabilities(capabilities);
        void listSessionBuiltinTools(appName)
          .then((tools) => {
            if (!cancelled) setSessionBuiltinTools(tools);
          })
          .catch(() => {
            if (!cancelled) setSessionBuiltinTools([]);
          });
      })
      .catch(() => {
        if (!cancelled) setSessionCapabilities(null);
      })
      .finally(() => {
        if (!cancelled) setSessionCapabilitiesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [appName, userId, sessionId]);
  useEffect(() => {
    let cancelled = false;
    setAgentInfo(null);
    setInvocation(emptyInvocation());
    if (!appName) {
      setCapabilitiesLoading(false);
      return;
    }
    setCapabilitiesLoading(true);
    getAgentInfo(appName)
      .then((info) => {
        if (!cancelled) setAgentInfo(info);
      })
      .catch(() => {
        if (!cancelled) setAgentInfo(null);
      })
      .finally(() => {
        if (!cancelled) setCapabilitiesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [appName]);
  useEffect(() => {
    if (!access) return;
    localStorage.setItem(
      LS.view,
      access.capabilities.createAgents ? createView ?? "chat" : "chat",
    );
  }, [access, createView]);
  useEffect(() => {
    localStorage.setItem(LS.session, sessionId);
    // Keep the stream-write guard in sync with the displayed session (backup for
    // any navigation path that doesn't set it synchronously).
    viewSidRef.current = sessionId;
  }, [sessionId]);
  // Abort the in-flight stream when the whole view unmounts.
  useEffect(
    () => () => streamAbortsRef.current.forEach((c) => c.abort()),
    [],
  );
  useEffect(
    () => () => streamPresentationTimersRef.current.forEach((timer) => {
      window.clearTimeout(timer);
    }),
    [],
  );
  useEffect(
    () => () => {
      sandboxLaunchAbortRef.current?.abort();
      sandboxMessageAbortRef.current?.abort();
    },
    [],
  );

  // When the app (or resolved user) changes, list existing sessions. On the
  // very first resolve, restore the previously-open session (if it still
  // exists and we weren't on a create view); otherwise start a fresh chat.
  useEffect(() => {
    if (!appName || !userId) return;
    (async () => {
      const list = await refreshSessions(appName);
      if (!restoredRef.current) {
        restoredRef.current = true;
        const savedId = localStorage.getItem(LS.session) || "";
        if (loadView() === null && savedId && list.some((s) => s.id === savedId)) {
          void pickSession(savedId);
          return;
        }
      }
      startNewChat();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appName, userId]);

  // After switching agent from a search result, open the target session (runs
  // after the agent-switch effect above, so it wins over its startNewChat()).
  useEffect(() => {
    const p = pendingOpenRef.current;
    if (p && p.app === appName) {
      pendingOpenRef.current = null;
      void pickSession(p.sid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appName]);

  // Open a session surfaced by search, switching agent first if needed.
  function openFromSearch(app: string, sid: string) {
    setSearchView(false);
    if (app === appName) {
      void pickSession(sid);
    } else {
      pendingOpenRef.current = { app, sid };
      setAppName(app);
    }
  }

  async function refreshSessions(app: string): Promise<AdkSession[]> {
    try {
      const list = await listSessions(app, userId);
      // Hydrate events so the sidebar can show a title per session.
      const hydrated = await Promise.all(
        list.map((s) =>
          s.events?.length ? Promise.resolve(s) : getSession(app, userId, s.id),
        ),
      );
      setSessions(hydrated);
      return hydrated;
    } catch (e) {
      setError(String(e));
      return [];
    }
  }

  function openSandboxLaunch() {
    if (sandboxSession) return;
    setError("");
    setSandboxLaunchError("");
    setSandboxLaunchState("confirm");
    setSandboxLaunchOpen(true);
  }

  function cancelSandboxLaunch() {
    sandboxLaunchAbortRef.current?.abort();
    sandboxLaunchAbortRef.current = null;
    setSandboxLaunchOpen(false);
    setSandboxLaunchState("confirm");
    setSandboxLaunchError("");
    if (!sandboxSession && newChatMode === "temporary") {
      setNewChatMode("agent");
    }
  }

  async function launchSandboxSession() {
    sandboxLaunchAbortRef.current?.abort();
    const controller = new AbortController();
    sandboxLaunchAbortRef.current = controller;
    setSandboxLaunchState("loading");
    setSandboxLaunchError("");
    try {
      const nextSession = await sandboxClient.startSession({
        signal: controller.signal,
      });
      if (sandboxLaunchAbortRef.current !== controller) return;
      viewSidRef.current = "";
      setSessionId("");
      setPendingTurns([]);
      setInput("");
      setInvocation(emptyInvocation());
      setNewChatMode("temporary");
      discardSkillCreation();
      setSkillCreating(false);
      discardDraftAttachments(attachments);
      setAttachments([]);
      setSandboxTurns([]);
      setSandboxSession(nextSession);
      setCreateView(null);
      setSkillCenter(false);
      setAddAgent(false);
      setAddMenu(false);
      setSearchView(false);
      setManageAgents(false);
      setAgentDetailTarget(null);
      setMyAgents(false);
      setSandboxLaunchOpen(false);
      setSandboxLaunchState("confirm");
    } catch (launchError) {
      if ((launchError as Error)?.name === "AbortError") return;
      if (sandboxLaunchAbortRef.current !== controller) return;
      setSandboxLaunchError(
        launchError instanceof Error
          ? launchError.message
          : String(launchError),
      );
      setSandboxLaunchState("error");
    } finally {
      if (sandboxLaunchAbortRef.current === controller) {
        sandboxLaunchAbortRef.current = null;
      }
    }
  }

  function exitSandboxSession() {
    sandboxMessageAbortRef.current?.abort();
    sandboxMessageAbortRef.current = null;
    setSandboxBusy(false);
    setSandboxTurns([]);
    setInput("");
    setError("");
    setNewChatMode("agent");
    const closingSession = sandboxSession;
    setSandboxSession(null);
    if (closingSession) {
      void sandboxClient
        .closeSession(closingSession.id)
        .catch((closeError) => setError(String(closeError)));
    }
  }

  async function sendSandboxMessage(text: string) {
    const activeSession = sandboxSession;
    if (!activeSession || sandboxBusy || !text.trim()) return;
    setError("");
    const controller = new AbortController();
    sandboxMessageAbortRef.current?.abort();
    sandboxMessageAbortRef.current = controller;
    const optimisticTurns: Turn[] = [
      {
        role: "user",
        blocks: [{ kind: "text", text }],
        meta: { ts: Date.now() / 1000 },
      },
      { role: "assistant", blocks: [] },
    ];
    setSandboxTurns((current) => [...current, ...optimisticTurns]);
    setSandboxBusy(true);
    try {
      const reply = await sandboxClient.sendMessage(
        { sessionId: activeSession.id, text },
        {
          signal: controller.signal,
          onBlocks: (blocks) => {
            if (sandboxMessageAbortRef.current !== controller) return;
            setSandboxTurns((current) => {
              const next = current.slice();
              const last = next[next.length - 1];
              if (last?.role === "assistant") {
                next[next.length - 1] = { ...last, blocks };
              }
              return next;
            });
          },
        },
      );
      if (sandboxMessageAbortRef.current !== controller) return;
      setSandboxTurns((current) => {
        const next = current.slice();
        const last = next[next.length - 1];
        if (last?.role === "assistant") {
          next[next.length - 1] = {
            ...last,
            blocks: reply.blocks,
            meta: { ts: Date.now() / 1000 },
          };
        }
        return next;
      });
    } catch (messageError) {
      if ((messageError as Error)?.name === "AbortError") return;
      if (sandboxMessageAbortRef.current !== controller) return;
      setSandboxTurns((current) => current.slice(0, -2));
      setInput(text);
      setError(
        `内置智能体发送失败：${
          messageError instanceof Error
            ? messageError.message
            : String(messageError)
        }`,
      );
    } finally {
      if (sandboxMessageAbortRef.current === controller) {
        sandboxMessageAbortRef.current = null;
        setSandboxBusy(false);
      }
    }
  }

  // Reset to a fresh, not-yet-created chat. The backend session is created
  // lazily on the first message (see send()). A background stream (if any)
  // keeps running and persisting — its writes are suppressed here by viewSidRef.
  function startNewChat() {
    exitSandboxSession();
    setError("");
    setAgentInfoOpen(false);
    setGreeting(pickGreeting());
    setNewChatMode("agent");
    discardSkillCreation();
    setSkillCreating(false);
    const abandonedSession = sessionId && persistentTurns.length === 0 && attachments.length > 0
      ? sessionId
      : "";
    viewSidRef.current = "";
    setSessionId("");
    setSessionCapabilities(null);
    setSessionBuiltinTools([]);
    setInitializingSession(false);
    setPendingTurns([]);
    setInvocation(emptyInvocation());
    discardDraftAttachments(attachments);
    setAttachments([]);
    if (abandonedSession) void abandonDraftSession(abandonedSession);
  }

  function showToast(message: string) {
    if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
    setToast(message);
    toastTimerRef.current = window.setTimeout(() => {
      setToast("");
      toastTimerRef.current = null;
    }, 3000);
  }

  function openNewChat() {
    setCreateView(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    setAgentDetailTarget(null);
    if (!appName && !sandboxSession) {
      setMyAgents(true);
      showToast("请先选择 agent");
      return;
    }
    setMyAgents(false);
    startNewChat();
  }

  async function removeSession(id: string) {
    try {
      // Deleting a session with a running stream — abort just that one.
      streamAbortsRef.current.get(id)?.abort();
      await deleteSessionMedia(appName, userId, id);
      await deleteSession(appName, userId, id);
      const presentationTimer = streamPresentationTimersRef.current.get(id);
      if (presentationTimer !== undefined) window.clearTimeout(presentationTimer);
      streamPresentationTimersRef.current.delete(id);
      setStreamPresentationSids((current) => {
        if (!current.has(id)) return current;
        const next = new Set(current);
        next.delete(id);
        return next;
      });
      setTurnsBySession((m) => {
        const { [id]: _drop, ...rest } = m;
        return rest;
      });
      if (id === sessionId) startNewChat();
      await refreshSessions(appName);
    } catch (e) {
      setError(String(e));
    }
  }

  async function pickSession(id: string) {
    if (sandboxSession) exitSandboxSession();
    if (id === sessionId) return;
    viewSidRef.current = id;
    setError("");
    setInitializingSession(false);
    setPendingTurns([]);
    setNewChatMode("agent");
    discardSkillCreation();
    setInvocation(emptyInvocation());
    setSessionCapabilities(null);
    setSessionBuiltinTools([]);
    setSessionId(id);
    // Already have this session's turns (it's cached, or streaming in the
    // background)? Show them instantly and let any live stream keep updating —
    // no re-fetch, no "loading" flash, streaming stays visible.
    if (turnsBySession[id] !== undefined) return;
    setLoadingSession(true);
    try {
      const s = await getSession(appName, userId, id);
      setTurnsFor(id, eventsToTurns(s.events ?? [], s.state));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingSession(false);
    }
  }

  async function openFeedbackCaseInStudio(item: AgentFeedbackCase) {
    if (!item.sessionId || !item.messageId) {
      setError("这条案例缺少会话定位信息，无法跳转。");
      return;
    }
    setSearchView(false);
    setCreateView(null);
    setAddAgent(false);
    setAddMenu(false);
    setSkillCenter(false);
    setManageAgents(false);
    setFeedbackCaseReturnAgentId(appName);
    setFeedbackCaseReturnKind(item.kind);
    setFeedbackTargetEventId(item.messageId);
    await pickSession(item.sessionId);
  }

  function returnToFeedbackCases() {
    const agentId = feedbackCaseReturnAgentId || appName;
    setSearchView(false);
    setCreateView(null);
    setAddAgent(false);
    setAddMenu(false);
    setSkillCenter(false);
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId(agentId);
    setFocusedWorkspaceAgentSection("evaluations");
    setFocusedWorkspaceCaseKind(feedbackCaseReturnKind);
    setManageAgents(true);
    setFeedbackCaseReturnAgentId("");
    setFeedbackTargetEventId("");
  }

  function clearDeletedFeedbackCases(items: AgentFeedbackCase[]) {
    const clearBySession = new Map<string, Set<string>>();
    const clearByCacheScope = new Map<string, {
      runtimeId: string;
      appName: string;
      userId: string;
      sessionId: string;
      eventIds: Set<string>;
    }>();
    for (const item of items) {
      if (!item.sessionId || !item.messageId) continue;
      const sessionEvents = clearBySession.get(item.sessionId) ?? new Set<string>();
      sessionEvents.add(item.messageId);
      clearBySession.set(item.sessionId, sessionEvents);
      if (item.runtimeId && item.userId) {
        const key = [
          item.runtimeId,
          appName,
          item.userId,
          item.sessionId,
        ].join(":");
        const scope = clearByCacheScope.get(key) ?? {
          runtimeId: item.runtimeId,
          appName,
          userId: item.userId,
          sessionId: item.sessionId,
          eventIds: new Set<string>(),
        };
        scope.eventIds.add(item.messageId);
        clearByCacheScope.set(key, scope);
      }
    }
    if (clearBySession.size === 0) return;
    setTurnsBySession((current) => {
      const next = { ...current };
      for (const [sid, eventIds] of clearBySession) {
        const existing = next[sid];
        if (!existing) continue;
        next[sid] = existing.map((turn) =>
          turn.meta?.eventId && eventIds.has(turn.meta.eventId)
            ? { ...turn, meta: { ...turn.meta, feedback: undefined } }
            : turn,
        );
      }
      return next;
    });
    setSessions((current) =>
      current.map((session) => {
        const eventIds = clearBySession.get(session.id);
        if (!eventIds || !session.state) return session;
        const state = { ...session.state };
        for (const eventId of eventIds) delete state[`veadk_feedback:${eventId}`];
        return { ...session, state };
      }),
    );
    setFeedbackPendingIds((current) => {
      const next = new Set(current);
      for (const eventIds of clearBySession.values()) {
        for (const eventId of eventIds) next.delete(eventId);
      }
      return next;
    });
    for (const scope of clearByCacheScope.values()) {
      clearMessageFeedbackCache({
        runtimeId: scope.runtimeId,
        appName: scope.appName,
        userId: scope.userId,
        sessionId: scope.sessionId,
        eventIds: [...scope.eventIds],
      });
    }
  }

  async function ensureSession(activate = true): Promise<string> {
    if (sessionId) return sessionId;
    if (!creatingSessionRef.current) {
      creatingSessionRef.current = createSession(appName, userId);
    }
    const pending = creatingSessionRef.current;
    try {
      const sid = await pending;
      if (activate) setSessionId(sid);
      const now = Date.now() / 1000;
      const optimistic: AdkSession = { id: sid, lastUpdateTime: now, events: [] };
      setSessions((prev) => [optimistic, ...prev.filter((s) => s.id !== sid)]);
      return sid;
    } finally {
      if (creatingSessionRef.current === pending) creatingSessionRef.current = null;
    }
  }

  async function addCapability(capability: AddSessionCapability): Promise<boolean> {
    if (!appName || !userId || !sessionId || !sessionCapabilities) return false;
    setSessionCapabilityMutating(true);
    setError("");
    try {
      const updated = await addSessionCapability(
        appName,
        userId,
        sessionId,
        capability,
        sessionCapabilities.revision,
      );
      setSessionCapabilities(updated);
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    } finally {
      setSessionCapabilityMutating(false);
    }
  }

  async function removeCapability(capabilityId: string) {
    if (!appName || !userId || !sessionId || !sessionCapabilities) return;
    setSessionCapabilityMutating(true);
    setError("");
    try {
      const updated = await removeSessionCapability(
        appName,
        userId,
        sessionId,
        capabilityId,
        sessionCapabilities.revision,
      );
      setSessionCapabilities(updated);
    } catch (e) {
      setError(String(e));
    } finally {
      setSessionCapabilityMutating(false);
    }
  }

  async function addFiles(files: FileList | File[]) {
    setError("");
    let sid: string;
    try {
      sid = await ensureSession();
    } catch (e) {
      setError(String(e));
      return;
    }
    const drafts = Array.from(files).map((file) => ({
      file,
      attachment: {
        id: attachmentDraftId(),
        mimeType: browserMimeType(file),
        name: file.name,
        sizeBytes: file.size,
        status: "uploading" as const,
      },
    }));
    setAttachments((current) => [...current, ...drafts.map((draft) => draft.attachment)]);
    await Promise.all(
      drafts.map(async ({ file, attachment }) => {
        try {
          const uploaded = await uploadMedia(appName, userId, sid, file);
          if (removedAttachmentIdsRef.current.delete(attachment.id)) {
            if (uploaded.uri) await deleteMedia(appName, uploaded.uri);
            return;
          }
          setAttachments((current) => current.map((item) =>
            item.id === attachment.id
              ? uploaded
              : item,
          ));
        } catch (e) {
          if (removedAttachmentIdsRef.current.delete(attachment.id)) return;
          const message = e instanceof Error ? e.message : String(e);
          setAttachments((current) => current.map((item) =>
            item.id === attachment.id ? { ...item, status: "error", error: message } : item,
          ));
          setError(message);
        }
      }),
    );
  }

  async function send(
    text: string,
    atts: Attachment[] = [],
    selectedInvocation: FrontendInvocation = emptyInvocation(),
  ) {
    // `busy` here = the CURRENT session is already streaming (can't double-send
    // to it). Other sessions can stream concurrently.
    if (
      (!text.trim() && atts.length === 0) ||
      conversationBusy ||
      sessionConfigurationBusy ||
      !appName ||
      !userId
    ) return;
    setError("");

    const userBlocks: Turn["blocks"] = [];
    if (selectedInvocation.skills.length > 0 || selectedInvocation.targetAgent) {
      userBlocks.push({ kind: "invocation", value: selectedInvocation });
    }
    if (atts.length)
      userBlocks.push({
        kind: "attachment",
        files: atts.map((a) => ({
          id: a.id,
          mimeType: a.mimeType,
          data: a.data,
          uri: a.uri,
          name: a.name,
          sizeBytes: a.sizeBytes,
        })),
      });
    if (text.trim()) userBlocks.push({ kind: "text", text });
    const optimisticTurns: Turn[] = [
      { role: "user", blocks: userBlocks, meta: { ts: Date.now() / 1000 } },
      { role: "assistant", blocks: [] },
    ];
    const createsSession = !sessionId;
    if (createsSession) {
      setPendingTurns(optimisticTurns);
      setInitializingSession(true);
    }

    let sid: string;
    try {
      sid = await ensureSession(!createsSession);
    } catch (e) {
      if (createsSession) {
        setPendingTurns([]);
        setInitializingSession(false);
        setInput(text);
        setInvocation(selectedInvocation);
      }
      setError(String(e));
      return;
    }

    setTurnsFor(sid, (current) =>
      createsSession ? optimisticTurns : [...current, ...optimisticTurns],
    );
    if (createsSession) {
      viewSidRef.current = sid;
      setSessionId(sid);
      setPendingTurns([]);
      setInitializingSession(false);
    }

    // Register this session's own stream (concurrent with other sessions').
    const ctrl = new AbortController();
    streamAbortsRef.current.set(sid, ctrl);
    setStreaming(sid, true);
    startStreamPresentation(sid);
    viewSidRef.current = sid;

    setActiveAgentBySession((m) => ({ ...m, [sid]: "" }));
    setSeenAgentsBySession((m) => ({ ...m, [sid]: new Set() }));
    setExecPathBySession((m) => ({ ...m, [sid]: [] }));

    try {
      let acc = emptyAcc();
      let currentStreamAuthor = "";
      let tokens = 0;
      let ts = Date.now() / 1000;
      let eventId = "";
      let invocationId = "";
      for await (const event of runSSE({
        appName,
        userId,
        sessionId: sid,
        text,
        attachments: atts,
        invocation: selectedInvocation,
        signal: ctrl.signal,
        sessionCapabilities: sessionCapabilities !== null,
      })) {
        if (ctrl.signal.aborted) break;
        const errMsg = event.error ?? event.errorMessage ?? event.error_message;
        if (typeof errMsg === "string" && errMsg) {
          if (viewSidRef.current === sid) setError(errMsg);
          break;
        }
        // Live topology: author + transfer/end signals, keyed by session.
        applyStreamSignals(sid, event);
        const eventAuthor = event.author && event.author !== "user"
          ? event.author
          : "";
        if (eventAuthor && eventAuthor !== currentStreamAuthor) {
          currentStreamAuthor = eventAuthor;
          acc = emptyAcc();
        }
        acc = applyEvent(acc, event);
        const usage = event.usageMetadata ?? event.usage_metadata;
        if (usage?.totalTokenCount) tokens = usage.totalTokenCount;
        if (event.timestamp) ts = event.timestamp;
        if (event.id) eventId = event.id;
        const nextInvocationId = event.invocationId ?? event.invocation_id;
        if (nextInvocationId) invocationId = nextInvocationId;
        const blocks = acc.blocks;
        const meta = {
          author: currentStreamAuthor || undefined,
          tokens: tokens || undefined,
          ts,
          eventId: eventId || undefined,
          invocationId: invocationId || undefined,
        };
        setTurnsFor(sid, (t) => {
          const next = t.slice();
          const last = next[next.length - 1];
          if (
            last?.role === "assistant" &&
            (!last.meta?.author || last.meta.author === currentStreamAuthor)
          ) {
            next[next.length - 1] = { ...last, blocks, meta };
          } else {
            next.push({ role: "assistant", blocks, meta });
          }
          return next;
        });
      }
      void refreshSessions(appName);
    } catch (e) {
      // An abort (unmount / session delete) is expected — surface only real
      // errors, and only while this session is on screen.
      if (
        (e as Error)?.name !== "AbortError" &&
        !ctrl.signal.aborted &&
        viewSidRef.current === sid
      ) {
        setError(String(e));
      }
    } finally {
      if (streamAbortsRef.current.get(sid) === ctrl) streamAbortsRef.current.delete(sid);
      setStreaming(sid, false);
      finishStreamPresentation(sid);
      setActiveAgentBySession((m) => ({ ...m, [sid]: "" }));
      setExecPathBySession((m) => ({ ...m, [sid]: [] }));
    }
  }

  function onAction(action: A2uiAction | undefined, node: A2uiComponent) {
    const name = action?.event?.name ?? node.id;
    const context = action?.event?.context ?? {};
    send(`[ui-action] ${name}: ${JSON.stringify(context)}`);
  }

  /** Complete an MCP/tool OAuth request: open the authorize URL, capture the
   *  callback, then send the credential back as a function response — ADK
   *  exchanges the code for a token and resumes the paused tool call. The
   *  continuation streams into the same assistant turn. */
  async function onAuth(block: Extract<Block, { kind: "auth" }>) {
    if (!block.authUri) throw new Error("事件中没有授权地址。");
    if (!appName || !userId || !sessionId) throw new Error("会话尚未就绪。");
    const sid = sessionId;
    const callbackUrl = await runOAuthPopup(block.authUri);
    const response = withAuthResponseUri(block.authConfig, callbackUrl);

    // The moment we have the callback, mark the auth card resolved so it
    // collapses to a compact "已授权" row immediately — rather than sitting on
    // "等待授权…" until the whole reply finishes streaming.
    const resolveAuth = (bs: Block[]) =>
      bs.map((b) => (b.kind === "auth" && !b.done ? { ...b, done: true } : b));
    setTurnsFor(sid, (t) => {
      const next = t.slice();
      const last = next[next.length - 1];
      if (last?.role === "assistant") {
        next[next.length - 1] = { ...last, blocks: resolveAuth(last.blocks) };
      }
      return next;
    });

    // Base = the current assistant turn's blocks (keeps the thinking + resolved
    // auth card); the resumed run's events are appended after it.
    const lastTurn = turns[turns.length - 1];
    const base = resolveAuth(
      lastTurn && lastTurn.role === "assistant" ? lastTurn.blocks : [],
    );

    const ctrl = new AbortController();
    streamAbortsRef.current.set(sid, ctrl);
    setStreaming(sid, true);
    startStreamPresentation(sid);
    try {
      let acc = emptyAcc();
      let currentStreamAuthor = lastTurn?.meta?.author ?? "";
      let currentBase = base;
      let tokens = 0;
      let ts = Date.now() / 1000;
      let eventId = lastTurn?.meta?.eventId ?? "";
      let invocationId = lastTurn?.meta?.invocationId ?? "";
      for await (const event of runSSE({
        appName,
        userId,
        sessionId,
        text: "",
        functionResponses: [
          { id: block.callId, name: "adk_request_credential", response },
        ],
        signal: ctrl.signal,
        sessionCapabilities: sessionCapabilities !== null,
      })) {
        if (ctrl.signal.aborted) break;
        applyStreamSignals(sid, event);
        const eventAuthor = event.author && event.author !== "user"
          ? event.author
          : "";
        if (eventAuthor && eventAuthor !== currentStreamAuthor) {
          currentStreamAuthor = eventAuthor;
          currentBase = [];
          acc = emptyAcc();
        }
        acc = applyEvent(acc, event);
        const usage = event.usageMetadata ?? event.usage_metadata;
        if (usage?.totalTokenCount) tokens = usage.totalTokenCount;
        if (event.timestamp) ts = event.timestamp;
        if (event.id) eventId = event.id;
        const nextInvocationId = event.invocationId ?? event.invocation_id;
        if (nextInvocationId) invocationId = nextInvocationId;
        const blocks = [...currentBase, ...acc.blocks];
        setTurnsFor(sid, (t) => {
          const next = t.slice();
          const last = next[next.length - 1];
          const meta = {
            author: currentStreamAuthor || last?.meta?.author,
            tokens: tokens || last?.meta?.tokens,
            ts,
            eventId: eventId || last?.meta?.eventId,
            invocationId: invocationId || last?.meta?.invocationId,
          };
          if (
            last?.role === "assistant" &&
            (!last.meta?.author || last.meta.author === currentStreamAuthor)
          ) {
            next[next.length - 1] = {
              ...last,
              blocks,
              meta,
            };
          } else {
            next.push({ role: "assistant", blocks, meta });
          }
          return next;
        });
      }
      void refreshSessions(appName);
    } catch (e) {
      if (
        (e as Error)?.name !== "AbortError" &&
        !ctrl.signal.aborted &&
        viewSidRef.current === sid
      ) {
        setError(String(e));
      }
    } finally {
      if (streamAbortsRef.current.get(sid) === ctrl) streamAbortsRef.current.delete(sid);
      setStreaming(sid, false);
      finishStreamPresentation(sid);
      setActiveAgentBySession((m) => ({ ...m, [sid]: "" }));
      setExecPathBySession((m) => ({ ...m, [sid]: [] }));
    }
  }

  if (authError) {
    return (
      <div className="boot boot-error">
        <p>{authError}</p>
        <button type="button" onClick={resolveAuth}>
          重试
        </button>
      </div>
    );
  }
  if (authStatus === null) {
    return <div className="boot" />; // resolving identity
  }
  if (authStatus === "unauthenticated") {
    return <LoginPage branding={siteBranding} onUsername={onUsername} />;
  }
  if (!access) {
    return <div className="boot" />;
  }

  const canCreateAgents = access.capabilities.createAgents;
  const canManageAgents = access.capabilities.manageAgents;
  const visibleCreateView = canCreateAgents ? createView : null;
  const showAddMenu = canCreateAgents && addMenu;
  const showAddAgent = canCreateAgents && addAgent;
  const showManageAgents = manageAgents;
  const agentEntries = buildAgentEntries(apps, connections);
  const workspaceAgentEntries: AgentEntry[] = agentEntries
    .filter(
      (entry) =>
        entry.runtimeId &&
        (libraryRuntimeIds === null || libraryRuntimeIds.has(entry.runtimeId)),
    )
    .map((entry) => ({
      ...entry,
      canDelete: entry.runtimeId
        ? libraryRuntimePermissions[entry.runtimeId]?.canDelete === true
        : false,
    }));
  const orderedWorkspaceAgentEntries: AgentEntry[] = (() => {
    if (workspaceAgentEntries.length === 0) return workspaceAgentEntries;
    const orderIndex = new Map(workspaceAgentOrder.map((id, index) => [id, index]));
    return [...workspaceAgentEntries].sort((left, right) => {
      const leftIndex = orderIndex.get(left.id);
      const rightIndex = orderIndex.get(right.id);
      if (leftIndex != null && rightIndex != null) return leftIndex - rightIndex;
      if (leftIndex != null) return -1;
      if (rightIndex != null) return 1;
      return workspaceAgentEntries.indexOf(left) - workspaceAgentEntries.indexOf(right);
    });
  })();
  const labelOf = (id: string) => agentEntries.find((e) => e.id === id)?.label ?? id;
  // The runtime backing the current selection (if it's a cloud runtime app) —
  // drives the picker's side detail panel.
  const currentConn = connections.find(
    (c) => c.runtimeId && c.apps.some((a) => remoteAppId(c.id, a) === appName),
  );
  const currentRuntime =
    currentConn && currentConn.runtimeId
      ? {
          runtimeId: currentConn.runtimeId,
          name: currentConn.name,
          region: currentConn.region ?? "cn-beijing",
        }
      : undefined;

  const rateAssistantTurn = async (
    turn: Turn,
    rating: MessageFeedbackRating | null,
  ) => {
    const eventId = turn.meta?.eventId;
    const sid = sessionId;
    if (!eventId || !sid || !currentRuntime) return;
    const previousFeedback = turn.meta?.feedback;
    const optimisticFeedback = {
      ...previousFeedback,
      rating,
      syncStatus: "syncing" as const,
      updatedAt: Date.now() / 1000,
    };
    setTurnsFor(sid, (current) =>
      current.map((item) =>
        item.meta?.eventId === eventId
          ? { ...item, meta: { ...item.meta, feedback: optimisticFeedback } }
          : item,
      ),
    );
    setFeedbackPendingIds((current) => new Set(current).add(eventId));
    try {
      const feedback = await submitMessageFeedback({
        appName,
        userId,
        sessionId: sid,
        eventId,
        rating,
      });
      setTurnsFor(sid, (current) =>
        current.map((item) =>
          item.meta?.eventId === eventId
            ? { ...item, meta: { ...item.meta, feedback } }
            : item,
        ),
      );
      setSessions((current) =>
        current.map((item) =>
          item.id === sid
            ? {
                ...item,
                state: {
                  ...(item.state ?? {}),
                  [`veadk_feedback:${eventId}`]: feedback,
                },
              }
            : item,
        ),
      );
    } catch (feedbackError) {
      setTurnsFor(sid, (current) =>
        current.map((item) =>
          item.meta?.eventId === eventId
            ? { ...item, meta: { ...item.meta, feedback: previousFeedback } }
            : item,
        ),
      );
      if (viewSidRef.current === sid) {
        setError(
          feedbackError instanceof Error
            ? feedbackError.message
            : String(feedbackError),
        );
      }
    } finally {
      setFeedbackPendingIds((current) => {
        const next = new Set(current);
        next.delete(eventId);
        return next;
      });
    }
  };

  // Selecting an agent starts a fresh chat; any
  // background stream keeps persisting to its own (old) session.
  const selectAgent = (id: string) => {
    setConnections(loadConnections());
    viewSidRef.current = "";
    setSessionId("");
    setMyAgents(false);
    setAppName(id);
  };

  const openAgentCreateFromMyAgents = () => {
    if (!canCreateAgents) {
      setError("当前账号没有添加 Agent 的权限。");
      return;
    }
    setMyAgents(false);
    setManageAgents(false);
    setImportedDraft(null);
    setCreateView(null);
    setAddMenu(true);
    setError("");
  };

  const connectMyAgent = async (agent: MyAgentCardData) => {
    if (!agent.runtime) return;
    try {
      const agentId = await connectRuntime(
        agent.runtime.runtimeId,
        agent.name,
        agent.runtime.region,
        agent.runtime.currentVersion,
      );
      setConnections(loadConnections());
      setAgentDetailTarget(null);
      setMyAgents(false);
      setManageAgents(false);
      startNewChat();
      setAppName(agentId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const openMyAgentDetails = (agent: MyAgentCardData) => {
    if (!agent.runtime) return;
    setAgentDetailTarget(agent);
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId("");
    setMyAgents(false);
    setManageAgents(true);
    setError("");
  };

  const openMyAgentsPage = () => {
    if (sandboxSession) exitSandboxSession();
    viewSidRef.current = "";
    setSessionId("");
    setCreateView(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    setAgentDetailTarget(null);
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId("");
    setMyAgents(true);
    setError("");
  };

  const talkToWorkspaceAgent = (id: string) => {
    setFeedbackCaseReturnAgentId("");
    setFeedbackTargetEventId("");
    selectAgent(id);
  };

  const selectWorkspaceAgentFromNavbar = (id: string) => {
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId(id);
    setFocusedWorkspaceAgentSection("basic");
    selectAgent(id);
  };

  const detailAgentEntry: AgentEntry | null = agentDetailTarget?.runtime
    ? {
        id: `detail:${agentDetailTarget.runtime.runtimeId}`,
        label: agentDetailTarget.name,
        app: agentDetailTarget.name,
        remote: true,
        runtimeId: agentDetailTarget.runtime.runtimeId,
        region: agentDetailTarget.runtime.region,
        currentVersion: agentDetailTarget.runtime.currentVersion,
        canDelete: agentDetailTarget.runtime.canDelete,
      }
    : null;

  return (
    <div className="layout">
      <Sidebar
        branding={siteBranding}
        access={access}
        features={features}
        sessions={sessions}
        currentSessionId={sessionId}
        streamingSids={streamingSids}
        onNewChat={openNewChat}
        onSearch={() => {
          if (sandboxSession) exitSandboxSession();
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setMyAgents(false);
          setSearchView(true);
          setError("");
        }}
        onQuickCreate={() => {
          if (!canCreateAgents) {
            setError("当前账号没有添加 Agent 的权限。");
            return;
          }
          if (sandboxSession) exitSandboxSession();
          // "添加 Agent" — open the two-card chooser. Drop any selected session.
          viewSidRef.current = "";
          setSessionId("");
          setSkillCenter(false);
          setAddAgent(false);
          setSearchView(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setMyAgents(false);
          setCreateView(null);
          setImportedDraft(null);
          setAddMenu(true);
          setError("");
        }}
        onSkillCenter={() => {
          if (sandboxSession) exitSandboxSession();
          setCreateView(null);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setMyAgents(false);
          setSkillCenter(true);
          setError("");
        }}
        onAddAgent={() => {
          if (!canCreateAgents) {
            setError("当前账号没有添加 Agent 的权限。");
            return;
          }
          if (sandboxSession) exitSandboxSession();
          viewSidRef.current = "";
          setCreateView(null);
          setSkillCenter(false);
          setSearchView(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setMyAgents(false);
          setSessionId("");
          setAddMenu(false);
          setAddAgent(true);
          setError("");
        }}
        onMyAgents={openMyAgentsPage}
        onPickSession={(id) => {
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setMyAgents(false);
          setError("");
          pickSession(id);
        }}
        onDeleteSession={removeSession}
        userInfo={userInfo}
        version={version}
        onLogout={onLogout}
      />

      {(() => {
        const composer = (
          <div
            className={`composer-slot${sandboxSession ? " sandbox-composer-wrap" : ""}`}
          >
            {sandboxSession && (
              <SandboxSessionWarning onExit={startNewChat} />
            )}
            <Composer
              sessionId={sandboxSession ? sandboxSession.id : sessionId}
              sessionInitializing={!sandboxSession && initializingSession}
              appName={appName}
              agentName={
                sandboxSession
                  ? "AgentKit 沙箱"
                  : appName
                    ? labelOf(appName)
                    : "Agent"
              }
              value={input}
              onChange={setInput}
              onSubmit={() => {
                if (!sandboxSession && newChatMode === "skill-create") {
                  const prompt = input.trim();
                  if (!prompt || skillCreating) return;
                  const provisionalJob: SkillCreationJob = {
                    id: `pending-${Date.now()}`,
                    prompt,
                    status: "provisioning",
                    candidates: SKILL_MODELS.map((model, index) => ({
                      id: `pending-${index}`,
                      model,
                      modelLabel: model,
                      status: "queued",
                      stage: "provisioning",
                      files: [],
                      activities: [{
                        id: "provisioning",
                        kind: "status",
                        text: "正在拉起 Sandbox",
                        status: "running",
                      }],
                    })),
                  };
                  setSkillCreating(true);
                  const creationRun = ++skillCreationRunRef.current;
                  setError("");
                  setSkillJob(provisionalJob);
                  setInput("");
                  void createSkillJob(prompt, (job) => {
                    if (skillCreationRunRef.current === creationRun) {
                      setSkillJob(job);
                    }
                  })
                    .then((job) => {
                      if (skillCreationRunRef.current === creationRun) {
                        setSkillJob(job);
                      }
                    })
                    .catch((cause) => {
                      if (skillCreationRunRef.current === creationRun) {
                        setSkillJob(null);
                        setInput(prompt);
                        setError(cause instanceof Error ? cause.message : String(cause));
                      }
                    })
                    .finally(() => {
                      if (skillCreationRunRef.current === creationRun) {
                        setSkillCreating(false);
                      }
                    });
                  return;
                }
                const text = input;
                setInput("");
                if (sandboxSession) {
                  void sendSandboxMessage(text);
                  return;
                }
                const atts = attachments;
                const selectedInvocation = invocation;
                setAttachments([]);
                setInvocation(emptyInvocation());
                send(text, atts, selectedInvocation);
                releaseAttachmentPreviews(atts);
              }}
              disabled={
                sandboxSession
                  ? false
                  : !userId ||
                    newChatMode === "temporary" ||
                    (newChatMode === "agent" && !appName)
              }
              busy={
                sandboxSession
                  ? sandboxBusy
                  : newChatMode === "skill-create"
                    ? skillCreating
                    : conversationBusy
              }
              showMeta={turns.length > 0 && !sandboxSession}
              attachments={sandboxSession ? [] : attachments}
              skills={sandboxSession ? [] : availableSkills}
              agents={sandboxSession ? [] : availableAgents}
              invocation={sandboxSession ? emptyInvocation() : invocation}
              capabilitiesLoading={!sandboxSession && capabilitiesLoading}
              allowAttachments={!sandboxSession}
              onInvocationChange={setInvocation}
              onAddFiles={addFiles}
              onRemoveAttachment={removeDraftAttachment}
              newChatMode={sandboxSession ? "agent" : newChatMode}
              newChatLayout={!sandboxSession && turns.length === 0 && skillJob === null}
              showModeSelector={false}
              temporaryEnabled={newChatCapabilities.temporaryEnabled}
              skillCreateEnabled={newChatCapabilities.skillCreateEnabled}
              onModeChange={(mode) => {
                if (
                  (mode === "temporary" && !newChatCapabilities.temporaryEnabled) ||
                  (mode === "skill-create" && !newChatCapabilities.skillCreateEnabled)
                ) return;
                if (mode === "temporary") {
                  setNewChatMode(mode);
                  openSandboxLaunch();
                  return;
                }
                setNewChatMode(mode);
                setError("");
                if (mode === "skill-create") {
                  setInvocation(emptyInvocation());
                  const abandonedSession =
                    sessionId && persistentTurns.length === 0 && attachments.length > 0
                      ? sessionId
                      : "";
                  discardDraftAttachments(attachments);
                  setAttachments([]);
                  if (abandonedSession) {
                    viewSidRef.current = "";
                    setSessionId("");
                    void abandonDraftSession(abandonedSession);
                  }
                }
              }}
            />
          </div>
        );
        return (
          <section className="main-shell">
            <Navbar
              appName={appName}
              onAppChange={showManageAgents ? selectWorkspaceAgentFromNavbar : selectAgent}
              agentLabel={labelOf}
              agentsSource={agentsSource}
              localApps={apps}
              currentRuntime={currentRuntime}
              runtimeScope={access.capabilities.runtimeScope}
              onBrowseAgents={openMyAgentsPage}
              title={
                sandboxSession
                  ? "Codex 智能体"
                  : myAgents
                  ? "智能体"
                  : showAddMenu
                  ? "添加 Agent"
                  : showAddAgent
                    ? "添加 AgentKit 智能体"
                    : showManageAgents
                      ? agentDetailTarget
                        ? agentDetailTarget.name
                        : focusedWorkspaceAgentId
                        ? labelOf(focusedWorkspaceAgentId)
                        : "智能体详情"
                      : undefined
              }
              titleLeading={
                turns.length > 0 &&
                !sandboxSession &&
                newChatMode === "agent" &&
                !showAddMenu &&
                !showAddAgent &&
                !skillCenter &&
                !searchView &&
                !showManageAgents &&
                !myAgents &&
                visibleCreateView === null &&
                appName ? (
                  <button
                    ref={agentInfoTriggerRef}
                    type="button"
                    className="agent-info-trigger"
                    aria-label="查看 Agent 信息"
                    title="Agent 信息"
                    aria-expanded={agentInfoOpen}
                    onClick={() => setAgentInfoOpen(true)}
                  >
                    <AgentIdentityIcon />
                  </button>
                ) : undefined
              }
              crumbs={
                skillCenter
                  ? [{ label: "技能中心" }, { label: "AgentKit Skill 空间" }]
                  : searchView || showAddAgent || showAddMenu || !visibleCreateView
                  ? undefined
                  : visibleCreateView === "menu"
                    ? [
                        {
                          label: CREATE_ROOT,
                          onClick: () => {
                            setCreateView(null);
                            setImportedDraft(null);
                            setAddMenu(true);
                          },
                        },
                        { label: "从 0 快速创建" },
                      ]
                    : [
                        { label: "从 0 快速创建", onClick: () => setConfirmLeave(true) },
                        { label: MODE_LABEL[visibleCreateView] },
                      ]
              }
              rightContent={
                <>
                  {access.role === "admin" && <StudioUpdateControl />}
                  <DeploymentTaskStatus
                    tasks={canCreateAgents ? deploymentTasks : []}
                    onCancel={cancelDeploymentTask}
                  />
                </>
              }
            />
            <main className={`main${sandboxSession ? " is-sandbox-session" : ""}`}>
            {error && <div className="error">{error}</div>}
            {loadingSession && (
              <div className="session-loading">
                <Loader2 className="icon spin" /> 加载会话…
              </div>
            )}
            {feedbackCaseReturnAgentId &&
              !showManageAgents &&
              !showAddMenu &&
              !showAddAgent &&
              !searchView &&
              !skillCenter &&
              visibleCreateView === null && (
                <div className="case-return-bar">
                  <button type="button" onClick={returnToFeedbackCases}>
                    <ArrowLeft aria-hidden />
                    <span>返回评测案例</span>
                  </button>
                </div>
              )}

            {myAgents ? (
              <MyAgents
                onCreateAgent={openAgentCreateFromMyAgents}
                onCreateCodexAgent={openSandboxLaunch}
                onUseAgent={connectMyAgent}
                onViewAgentDetails={openMyAgentDetails}
                connectedRuntimeId={currentRuntime?.runtimeId}
              />
            ) : showManageAgents ? (
              <AgentWorkspace
                key={detailAgentEntry?.id ?? "workspace"}
                agents={detailAgentEntry ? [detailAgentEntry] : orderedWorkspaceAgentEntries}
                drafts={savedAgentDrafts}
                agentOrder={workspaceAgentOrder}
                selectedAgentId={appName}
                agentInfo={agentInfo}
                agentInfoAgentId={appName}
                loadingAgentInfo={capabilitiesLoading}
                canCreate={canCreateAgents}
                canUpdate={canCreateAgents || canManageAgents}
                loadingAgents={agentLibraryLoading}
                agentsError={agentLibraryError}
                deploymentTasks={deploymentTasks}
                focusedDeploymentTaskId={focusedDeploymentTaskId}
                focusedAgentId={detailAgentEntry?.id ?? focusedWorkspaceAgentId}
                focusedAgentSection={focusedWorkspaceAgentSection}
                focusedCaseKind={focusedWorkspaceCaseKind}
                detailOnly={!!detailAgentEntry || !!focusedDeploymentTaskId}
                onRetryAgents={() => void refreshAgentLibrary()}
                onAgentOrderChange={saveWorkspaceAgentOrder}
                onDeleteAgents={deleteWorkspaceAgents}
                onDeleteDrafts={deleteWorkspaceDrafts}
                onSelectAgent={selectAgent}
                onTalkAgent={talkToWorkspaceAgent}
                onOpenFeedbackCase={(item) => void openFeedbackCaseInStudio(item)}
                onFeedbackCasesDeleted={clearDeletedFeedbackCases}
                onCreateAgent={() => {
                  if (!canCreateAgents) {
                    setError("当前账号没有添加 Agent 的权限。");
                    return;
                  }
                  setManageAgents(false);
                  setAddMenu(true);
                  setCreateView(null);
                  setImportedDraft(null);
                  setRuntimeUpdateTarget(null);
                  setEditingDraftId("");
                  editingDraftBaselineRef.current = null;
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setError("");
                }}
                onUpdateAgent={(nextDraft) => {
                  if (!canManageAgents && !canCreateAgents) {
                    setError("当前账号没有管理 Agent 的权限。");
                    return;
                  }
                  if (!currentConn?.runtimeId) {
                    setError("仅支持更新已部署的云端智能体。");
                    return;
                  }
                  setManageAgents(false);
                  setImportedDraft(nextDraft);
                  const nextDraftId = `runtime-${currentConn.runtimeId}`;
                  setEditingDraftId(nextDraftId);
                  editingDraftBaselineRef.current =
                    savedAgentDrafts.find((item) => item.id === nextDraftId) ?? null;
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setRuntimeUpdateTarget({
                    runtimeId: currentConn.runtimeId,
                    name: currentConn.name,
                    region: currentConn.region ?? "cn-beijing",
                    currentVersion: currentConn.currentVersion,
                  });
                  setCreateView("custom");
                  setError("");
                }}
                onEditDraft={(item) => {
                  setManageAgents(false);
                  setImportedDraft(item.draft);
                  setEditingDraftId(item.id);
                  editingDraftBaselineRef.current = item;
                  setRuntimeUpdateTarget(item.deploymentTarget ?? null);
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setCreateView("custom");
                  setError("");
                }}
              />
            ) : showAddMenu ? (
              <StackCards
                title="您想以哪种方式添加 Agent 来运行？"
                sub="选择最适合你的方式，下一步即可开始"
                cards={[
                  {
                    key: "scratch",
                    icon: ScratchIcon,
                    title: "从 0 快速创建",
                    desc: "用智能 / 自定义 / 模板 / 工作流的方式从零创建一个 Agent。",
                    onClick: () => {
                      setAddMenu(false);
                      setImportedDraft(null);
                      setCreateView("menu");
                    },
                  },
                  {
                    key: "package",
                    icon: FileArchive,
                    title: "从代码包添加和部署",
                    desc: "上传 Agent 项目压缩包，查看代码并直接部署到 AgentKit Runtime。",
                    onClick: () => {
                      setAddMenu(false);
                      setImportedDraft(null);
                      setCreateView("package");
                    },
                  },
                ]}
              />
            ) : searchView ? (
              <SearchView
                userId={userId}
                appId={appName}
                agentInfo={agentInfo}
                capabilitiesLoading={capabilitiesLoading}
                agentLabel={labelOf}
                onOpenSession={openFromSearch}
              />
            ) : showAddAgent ? (
              <AddAgentKitView
                onAdded={(id) => {
                  setConnections(loadConnections());
                  setAddAgent(false);
                  setAppName(id);
                }}
                onCancel={() => setAddAgent(false)}
              />
            ) : skillCenter ? (
              <SkillCenterView />
            ) : visibleCreateView !== null && !hasCreds ? (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 12,
                  height: "100%",
                  padding: 24,
                  textAlign: "center",
                  color: "var(--text-secondary, #6b7280)",
                }}
              >
                <div style={{ fontSize: 18, fontWeight: 600 }}>
                  需要配置火山引擎 AK/SK
                </div>
                <div style={{ maxWidth: 420, lineHeight: 1.6 }}>
                  智能体工作台需要 Volcengine 凭据才能使用。请在运行环境中设置
                  {" "}
                  <code>VOLCENGINE_ACCESS_KEY</code> 与{" "}
                  <code>VOLCENGINE_SECRET_KEY</code> 后重试。
                </div>
              </div>
            ) : visibleCreateView === "menu" ? (
              <QuickCreate
                onSelect={(k) => {
                  setImportedDraft(null);
                  setRuntimeUpdateTarget(null);
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setEditingDraftId(
                    k === "custom" ? `draft-${Date.now().toString(36)}` : "",
                  );
                  editingDraftBaselineRef.current = null;
                  setCreateView(k);
                }}
                onImport={(d) => {
                  setImportedDraft(d);
                  setRuntimeUpdateTarget(null);
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setEditingDraftId(`draft-${Date.now().toString(36)}`);
                  editingDraftBaselineRef.current = null;
                  setCreateView("custom");
                }}
              />
            ) : visibleCreateView === "intelligent" ? (
              <IntelligentCreate
                userId={userId}
                onBack={() => setCreateView("menu")}
                onCreate={onCreate}
                onAgentAdded={onAgentAdded}
                onDeploymentTaskChange={updateDeploymentTask}
              />
            ) : visibleCreateView === "custom" ? (
              <CustomCreate
                key={editingDraftId || "custom"}
                initialDraft={importedDraft ?? undefined}
                onBack={() => setCreateView("menu")}
                onCreate={onCreate}
                onAgentAdded={onAgentAdded}
                features={features}
                onDeploymentTaskChange={updateDeploymentTask}
                deploymentTarget={runtimeUpdateTarget ?? undefined}
                onDraftChange={(draft, dirty) => {
                  if (!editingDraftId) return;
                  if (dirty) {
                    saveWorkspaceDraft(
                      editingDraftId,
                      draft,
                      runtimeUpdateTarget ?? undefined,
                    );
                  } else {
                    restoreWorkspaceDraftBaseline(editingDraftId);
                  }
                }}
                onDiscard={editingDraftId ? () => {
                  restoreWorkspaceDraftBaseline(editingDraftId);
                  setEditingDraftId("");
                  editingDraftBaselineRef.current = null;
                  setImportedDraft(null);
                  setRuntimeUpdateTarget(null);
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId(appName);
                  setCreateView(null);
                  setAddMenu(false);
                  setManageAgents(true);
                  setError("");
                } : undefined}
                onDeploymentStarted={openDeploymentDetail}
                onDeploymentComplete={finishDeployment}
              />
            ) : visibleCreateView === "template" ? (
              <TemplateCreate onBack={() => setCreateView("menu")} onCreate={onCreate} />
            ) : visibleCreateView === "workflow" ? (
              <WorkflowCreate onBack={() => setCreateView("menu")} onCreate={onCreate} />
            ) : visibleCreateView === "package" ? (
              <CodePackageCreate
                onBack={() => {
                  setCreateView(null);
                  setAddMenu(true);
                }}
                onAgentAdded={onAgentAdded}
                onDeploymentTaskChange={updateDeploymentTask}
              />
            ) : turns.length === 0 && skillJob ? (
              <SkillCreateWorkspace initialJob={skillJob} />
            ) : turns.length === 0 ? (
              <div className="welcome">
                <TextShimmer as="h1" className="welcome-title" duration={4.8} spread={22}>
                  {sandboxSession
                    ? "让灵感在临时空间里自由生长"
                    : newChatMode === "skill-create"
                      ? "想创建一个什么 Skill？"
                      : greeting}
                </TextShimmer>
                {composer}
              </div>
            ) : (
              <>
                <div
                  className={`transcript${activeConversationPresenting ? " is-streaming" : ""}`}
                  ref={scrollRef}
                  onScroll={onConversationScroll}
                  onWheel={onConversationWheel}
                  onTouchMove={onConversationTouchMove}
                >
                  {turns.map((turn, i) => {
            const isLast = i === turns.length - 1;
            if (turn.role === "user") {
              const text = turn.blocks.map((b) => (b.kind === "text" ? b.text : "")).join("");
              const atts = turn.blocks.flatMap((b) =>
                b.kind === "attachment" ? b.files : [],
              );
              const turnInvocation = turn.blocks.find((b) => b.kind === "invocation");
              return (
                <motion.div
                  key={i}
                  className="turn turn--user"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                >
                  {turnInvocation?.kind === "invocation" && (
                    <InvocationChips value={turnInvocation.value} />
                  )}
                  {atts.length > 0 && (
                    <MediaGroup appName={appName} items={atts} />
                  )}
                  {text && (
                    <div className="bubble">
                      <Markdown text={text} />
                    </div>
                  )}
                  <div className="turn-actions turn-actions--right">
                    {turn.meta?.ts && <span className="meta-text">{fmtTime(turn.meta.ts)}</span>}
                    <CopyButton text={text} />
                  </div>
                </motion.div>
              );
            }
            const agentAuthor = turn.meta?.author ?? "";
            const agentNode = agentAuthor && rootCapabilityNode
              ? findAgentNode(rootCapabilityNode, agentAuthor)
              : undefined;
            const isSubAgent = Boolean(
              agentAuthor &&
              rootAgentNames.length > 0 &&
              !rootAgentNames.includes(agentAuthor),
            );
            const agentDisplayName = agentNode?.name || agentAuthor;
            const agentDescription = agentNode?.description ||
              (isSubAgent ? "正在执行主 Agent 移交的任务。" : "");
            if (
              turn.blocks.length > 0 &&
              turn.blocks.every((block) => block.kind === "agent-transfer")
            ) return null;
            const pending = turn.blocks.length === 0;
            const feedbackRating = turn.meta?.feedback?.rating ?? null;
            const feedbackEventId = turn.meta?.eventId ?? "";
            const feedbackPending = feedbackPendingIds.has(feedbackEventId);
            const canRate = Boolean(
              currentRuntime && feedbackEventId && turnText(turn),
            );
            return (
              <motion.div
                key={i}
                ref={(node) => {
                  if (!feedbackEventId) return;
                  if (node) {
                    turnNodeRefs.current.set(feedbackEventId, node);
                  } else {
                    turnNodeRefs.current.delete(feedbackEventId);
                  }
                }}
                className={[
                  "turn turn--assistant",
                  isSubAgent ? "turn--subagent" : "",
                  feedbackTargetEventId === feedbackEventId ? "is-feedback-target" : "",
                ].filter(Boolean).join(" ")}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                {isSubAgent && (
                  <>
                    <div className="subagent-run-label">
                      <span className="subagent-run-handoff">
                        <CornerDownRight />
                        <span>智能体移交</span>
                      </span>
                      <span className="subagent-run-title">{agentDisplayName}</span>
                    </div>
                    <p className="subagent-run-description" title={agentDescription}>
                      {agentDescription}
                    </p>
                  </>
                )}
                {pending ? (
                  isLast && activeConversationBusy ? <ThinkingPlaceholder /> : null
                ) : (
                  <>
                    <Blocks
                      appName={appName}
                      blocks={turn.blocks}
                      streaming={isLast && (activeConversationBusy || presentingStream)}
                      onStreamFrame={isLast ? followConversationStreamFrame : undefined}
                      onAction={onAction}
                      onAuth={onAuth}
                    />
                    {/* Finalized turn that produced no visible answer (e.g. only
                        thinking + an empty A2UI surface) — show a fallback note. */}
                    {!(isLast && activeConversationBusy) && !turnHasVisibleContent(turn) && (
                      <div className="turn-empty">本次没有返回可显示的内容。</div>
                    )}
                    {/* Hide the actions/timestamp row while this turn is still
                        thinking/streaming or waiting on an OAuth card; reveal it
                        only once the reply is done. */}
                    {!(isLast && activeConversationBusy) && !turnAwaitingAuth(turn) && (
                      <div className="turn-meta">
                        <div className="turn-actions">
                          {canRate && (
                            <>
                              <button
                                type="button"
                                className={`icon-btn feedback-btn${
                                  feedbackRating === "good"
                                    ? " feedback-btn--good"
                                    : ""
                                }`}
                                aria-label="赞"
                                aria-pressed={feedbackRating === "good"}
                                aria-busy={feedbackPending}
                                title={feedbackRating === "good" ? "取消点赞" : "赞"}
                                disabled={feedbackPending}
                                onClick={() => void rateAssistantTurn(
                                  turn,
                                  feedbackRating === "good" ? null : "good",
                                )}
                              >
                                <FeedbackUpIcon
                                  className="icon"
                                  filled={feedbackRating === "good"}
                                />
                              </button>
                              <button
                                type="button"
                                className={`icon-btn feedback-btn${
                                  feedbackRating === "bad"
                                    ? " feedback-btn--bad"
                                    : ""
                                }`}
                                aria-label="踩"
                                aria-pressed={feedbackRating === "bad"}
                                aria-busy={feedbackPending}
                                title={feedbackRating === "bad" ? "取消点踩" : "踩"}
                                disabled={feedbackPending}
                                onClick={() => void rateAssistantTurn(
                                  turn,
                                  feedbackRating === "bad" ? null : "bad",
                                )}
                              >
                                <FeedbackDownIcon
                                  className="icon"
                                  filled={feedbackRating === "bad"}
                                />
                              </button>
                            </>
                          )}
                          {!sandboxSession && (
                            <button
                              className="icon-btn"
                              title="Tracing 火焰图"
                              onClick={() => setTraceOpen(true)}
                            >
                              <TraceIcon />
                            </button>
                          )}
                          <CopyButton text={turnText(turn)} />
                        </div>
                        {turn.meta && <span className="meta-text">{fmtMeta(turn.meta)}</span>}
                      </div>
                    )}
                  </>
                )}
              </motion.div>
            );
          })}
                </div>
                {!sandboxSession && (
                  <AgentInfoPanel
                    appName={appName}
                    info={agentInfo}
                    loading={capabilitiesLoading}
                    activeAgent={activeAgent}
                    seenAgents={seenAgents}
                    execPath={execPath}
                    capabilities={sessionCapabilities}
                    capabilityLoading={sessionCapabilitiesLoading}
                    capabilityMutating={sessionCapabilityMutating}
                    builtinTools={sessionBuiltinTools}
                    onAddCapability={addCapability}
                    onRemoveCapability={(id) => void removeCapability(id)}
                  />
                )}
                <div className="conversation-composer-slot">
                  {composer}
                </div>
              </>
            )}
            </main>
          </section>
        );
      })()}

      {traceOpen && sessionId && (
        <TraceDrawer
          appName={appName}
          sessionId={sessionId}
          onClose={() => setTraceOpen(false)}
        />
      )}

      {agentInfoOpen && turns.length > 0 && (
        <AgentInfoDrawer
          appName={appName}
          info={agentInfo}
          loading={capabilitiesLoading}
          activeAgent={activeAgent}
          seenAgents={seenAgents}
          execPath={execPath}
          capabilities={sessionCapabilities}
          capabilityLoading={sessionCapabilitiesLoading}
          capabilityMutating={sessionCapabilityMutating}
          builtinTools={sessionBuiltinTools}
          onAddCapability={addCapability}
          onRemoveCapability={(id) => void removeCapability(id)}
          onClose={closeAgentInfo}
          returnFocusRef={agentInfoTriggerRef}
        />
      )}

      <SandboxLaunchDialog
        open={sandboxLaunchOpen}
        state={sandboxLaunchState}
        error={sandboxLaunchError}
        onCancel={cancelSandboxLaunch}
        onConfirm={() => void launchSandboxSession()}
      />

      {toast && (
        <div className="app-toast" role="status" aria-live="polite">
          {toast}
        </div>
      )}

      <AuthExpiredDialog
        open={authExpired}
        checking={authRecoveryChecking}
        error={authRecoveryError}
        onLogin={() => void recoverAuthentication()}
      />

      {confirmLeave && (
        <div className="confirm-scrim" onClick={() => setConfirmLeave(false)}>
          <div className="confirm-box" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-title">返回创建首页？</div>
            <div className="confirm-text">返回后当前填写的内容将会丢失，确定要返回吗？</div>
            <div className="confirm-actions">
              <button className="confirm-btn" onClick={() => setConfirmLeave(false)}>
                取消
              </button>
              <button
                className="confirm-btn confirm-btn--danger"
                onClick={() => {
                  setImportedDraft(null);
                  setCreateView("menu");
                  setConfirmLeave(false);
                }}
              >
                确定返回
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
