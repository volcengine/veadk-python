import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ChevronRight, Download, Eye, FileText, Loader2, ShieldCheck, X } from "lucide-react";
import { motion } from "motion/react";
import type { Block } from "../blocks";
import { buildSurfaces, SurfaceView } from "../a2ui/Surface";
import { useStickToBottom } from "./useStickToBottom";
import { Markdown } from "./Markdown";
import { InvocationChips } from "./InvocationChips";
import { MediaGroup } from "./Media";
import type { A2uiAction, A2uiComponent } from "../a2ui/types";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import { BuiltinToolHeader } from "./builtin-tools/BuiltinToolHeader";
import { ToolDisclosureIcon } from "./builtin-tools/icons";
import { getBuiltinToolDefinition } from "./builtin-tools/registry";

const A2UI_TOOL = "send_a2ui_json_to_client";
const STREAM_FRAME_INTERVAL_MS = 28;

function advanceCodePoints(text: string, start: number, count: number): number {
  let index = start;
  for (let step = 0; step < count && index < text.length; step += 1) {
    const codePoint = text.codePointAt(index);
    index += codePoint !== undefined && codePoint > 0xffff ? 2 : 1;
  }
  return index;
}

function streamChunkSize(remaining: number): number {
  if (remaining <= 4) return 1;
  return Math.min(18, Math.max(2, Math.ceil(remaining / 6)));
}

function useSmoothStreamingText(
  text: string,
  streaming: boolean,
  onFrame?: () => void,
): string {
  const [displayed, setDisplayed] = useState(() => (streaming ? "" : text));
  const displayedRef = useRef(displayed);
  const targetRef = useRef(text);
  const frameRef = useRef<number | null>(null);
  const lastFrameRef = useRef(0);
  const onFrameRef = useRef(onFrame);
  targetRef.current = text;
  onFrameRef.current = onFrame;

  useEffect(() => {
    const current = displayedRef.current;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!streaming || reduceMotion || !text.startsWith(current)) {
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      if (current !== text) {
        displayedRef.current = text;
        setDisplayed(text);
      }
      return;
    }
    if (current === text || frameRef.current !== null) return;

    const renderFrame = (timestamp: number) => {
      const target = targetRef.current;
      const visible = displayedRef.current;
      if (!target.startsWith(visible)) {
        displayedRef.current = target;
        setDisplayed(target);
        frameRef.current = null;
        return;
      }
      if (timestamp - lastFrameRef.current < STREAM_FRAME_INTERVAL_MS) {
        frameRef.current = window.requestAnimationFrame(renderFrame);
        return;
      }

      const remaining = target.length - visible.length;
      if (remaining <= 0) {
        frameRef.current = null;
        return;
      }
      const end = advanceCodePoints(
        target,
        visible.length,
        streamChunkSize(remaining),
      );
      const next = target.slice(0, end);
      displayedRef.current = next;
      lastFrameRef.current = timestamp;
      setDisplayed(next);
      frameRef.current = next === target
        ? null
        : window.requestAnimationFrame(renderFrame);
    };

    frameRef.current = window.requestAnimationFrame(renderFrame);
  }, [streaming, text]);

  useLayoutEffect(() => {
    onFrameRef.current?.();
  }, [displayed]);

  useEffect(() => () => {
    if (frameRef.current !== null) {
      window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  return displayed;
}

/** Hand-drawn "spark" icon for the thinking indicator. */
function SparkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2.2l1.7 5.1a3 3 0 0 0 1.9 1.9L20.8 11l-5.1 1.7a3 3 0 0 0-1.9 1.9L12 19.8l-1.7-5.1a3 3 0 0 0-1.9-1.9L3.2 11l5.1-1.7a3 3 0 0 0 1.9-1.9L12 2.2z" />
    </svg>
  );
}

