import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ChevronRight,
  Download,
  Eye,
  FileText,
  Loader2,
  ShieldCheck,
  X,
} from "lucide-react";
import { motion } from "motion/react";
import { Trans, useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
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
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    if (!streaming || reduceMotion || !text.startsWith(current)) {
      if (frameRef.current !== null)
        window.cancelAnimationFrame(frameRef.current);
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
      frameRef.current =
        next === target ? null : window.requestAnimationFrame(renderFrame);
    };

    frameRef.current = window.requestAnimationFrame(renderFrame);
  }, [streaming, text]);

  useLayoutEffect(() => {
    onFrameRef.current?.();
  }, [displayed]);

  useEffect(() => {
    if (displayed === text) onComplete?.();
  }, [displayed, onComplete, text]);

  useEffect(
    () => () => {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    },
    [],
  );

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

function SandboxHandoffIcon() {
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
      <path d="M5 5v7.25A3.75 3.75 0 0 0 8.75 16H19" />
      <path d="m15.5 12.5 3.5 3.5-3.5 3.5" />
    </svg>
  );
}

function CodexSandboxIdentity({
  activity,
}: {
  activity: NonNullable<Extract<Block, { kind: "tool" }>["codexActivity"]>;
}) {
  const { t } = useTranslation("conversation");
  const details: Array<[string, string | undefined]> = [
    ["Agent Session", activity.agentSessionId],
    ["Sandbox Session", activity.sandboxSessionId],
    ["Codex Thread", activity.threadId],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));
  if (!details.length) return null;
  return (
    <dl
      className="codex-sandbox-run__identity"
      aria-label={t("blocks.sandboxIdentity")}
    >
      {details.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd title={value}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function loadSkillLabel(name: string, args: unknown, t: TFunction): string | undefined {
  if (
    name !== "load_skill" ||
    args == null ||
    typeof args !== "object" ||
    Array.isArray(args)
  ) {
    return undefined;
  }
  const skillName = (args as Record<string, unknown>).skill_name;
  if (typeof skillName !== "string" || !skillName.trim()) return undefined;
  return t("blocks.useSkill", { name: skillName.trim() });
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
  const { t } = useTranslation("conversation");
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
  const body = text
    .replace(/\r\n?/g, "\n")
    .trimStart()
    .split(/\n{2,}/)
    .map((paragraph) =>
      paragraph.replace(/[^\S\n]*\n[^\S\n]*/g, (lineBreak, offset, source) => {
        const before = source[offset - 1] ?? "";
        const after = source[offset + lineBreak.length] ?? "";
        if (!before || !after) return "";
        if (/\p{Script=Han}/u.test(before) && /\p{Script=Han}/u.test(after)) {
          return "";
        }
        if (
          /[(\[{“‘/]/u.test(before) ||
          /[),.\]}，。！？；：、”’]/u.test(after)
        ) {
          return "";
        }
        return " ";
      }),
    )
    .join("\n\n");
  const displayedBody = useSmoothStreamingText(
    body,
    !done || streaming,
    onStreamFrame,
  );
  const { ref, onScroll } = useStickToBottom<HTMLDivElement>(displayedBody);
  return (
    <div className="block-thinking">
      <button className="think-head" onClick={toggle} type="button">
        <span className="think-icon" aria-hidden="true">
          <AgentKitLogoIcon
            className={`thinking-logo ${done ? "" : "is-active"}`}
          />
        </span>
        {done ? (
          <span className="think-label think-label--done">{t("blocks.thinkingDone")}</span>
        ) : (
          <TextShimmer className="think-label" duration={2.4} spread={18}>
            {t("blocks.thinking")}
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
  const { t, i18n } = useTranslation("conversation");
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
    ? t("blocks.justNow")
    : Number.isNaN(validatedAt.getTime())
      ? value.validatedAt
      : validatedAt.toLocaleString(i18n.resolvedLanguage ?? i18n.language, { hour12: false });

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
    if (!onResolve) throw new Error(t("blocks.sourceUnavailable"));
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
      setDownloadStatus({ message: t("blocks.downloadStarted") });
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
      const result = comparison ?? (await onResolveComparison(value));
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
        aria-label={value.verified ? t("blocks.verifiedDelivery") : t("blocks.generatedSource")}
      >
        <header className="delivery-card-header">
          <span className="delivery-card-icon">
            {value.verified ? <DeliveryVerifiedIcon /> : <DeliverySourceIcon />}
          </span>
          <div>
            <strong>
              {value.verified ? t("blocks.verifiedDelivery") : t("blocks.generatedSource")}
            </strong>
            <span>{value.agentName}</span>
          </div>
        </header>
        <dl className="delivery-card-grid">
          <div>
            <dt>{t("blocks.entryPoint")}</dt>
            <dd>
              <code>{value.entryPoint}</code>
            </dd>
          </div>
          <div>
            <dt>{t("blocks.fileCount")}</dt>
            <dd>{value.fileCount}</dd>
          </div>
          <div>
            <dt>{t("blocks.size")}</dt>
            <dd>{(value.artifactSize / 1024).toFixed(1)} KiB</dd>
          </div>
          <div>
            <dt>{value.verified ? t("blocks.validationTime") : t("blocks.generationTime")}</dt>
            <dd>{time}</dd>
          </div>
        </dl>
        <p className="delivery-card-gates">
          {value.verified
            ? t("blocks.checksPassed", { count: value.gateSummary.length })
            : t("blocks.sourceReady")}{" "}
          · <code>{value.artifactSha256.slice(0, 12)}</code>
        </p>
        {!value.verified ? (
          <p className="delivery-card-guidance">
            {t("blocks.sourceGuidance")}
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
            {t("blocks.viewSource")}
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
              {busyAction === "compare" ? t("blocks.preparing") : t("blocks.viewChanges")}
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
            {busyAction === "download" ? t("blocks.preparing") : t("blocks.downloadSource")}
          </button>
          <button
            type="button"
            onClick={() => void deploy()}
            disabled={
              !value.deployable ||
              !onDeploy ||
              !onResolve ||
              busyAction !== null
            }
            title={value.deployable ? undefined : t("blocks.sourceNotReady")}
          >
            {busyAction === "deploy" ? (
              <Loader2 className="spin" aria-hidden="true" />
            ) : null}
            {t("blocks.manualDeploy")}
          </button>
        </div>
        {error ? (
          <p className="delivery-card-error" role="alert">
            {error}
          </p>
        ) : null}
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
        comparison={
          comparison
            ? {
                baseProject: {
                  name: comparison.base.agentName,
                  files: comparison.base.files ?? [],
                },
                baseLabel: t("blocks.beforeOptimization"),
                targetLabel: t("blocks.afterOptimization"),
              }
            : undefined
        }
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

function PlanBlock({
  title,
  summary,
  items,
  done,
}: Omit<PlanBlockValue, "kind">) {
  const { t } = useTranslation("conversation");
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
          <ToolDisclosureIcon
            className={`plan-chevron${open ? " is-open" : ""}`}
          />
        ) : null}
      </button>
      <div
        className={`think-collapse ${open && items.length > 0 ? "open" : ""}`}
      >
        <div className="think-collapse-inner">
          {items.length > 0 ? (
            <ol className="plan-items">
              {items.map((item, index) => (
                <li data-status={item.status} key={`${index}:${item.text}`}>
                  <span className="plan-item-marker" aria-hidden="true" />
                  <span className="plan-item-text">{item.text}</span>
                  <small>{t(`blocks.planStatuses.${item.status}`)}</small>
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
    const nestedArtifacts = (nested as Record<string, unknown>)
      .studio_artifacts;
    if (Array.isArray(nestedArtifacts)) candidates = nestedArtifacts;
  }
  return candidates.flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object") return [];
    const artifact = candidate as Record<string, unknown>;
    return typeof artifact.name === "string" &&
      typeof artifact.contentUrl === "string"
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
  codexActivity,
  onBranchSelect,
  onAction,
}: {
  name: string;
  args?: unknown;
  response?: unknown;
  done: boolean;
  status?: "running" | "completed" | "failed";
  defaultOpen?: boolean;
  retrying?: boolean;
  codexActivity?: Extract<Block, { kind: "tool" }>["codexActivity"];
  onBranchSelect?: (branch: BranchCompareBranch) => void;
  onAction: BlocksProps["onAction"];
}) {
  const { t } = useTranslation("conversation");
  const inferredCreateAgentFailure =
    name === "create_agents" &&
    done &&
    createdAgentsHaveFailure(args, response);
  const toolStatus = inferredCreateAgentFailure
    ? "failed"
    : (status ?? (done ? "completed" : "running"));
  const isAdjustingAgent =
    name === "create_agents" && toolStatus === "failed" && retrying;
  const builtinTool = getBuiltinToolDefinition(name);
  const DetailRenderer = builtinTool?.detailRenderer;
  const hideHeader = builtinTool?.hideHeader === true;
  const shouldDefaultOpen =
    hideHeader ||
    defaultOpen ||
    Boolean(DetailRenderer) ||
    Boolean(codexActivity);
  const [open, setOpen] = useState(shouldDefaultOpen);
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current && shouldDefaultOpen) setOpen(true);
  }, [shouldDefaultOpen]);
  const toggle = () => {
    touched.current = true;
    setOpen((value) => !value);
  };
  const label = name === A2UI_TOOL ? t("blocks.renderUi") : name;
  const studioArtifacts = studioToolArtifacts(response);
  const respText =
    response == null
      ? null
      : typeof response === "string"
        ? response
        : JSON.stringify(response, null, 2);
  const truncated =
    respText && respText.length > 2000
      ? `${respText.slice(0, 2000)}\n${t("blocks.truncated")}`
      : respText;
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
          label={
            isAdjustingAgent
              ? t("blocks.agentAdjusting")
              : toolStatus === "failed"
                ? t(`blocks.tools.${builtinTool.name}.failed`, {
                    defaultValue: builtinTool.failedLabel ?? builtinTool.doneLabel,
                  })
                : loadSkillLabel(name, args, t)
          }
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
          <ToolDisclosureIcon
            className={`tool-chevron${open ? " is-open" : ""}`}
          />
        </button>
      ) : null}
      <div
        className={`${hideHeader ? "" : "think-collapse "}${open ? "open" : ""}`}
      >
        <div className="think-collapse-inner">
          {codexActivity ? (
            <section
              className="codex-sandbox-run"
              aria-label={t("blocks.sandboxDetails")}
            >
              <div className="codex-sandbox-run__label">
                <span className="codex-sandbox-run__badge">
                  <SandboxHandoffIcon />
                  <span>Codex Sandbox</span>
                </span>
                <span className="codex-sandbox-run__title">
                  {codexActivity.title}
                </span>
              </div>
              <CodexSandboxIdentity activity={codexActivity} />
              <div className="codex-sandbox-run__stream">
                {codexActivity.items.length > 0 ? (
                  <Blocks
                    blocks={codexActivity.items.map((item) => item.block)}
                    streaming={!done}
                    onAction={onAction}
                  />
                ) : (
                  <TextShimmer className="codex-sandbox-run__empty">
                    {t("blocks.waitingCodex")}
                  </TextShimmer>
                )}
              </div>
            </section>
          ) : null}
          {DetailRenderer ? (
            <DetailRenderer
              args={args}
              response={response}
              status={toolStatus}
              onBranchSelect={onBranchSelect}
            />
          ) : !codexActivity ? (
            <div className="tool-detail">
              {args != null && (
                <div className="tool-section">
                  <div className="tool-section-label">{t("blocks.arguments")}</div>
                  <pre className="tool-args">
                    {JSON.stringify(args, null, 2)}
                  </pre>
                </div>
              )}
              {truncated != null && (
                <div className="tool-section">
                  <div className="tool-section-label">{t("blocks.result")}</div>
                  <pre className="tool-args tool-result">{truncated}</pre>
                </div>
              )}
              {studioArtifacts.length > 0 && (
                <div className="tool-section">
                  <div className="tool-section-label">{t("blocks.artifacts")}</div>
                  <div className="studio-tool-artifacts">
                    {studioArtifacts.map((artifact) => (
                      <a
                        key={`${artifact.contentUrl}:${artifact.name}`}
                        href={artifact.contentUrl}
                        download={artifact.name}
                      >
                        {t("blocks.downloadNamed", { name: artifact.name })}
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null}
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
  const { t } = useTranslation("conversation");
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{ name: string; url: string } | null>(
    null,
  );
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview.url);
    },
    [preview],
  );

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
  const openPreview = async (
    filename: string,
    version: number,
    name: string,
  ) => {
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
  const files = block.files.filter(
    (file) => !file.filename.endsWith(".preview.webp"),
  );
  return (
    <div className="artifact-list">
      {files.map((file) => {
        const previewName = `${file.filename.replace(/\.pptx$/i, "")}.preview.webp`;
        const previewFile = block.files.find(
          (item) => item.filename === previewName,
        );
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
              <span className="artifact-card__hint">{t("blocks.powerpoint")}</span>
            </span>
            <span className="artifact-card__actions">
              {previewFile && (
                <button
                  className="artifact-card__action"
                  type="button"
                  disabled={!onPreview || pending !== ""}
                  onClick={() =>
                    void openPreview(
                      previewFile.filename,
                      previewFile.version,
                      file.filename,
                    )
                  }
                >
                  {pending === `preview:${file.filename}` ? (
                    <Loader2 className="spin" />
                  ) : (
                    <Eye />
                  )}
                  {t("blocks.preview")}
                </button>
              )}
              <button
                className="artifact-card__action artifact-card__action--primary"
                type="button"
                disabled={!onDownload || pending !== ""}
                onClick={() => void download(file.filename, file.version)}
              >
                {pending === `download:${file.filename}` ? (
                  <Loader2 className="spin" />
                ) : (
                  <Download />
                )}
                {t("blocks.download")}
              </button>
            </span>
          </div>
        );
      })}
      {error && <div className="artifact-card__error">{error}</div>}
      {preview && (
        <div
          className="artifact-preview"
          role="dialog"
          aria-modal="true"
          aria-label={t("blocks.previewDialog", { name: preview.name })}
        >
          <button
            className="artifact-preview__backdrop"
            type="button"
            aria-label={t("blocks.closePreview")}
            onClick={closePreview}
          />
          <div className="artifact-preview__panel">
            <div className="artifact-preview__header">
              <span>{preview.name}</span>
              <button
                type="button"
                aria-label={t("blocks.closePreview")}
                onClick={closePreview}
              >
                <X />
              </button>
            </div>
            <div className="artifact-preview__canvas">
              <img src={preview.url} alt={t("blocks.slidePreview", { name: preview.name })} />
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
  const { t } = useTranslation("conversation");
  const [status, setStatus] = useState<
    "idle" | "authorizing" | "done" | "error"
  >(block.done ? "done" : "idle");
  const [err, setErr] = useState("");

  const toolLabel = block.label || t("blocks.mcpToolset");
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
        <span>{t("blocks.authorized", { tool: toolLabel })}</span>
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
        <span className="auth-card-title">{t("blocks.authorizationRequired", { tool: toolLabel })}</span>
      </div>
      <p className="auth-card-desc">
        <Trans
          t={t}
          i18nKey="blocks.oauthDescription"
          values={{ tool: toolLabel }}
          components={{ code: <code className="auth-card-code" /> }}
        />
        {provider && (
          <>
            {" "}
            <Trans
              t={t}
              i18nKey="blocks.oauthProvider"
              values={{ provider }}
              components={{ code: <code className="auth-card-code" /> }}
            />{" "}
          </>
        )}
        {t("blocks.oauthContinue")}
      </p>
      <button
        className="auth-card-btn"
        onClick={go}
        disabled={status === "authorizing" || !block.authUri}
      >
        {status === "authorizing" ? (
          <>
            <Loader2 className="cw-i spin" /> {t("blocks.waitingAuthorization")}
          </>
        ) : (
          <>{t("blocks.authorize")}</>
        )}
      </button>
      {!block.authUri && (
        <div className="auth-card-err">{t("blocks.missingAuthorizationUrl")}</div>
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
  onDeployDelivery?: (
    delivery: Extract<Block, { kind: "delivery" }>["value"],
  ) => void;
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
    (lastIndex, block, index) => (block.kind === "text" ? index : lastIndex),
    -1,
  );
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.kind) {
          case "progress":
            return <BuildProgressBlock key="build-progress" text={b.text} />;
          case "thinking": {
            const answerStarted = blocks
              .slice(i + 1)
              .some(
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
                onStreamComplete={
                  i === lastTextBlockIndex ? onStreamComplete : undefined
                }
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
            return (
              <ArtifactCard
                key={i}
                block={b}
                onDownload={onArtifactDownload}
                onPreview={onArtifactPreview}
              />
            );
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
            const hasLaterCreateAgentAttempt =
              b.name === "create_agents" &&
              blocks
                .slice(i + 1)
                .some(
                  (block) =>
                    block.kind === "tool" && block.name === "create_agents",
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
                retrying={
                  b.name === "create_agents" &&
                  (streaming || hasLaterCreateAgentAttempt)
                }
                codexActivity={b.codexActivity}
                onBranchSelect={onBranchSelect}
                onAction={onAction}
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
