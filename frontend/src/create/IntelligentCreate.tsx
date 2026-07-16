import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Send, Sparkles, Bot, FolderTree, AlertCircle, Loader2 } from "lucide-react";
import { createSession, runSSE, getAgentInfo, deployAgentkitProject } from "../adk/client";
import type { DeployStage } from "../adk/client";
import { applyEvent, emptyAcc, type Acc } from "../blocks";
import { Markdown } from "../ui/Markdown";
import { ProjectPreview } from "../ui/ProjectPreview";
import type { AgentProject } from "./project";
import { generateProject, normalizeDraft } from "./codegen";
import type { AgentDraft } from "./types";
import "./IntelligentCreate.css";

/* ------------------------------------------------------------------ *
 * Conversational ("智能模式") agent builder.
 *
 * Talks to a REAL backend ADK app — the `dogfooding` agent builder. The
 * user describes what they want; the agent streams back EXACTLY ONE JSON
 * object `{ "name", "files": [{ "path", "content" }] }` (or, only when the
 * requirement is empty, a short plain-text clarifying question).
 *
 * We accumulate the assistant's non-thought TEXT across stream events,
 * then at turn end try to parse it as the project JSON. On success we
 * render a live, editable <ProjectPreview> on the right; otherwise we just
 * show the text as a normal assistant chat message.
 * ------------------------------------------------------------------ */

const APP_NAME = "dogfooding";
/** The two builder ADK apps used in A/B compare mode. They share the same
 *  instruction but can be wired to different models server-side. */
const APP_A = "dogfooding";
const APP_B = "dogfooding_b";

export interface IntelligentCreateProps {
  userId: string;
  /** App-level breadcrumb also handles leaving; kept for parity. */
  onBack: () => void;
  onCreate: (draft: AgentDraft) => void;
  /** Called after successfully adding an agent to navigate to it. */
  onAgentAdded?: (agentId: string, agentName: string) => void;
}

type Role = "assistant" | "user";

interface ChatMessage {
  id: number;
  role: Role;
  text: string;
}

let _mid = 0;
const nextId = () => ++_mid;

/** Pull the assistant's final consolidated, non-thought text out of a turn
 *  accumulator (thinking parts are dropped — only `kind: "text"` blocks). */
function accText(acc: Acc): string {
  return acc.blocks
    .filter((b): b is { kind: "text"; text: string } => b.kind === "text")
    .map((b) => b.text)
    .join("");
}

/** Strip an accidental ```json … ``` (or bare ``` … ```) fence, returning the
 *  inner body so JSON.parse can run on it. No-op when there is no fence. */
function stripFence(raw: string): string {
  const t = raw.trim();
  const fenced = t.match(/^```(?:json)?\s*\n?([\s\S]*?)\n?```$/i);
  return (fenced ? fenced[1] : t).trim();
}

/** Try to interpret the assistant's text as an agent-CONFIG JSON, then run it
 *  through the shared codegen to produce the project. Tolerant of surrounding
 *  prose: falls back to the first `{ … }` slice. Returns null when the text
 *  isn't a config (e.g. a clarifying question). */
function parseProject(raw: string): AgentProject | null {
  const candidates: string[] = [];
  const stripped = stripFence(raw);
  candidates.push(stripped);
  const first = stripped.indexOf("{");
  const last = stripped.lastIndexOf("}");
  if (first >= 0 && last > first) candidates.push(stripped.slice(first, last + 1));

  for (const c of candidates) {
    try {
      const obj = JSON.parse(c) as unknown;
      // A config must at least carry a name or an instruction — a bare question
      // won't parse to such an object.
      if (
        obj &&
        typeof obj === "object" &&
        (typeof (obj as Record<string, unknown>).name === "string" ||
          typeof (obj as Record<string, unknown>).instruction === "string")
      ) {
        // Shared path: config -> normalized draft -> generated project files.
        return generateProject(normalizeDraft(obj));
      }
    } catch {
      /* try next candidate */
    }
  }
  return null;
}

