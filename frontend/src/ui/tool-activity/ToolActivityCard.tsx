import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { ToolActivityInput, ToolPresentation } from "./model";
import { presentToolActivity } from "./model";
import {
  ToolAuthorizationIcon,
  ToolCheckIcon,
  ToolChevronIcon,
  ToolCommandIcon,
  ToolCopyIcon,
  ToolErrorIcon,
  ToolFileChangeIcon,
  ToolGenericIcon,
  ToolMcpIcon,
  ToolReadIcon,
  ToolSearchIcon,
  ToolSpinnerIcon,
} from "./ToolActivityIcons";
import "./tool-activity.css";

const ICONS = {
  goal: ToolGenericIcon,
  command: ToolCommandIcon,
  read: ToolReadIcon,
  search: ToolSearchIcon,
  "file-change": ToolFileChangeIcon,
  mcp: ToolMcpIcon,
  authorization: ToolAuthorizationIcon,
  generic: ToolGenericIcon,
} as const;

function durationLabel(durationMs: number): string {
  if (durationMs < 1_000) return `${Math.round(durationMs)} ms`;
  return `${(durationMs / 1_000).toFixed(durationMs < 10_000 ? 1 : 0)} s`;
}

function jsonText(value: unknown): string {
  if (value === undefined) return "";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        return JSON.stringify(JSON.parse(trimmed), null, 2);
      } catch {
        return value;
      }
    }
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function ToolStatusIcon({ status }: { status: ToolPresentation["status"] }) {
  if (status === "running" || status === "queued") {
    return (
      <ToolSpinnerIcon className="tool-activity__status-icon is-spinning" />
    );
  }
  if (status === "failed") {
    return <ToolErrorIcon className="tool-activity__status-icon" />;
  }
  return <ToolCheckIcon className="tool-activity__status-icon" />;
}

