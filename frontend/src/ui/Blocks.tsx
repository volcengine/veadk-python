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
import { createdAgentsHaveFailure } from "./builtin-tools/createAgentToolCardData";
import { ToolDisclosureIcon } from "./builtin-tools/icons";
import { getBuiltinToolDefinition } from "./builtin-tools/registry";
import type { BranchCompareBranch } from "./builtin-tools/branchCompareData";
import { AgentKitLogoIcon } from "./icons/AgentKitLogoIcon";
import { DeliverySourceIcon } from "./icons/DeliverySourceIcon";
import { DeliveryVerifiedIcon } from "./icons/DeliveryVerifiedIcon";
import { CodeBrowserDialog } from "./CodeBrowserDialog";

const A2UI_TOOL = "send_a2ui_json_to_client";
const STREAM_FRAME_INTERVAL_MS = 28;
const DOWNLOAD_STATUS_DURATION_MS = 3_000;

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
  onComplete?: () => void,
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

  useEffect(() => {
    if (displayed === text) onComplete?.();
  }, [displayed, onComplete, text]);

  useEffect(() => () => {
    if (frameRef.current !== null) {
      window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }, []);

  return displayed;
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

function PlanIcon() {
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
      <path d="m4.5 7 1.8 1.8L9.5 5.5" />
      <path d="M12 7h7.5" />
      <path d="m4.5 13 1.8 1.8 3.2-3.3" />
      <path d="M12 13h7.5" />
      <path d="M5 19h4" />
      <path d="M12 19h7.5" />
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
  answerStarted = false,
  streaming = false,
  onStreamFrame,
}: {
  text: string;
  done: boolean;
  answerStarted?: boolean;
  streaming?: boolean;
  onStreamFrame?: () => void;
}) {
  // Expanded while thinking; auto-collapses when the answer starts. A manual toggle wins.
  const [open, setOpen] = useState(!(done || answerStarted));
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current) setOpen(!(done || answerStarted));
  }, [answerStarted, done]);
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
          <AgentKitLogoIcon className={`thinking-logo ${done ? "" : "is-active"}`} />
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

function BuildProgressBlock({ text }: { text: string }) {
  return (
    <div
      className="block-progress"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="think-head progress-head">
        <span className="think-icon" aria-hidden="true">
          <AgentKitLogoIcon className="thinking-logo is-active" />
        </span>
        <TextShimmer className="think-label" duration={2.4} spread={18}>
          {text}
        </TextShimmer>
      </div>
    </div>
  );
}

