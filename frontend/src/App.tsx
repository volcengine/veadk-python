import { useEffect, useRef, useState } from "react";
import { Check, Copy, FileText, Loader2 } from "lucide-react";
import { motion } from "motion/react";
import {
  createSession,
  deleteSession,
  getSession,
  listApps,
  listSessions,
  runSSE,
  type AdkSession,
  type Attachment,
} from "./adk/client";
import { applyEvent, emptyAcc, eventsToTurns, type Block, type Turn } from "./blocks";
import { Sidebar } from "./ui/Sidebar";
import { Navbar } from "./ui/Navbar";
import { SkillCenterView } from "./ui/SkillCenter";
import { AddAgentKitView } from "./ui/AddAgentKit";
import { SearchView } from "./ui/Search";
import {
  buildAgentEntries,
  loadConnections,
  registerConnections,
  remoteAppId,
  type RemoteConnection,
} from "./adk/connections";
import { Blocks, ThinkingPlaceholder } from "./ui/Blocks";
import { Composer } from "./ui/Composer";
import { QuickCreate, type QuickCreateKind } from "./ui/QuickCreate";
import { StackCards } from "./ui/AddAgentMenu";
import { IntelligentCreate } from "./create/IntelligentCreate";
import { CustomCreate } from "./create/CustomCreate";
import { TemplateCreate } from "./create/TemplateCreate";
import { WorkflowCreate } from "./create/WorkflowCreate";
import type { AgentDraft } from "./create/types";

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

/** Hand-drawn "AgentKit" mark: a little agent/robot module with side ports —
 *  a packaged remote agent you plug into. */
function AgentKitIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="5" y="7.5" width="14" height="10.5" rx="3.2" />
      <circle cx="9.6" cy="12.6" r="1.25" fill="currentColor" stroke="none" />
      <circle cx="14.4" cy="12.6" r="1.25" fill="currentColor" stroke="none" />
      <path d="M12 7.5V4.4" />
      <circle cx="12" cy="3.4" r="1.15" fill="currentColor" stroke="none" />
      <path d="M5 13.2H2.8M19 13.2h2.2" />
    </svg>
  );
}

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
 *  text, a renderable A2UI surface, or a non-A2UI tool. Thinking, the hidden
 *  (done) A2UI tool, and empty A2UI surfaces don't count, so a reply that was
 *  ONLY thinking + an empty surface returns false (→ we show a fallback). */