function RawData({
  presentation,
  callId,
}: {
  presentation: ToolPresentation;
  callId?: string;
}) {
  const { t } = useTranslation("conversation");
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState("");
  const [copyFailed, setCopyFailed] = useState(false);
  const copyTimer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(copyTimer.current), []);
  const copy = async (label: string, value: unknown) => {
    window.clearTimeout(copyTimer.current);
    try {
      await navigator.clipboard.writeText(
        typeof value === "string" ? value : jsonText(value),
      );
      setCopied(label);
      setCopyFailed(false);
      copyTimer.current = window.setTimeout(() => setCopied(""), 1_500);
    } catch {
      setCopied("");
      setCopyFailed(true);
      copyTimer.current = window.setTimeout(() => setCopyFailed(false), 3_000);
    }
  };
  if (
    presentation.rawArgs === undefined &&
    presentation.rawResponse === undefined &&
    !callId
  )
    return null;
  return (
    <div className="tool-activity__raw">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {t("blocks.toolActivity.rawData")}
        <ToolChevronIcon className={open ? "is-open" : ""} />
      </button>
      {open ? (
        <div className="tool-activity__raw-body">
          {callId ? (
            <div className="tool-activity__raw-id">
              <span>{t("blocks.toolActivity.callId")}</span>
              <code>{callId}</code>
              <button
                type="button"
                onClick={() => void copy("id", callId)}
                aria-label={t("blocks.toolActivity.copyCallId")}
              >
                <ToolCopyIcon />
              </button>
            </div>
          ) : null}
          {presentation.rawArgs !== undefined ? (
            <RawSection
              label={t("blocks.arguments")}
              value={presentation.rawArgs}
              preview={presentation.rawArgsPreview}
              copied={copied === "input"}
              onCopy={() => void copy("input", presentation.rawArgs)}
            />
          ) : null}
          {presentation.rawResponse !== undefined ? (
            <RawSection
              label={t("blocks.result")}
              value={presentation.rawResponse}
              preview={presentation.rawResponsePreview}
              copied={copied === "result"}
              onCopy={() => void copy("result", presentation.rawResponse)}
            />
          ) : null}
          {copyFailed ? (
            <span className="tool-activity__copy-error" role="alert">
              {t("blocks.toolActivity.copyFailed")}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function RawSection({
  label,
  value,
  preview,
  copied,
  onCopy,
}: {
  label: string;
  value: unknown;
  preview?: ToolPresentation["rawArgsPreview"];
  copied: boolean;
  onCopy: () => void;
}) {
  const { t } = useTranslation("conversation");
  return (
    <section className="tool-activity__raw-section">
      <div>
        <span>{label}</span>
        <button type="button" onClick={onCopy}>
          {copied
            ? t("blocks.toolActivity.copied")
            : t("blocks.toolActivity.copy")}
        </button>
      </div>
      <pre>
        {preview?.head.join("\n") ?? jsonText(value)}
        {preview && preview.omittedCharacters > 0
          ? `\n${t("blocks.toolActivity.omittedCharacters", { count: preview.omittedCharacters })}\n${preview.tail.join("\n")}`
          : preview && preview.omittedLines > 0
            ? `\n${t("blocks.toolActivity.omittedLines", { count: preview.omittedLines })}\n${preview.tail.join("\n")}`
            : ""}
      </pre>
    </section>
  );
}

function OutputPreview({ presentation }: { presentation: ToolPresentation }) {
  const { t } = useTranslation("conversation");
  const output = presentation.output;
  if (!output) return null;
  return (
    <pre className="tool-activity__output">
      {output.head.join("\n")}
      {output.omittedCharacters > 0
        ? "\n" +
          t("blocks.toolActivity.omittedCharacters", {
            count: output.omittedCharacters,
          }) +
          "\n" +
          output.tail.join("\n")
        : output.omittedLines > 0
          ? `\n${t("blocks.toolActivity.omittedLines", { count: output.omittedLines })}\n${output.tail.join("\n")}`
          : ""}
    </pre>
  );
}

export function ToolActivityCard({
  input,
  children,
}: {
  input: ToolActivityInput;
  children?: ReactNode;
}) {
  const { t } = useTranslation("conversation");
  const presentation = presentToolActivity(input);
  const [open, setOpen] = useState(presentation.defaultOpen);
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current) setOpen(presentation.defaultOpen);
  }, [presentation.defaultOpen]);
  const Icon = ICONS[presentation.category];
  const title = presentation.title || t(`blocks.toolActivity.${presentation.titleKey}`, {
    ...presentation.titleParams,
    defaultValue: input.name || t("blocks.toolActivity.generic.completed"),
  });
  const metrics = [
    presentation.durationMs === undefined
      ? ""
      : durationLabel(presentation.durationMs),
    presentation.exitCode === undefined
      ? ""
      : t("blocks.toolActivity.exitCode", { code: presentation.exitCode }),
  ].filter(Boolean);
  const hasDetails = Boolean(
    children ||
    presentation.command ||
    presentation.output ||
    presentation.paths.length ||
    presentation.rawArgs !== undefined ||
    presentation.rawResponse !== undefined,
  );
  return (
    <section
      className="tool-activity"
      data-status={presentation.status}
      data-category={presentation.category}
    >
      <button
        className="tool-activity__head"
        type="button"
        aria-expanded={hasDetails ? open : undefined}
        disabled={!hasDetails}
        onClick={() => {
          touched.current = true;
          setOpen((value) => !value);
        }}
      >
        <span className="tool-activity__icon" aria-hidden="true">
          <Icon />
        </span>
        <span
          className="tool-activity__status"
          role="img"
          aria-label={t(`blocks.toolActivity.status.${presentation.status}`)}
        >
          <ToolStatusIcon status={presentation.status} />
        </span>
        <span className="tool-activity__title">{title}</span>
        {presentation.summary ? (
          <span className="tool-activity__summary">{presentation.summary}</span>
        ) : null}
        {metrics.length ? (
          <span className="tool-activity__metrics">{metrics.join(" · ")}</span>
        ) : null}
        {hasDetails ? (
          <ToolChevronIcon
            className={`tool-activity__chevron${open ? " is-open" : ""}`}
            aria-hidden="true"
          />
        ) : null}
      </button>
      <div
        className={`tool-activity__collapse${open && hasDetails ? " is-open" : ""}`}
        aria-hidden={!open || !hasDetails}
        inert={!open || !hasDetails ? true : undefined}
      >
        <div className="tool-activity__collapse-inner">
          <div className="tool-activity__detail">
            {presentation.command ? (
              <code className="tool-activity__command">
                $ {presentation.command}
              </code>
            ) : null}
            {presentation.cwd ? (
              <div className="tool-activity__cwd">{presentation.cwd}</div>
            ) : null}
            {presentation.paths.length ? (
              <ul className="tool-activity__paths">
                {presentation.paths.map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
            ) : null}
            <OutputPreview presentation={presentation} />
            {children}
            <RawData presentation={presentation} callId={input.callId} />
          </div>
        </div>
      </div>
    </section>
  );
}

export function ToolExplorationGroup({
  items,
}: {
  items: ToolActivityInput[];
}) {
  const { t } = useTranslation("conversation");
  const [open, setOpen] = useState(false);
  return (
    <section className="tool-activity tool-activity--exploration">
      <button
        className="tool-activity__head"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="tool-activity__icon" aria-hidden="true">
          <ToolReadIcon />
        </span>
        <span
          className="tool-activity__status"
          role="img"
          aria-label={t("blocks.toolActivity.status.completed")}
        >
          <ToolCheckIcon className="tool-activity__status-icon" />
        </span>
        <span className="tool-activity__title">
          {t("blocks.toolActivity.explored", { count: items.length })}
        </span>
        <span className="tool-activity__summary">
          {items
            .map((item) => presentToolActivity(item).summary)
            .filter(Boolean)
            .slice(0, 2)
            .join(", ")}
        </span>
        <ToolChevronIcon
          className={`tool-activity__chevron${open ? " is-open" : ""}`}
          aria-hidden="true"
        />
      </button>
      <div
        className={`tool-activity__collapse${open ? " is-open" : ""}`}
        aria-hidden={!open}
        inert={!open ? true : undefined}
      >
        <div className="tool-activity__collapse-inner">
          <div className="tool-activity__exploration-items">
            {items.map((item, index) => (
              <ToolActivityCard
                key={item.callId || `${item.name}:${index}`}
                input={item}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
