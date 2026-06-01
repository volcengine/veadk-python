import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import {
  createSession,
  deleteSession,
  getSession,
  listApps,
  listSessions,
  runSSE,
  type AdkSession,
} from "./adk/client";
import { applyEvent, emptyAcc, eventsToTurns, type Turn } from "./blocks";
import { Sidebar } from "./ui/Sidebar";
import { Blocks, ThinkingPlaceholder } from "./ui/Blocks";
import { Composer } from "./ui/Composer";
import { TraceDrawer } from "./ui/TraceDrawer";
import { LoginPage } from "./ui/LoginPage";
import { useStickToBottom } from "./ui/useStickToBottom";
import { login, logout, resolveIdentity, type AuthStatus } from "./adk/identity";
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
  if (!text) return null;
  return (
    <button
      className="icon-btn"
      title={copied ? "已复制" : "复制"}
      onClick={async () => {
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
  "想看看什么样的卡片？",
  "嗨，我们开始吧",
  "试试让我用 UI 来回答你",
];
const pickGreeting = () => GREETINGS[Math.floor(Math.random() * GREETINGS.length)];

export default function App() {
  const [apps, setApps] = useState<string[]>([]);
  const [appName, setAppName] = useState("");
  const [sessions, setSessions] = useState<AdkSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [traceOpen, setTraceOpen] = useState(false);
  const [greeting, setGreeting] = useState(pickGreeting);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [userId, setUserId] = useState("");
  const [userInfo, setUserInfo] = useState<Record<string, unknown> | undefined>();
  const { ref: scrollRef, onScroll } = useStickToBottom<HTMLDivElement>(turns);

  // Resolve SSO identity first; it provides the ADK user_id.
  useEffect(() => {
    resolveIdentity().then((id) => {
      setUserId(id.userId);
      setUserInfo(id.info);
      setAuthStatus(id.status);
    });
  }, []);

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

  // When the app (or resolved user) changes: load sessions and open a fresh one.
  useEffect(() => {
    if (!appName || !userId) return;
    void startNewChat(appName);
    void refreshSessions(appName);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appName, userId]);

  async function refreshSessions(app: string) {
    setLoadingSessions(true);
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
    } finally {
      setLoadingSessions(false);
    }
  }

  async function startNewChat(app: string) {
    setError("");
    setGreeting(pickGreeting());
    try {
      const id = await createSession(app, userId);
      setSessionId(id);
      setTurns([]);
    } catch (e) {
      setError(String(e));
    }
  }

  async function removeSession(id: string) {
    try {
      await deleteSession(appName, userId, id);
      if (id === sessionId) await startNewChat(appName);
      await refreshSessions(appName);
    } catch (e) {
      setError(String(e));
    }
  }

  async function pickSession(id: string) {
    setError("");
    try {
      const s = await getSession(appName, userId, id);
      setSessionId(id);
      setTurns(eventsToTurns(s.events ?? []));
    } catch (e) {
      setError(String(e));
    }
  }

  async function send(text: string) {
    if (!text.trim() || !sessionId || busy) return;
    setError("");
    setBusy(true);
    setTurns((t) => [
      ...t,
      { role: "user", blocks: [{ kind: "text", text }], meta: { ts: Date.now() / 1000 } },
      { role: "assistant", blocks: [] },
    ]);

    try {
      let acc = emptyAcc();
      let tokens = 0;
      let ts = Date.now() / 1000;
      for await (const event of runSSE({ appName, userId: userId, sessionId, text })) {
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
    return <LoginPage onLogin={login} />;
  }

  return (
    <div className="layout">
      <Sidebar
        apps={apps}
        appName={appName}
        onAppChange={setAppName}
        sessions={sessions}
        currentSessionId={sessionId}
        onNewChat={() => startNewChat(appName)}
        onPickSession={pickSession}
        onDeleteSession={removeSession}
        onRefresh={() => refreshSessions(appName)}
        loadingSessions={loadingSessions}
        userInfo={userInfo}
        onLogout={logout}
      />

      {(() => {
        const composer = (
          <Composer
            value={input}
            onChange={setInput}
            onSubmit={() => {
              const text = input;
              setInput("");
              send(text);
            }}
            disabled={!sessionId}
            busy={busy}
          />
        );
        return (
          <main className="main">
            {error && <div className="error">{error}</div>}

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
              const text = turn.blocks.map((b) => ("text" in b ? b.text : "")).join("");
              return (
                <div key={i} className="turn turn--user">
                  <div className="bubble">{text}</div>
                  <div className="turn-actions turn-actions--right">
                    {turn.meta?.ts && <span className="meta-text">{fmtTime(turn.meta.ts)}</span>}
                    <CopyButton text={text} />
                  </div>
                </div>
              );
            }
            const pending = turn.blocks.length === 0;
            return (
              <div key={i} className="turn turn--assistant">
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
              </div>
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
