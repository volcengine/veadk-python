import { useEffect, useRef, useState } from "react";
import { ChevronRight, Loader2, ShieldCheck } from "lucide-react";
import { motion } from "motion/react";
import type { Block } from "../blocks";
import { buildSurfaces, SurfaceView } from "../a2ui/Surface";
import { useStickToBottom } from "./useStickToBottom";
import { Markdown } from "./Markdown";
import { InvocationChips } from "./InvocationChips";
import { MediaGroup } from "./Media";
import type { A2uiAction, A2uiComponent } from "../a2ui/types";

const A2UI_TOOL = "send_a2ui_json_to_client";

/** Hand-drawn "spark" icon for the thinking indicator. */
function SparkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden>
      <path d="M12 2.2l1.7 5.1a3 3 0 0 0 1.9 1.9L20.8 11l-5.1 1.7a3 3 0 0 0-1.9 1.9L12 19.8l-1.7-5.1a3 3 0 0 0-1.9-1.9L3.2 11l5.1-1.7a3 3 0 0 0 1.9-1.9L12 2.2z" />
    </svg>
  );
}

export function ThinkingBlock({ text, done }: { text: string; done: boolean }) {
  // Expanded while thinking; auto-collapses when done. A manual toggle wins.
  const [open, setOpen] = useState(!done);
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current) setOpen(!done);
  }, [done]);
  const toggle = () => {
    touched.current = true;
    setOpen((o) => !o);
  };
  const body = text.replace(/^\s+/, "");
  const { ref, onScroll } = useStickToBottom<HTMLDivElement>(body);
  return (
    <div className="block-thinking">
      <button className="think-head" onClick={toggle} type="button">
        <SparkIcon className={`spark ${done ? "" : "pulse"}`} />
        <span className={`think-label ${done ? "think-label--done" : "shimmer"}`}>
          {done ? "已完成思考" : "思考中"}
        </span>
        <ChevronRight className={`chev ${open ? "open" : ""}`} />
      </button>
      <div className={`think-collapse ${open && body ? "open" : ""}`}>
        <div className="think-collapse-inner">
          <div className="think-body scroll" ref={ref} onScroll={onScroll}>
            {body}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Shown immediately after sending — identical head to ThinkingBlock so there
 *  is no layout jump when real content streams in. */
export function ThinkingPlaceholder() {
  return <ThinkingBlock text="" done={false} />;
}

/** Generic tool-call row. Visual treatment mirrors the janus-ee extension's
 *  `tool_pair` renderer (extension/src/components/event-renderer.tsx
 *  lines 922-980): a small status dot (running → done), the tool name with a
 *  shimmer while pending, a chevron, and a grid-rows collapse holding
 *  "参数" (args) and "返回" (result) sections in muted code blocks. The A2UI
 *  tool is shown as "渲染 UI" and hidden once done (handled by the caller). */
function ToolBlock({
  name,
  args,
  response,
  done,
}: {
  name: string;
  args?: unknown;
  response?: unknown;
  done: boolean;
}) {
  const [open, setOpen] = useState(false);
  const label = name === A2UI_TOOL ? "渲染 UI" : name;
  const respText =
    response == null
      ? null
      : typeof response === "string"
        ? response
        : JSON.stringify(response, null, 2);
  const truncated =
    respText && respText.length > 2000 ? respText.slice(0, 2000) + "\n…（已截断）" : respText;
  return (
    <motion.div
      className="block-tool"
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      <button className="tool-head" onClick={() => setOpen((o) => !o)} type="button">
        <span className={`tool-dot ${done ? "tool-dot--done" : "tool-dot--running"}`} aria-hidden />
        <span className={`tool-name ${done ? "" : "shimmer"}`}>{label}</span>
        <ChevronRight className={`chev ${open ? "open" : ""}`} />
      </button>
      <div className={`think-collapse ${open ? "open" : ""}`}>
        <div className="think-collapse-inner">
          <div className="tool-detail">
            {args != null && (
              <div className="tool-section">
                <div className="tool-section-label">参数</div>
                <pre className="tool-args">{JSON.stringify(args, null, 2)}</pre>
              </div>
            )}
            {truncated != null && (
              <div className="tool-section">
                <div className="tool-section-label">返回</div>
                <pre className="tool-args tool-result">{truncated}</pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

type AuthBlock = Extract<Block, { kind: "auth" }>;

/** OAuth authorization card for an `adk_request_credential` request (MCP/tool
 *  OAuth). Clicking runs the app's onAuth handler (popup + callback + resume). */
function AuthCard({
  block,
  onAuth,
}: {
  block: AuthBlock;
  onAuth?: (block: AuthBlock) => Promise<void>;
}) {
  const [status, setStatus] = useState<"idle" | "authorizing" | "done" | "error">(
    block.done ? "done" : "idle",
  );
  const [err, setErr] = useState("");

  const toolLabel = block.label || "MCP 工具集";
  const provider = (() => {
    try {
      return block.authUri ? new URL(block.authUri).host : "";
    } catch {
      return "";
    }
  })();

  const go = async () => {
    if (!onAuth) return;
    setErr("");
    setStatus("authorizing");
    try {
      await onAuth(block);
      setStatus("done");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setStatus("idle");
    }
  };

  // Resolved as soon as the credential comes back (block.done is set the moment
  // the callback is captured, before the reply finishes streaming). Collapse the
  // full card into a compact green "已授权" row.
  const resolved = block.done || status === "done";
  if (resolved) {
    return (
      <motion.div
        className="auth-card-collapsed"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2 }}
      >
        <ShieldCheck className="auth-card-icon auth-card-icon--done" />
        <span>已授权 · {toolLabel}</span>
      </motion.div>
    );
  }

  return (
    <motion.div
      className="auth-card"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      <div className="auth-card-head">
        <ShieldCheck className="auth-card-icon" />
        <span className="auth-card-title">{toolLabel} 需要授权</span>
      </div>
      <p className="auth-card-desc">
        工具集 <code className="auth-card-code">{toolLabel}</code> 使用 OAuth 保护，
        需登录授权后方可调用。
        {provider && (
          <>
            {" "}将跳转至 <code className="auth-card-code">{provider}</code> 完成登录，
          </>
        )}
        授权完成后对话自动继续。
      </p>
      <button
        className="auth-card-btn"
        onClick={go}
        disabled={status === "authorizing" || !block.authUri}
      >
        {status === "authorizing" ? (
          <>
            <Loader2 className="cw-i spin" /> 等待授权…
          </>
        ) : (
          <>去授权</>
        )}
      </button>
      {!block.authUri && (
        <div className="auth-card-err">未在事件中找到授权地址。</div>
      )}
      {err && <div className="auth-card-err">{err}</div>}
    </motion.div>
  );
}

export interface BlocksProps {
  blocks: Block[];
  appName?: string;
  onAction: (action: A2uiAction | undefined, node: A2uiComponent) => void;
  /** Handle an MCP/tool OAuth request (opens auth URL, resumes the run). */
  onAuth?: (block: AuthBlock) => Promise<void>;
}

export function Blocks({ blocks, appName = "", onAction, onAuth }: BlocksProps) {
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.kind) {
          case "thinking":
            return <ThinkingBlock key={i} text={b.text} done={b.done} />;
          case "text": {
            const t = b.text.replace(/^\s+/, "");
            return t ? (
              <div key={i} className="bubble">
                <Markdown text={t} />
              </div>
            ) : null;
          }
          case "attachment":
            return <MediaGroup key={i} appName={appName} items={b.files} />;
          case "invocation":
            return <InvocationChips key={i} value={b.value} />;
          case "tool":
            if (b.name === A2UI_TOOL && b.done) return null;
            return (
              <ToolBlock key={i} name={b.name} args={b.args} response={b.response} done={b.done} />
            );
          case "auth":
            return <AuthCard key={i} block={b} onAuth={onAuth} />;
          case "a2ui":
            // Skip surfaces with no renderable root (e.g. a createSurface that
            // was never followed by updateComponents) so we don't emit an empty box.
            return buildSurfaces(b.messages)
              .filter((s) => s.components[s.rootId])
              .map((s) => (
              <motion.div
                key={`${i}-${s.surfaceId}`}
                initial={{ opacity: 0, y: 8, scale: 0.985 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ type: "spring", stiffness: 380, damping: 30 }}
              >
                <SurfaceView surface={s} onAction={onAction} />
              </motion.div>
            ));
          default:
            return null;
        }
      })}
    </>
  );
}