export function IntelligentCreate({ userId, onBack, onCreate, onAgentAdded }: IntelligentCreateProps) {
  // onBack/onCreate are part of the contract but the deploy/preview is the
  // outcome here, so we don't drive navigation from this component.
  void onBack;
  void onCreate;

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: nextId(),
      role: "assistant",
      text:
        "你好，我是 VeADK 的智能构建助手。用自然语言描述你想要的 Agent，我会直接帮你生成一个可运行的 VeADK 项目，并在右侧实时预览。",
    },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState<AgentProject | null>(null);

  // ---- A/B compare mode -----------------------------------------------------
  const [abMode, setAbMode] = useState(false);
  const [projectA, setProjectA] = useState<AgentProject | null>(null);
  const [projectB, setProjectB] = useState<AgentProject | null>(null);
  // Per-side streaming flags so each pane shows its own spinner.
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);
  // Cached builder model names, fetched lazily via getAgentInfo (falls back to
  // the app name on failure).
  const [models, setModels] = useState<{ a?: string; b?: string }>({});

  // Lazily-created session for the `dogfooding` app (mirrors the main chat:
  // we defer creation until the first user message rather than on mount).
  const sessionRef = useRef<string | null>(null);
  // Independent lazily-created sessions for the two A/B builder apps.
  const sessionRefA = useRef<string | null>(null);
  const sessionRefB = useRef<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Keep the chat pinned to the latest message / stream delta.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  // Auto-grow the composer textarea.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [input]);

  const pushAssistant = (text: string) =>
    setMessages((m) => [...m, { id: nextId(), role: "assistant", text }]);

  async function ensureSession(): Promise<string> {
    if (sessionRef.current) return sessionRef.current;
    const id = await createSession(APP_NAME, userId);
    sessionRef.current = id;
    return id;
  }

  /** Lazily create (and cache) a session for a specific builder app, keyed by
   *  the provided ref. Used by the two A/B slots. */
  async function ensureSessionFor(
    appName: string,
    ref: React.MutableRefObject<string | null>,
  ): Promise<string> {
    if (ref.current) return ref.current;
    const id = await createSession(appName, userId);
    ref.current = id;
    return id;
  }

  /** Fetch + cache the model name for one A/B slot. Best-effort: on failure we
   *  fall back to the app name so the pane header always has a label. */
  async function fetchModel(slot: "a" | "b", appName: string) {
    if (models[slot]) return;
    try {
      const info = await getAgentInfo(appName);
      setModels((prev) => ({ ...prev, [slot]: info.model || appName }));
    } catch {
      setModels((prev) => ({ ...prev, [slot]: appName }));
    }
  }

  /** Stream one builder app to completion and parse its project. Shared by both
   *  A/B slots so they run with identical accumulation semantics. */
  async function runBuilder(
    appName: string,
    ref: React.MutableRefObject<string | null>,
    text: string,
  ): Promise<{ project: AgentProject | null; finalText: string }> {
    const sessionId = await ensureSessionFor(appName, ref);
    let acc = emptyAcc();
    for await (const evt of runSSE({ appName, userId, sessionId, text })) {
      acc = applyEvent(acc, evt);
    }
    const finalText = accText(acc).trim();
    return { project: parseProject(finalText), finalText };
  }

  const handleDeploy = async (
    proj: AgentProject,
    onStage?: (s: DeployStage) => void,
    options?: Parameters<typeof deployAgentkitProject>[3],
  ) => {
    return deployAgentkitProject(
      proj.name,
      proj.files,
      {
        region: "cn-beijing",
        projectName: "default",
      },
      { ...options, onStage },
    );
  };

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    setMessages((m) => [...m, { id: nextId(), role: "user", text }]);
    setInput("");
    setError(null);
    setStreaming(true);

    if (abMode) {
      // ---- A/B: run both builders concurrently ----
      setProjectA(null);
      setProjectB(null);
      setLoadingA(true);
      setLoadingB(true);
      // Kick off model-name fetches (cached; no-op if already known).
      void fetchModel("a", APP_A);
      void fetchModel("b", APP_B);

      const runA = runBuilder(APP_A, sessionRefA, text)
        .then(({ project }) => {
          setProjectA(project);
          return project;
        })
        .catch((err) => {
          const msg = err instanceof Error ? err.message : String(err);
          setError(msg);
          return null;
        })
        .finally(() => setLoadingA(false));

      const runB = runBuilder(APP_B, sessionRefB, text)
        .then(({ project }) => {
          setProjectB(project);
          return project;
        })
        .catch((err) => {
          const msg = err instanceof Error ? err.message : String(err);
          setError(msg);
          return null;
        })
        .finally(() => setLoadingB(false));

      try {
        const [pa, pb] = await Promise.all([runA, runB]);
        const names = [
          pa ? `方案 A：${pa.name}` : null,
          pb ? `方案 B：${pb.name}` : null,
        ].filter(Boolean);
        if (names.length) {
          pushAssistant(`已生成两个方案（${names.join("，")}），请在右侧对比后采用其一。`);
        } else {
          pushAssistant("（两个方案都没有返回可用的项目，请再描述一下你的需求。）");
        }
      } finally {
        setStreaming(false);
      }
      return;
    }

    try {
      const sessionId = await ensureSession();

      // Accumulate non-thought text across the streamed events of this turn.
      let acc = emptyAcc();
      for await (const evt of runSSE({ appName: APP_NAME, userId, sessionId, text })) {
        acc = applyEvent(acc, evt);
      }

      const finalText = accText(acc).trim();
      const parsed = parseProject(finalText);
      if (parsed) {
        setProject(parsed);
        pushAssistant(
          `已生成项目：${parsed.name}（${parsed.files.length} 个文件），可在右侧预览和编辑。`,
        );
      } else {
        pushAssistant(finalText || "（助手没有返回内容，请再描述一下你的需求。）");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      pushAssistant(`抱歉，调用智能构建助手失败：${msg}`);
    } finally {
      setStreaming(false);
    }
  };

  /** Adopt one A/B side: promote it to the single editable project, exit
   *  compare mode, and clear the per-side state. */
  const adopt = (side: "a" | "b") => {
    const chosen = side === "a" ? projectA : projectB;
    if (!chosen) return;
    setProject(chosen);
    setAbMode(false);
    setProjectA(null);
    setProjectB(null);
    setLoadingA(false);
    setLoadingB(false);
    const label = side === "a" ? "A" : "B";
    const model = side === "a" ? models.a : models.b;
    pushAssistant(`已采用方案 ${label}（${model ?? (side === "a" ? APP_A : APP_B)}），可继续编辑。`);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <div className="ic-root">
      <div className="ic-body">
        {/* ---------- chat column ---------- */}
        <div className="ic-chat">
          <div className="ic-transcript" ref={scrollRef}>
            <AnimatePresence initial={false}>
              {messages.map((m) => (
                <motion.div
                  key={m.id}
                  className={`ic-turn ic-turn--${m.role}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22, ease: "easeOut" }}
                >
                  {m.role === "assistant" && (
                    <div className="ic-avatar">
                      <Bot className="ic-avatar-icon" />
                    </div>
                  )}
                  <div className="ic-bubble">
                    {m.role === "assistant" ? (
                      <Markdown text={m.text} />
                    ) : (
                      m.text
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>

            {streaming && (
              <motion.div
                className="ic-turn ic-turn--assistant"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <div className="ic-avatar">
                  <Bot className="ic-avatar-icon" />
                </div>
                <div className="ic-bubble ic-bubble--typing">
                  <span className="ic-dot" />
                  <span className="ic-dot" />
                  <span className="ic-dot" />
                </div>
              </motion.div>
            )}
          </div>

          {error && (
            <div className="ic-error">
              <AlertCircle className="ic-error-icon" />
              {error}
            </div>
          )}

          {/* composer */}
          <div className="ic-composer">
            <div className="ic-composer-box">
              <textarea
                ref={inputRef}
                className="ic-input"
                rows={1}
                placeholder="描述你想要的 Agent，例如「一个帮我整理周报的写作助手」…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                disabled={streaming}
              />
              <button
                className="ic-send"
                onClick={() => void send()}
                disabled={!input.trim() || streaming}
                title="发送 (Enter)"
              >
                <Send className="ic-send-icon" />
              </button>
            </div>
            <div className="ic-composer-foot">
              <label className="ic-ab-toggle" title="同时用两个模型生成方案进行对比">
                <input
                  type="checkbox"
                  className="ic-ab-checkbox"
                  checked={abMode}
                  disabled={streaming}
                  onChange={(e) => setAbMode(e.target.checked)}
                />
                <span className="ic-ab-track"><span className="ic-ab-thumb" /></span>
                <span className="ic-ab-label">A/B 对比</span>
              </label>
              <div className="ic-composer-hint">Enter 发送 · Shift+Enter 换行</div>
            </div>
          </div>
        </div>

        {/* ---------- live project preview column ---------- */}
        <aside className="ic-preview">
          {abMode ? (
            <div className="ic-compare">
              <ComparePane
                side="a"
                project={projectA}
                loading={loadingA}
                model={models.a}
                onAdopt={() => adopt("a")}
              />
              <div className="ic-compare-divider" />
              <ComparePane
                side="b"
                project={projectB}
                loading={loadingB}
                model={models.b}
                onAdopt={() => adopt("b")}
              />
            </div>
          ) : project ? (
            <ProjectPreview project={project} onChange={setProject} onDeploy={handleDeploy} onAgentAdded={onAgentAdded} />
          ) : (
            <div className="ic-preview-empty">
              <div className="ic-preview-empty-icon">
                <FolderTree className="ic-preview-empty-glyph" />
                <Sparkles className="ic-preview-empty-spark" />
              </div>
              <div className="ic-preview-empty-title">还没有项目</div>
              <div className="ic-preview-empty-sub">
                描述你的需求，我会帮你生成 VeADK 项目
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * One side of the A/B compare view: a labelled header (方案 A/B + model)
 * and a READ-ONLY ProjectPreview, plus a primary "采用" button. Shows a
 * spinner while that side is still streaming.
 * ------------------------------------------------------------------ */
interface ComparePaneProps {
  side: "a" | "b";
  project: AgentProject | null;
  loading: boolean;
  model?: string;
  onAdopt: () => void;
}

function ComparePane({ side, project, loading, model, onAdopt }: ComparePaneProps) {
  const label = side === "a" ? "方案 A" : "方案 B";
  return (
    <div className="ic-pane">
      <div className="ic-pane-head">
        <div className="ic-pane-title">
          <span className={`ic-pane-tag ic-pane-tag--${side}`}>{label}</span>
          {model && <span className="ic-pane-model">{model}</span>}
        </div>
        <button
          className="ic-adopt"
          onClick={onAdopt}
          disabled={!project || loading}
          title={`采用${label}`}
        >
          采用{side === "a" ? "方案 A" : "方案 B"}
        </button>
      </div>
      <div className="ic-pane-body">
        {loading ? (
          <div className="ic-pane-loading">
            <Loader2 className="ic-pane-spinner" />
            <span>正在生成…</span>
          </div>
        ) : project ? (
          <ProjectPreview project={project} />
        ) : (
          <div className="ic-pane-empty">该方案未返回可用项目</div>
        )}
      </div>
    </div>
  );
}