function turnHasVisibleContent(turn: Turn): boolean {
  return turn.blocks.some((b) => {
    if (b.kind === "text") return b.text.trim().length > 0;
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

const MAX_FILE_BYTES = 20 * 1024 * 1024; // 20 MB/file (base64 inflates ~33%)

/** Read a File as base64 (without the `data:...;base64,` prefix). */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const res = String(reader.result);
      const comma = res.indexOf(",");
      resolve(comma >= 0 ? res.slice(comma + 1) : res);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export default function App() {
  const [apps, setApps] = useState<string[]>([]);
  const [appName, setAppName] = useState("");
  const [sessions, setSessions] = useState<AdkSession[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [traceOpen, setTraceOpen] = useState(false);
  const [greeting, setGreeting] = useState(pickGreeting);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [userId, setUserId] = useState("");
  const [userInfo, setUserInfo] = useState<Record<string, unknown> | undefined>();
  const [localMode, setLocalMode] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [createView, setCreateView] = useState<CreateView>(loadView);
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
        const saved = localStorage.getItem(LS.app);
        const remoteIds = connections.flatMap((c) => c.apps.map((a) => remoteAppId(c.id, a)));
        const valid = saved && (list.includes(saved) || remoteIds.includes(saved));
        const fallback =
          ["web_search_agent", "web_demo"].find((a) => list.includes(a)) ??
          list.find((a) => !/^\d/.test(a)) ??
          list[0];
        const preferred = valid ? saved : fallback;
        if (preferred) setAppName(preferred);
      })
      .catch((e) => setError(String(e)));
  }, [authStatus]);

  // Persist the current view/agent/session so a refresh restores them.
  useEffect(() => {
    if (appName) localStorage.setItem(LS.app, appName);
  }, [appName]);
  useEffect(() => {
    localStorage.setItem(LS.view, createView ?? "chat");
  }, [createView]);
  useEffect(() => {
    localStorage.setItem(LS.session, sessionId);
  }, [sessionId]);

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
  // lazily on the first message (see send()).
  function startNewChat() {
    setError("");
    setGreeting(pickGreeting());
    setSessionId("");
    setTurns([]);
  }

  async function removeSession(id: string) {
    try {
      await deleteSession(appName, userId, id);
      if (id === sessionId) startNewChat();
      await refreshSessions(appName);
    } catch (e) {
      setError(String(e));
    }
  }

  async function pickSession(id: string) {
    if (id === sessionId) return;
    setError("");
    setLoadingSession(true);
    setSessionId(id);
    try {
      const s = await getSession(appName, userId, id);
      setTurns(eventsToTurns(s.events ?? []));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingSession(false);
    }
  }

  async function addFiles(files: FileList | File[]) {
    const picked: Attachment[] = [];
    for (const f of Array.from(files)) {
      if (f.size > MAX_FILE_BYTES) {
        setError(`文件过大（>20MB）：${f.name}`);
        continue;
      }
      const data = await fileToBase64(f);
      picked.push({
        mimeType: f.type || "application/octet-stream",
        data,
        name: f.name,
      });
    }
    if (picked.length) setAttachments((a) => [...a, ...picked]);
  }

  async function send(text: string, atts: Attachment[] = []) {
    if ((!text.trim() && atts.length === 0) || busy || !appName || !userId) return;
    setError("");
    setBusy(true);

    // Lazily create the backend session on the first message.
    let sid = sessionId;
    if (!sid) {
      try {
        sid = await createSession(appName, userId);
        setSessionId(sid);
        // Show the session in the sidebar immediately (titled with this first
        // message) instead of waiting for the reply to finish; the post-stream
        // refreshSessions() below reconciles it with the server.
        const now = Date.now() / 1000;
        const optimistic: AdkSession = {
          id: sid,
          lastUpdateTime: now,
          events: [{ author: "user", timestamp: now, content: { role: "user", parts: [{ text }] } }],
        };
        setSessions((prev) => [optimistic, ...prev.filter((s) => s.id !== sid)]);
      } catch (e) {
        setError(String(e));
        setBusy(false);
        return;
      }
    }

    const userBlocks: Turn["blocks"] = [];
    if (atts.length)
      userBlocks.push({
        kind: "attachment",
        files: atts.map((a) => ({ mimeType: a.mimeType, data: a.data, name: a.name })),
      });
    if (text.trim()) userBlocks.push({ kind: "text", text });
    setTurns((t) => [
      ...t,
      { role: "user", blocks: userBlocks, meta: { ts: Date.now() / 1000 } },
      { role: "assistant", blocks: [] },
    ]);

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
      })) {
        const errMsg = event.error ?? event.errorMessage ?? event.error_message;
        if (typeof errMsg === "string" && errMsg) {
          setError(errMsg);
          break;
        }
        acc = applyEvent(acc, event);
        const usage = event.usageMetadata ?? event.usage_metadata;
        if (usage?.totalTokenCount) tokens = usage.totalTokenCount;
        if (event.timestamp) ts = event.timestamp;
        const blocks = acc.blocks;
        const meta = { tokens: tokens || undefined, ts };
        setTurns((t) => {
          const next = t.slice();
          const last = next[next.length - 1];
          if (last?.role === "assistant") next[next.length - 1] = { ...last, blocks, meta };
          return next;
        });
      }
      void refreshSessions(appName);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
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
    const callbackUrl = await runOAuthPopup(block.authUri);
    const response = withAuthResponseUri(block.authConfig, callbackUrl);

    // The moment we have the callback, mark the auth card resolved so it
    // collapses to a compact "已授权" row immediately — rather than sitting on
    // "等待授权…" until the whole reply finishes streaming.
    const resolveAuth = (bs: Block[]) =>
      bs.map((b) => (b.kind === "auth" && !b.done ? { ...b, done: true } : b));
    setTurns((t) => {
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

    setBusy(true);
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
      })) {
        acc = applyEvent(acc, event);
        const usage = event.usageMetadata ?? event.usage_metadata;
        if (usage?.totalTokenCount) tokens = usage.totalTokenCount;
        if (event.timestamp) ts = event.timestamp;
        const blocks = [...base, ...acc.blocks];
        setTurns((t) => {
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
    } finally {
      setBusy(false);
    }
  }

  if (authStatus === null) {
    return <div className="boot" />; // resolving identity
  }
  if (authStatus === "unauthenticated") {
    return <LoginPage onUsername={onUsername} />;
  }

  return (
    <div className="layout">
      <Sidebar
        sessions={sessions}
        currentSessionId={sessionId}
        onNewChat={() => {
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          startNewChat();
        }}
        onSearch={() => {
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(true);
          setError("");
        }}
        onQuickCreate={() => {
          // "添加 Agent" — open the two-card chooser. Drop any selected session.
          setSessionId("");
          setTurns([]);
          setSkillCenter(false);
          setAddAgent(false);
          setSearchView(false);
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
          setSkillCenter(true);
          setError("");
        }}
        onAddAgent={() => {
          setCreateView(null);
          setSkillCenter(false);
          setSearchView(false);
          setSessionId("");
          setTurns([]);
          setAddMenu(false);
          setAddAgent(true);
          setError("");
        }}
        onPickSession={(id) => {
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
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
            value={input}
            onChange={setInput}
            onSubmit={() => {
              const text = input;
              const atts = attachments;
              setInput("");
              setAttachments([]);
              send(text, atts);
            }}
            disabled={!appName || !userId}
            busy={busy}
            attachments={attachments}
            onAddFiles={addFiles}
            onRemoveAttachment={(i) =>
              setAttachments((a) => a.filter((_, j) => j !== i))
            }
          />
        );
        const agentEntries = buildAgentEntries(apps, connections);
        const labelOf = (id: string) => agentEntries.find((e) => e.id === id)?.label ?? id;
        return (
          <main className="main">
            <Navbar
              apps={agentEntries.map((e) => e.id)}
              appName={appName}
              onAppChange={setAppName}
              agentLabel={labelOf}
              title={
                addMenu
                  ? "添加 Agent"
                  : addAgent
                    ? "添加 AgentKit 智能体"
                    : skillCenter
                      ? "技能中心"
                      : undefined
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
            />
            {error && <div className="error">{error}</div>}
            {loadingSession && (
              <div className="session-loading">
                <Loader2 className="icon spin" /> 加载会话…
              </div>
            )}

            {addMenu ? (
              <StackCards
                title="您想以哪种方式添加 Agent 来运行？"
                sub="选择最适合你的方式，下一步即可开始"
                cards={[
                  {
                    key: "agentkit",
                    icon: AgentKitIcon,
                    title: "添加 AgentKit 智能体",
                    desc: "连接已部署在火山引擎 AgentKit 上的远程智能体。",
                    onClick: () => {
                      setAddMenu(false);
                      setAddAgent(true);
                    },
                  },
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
              <IntelligentCreate userId={userId} onBack={() => setCreateView("menu")} onCreate={onCreate} onAgentAdded={onAgentAdded} />
            ) : createView === "custom" ? (
              <CustomCreate
                initialDraft={importedDraft ?? undefined}
                onBack={() => setCreateView("menu")}
                onCreate={onCreate}
                onAgentAdded={onAgentAdded}
              />
            ) : createView === "template" ? (
              <TemplateCreate onBack={() => setCreateView("menu")} onCreate={onCreate} />
            ) : createView === "workflow" ? (
              <WorkflowCreate onBack={() => setCreateView("menu")} onCreate={onCreate} />
            ) : turns.length === 0 ? (
              <div className="welcome">
                <h1 className="welcome-title">{greeting}</h1>
                {composer}
              </div>
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
              return (
                <motion.div
                  key={i}
                  className="turn turn--user"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                >
                  {atts.length > 0 && (
                    <div className="msg-attachments">
                      {atts.map((f, j) =>
                        f.mimeType?.startsWith("image/") && f.data ? (
                          <img
                            key={j}
                            className="attachment-thumb"
                            src={`data:${f.mimeType};base64,${f.data}`}
                            alt={f.name ?? "image"}
                          />
                        ) : (
                          <div key={j} className="attachment-file">
                            <FileText className="icon" />
                            <span className="attachment-file-name">{f.name ?? "文件"}</span>
                          </div>
                        ),
                      )}
                    </div>
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
                    <Blocks blocks={turn.blocks} onAction={onAction} onAuth={onAuth} />
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
                {composer}
              </>
            )}
          </main>
        );
      })()}

      {traceOpen && sessionId && (
        <TraceDrawer sessionId={sessionId} onClose={() => setTraceOpen(false)} />
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
