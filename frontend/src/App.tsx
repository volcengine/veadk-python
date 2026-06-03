import { useEffect, useState } from "react";
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
import { applyEvent, emptyAcc, eventsToTurns, type Turn } from "./blocks";
import { Sidebar } from "./ui/Sidebar";
import { Blocks, ThinkingPlaceholder } from "./ui/Blocks";
import { Composer } from "./ui/Composer";
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
        const preferred = list.find((a) => a.includes("a2ui")) ?? list[0];
        if (preferred) setAppName(preferred);
      })
      .catch((e) => setError(String(e)));
  }, [authStatus]);

  // When the app (or resolved user) changes: reset to a fresh chat and list
  // existing sessions. No session is created until the first message is sent.
  useEffect(() => {
    if (!appName || !userId) return;
    startNewChat();
    void refreshSessions(appName);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appName, userId]);

  async function refreshSessions(app: string) {
    try {
      const list = await listSessions(app, userId);
      // Hydrate events so the sidebar can show a title per session.
      const hydrated = await Promise.all(
        list.map((s) =>
          s.events?.length ? Promise.resolve(s) : getSession(app, userId, s.id),
        ),
      );
      setSessions(hydrated);
    } catch (e) {
      setError(String(e));
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

  if (authStatus === null) {
    return <div className="boot" />; // resolving identity
  }
  if (authStatus === "unauthenticated") {
    return <LoginPage onUsername={onUsername} />;
  }

  return (
    <div className="layout">
      <Sidebar
        apps={apps}
        appName={appName}
        onAppChange={setAppName}
        sessions={sessions}
        currentSessionId={sessionId}
        onNewChat={() => startNewChat()}
        onPickSession={pickSession}
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
        return (
          <main className="main">
            {error && <div className="error">{error}</div>}
            {loadingSession && (
              <div className="session-loading">
                <Loader2 className="icon spin" /> 加载会话…
              </div>
            )}

            {turns.length === 0 ? (
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
                    <Blocks blocks={turn.blocks} onAction={onAction} />
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
    </div>
  );
}