/** Repository-drawn neutral icon for tools without a dedicated treatment. */
function GenericToolIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M14.3 5.25a4.6 4.6 0 0 0-5.55 5.55L3.6 15.95a1.8 1.8 0 0 0 0 2.55l1.9 1.9a1.8 1.8 0 0 0 2.55 0l5.15-5.15a4.6 4.6 0 0 0 5.55-5.55l-2.9 2.9-2.45-.55-.55-2.45 2.9-2.9a4.6 4.6 0 0 0-1.45-1.45Z" />
    </svg>
  );
}

function loadSkillLabel(name: string, args: unknown): string | undefined {
  if (name !== "load_skill" || args == null || typeof args !== "object" || Array.isArray(args)) {
    return undefined;
  }
  const skillName = (args as Record<string, unknown>).skill_name;
  if (typeof skillName !== "string" || !skillName.trim()) return undefined;
  return `使用 ${skillName.trim()} 技能`;
}

export function ThinkingBlock({
  text,
  done,
  streaming = false,
  onStreamFrame,
}: {
  text: string;
  done: boolean;
  streaming?: boolean;
  onStreamFrame?: () => void;
}) {
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
  const displayedBody = useSmoothStreamingText(body, !done || streaming, onStreamFrame);
  const { ref, onScroll } = useStickToBottom<HTMLDivElement>(displayedBody);
  return (
    <div className="block-thinking">
      <button className="think-head" onClick={toggle} type="button">
        <span className="think-icon" aria-hidden="true">
          <SparkIcon className={`spark ${done ? "" : "pulse"}`} />
        </span>
        {done ? (
          <span className="think-label think-label--done">已完成思考</span>
        ) : (
          <TextShimmer className="think-label" duration={2.4} spread={18}>
            思考中
          </TextShimmer>
        )}
        <ChevronRight className={`chev ${open ? "open" : ""}`} />
      </button>
      <div className={`think-collapse ${open && displayedBody ? "open" : ""}`}>
        <div className="think-collapse-inner">
          <div className="think-body scroll" ref={ref} onScroll={onScroll}>
            {displayedBody}
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

const StreamingTextBlock = memo(function StreamingTextBlock({
  text,
  streaming,
  onStreamFrame,
}: {
  text: string;
  streaming: boolean;
  onStreamFrame?: () => void;
}) {
  const displayedText = useSmoothStreamingText(text, streaming, onStreamFrame);
  return displayedText ? (
    <div className="bubble">
      <Markdown text={displayedText} />
    </div>
  ) : null;
});

/** Tool-call row. Dedicated built-ins use their registered icon and Chinese
 *  status copy; other tools use a neutral repository-drawn tool icon. Both
 *  treatments share the same header and detail alignment. */
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
  const builtinTool = getBuiltinToolDefinition(name);
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
      className={`block-tool${builtinTool ? " block-tool--builtin" : ""}`}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      {builtinTool ? (
        <BuiltinToolHeader
          definition={builtinTool}
          label={loadSkillLabel(name, args)}
          done={done}
          open={open}
          onToggle={() => setOpen((value) => !value)}
        />
      ) : (
        <button
          className="tool-head tool-head--generic"
          onClick={() => setOpen((o) => !o)}
          type="button"
          aria-expanded={open}
        >
          <span className="tool-icon tool-icon--generic" aria-hidden="true">
            <GenericToolIcon />
          </span>
          {done ? (
            <span className="tool-name">{label}</span>
          ) : (
            <TextShimmer className="tool-name" duration={2.2} spread={15}>
              {label}
            </TextShimmer>
          )}
          <ToolDisclosureIcon className={`tool-chevron${open ? " is-open" : ""}`} />
        </button>
      )}
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
type ArtifactBlock = Extract<Block, { kind: "artifact" }>;

function ArtifactCard({
  block,
  onDownload,
  onPreview,
}: {
  block: ArtifactBlock;
  onDownload?: (filename: string, version: number) => Promise<void>;
  onPreview?: (filename: string, version: number) => Promise<string>;
}) {
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{ name: string; url: string } | null>(null);
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview.url);
  }, [preview]);

  const closePreview = () => setPreview(null);
  const download = async (filename: string, version: number) => {
    if (!onDownload) return;
    setPending(`download:${filename}`);
    setError("");
    try {
      await onDownload(filename, version);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending("");
    }
  };
  const openPreview = async (filename: string, version: number, name: string) => {
    if (!onPreview) return;
    setPending(`preview:${name}`);
    setError("");
    try {
      const url = await onPreview(filename, version);
      setPreview({ name, url });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPending("");
    }
  };
  const files = block.files.filter((file) => !file.filename.endsWith(".preview.webp"));
  return (
    <div className="artifact-list">
      {files.map((file) => {
        const previewName = `${file.filename.replace(/\.pptx$/i, "")}.preview.webp`;
        const previewFile = block.files.find((item) => item.filename === previewName);
        return (
        <div
          className="artifact-card"
          key={`${file.filename}:${file.version}`}
        >
          <span className="artifact-card__icon" aria-hidden="true">
            <FileText />
          </span>
          <span className="artifact-card__copy">
            <span className="artifact-card__name">{file.filename}</span>
            <span className="artifact-card__hint">PowerPoint 演示文稿</span>
          </span>
          <span className="artifact-card__actions">
            {previewFile && (
              <button
                className="artifact-card__action"
                type="button"
                disabled={!onPreview || pending !== ""}
                onClick={() => void openPreview(previewFile.filename, previewFile.version, file.filename)}
              >
                {pending === `preview:${file.filename}` ? <Loader2 className="spin" /> : <Eye />}
                预览
              </button>
            )}
            <button
              className="artifact-card__action artifact-card__action--primary"
              type="button"
              disabled={!onDownload || pending !== ""}
              onClick={() => void download(file.filename, file.version)}
            >
              {pending === `download:${file.filename}` ? <Loader2 className="spin" /> : <Download />}
              下载
            </button>
          </span>
        </div>
      )})}
      {error && <div className="artifact-card__error">{error}</div>}
      {preview && (
        <div className="artifact-preview" role="dialog" aria-modal="true" aria-label={`${preview.name} 预览`}>
          <button className="artifact-preview__backdrop" type="button" aria-label="关闭预览" onClick={closePreview} />
          <div className="artifact-preview__panel">
            <div className="artifact-preview__header">
              <span>{preview.name}</span>
              <button type="button" aria-label="关闭预览" onClick={closePreview}><X /></button>
            </div>
            <div className="artifact-preview__canvas">
              <img src={preview.url} alt={`${preview.name} 幻灯片预览`} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

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
  streaming?: boolean;
  onStreamFrame?: () => void;
  onAction: (action: A2uiAction | undefined, node: A2uiComponent) => void;
  /** Handle an MCP/tool OAuth request (opens auth URL, resumes the run). */
  onAuth?: (block: AuthBlock) => Promise<void>;
  onArtifactDownload?: (filename: string, version: number) => Promise<void>;
  onArtifactPreview?: (filename: string, version: number) => Promise<string>;
}

export function Blocks({
  blocks,
  appName = "",
  streaming = false,
  onStreamFrame,
  onAction,
  onAuth,
  onArtifactDownload,
  onArtifactPreview,
}: BlocksProps) {
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.kind) {
          case "thinking":
            return (
              <ThinkingBlock
                key={i}
                text={b.text}
                done={b.done}
                streaming={streaming}
                onStreamFrame={onStreamFrame}
              />
            );
          case "text": {
            const t = b.text.replace(/^\s+/, "");
            return t ? (
              <StreamingTextBlock
                key={i}
                text={t}
                streaming={streaming}
                onStreamFrame={onStreamFrame}
              />
            ) : null;
          }
          case "attachment":
            return <MediaGroup key={i} appName={appName} items={b.files} />;
          case "artifact":
            return <ArtifactCard key={i} block={b} onDownload={onArtifactDownload} onPreview={onArtifactPreview} />;
          case "invocation":
            return <InvocationChips key={i} value={b.value} />;
          case "tool":
            if (b.name === A2UI_TOOL && b.done) return null;
            return (
              <ToolBlock key={i} name={b.name} args={b.args} response={b.response} done={b.done} />
            );
          case "agent-transfer":
            return null;
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
