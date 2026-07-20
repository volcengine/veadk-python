import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  CircleX,
  Copy,
  ListTodo,
  Loader2,
} from "lucide-react";
import { motion } from "motion/react";
import {
  cancelAgentkitDeployment,
  createSession,
  DEFAULT_SITE_BRANDING,
  deleteMedia,
  deleteSessionMedia,
  deleteSession,
  getAgentInfo,
  getSession,
  listApps,
  listSessions,
  runSSE,
  uploadMedia,
  getUiConfig,
  type AdkEvent,
  type AgentInfo,
  type AgentNode,
  type AgentTarget,
  type AdkSession,
  type Attachment,
  type FrontendInvocation,
  type ManagedRuntime,
  type SiteBranding,
  type UiFeatures,
} from "./adk/client";
import { applyEvent, emptyAcc, eventsToTurns, type Block, type Turn } from "./blocks";
import { Sidebar } from "./ui/Sidebar";
import { Navbar } from "./ui/Navbar";
import { AgentTopology } from "./ui/AgentTopology";
import { SkillCenterView } from "./ui/SkillCenter";
import { AddAgentKitView } from "./ui/AddAgentKit";
import { ManageAgentsView } from "./ui/ManageAgents";
import { SearchView } from "./ui/Search";
import {
  buildAgentEntries,
  connectRuntime,
  loadConnections,
  registerConnections,
  remoteAppId,
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
import type { AgentDraft } from "./create/types";
import type { DeploymentTaskUpdate } from "./ui/ProjectPreview";
import { DeploymentErrorMessage } from "./ui/DeploymentErrorMessage";
import defaultSiteLogo from "./assets/volcengine.svg";

// Breadcrumb root label for the create flow and the per-mode leaf labels.
const CREATE_ROOT = "创建 Agent";
const MODE_LABEL: Record<QuickCreateKind, string> = {
  intelligent: "智能模式",
  custom: "自定义",
  template: "从模板新建",
  workflow: "工作流",
};

type CreateView = "menu" | QuickCreateKind | null;

// Persist the last view so a page refresh restores where the user was.
const LS = { app: "veadk.appName", view: "veadk.view", session: "veadk.sessionId" } as const;
const EMPTY_STRING_SET: Set<string> = new Set<string>();
const EMPTY_STRING_ARR: string[] = [];

function emptyInvocation(): FrontendInvocation {
  return { skills: [] };
}

function findAgentNode(node: AgentNode, name: string): AgentNode | undefined {
  if (node.name === name) return node;
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
import { Markdown } from "./ui/Markdown";
import { useStickToBottom } from "./ui/useStickToBottom";
import {
  clearLocalUser,
  logout,
  resolveIdentity,
  setLocalUser,
  type AuthStatus,
} from "./adk/identity";
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
  // Turns are stored PER SESSION, so a background stream can keep updating its
  // own session's transcript while you view another one — no cross-session
  // leak, no data loss, and no re-fetch when you switch back (its entry is
  // already live). The view shows the active session's entry.
  const [turnsBySession, setTurnsBySession] = useState<Record<string, Turn[]>>(
    {},
  );
  const turns = turnsBySession[sessionId] ?? [];
  const setTurnsFor = (
    sid: string,
    updater: Turn[] | ((prev: Turn[]) => Turn[]),
  ) =>
    setTurnsBySession((m) => ({
      ...m,
      [sid]: typeof updater === "function" ? updater(m[sid] ?? []) : updater,
    }));
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [invocation, setInvocation] = useState<FrontendInvocation>(emptyInvocation);
  const [agentInfo, setAgentInfo] = useState<AgentInfo | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);
  const removedAttachmentIdsRef = useRef<Set<string>>(new Set());
  // Streaming state is PER SESSION so multiple sessions can stream at once
  // (each /run_sse is an independent request). `streamingSids` = which sessions
  // are currently streaming; the AbortControllers let unmount / delete cancel
  // a specific session's stream. A normal switch does NOT abort — the stream
  // keeps running and persisting.
  const [streamingSids, setStreamingSids] = useState<Set<string>>(
    () => new Set(),
  );
  const streamAbortsRef = useRef<Map<string, AbortController>>(new Map());
  const setStreaming = (sid: string, on: boolean) =>
    setStreamingSids((s) => {
      const n = new Set(s);
      if (on) n.add(sid);
      else n.delete(sid);
      return n;
    });
  // The session currently on screen — used to gate the single global error
  // banner (per-session transcripts/topology don't need it).
  const viewSidRef = useRef("");
  const [error, setError] = useState("");
  const [traceOpen, setTraceOpen] = useState(false);
  const [greeting, setGreeting] = useState(pickGreeting);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [userId, setUserId] = useState("");
  const [userInfo, setUserInfo] = useState<Record<string, unknown> | undefined>();
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
  const activeAgent = activeAgentBySession[sessionId] ?? "";
  const seenAgents = seenAgentsBySession[sessionId] ?? EMPTY_STRING_SET;
  const execPath = execPathBySession[sessionId] ?? EMPTY_STRING_ARR;
  const rootCapabilityNode = agentInfo?.graph;
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
  const [searchView, setSearchView] = useState(false);
  // The "管理 Agent" view: lists/deletes the current user's AgentKit runtimes.
  const [manageAgents, setManageAgents] = useState(false);
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
  // Shown when the user clicks the breadcrumb root to leave a create mode;
  // warns that the in-progress draft will be discarded.
  const [confirmLeave, setConfirmLeave] = useState(false);
  // Restore the previously-open session only once, after apps/user resolve.
  const restoredRef = useRef(false);

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
    setCreateView(null);
    setAppName(agentId);
    // startNewChat will be called automatically by the appName change effect
  }
  const { ref: scrollRef, onScroll } = useStickToBottom<HTMLDivElement>(turns);

  // Resolve SSO identity first; it provides the ADK user_id.
  useEffect(() => {
    resolveIdentity().then((id) => {
      setUserId(id.userId);
      setUserInfo(id.info);
      setLocalMode(!!id.local);
      setAuthStatus(id.status);
    });
  }, []);

  // Load per-module feature gates; studio mode lands on the add-agent page.
  useEffect(() => {
    getUiConfig().then((cfg) => {
      setFeatures(cfg.features);
      setAgentsSource(cfg.agentsSource);
      setSiteBranding(cfg.branding);
      if (cfg.defaultView === "addAgent") {
        setCreateView(null);
        setSkillCenter(false);
        setSearchView(false);
        setManageAgents(false);
        setAddAgent(false);
        setAddMenu(true);
      }
    });
  }, []);

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
    fetch("/web/runtime-config")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) setHasCreds(!!d.credentials);
      })
      .catch(() => {});
  }, []);

  function onUsername(name: string) {
    setLocalUser(name);
    // A completed login is a fresh entry into the app. Do not reveal a create
    // or management view that was persisted before the login page appeared.
    restoredRef.current = true;
    setCreateView(null);
    setImportedDraft(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    startNewChat();
    setUserId(name);
    setUserInfo({ name });
    setLocalMode(true);
    setAuthStatus("authenticated");
  }

  function onLogout() {
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
        // Cloud mode: nothing is selected by default — the user picks a runtime
        // each session (the sidebar shows the red "请选择 Agent" prompt until then).
        if (agentsSource === "cloud") {
          setAppName("");
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
  }, [authStatus, agentsSource]);

  // Persist the current view/agent/session so a refresh restores them.
  useEffect(() => {
    if (appName) localStorage.setItem(LS.app, appName);
  }, [appName]);
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
    localStorage.setItem(LS.view, createView ?? "chat");
  }, [createView]);
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

  // Reset to a fresh, not-yet-created chat. The backend session is created
  // lazily on the first message (see send()). A background stream (if any)
  // keeps running and persisting — its writes are suppressed here by viewSidRef.
  function startNewChat() {
    setError("");
    setGreeting(pickGreeting());
    const abandonedSession = sessionId && turns.length === 0 && attachments.length > 0
      ? sessionId
      : "";
    viewSidRef.current = "";
    setSessionId("");
    setInvocation(emptyInvocation());
    discardDraftAttachments(attachments);
    setAttachments([]);
    if (abandonedSession) void abandonDraftSession(abandonedSession);
  }

  async function removeSession(id: string) {
    try {
      // Deleting a session with a running stream — abort just that one.
      streamAbortsRef.current.get(id)?.abort();
      await deleteSessionMedia(appName, userId, id);
      await deleteSession(appName, userId, id);
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
    if (id === sessionId) return;
    viewSidRef.current = id;
    setError("");
    setInvocation(emptyInvocation());
    setSessionId(id);
    // Already have this session's turns (it's cached, or streaming in the
    // background)? Show them instantly and let any live stream keep updating —
    // no re-fetch, no "loading" flash, streaming stays visible.
    if (turnsBySession[id] !== undefined) return;
    setLoadingSession(true);
    try {
      const s = await getSession(appName, userId, id);
      setTurnsFor(id, eventsToTurns(s.events ?? []));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingSession(false);
    }
  }

  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId;
    if (!creatingSessionRef.current) {
      creatingSessionRef.current = createSession(appName, userId);
    }
    const pending = creatingSessionRef.current;
    try {
      const sid = await pending;
      setSessionId(sid);
      const now = Date.now() / 1000;
      const optimistic: AdkSession = { id: sid, lastUpdateTime: now, events: [] };
      setSessions((prev) => [optimistic, ...prev.filter((s) => s.id !== sid)]);
      return sid;
    } finally {
      if (creatingSessionRef.current === pending) creatingSessionRef.current = null;
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
    if ((!text.trim() && atts.length === 0) || busy || !appName || !userId) return;
    setError("");

    let sid: string;
    try {
      sid = await ensureSession();
    } catch (e) {
      setError(String(e));
      return;
    }

    // Register this session's own stream (concurrent with other sessions').
    const ctrl = new AbortController();
    streamAbortsRef.current.set(sid, ctrl);
    setStreaming(sid, true);
    viewSidRef.current = sid;

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
    setTurnsFor(sid, (t) => [
      ...t,
      { role: "user", blocks: userBlocks, meta: { ts: Date.now() / 1000 } },
      { role: "assistant", blocks: [] },
    ]);
    setActiveAgentBySession((m) => ({ ...m, [sid]: "" }));
    setSeenAgentsBySession((m) => ({ ...m, [sid]: new Set() }));
    setExecPathBySession((m) => ({ ...m, [sid]: [] }));

    try {
      let acc = emptyAcc();
      let tokens = 0;
      let ts = Date.now() / 1000;
      for await (const event of runSSE({
        appName,
        userId,
        sessionId: sid,
        text,
        attachments: atts,
        invocation: selectedInvocation,
        signal: ctrl.signal,
      })) {
        if (ctrl.signal.aborted) break;
        const errMsg = event.error ?? event.errorMessage ?? event.error_message;
        if (typeof errMsg === "string" && errMsg) {
          if (viewSidRef.current === sid) setError(errMsg);
          break;
        }
        // Live topology: author + transfer/end signals, keyed by session.
        applyStreamSignals(sid, event);
        acc = applyEvent(acc, event);
        const usage = event.usageMetadata ?? event.usage_metadata;
        if (usage?.totalTokenCount) tokens = usage.totalTokenCount;
        if (event.timestamp) ts = event.timestamp;
        const blocks = acc.blocks;
        const meta = { tokens: tokens || undefined, ts };
        setTurnsFor(sid, (t) => {
          const next = t.slice();
          const last = next[next.length - 1];
          if (last?.role === "assistant") next[next.length - 1] = { ...last, blocks, meta };
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
    try {
      let acc = emptyAcc();
      let tokens = 0;
      let ts = Date.now() / 1000;
      for await (const event of runSSE({
        appName,
        userId,
        sessionId,
        text: "",
        functionResponses: [
          { id: block.callId, name: "adk_request_credential", response },
        ],
        signal: ctrl.signal,
      })) {
        if (ctrl.signal.aborted) break;
        applyStreamSignals(sid, event);
        acc = applyEvent(acc, event);
        const usage = event.usageMetadata ?? event.usage_metadata;
        if (usage?.totalTokenCount) tokens = usage.totalTokenCount;
        if (event.timestamp) ts = event.timestamp;
        const blocks = [...base, ...acc.blocks];
        setTurnsFor(sid, (t) => {
          const next = t.slice();
          const last = next[next.length - 1];
          if (last?.role === "assistant") {
            next[next.length - 1] = {
              ...last,
              blocks,
              meta: { tokens: tokens || last.meta?.tokens, ts },
            };
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
      setActiveAgentBySession((m) => ({ ...m, [sid]: "" }));
      setExecPathBySession((m) => ({ ...m, [sid]: [] }));
    }
  }

  if (authStatus === null) {
    return <div className="boot" />; // resolving identity
  }
  if (authStatus === "unauthenticated") {
    return <LoginPage branding={siteBranding} onUsername={onUsername} />;
  }

  const agentEntries = buildAgentEntries(apps, connections);
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
  // Selecting an agent (from the sidebar picker) starts a fresh chat; any
  // background stream keeps persisting to its own (old) session.
  const selectAgent = (id: string) => {
    setConnections(loadConnections());
    viewSidRef.current = "";
    setSessionId("");
    setAppName(id);
  };
  const connectManagedRuntime = async (runtime: ManagedRuntime) => {
    const agentId = await connectRuntime(
      runtime.runtimeId,
      runtime.name,
      runtime.region,
    );
    selectAgent(agentId);
  };

  return (
    <div className="layout">
      <Sidebar
        branding={siteBranding}
        agentsSource={agentsSource}
        localApps={apps}
        currentAgentId={appName}
        currentAgentLabel={appName ? labelOf(appName) : ""}
        currentRuntime={currentRuntime}
        author={String(userInfo?.email ?? userId ?? "")}
        onSelectAgent={selectAgent}
        features={features}
        sessions={sessions}
        currentSessionId={sessionId}
        streamingSids={streamingSids}
        onNewChat={() => {
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(false);
          startNewChat();
        }}
        onSearch={() => {
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setManageAgents(false);
          setSearchView(true);
          setError("");
        }}
        onQuickCreate={() => {
          // "添加 Agent" — open the two-card chooser. Drop any selected session.
          viewSidRef.current = "";
          setSessionId("");
          setSkillCenter(false);
          setAddAgent(false);
          setSearchView(false);
          setManageAgents(false);
          setCreateView(null);
          setImportedDraft(null);
          setAddMenu(true);
          setError("");
        }}
        onSkillCenter={() => {
          setCreateView(null);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(false);
          setSkillCenter(true);
          setError("");
        }}
        onAddAgent={() => {
          viewSidRef.current = "";
          setCreateView(null);
          setSkillCenter(false);
          setSearchView(false);
          setManageAgents(false);
          setSessionId("");
          setAddMenu(false);
          setAddAgent(true);
          setError("");
        }}
        onManageAgents={() => {
          viewSidRef.current = "";
          setSessionId("");
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(true);
          setError("");
        }}
        onPickSession={(id) => {
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(false);
          setError("");
          pickSession(id);
        }}
        onDeleteSession={removeSession}
        userInfo={userInfo}
        onLogout={onLogout}
      />

      {(() => {
        const composer = (
          <Composer
            sessionId={sessionId}
            appName={appName}
            value={input}
            onChange={setInput}
            onSubmit={() => {
              const text = input;
              const atts = attachments;
              const selectedInvocation = invocation;
              setInput("");
              setAttachments([]);
              setInvocation(emptyInvocation());
              send(text, atts, selectedInvocation);
              releaseAttachmentPreviews(atts);
            }}
            disabled={!appName || !userId}
            busy={busy}
            showMeta={turns.length > 0}
            attachments={attachments}
            skills={availableSkills}
            agents={availableAgents}
            invocation={invocation}
            capabilitiesLoading={capabilitiesLoading}
            onInvocationChange={setInvocation}
            onAddFiles={addFiles}
            onRemoveAttachment={removeDraftAttachment}
          />
        );
        return (
          <section className="main-shell">
            <Navbar
              apps={agentEntries.map((e) => e.id)}
              appName={appName}
              onAppChange={selectAgent}
              agentLabel={labelOf}
              title={
                addMenu
                  ? "添加 Agent"
                  : addAgent
                    ? "添加 AgentKit 智能体"
                    : skillCenter
                      ? "技能中心"
                      : searchView
                        ? "搜索"
                        : manageAgents
                          ? "管理 Agent"
                          : createView
                            ? undefined
                            : appName
                              ? labelOf(appName)
                              : "选择 Agent"
              }
              crumbs={
                searchView || addAgent || skillCenter || addMenu || !createView
                  ? undefined
                  : createView === "menu"
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
                        { label: MODE_LABEL[createView] },
                      ]
              }
              rightContent={
                <DeploymentTaskStatus
                  tasks={deploymentTasks}
                  onCancel={cancelDeploymentTask}
                />
              }
            />
            <main className="main">
            {error && <div className="error">{error}</div>}
            {loadingSession && (
              <div className="session-loading">
                <Loader2 className="icon spin" /> 加载会话…
              </div>
            )}

            {manageAgents ? (
              <ManageAgentsView
                author={String(userInfo?.email ?? userId ?? "")}
                currentRuntimeId={currentRuntime?.runtimeId}
                onConnect={connectManagedRuntime}
              />
            ) : addMenu ? (
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
                ]}
              />
            ) : searchView ? (
              <SearchView
                userId={userId}
                appId={appName}
                agentLabel={labelOf}
                onOpenSession={openFromSearch}
              />
            ) : addAgent ? (
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
            ) : createView !== null && !hasCreds ? (
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
            ) : createView === "menu" ? (
              <QuickCreate
                onSelect={(k) => {
                  setImportedDraft(null);
                  setCreateView(k);
                }}
                onImport={(d) => {
                  setImportedDraft(d);
                  setCreateView("custom");
                }}
              />
            ) : createView === "intelligent" ? (
              <IntelligentCreate
                userId={userId}
                onBack={() => setCreateView("menu")}
                onCreate={onCreate}
                onAgentAdded={onAgentAdded}
                onDeploymentTaskChange={updateDeploymentTask}
              />
            ) : createView === "custom" ? (
              <CustomCreate
                initialDraft={importedDraft ?? undefined}
                onBack={() => setCreateView("menu")}
                onCreate={onCreate}
                onAgentAdded={onAgentAdded}
                author={String(userInfo?.email ?? userId ?? "")}
                features={features}
                onDeploymentTaskChange={updateDeploymentTask}
              />
            ) : createView === "template" ? (
              <TemplateCreate onBack={() => setCreateView("menu")} onCreate={onCreate} />
            ) : createView === "workflow" ? (
              <WorkflowCreate onBack={() => setCreateView("menu")} onCreate={onCreate} />
            ) : turns.length === 0 ? (
              <>
                <div className="welcome">
                  <h1 className="welcome-title">{greeting}</h1>
                  {composer}
                </div>
                {/* Show the agent's structure as soon as it's selected, before
                    any conversation — only renders when it has sub-agents. */}
                <AgentTopology
                  appName={appName}
                  activeAgent={activeAgent}
                  seenAgents={seenAgents}
                  execPath={execPath}
                />
              </>
            ) : (
              <>
                <div className="transcript" ref={scrollRef} onScroll={onScroll}>
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
            const pending = turn.blocks.length === 0;
            return (
              <motion.div
                key={i}
                className="turn turn--assistant"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                {pending ? (
                  isLast && busy ? <ThinkingPlaceholder /> : null
                ) : (
                  <>
                    <Blocks appName={appName} blocks={turn.blocks} onAction={onAction} onAuth={onAuth} />
                    {/* Finalized turn that produced no visible answer (e.g. only
                        thinking + an empty A2UI surface) — show a fallback note. */}
                    {!(isLast && busy) && !turnHasVisibleContent(turn) && (
                      <div className="turn-empty">本次没有返回可显示的内容。</div>
                    )}
                    {/* Hide the actions/timestamp row while this turn is still
                        thinking/streaming or waiting on an OAuth card; reveal it
                        only once the reply is done. */}
                    {!(isLast && busy) && !turnAwaitingAuth(turn) && (
                      <div className="turn-meta">
                        <div className="turn-actions">
                          <button
                            className="icon-btn"
                            title="Tracing 火焰图"
                            onClick={() => setTraceOpen(true)}
                          >
                            <TraceIcon />
                          </button>
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
                <AgentTopology
                  appName={appName}
                  activeAgent={activeAgent}
                  seenAgents={seenAgents}
                  execPath={execPath}
                />
                {composer}
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