function DeliveryCard({
  value,
  onResolve,
  onResolveComparison,
  onDownload,
  onDeploy,
}: {
  value: Extract<Block, { kind: "delivery" }>["value"];
  onResolve?: (
    value: Extract<Block, { kind: "delivery" }>["value"],
  ) => Promise<Extract<Block, { kind: "delivery" }>["value"]>;
  onResolveComparison?: (
    value: Extract<Block, { kind: "delivery" }>["value"],
  ) => Promise<{
    base: Extract<Block, { kind: "delivery" }>["value"];
    target: Extract<Block, { kind: "delivery" }>["value"];
  }>;
  onDownload?: (
    value: Extract<Block, { kind: "delivery" }>["value"],
  ) => Promise<void>;
  onDeploy?: (value: Extract<Block, { kind: "delivery" }>["value"]) => void;
}) {
  const [resolved, setResolved] = useState<
    Extract<Block, { kind: "delivery" }>["value"] | null
  >(value.files ? value : null);
  const [codeOpen, setCodeOpen] = useState(false);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [comparison, setComparison] = useState<{
    base: Extract<Block, { kind: "delivery" }>["value"];
    target: Extract<Block, { kind: "delivery" }>["value"];
  } | null>(null);
  const [busyAction, setBusyAction] = useState<
    "source" | "compare" | "download" | "deploy" | null
  >(null);
  const [error, setError] = useState("");
  const [downloadStatus, setDownloadStatus] = useState<{
    message: string;
  } | null>(null);
  const validatedAt = new Date(value.validatedAt);
  const time = !value.validatedAt
    ? "刚刚"
    : Number.isNaN(validatedAt.getTime())
      ? value.validatedAt
      : validatedAt.toLocaleString("zh-CN", { hour12: false });

  useEffect(() => {
    if (!downloadStatus) return;
    const timer = window.setTimeout(
      () => setDownloadStatus(null),
      DOWNLOAD_STATUS_DURATION_MS,
    );
    return () => window.clearTimeout(timer);
  }, [downloadStatus]);

  async function resolveDelivery() {
    if (resolved) return resolved;
    if (!onResolve) throw new Error("暂时无法读取生成的源码，请稍后重试。");
    const delivery = await onResolve(value);
    setResolved(delivery);
    return delivery;
  }

  async function openSource() {
    setBusyAction("source");
    setError("");
    setDownloadStatus(null);
    try {
      await resolveDelivery();
      setCodeOpen(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusyAction(null);
    }
  }

  async function download() {
    if (!onDownload) return;
    setBusyAction("download");
    setError("");
    setDownloadStatus(null);
    try {
      await onDownload(value);
      setDownloadStatus({ message: "已开始下载" });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusyAction(null);
    }
  }

  async function openComparison() {
    if (!onResolveComparison) return;
    setBusyAction("compare");
    setError("");
    setDownloadStatus(null);
    try {
      const result = comparison ?? await onResolveComparison(value);
      setComparison(result);
      setComparisonOpen(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusyAction(null);
    }
  }

  async function deploy() {
    setBusyAction("deploy");
    setError("");
    setDownloadStatus(null);
    try {
      onDeploy?.(await resolveDelivery());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <>
      <section
        className={`delivery-card${value.verified ? " is-verified" : " is-unverified"}`}
        aria-label={value.verified ? "已验证交付物" : "生成的 Agent 源码"}
      >
        <header className="delivery-card-header">
          <span className="delivery-card-icon">
            {value.verified ? <DeliveryVerifiedIcon /> : <DeliverySourceIcon />}
          </span>
          <div>
            <strong>{value.verified ? "已验证交付物" : "生成的 Agent 源码"}</strong>
            <span>{value.agentName}</span>
          </div>
        </header>
        <dl className="delivery-card-grid">
          <div>
            <dt>入口</dt>
            <dd><code>{value.entryPoint}</code></dd>
          </div>
          <div>
            <dt>文件数</dt>
            <dd>{value.fileCount}</dd>
          </div>
          <div>
            <dt>大小</dt>
            <dd>{(value.artifactSize / 1024).toFixed(1)} KiB</dd>
          </div>
          <div>
            <dt>{value.verified ? "验证时间" : "生成时间"}</dt>
            <dd>{time}</dd>
          </div>
        </dl>
        <p className="delivery-card-gates">
          {value.verified
            ? `${value.gateSummary.length} 项检查通过`
            : "源码已准备好，可部署"} ·{" "}
          <code>{value.artifactSha256.slice(0, 12)}</code>
        </p>
        {!value.verified ? (
          <p className="delivery-card-guidance">
            源码已准备好，可查看、下载或部署；部署前请确认 Runtime 配置。
          </p>
        ) : null}
        <div className="delivery-card-actions">
          <button
            type="button"
            className="delivery-card-secondary"
            onClick={() => void openSource()}
            disabled={!onResolve || busyAction !== null}
          >
            {busyAction === "source" ? (
              <Loader2 className="spin" aria-hidden="true" />
            ) : null}
            查看源码
          </button>
          {value.projectId && value.versionId && value.parentVersionId ? (
            <button
              type="button"
              className="delivery-card-secondary"
              onClick={() => void openComparison()}
              disabled={!onResolveComparison || busyAction !== null}
            >
              {busyAction === "compare" ? (
                <Loader2 className="spin" aria-hidden="true" />
              ) : null}
              {busyAction === "compare" ? "正在准备…" : "查看本次变更"}
            </button>
          ) : null}
          <button
            type="button"
            className="delivery-card-secondary"
            onClick={() => void download()}
            disabled={!onDownload || busyAction !== null}
            aria-busy={busyAction === "download"}
          >
            {busyAction === "download" ? (
              <Loader2 className="spin" aria-hidden="true" />
            ) : null}
            {busyAction === "download" ? "正在准备…" : "下载源码"}
          </button>
          <button
            type="button"
            onClick={() => void deploy()}
            disabled={
              !value.deployable || !onDeploy || !onResolve || busyAction !== null
            }
            title={value.deployable ? undefined : "源码尚未准备好"}
          >
            {busyAction === "deploy" ? (
              <Loader2 className="spin" aria-hidden="true" />
            ) : null}
            手动部署到 Runtime
          </button>
        </div>
        {error ? <p className="delivery-card-error" role="alert">{error}</p> : null}
        {downloadStatus ? (
          <p className="delivery-card-status" role="status" aria-live="polite">
            {downloadStatus.message}
          </p>
        ) : null}
      </section>
      <CodeBrowserDialog
        project={{ name: value.agentName, files: resolved?.files ?? [] }}
        open={codeOpen}
        onClose={() => setCodeOpen(false)}
        onChange={() => {}}
        readOnly
      />
      <CodeBrowserDialog
        project={{
          name: comparison?.target.agentName ?? value.agentName,
          files: comparison?.target.files ?? [],
        }}
        comparison={comparison ? {
          baseProject: {
            name: comparison.base.agentName,
            files: comparison.base.files ?? [],
          },
          baseLabel: "优化前",
          targetLabel: "优化后",
        } : undefined}
        open={comparisonOpen}
        onClose={() => setComparisonOpen(false)}
        onChange={() => {}}
        readOnly
      />
    </>
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
  onStreamComplete,
}: {
  text: string;
  streaming: boolean;
  onStreamFrame?: () => void;
  onStreamComplete?: () => void;
}) {
  const displayedText = useSmoothStreamingText(
    text,
    streaming,
    onStreamFrame,
    onStreamComplete,
  );
  return displayedText ? (
    <div className="bubble">
      <Markdown text={displayedText} streaming={streaming} />
    </div>
  ) : null;
});

type PlanBlockValue = Extract<Block, { kind: "plan" }>;

const PLAN_STATUS_LABELS: Record<PlanBlockValue["items"][number]["status"], string> = {
  pending: "待处理",
  in_progress: "进行中",
  completed: "已完成",
  failed: "未完成",
};

function PlanBlock({
  title,
  summary,
  items,
  done,
}: Omit<PlanBlockValue, "kind">) {
  const [open, setOpen] = useState(!done);
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current) setOpen(!done);
  }, [done]);
  const toggle = () => {
    touched.current = true;
    setOpen((value) => !value);
  };

  return (
    <div className="block-plan">
      <button
        className="plan-head"
        type="button"
        onClick={toggle}
        aria-expanded={items.length > 0 ? open : undefined}
        disabled={items.length === 0}
      >
        <span className="plan-icon" aria-hidden="true">
          <PlanIcon />
        </span>
        {done ? (
          <span className="plan-title">{title}</span>
        ) : (
          <TextShimmer className="plan-title" duration={2.2} spread={15}>
            {title}
          </TextShimmer>
        )}
        {summary ? <span className="plan-summary">{summary}</span> : null}
        {items.length > 0 ? (
          <ToolDisclosureIcon className={`plan-chevron${open ? " is-open" : ""}`} />
        ) : null}
      </button>
      <div className={`think-collapse ${open && items.length > 0 ? "open" : ""}`}>
        <div className="think-collapse-inner">
          {items.length > 0 ? (
            <ol className="plan-items">
              {items.map((item, index) => (
                <li data-status={item.status} key={`${index}:${item.text}`}>
                  <span className="plan-item-marker" aria-hidden="true" />
                  <span className="plan-item-text">{item.text}</span>
                  <small>{PLAN_STATUS_LABELS[item.status]}</small>
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      </div>
    </div>
  );
}

interface StudioToolArtifact {
  name: string;
  contentUrl: string;
}

function studioToolArtifacts(response: unknown): StudioToolArtifact[] {
  if (!response || typeof response !== "object") return [];
  const record = response as Record<string, unknown>;
  const nested = record.result;
  let candidates: unknown[] = [];
  if (Array.isArray(record.studio_artifacts)) {
    candidates = record.studio_artifacts;
  } else if (nested && typeof nested === "object") {
    const nestedArtifacts = (nested as Record<string, unknown>).studio_artifacts;
    if (Array.isArray(nestedArtifacts)) candidates = nestedArtifacts;
  }
  return candidates.flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object") return [];
    const artifact = candidate as Record<string, unknown>;
    return typeof artifact.name === "string" && typeof artifact.contentUrl === "string"
      ? [{ name: artifact.name, contentUrl: artifact.contentUrl }]
      : [];
  });
}

/** Tool-call row. Dedicated built-ins use their registered icon and Chinese
 *  status copy; other tools use a neutral repository-drawn tool icon. Both
 *  treatments share the same header and detail alignment. */
function ToolBlock({
  name,
  args,
  response,
  done,
  status,
  defaultOpen = false,
  retrying = false,
  onBranchSelect,
}: {
  name: string;
  args?: unknown;
  response?: unknown;
  done: boolean;
  status?: "running" | "completed" | "failed";
  defaultOpen?: boolean;
  retrying?: boolean;
  onBranchSelect?: (branch: BranchCompareBranch) => void;
}) {
  const inferredCreateAgentFailure = name === "create_agents"
    && done
    && createdAgentsHaveFailure(args, response);
  const toolStatus = inferredCreateAgentFailure
    ? "failed"
    : status ?? (done ? "completed" : "running");
  const isAdjustingAgent = name === "create_agents"
    && toolStatus === "failed"
    && retrying;
  const builtinTool = getBuiltinToolDefinition(name);
  const DetailRenderer = builtinTool?.detailRenderer;
  const hideHeader = builtinTool?.hideHeader === true;
  const shouldDefaultOpen = hideHeader || defaultOpen || Boolean(DetailRenderer);
  const [open, setOpen] = useState(shouldDefaultOpen);
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current && shouldDefaultOpen) setOpen(true);
  }, [shouldDefaultOpen]);
  const toggle = () => {
    touched.current = true;
    setOpen((value) => !value);
  };
  const label = name === A2UI_TOOL ? "渲染 UI" : name;
  const studioArtifacts = studioToolArtifacts(response);
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
      data-status={toolStatus}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      {builtinTool && !hideHeader ? (
        <BuiltinToolHeader
          definition={builtinTool}
          label={isAdjustingAgent
            ? "Agent 正在调整"
            : toolStatus === "failed"
              ? builtinTool.failedLabel
              : loadSkillLabel(name, args)}
          done={done}
          open={open}
          onToggle={toggle}
        />
      ) : !builtinTool ? (
        <button
          className="tool-head tool-head--generic"
          onClick={toggle}
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
      ) : null}
      <div className={`${hideHeader ? "" : "think-collapse "}${open ? "open" : ""}`}>
        <div className="think-collapse-inner">
          {DetailRenderer ? (
            <DetailRenderer
              args={args}
              response={response}
              status={toolStatus}
              onBranchSelect={onBranchSelect}
            />
          ) : <div className="tool-detail">
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
            {studioArtifacts.length > 0 && (
              <div className="tool-section">
                <div className="tool-section-label">产物</div>
                <div className="studio-tool-artifacts">
                  {studioArtifacts.map((artifact) => (
                    <a
                      key={`${artifact.contentUrl}:${artifact.name}`}
                      href={artifact.contentUrl}
                      download={artifact.name}
                    >
                      下载 {artifact.name}
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>}
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
  onStreamComplete?: () => void;
  onAction: (action: A2uiAction | undefined, node: A2uiComponent) => void;
  /** Handle an MCP/tool OAuth request (opens auth URL, resumes the run). */
  onAuth?: (block: AuthBlock) => Promise<void>;
  onArtifactDownload?: (filename: string, version: number) => Promise<void>;
  onArtifactPreview?: (filename: string, version: number) => Promise<string>;
  onResolveDelivery?: (
    delivery: Extract<Block, { kind: "delivery" }>["value"],
  ) => Promise<Extract<Block, { kind: "delivery" }>["value"]>;
  onResolveDeliveryComparison?: (
    delivery: Extract<Block, { kind: "delivery" }>["value"],
  ) => Promise<{
    base: Extract<Block, { kind: "delivery" }>["value"];
    target: Extract<Block, { kind: "delivery" }>["value"];
  }>;
  onDownloadDelivery?: (
    delivery: Extract<Block, { kind: "delivery" }>["value"],
  ) => Promise<void>;
  onDeployDelivery?: (delivery: Extract<Block, { kind: "delivery" }>["value"]) => void;
  onBranchSelect?: (branch: BranchCompareBranch) => void;
}

export function Blocks({
  blocks,
  appName = "",
  streaming = false,
  onStreamFrame,
  onStreamComplete,
  onAction,
  onAuth,
  onArtifactDownload,
  onArtifactPreview,
  onResolveDelivery,
  onResolveDeliveryComparison,
  onDownloadDelivery,
  onDeployDelivery,
  onBranchSelect,
}: BlocksProps) {
  const lastTextBlockIndex = blocks.reduce(
    (lastIndex, block, index) => block.kind === "text" ? index : lastIndex,
    -1,
  );
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.kind) {
          case "progress":
            return <BuildProgressBlock key="build-progress" text={b.text} />;
          case "thinking": {
            const answerStarted = blocks.slice(i + 1).some(
              (block) => block.kind === "text" && Boolean(block.text.trim()),
            );
            return (
              <ThinkingBlock
                key={i}
                text={b.text}
                done={b.done}
                answerStarted={answerStarted}
                streaming={streaming}
                onStreamFrame={onStreamFrame}
              />
            );
          }
          case "text": {
            const t = b.text.replace(/^\s+/, "");
            return t ? (
              <StreamingTextBlock
                key={i}
                text={t}
                streaming={streaming}
                onStreamFrame={onStreamFrame}
                onStreamComplete={i === lastTextBlockIndex
                  ? onStreamComplete
                  : undefined}
              />
            ) : null;
          }
          case "plan":
            return (
              <PlanBlock
                key={i}
                title={b.title}
                summary={b.summary}
                items={b.items}
                done={b.done}
              />
            );
          case "attachment":
            return <MediaGroup key={i} appName={appName} items={b.files} />;
          case "artifact":
            return <ArtifactCard key={i} block={b} onDownload={onArtifactDownload} onPreview={onArtifactPreview} />;
          case "delivery":
            return (
              <DeliveryCard
                key={i}
                value={b.value}
                onResolve={onResolveDelivery}
                onResolveComparison={onResolveDeliveryComparison}
                onDownload={onDownloadDelivery}
                onDeploy={onDeployDelivery}
              />
            );
          case "invocation":
            return <InvocationChips key={i} value={b.value} />;
          case "tool": {
            if (b.name === A2UI_TOOL && b.done) return null;
            const hasLaterCreateAgentAttempt = b.name === "create_agents"
              && blocks.slice(i + 1).some(
                (block) => block.kind === "tool" && block.name === "create_agents",
              );
            return (
              <ToolBlock
                key={i}
                name={b.name}
                args={b.args}
                response={b.response}
                done={b.done}
                status={b.status}
                defaultOpen={b.defaultOpen}
                retrying={b.name === "create_agents"
                  && (streaming || hasLaterCreateAgentAttempt)}
                onBranchSelect={onBranchSelect}
              />
            );
          }
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
