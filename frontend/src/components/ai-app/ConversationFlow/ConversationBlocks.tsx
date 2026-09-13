import { useId, useMemo, useState, type ReactNode } from "react";
import { Dropdown } from "../../primitives/Dropdown";
import { CodeBlock } from "../../composites/CodeBlock";
import { Item } from "../../composites/Item";
import { Loading } from "../../primitives/Loading";
import { Button } from "../../primitives/Button";
import type { ConversationAuthorizationBlock, ConversationBlock, ConversationFile, ConversationFilesBlock, ConversationHandoffBlock, ConversationPlanBlock, ConversationStatus, ConversationStep } from "./ConversationFlow.types";
import { ConversationAuthorizationIcon, ConversationCancelIcon, ConversationCheckIcon, ConversationDownloadIcon, ConversationErrorIcon, ConversationFileIcon, ConversationHandoffIcon, ConversationPendingIcon, ConversationPreviewIcon, ConversationReasoningIcon, ConversationToolIcon } from "./ConversationFlowIcons";
import { ConversationMarkdown, ConversationVisualization } from "./ConversationRichContent";
import { useConversationElapsedTime } from "./ConversationTiming";
import { ConversationMedia } from "./ConversationMedia";

export function formatConversationDuration(value: number | undefined, running = false): string | null {
  if (value === undefined || !Number.isFinite(value) || value < 0) return null;
  if (running) return `${(value / 1000).toFixed(1)} s`;
  return value < 1000 ? `${Math.round(value)} ms` : `${Number((value / 1000).toFixed(2))} s`;
}

export const conversationStatusLabels: Record<ConversationStatus, string> = {
  pending: "等待中", running: "进行中", complete: "已完成", error: "失败", cancelled: "已取消",
};

function StatusIcon({ status, completeIcon }: { status: ConversationStatus; completeIcon?: ReactNode }) {
  if (status === "running") return <Loading size={24} decorative />;
  if (status === "error") return <ConversationErrorIcon />;
  if (status === "cancelled") return <ConversationCancelIcon />;
  if (status === "pending") return <ConversationPendingIcon />;
  return completeIcon ?? <ConversationCheckIcon />;
}

function StepLabel({ id, title, status, durationMs, startedAt, endedAt, icon, target }: { id: string; title: string; status: ConversationStatus; durationMs?: number; startedAt?: number; endedAt?: number; icon: ReactNode; target?: string }) {
  const elapsedMs = useConversationElapsedTime("step", id, { status, durationMs, startedAt, endedAt });
  const duration = formatConversationDuration(elapsedMs, status === "running");
  return <span className="studio-conversation-step__label">
    <span className="studio-conversation-step__icon" aria-hidden="true"><StatusIcon status={status} completeIcon={icon} /></span>
    <span className="studio-conversation-step__title">{title}</span>
    {target && <span className="studio-conversation-step__target">{target}</span>}
    <span className="studio-conversation-step__status" role="status">{conversationStatusLabels[status]}</span>
    {duration !== null && <span className="studio-conversation-step__duration">{duration}</span>}
  </span>;
}

function ToolCode({ kind, value, language = "json" }: { kind: "input" | "output"; value: string; language?: string }) {
  const [open, setOpen] = useState(true);
  const lines = useMemo(() => [value], [value]);
  const name = kind === "input" ? "工具输入" : "工具输出";
  return <Dropdown className="studio-conversation-step__io-dropdown"
    label={<span>{kind === "input" ? "Input" : "Output"}<span className="studio-conversation-flow__sr-only">，{name}</span></span>}
    open={open} onOpenChange={setOpen}>
    <div className="studio-conversation-step__io-body" inert={!open || undefined} aria-hidden={!open || undefined}>
      <CodeBlock title={language.toUpperCase()} lines={lines} language={language} wordWrap scrollAreaProps={{ maxHeight: 280, "aria-label": `${name}代码` }} />
    </div>
  </Dropdown>;
}

export function ConversationStepView({ step }: { step: ConversationStep }) {
  const [open, setOpen] = useState(step.defaultOpen ?? false);
  const [hasOpened, setHasOpened] = useState(step.defaultOpen ?? false);
  const status = step.status ?? "complete";
  function changeOpen(next: boolean) {
    setOpen(next);
    if (next) setHasOpened(true);
  }
  return <div className="studio-conversation-step" data-type={step.type} data-status={status}>
    <Dropdown className="studio-conversation-step__dropdown" open={open} onOpenChange={changeOpen}
      label={<StepLabel id={step.id} title={step.title} status={status} durationMs={step.durationMs} startedAt={step.startedAt} endedAt={step.endedAt} icon={step.type === "reasoning" ? <ConversationReasoningIcon /> : <ConversationToolIcon />} />}>
      <div className="studio-conversation-step__details" inert={!open || undefined} aria-hidden={!open || undefined}>
        {hasOpened && (step.type === "reasoning" ? <div className="studio-conversation-step__reasoning">{step.content}</div> : <>
          {step.input !== undefined && <ToolCode kind="input" value={step.input} language={step.inputLanguage} />}
          {step.output !== undefined && <ToolCode kind="output" value={step.output} language={step.outputLanguage} />}
          {step.result != null && <div className="studio-conversation-step__result">{step.result}</div>}
          {step.error != null && <div className="studio-conversation-step__error" role="alert"><ConversationErrorIcon /><div>{step.error}</div></div>}
        </>)}
      </div>
    </Dropdown>
  </div>;
}

function HandoffBlock({ block }: { block: ConversationHandoffBlock }) {
  const [open, setOpen] = useState(block.defaultOpen ?? false);
  const [hasOpened, setHasOpened] = useState(block.defaultOpen ?? false);
  return <div className="studio-conversation-step studio-conversation-handoff" data-type="handoff" data-status={block.status}>
    <Dropdown className="studio-conversation-step__dropdown" open={open} onOpenChange={next => { setOpen(next); if (next) setHasOpened(true); }}
      label={<StepLabel id={block.id} title={block.title} status={block.status} durationMs={block.durationMs} startedAt={block.startedAt} endedAt={block.endedAt} icon={<ConversationHandoffIcon />} target={block.toAgent} />}>
      <div className="studio-conversation-step__details" inert={!open || undefined} aria-hidden={!open || undefined}>
        {hasOpened && <>
          <div className="studio-conversation-handoff__route">
            {block.fromAgent && <><span>{block.fromAgent}</span><ConversationHandoffIcon /></>}
            <span>{block.toAgent}</span>
          </div>
          {block.content != null && <div className="studio-conversation-handoff__content">{block.content}</div>}
          {block.steps && block.steps.length > 0 && <div className="studio-conversation-handoff__steps">{block.steps.map(step => <ConversationStepView key={step.id} step={step} />)}</div>}
        </>}
      </div>
    </Dropdown>
  </div>;
}

function PlanBlock({ block }: { block: ConversationPlanBlock }) {
  const titleId = useId();
  return <section className="studio-conversation-plan" aria-labelledby={titleId}>
    <h3 id={titleId} className="studio-conversation-block__title">{block.title}</h3>
    <ol className="studio-conversation-plan__items">
      {block.items.map(item => <li key={item.id} className="studio-conversation-plan__item" data-status={item.status}>
        <span className="studio-conversation-plan__icon" aria-hidden="true"><StatusIcon status={item.status} /></span>
        <span className="studio-conversation-plan__title">{item.title}</span>
        <span className="studio-conversation-plan__status">{conversationStatusLabels[item.status]}</span>
      </li>)}
    </ol>
  </section>;
}

function safeDownloadHref(href: string | undefined): string | undefined {
  const value = href?.trim();
  if (!value || /[\u0000-\u001f\u007f]/.test(value)) return undefined;
  if (/^data:/i.test(value)) {
    const comma = value.indexOf(",");
    if (comma < 0) return undefined;
    const [mime, ...parameters] = value.slice(5, comma).toLowerCase().split(";");
    const safeMimeTypes = new Set([
      "text/plain", "text/csv", "text/markdown", "text/tab-separated-values",
      "application/json", "application/pdf", "application/octet-stream", "application/zip", "application/gzip",
      "image/png", "image/jpeg", "image/webp", "image/gif", "image/avif", "image/bmp",
    ]);
    return safeMimeTypes.has(mime) && parameters.every(parameter => parameter === "base64" || /^charset=[a-z0-9._-]+$/.test(parameter)) ? value : undefined;
  }
  if (value.includes("\\") || value.startsWith("//")) return undefined;
  if (/^[a-z][a-z0-9+.-]*:/i.test(value)) {
    try {
      const url = new URL(value);
      if (/^https?:\/\//i.test(value) && (url.protocol === "http:" || url.protocol === "https:")) return value;
      return url.protocol === "blob:" && url.pathname ? value : undefined;
    } catch {
      return undefined;
    }
  }
  return value;
}

function FileRow({ file }: { file: ConversationFile }) {
  const [open, setOpen] = useState(false);
  const previewId = useId();
  const hasPreview = file.preview != null;
  const downloadHref = safeDownloadHref(file.href);
  return <div className="studio-conversation-file">
    <div className="studio-conversation-file__row">
      <Item variant="compact" title={file.name} description={file.description ?? ""} icon={<ConversationFileIcon />} className="studio-conversation-file__item" />
      <div className="studio-conversation-file__actions">
        {(hasPreview || file.onPreview) && <Button variant="ghost" iconOnly aria-label={`预览 ${file.name}`} title={`预览 ${file.name}`} aria-expanded={hasPreview ? open : undefined} aria-controls={hasPreview ? previewId : undefined} onClick={() => { file.onPreview?.(); if (hasPreview) setOpen(current => !current); }} startIcon={<ConversationPreviewIcon />} />}
        {file.onDownload ? <Button variant="ghost" iconOnly aria-label={`下载 ${file.name}`} title={`下载 ${file.name}`} onClick={file.onDownload} startIcon={<ConversationDownloadIcon />} />
          : downloadHref && <a className="studio-conversation-file__download" href={downloadHref} download={file.name} aria-label={`下载 ${file.name}`} title={`下载 ${file.name}`}><ConversationDownloadIcon /></a>}
      </div>
    </div>
    {hasPreview && <div id={previewId} className="studio-conversation-file__preview" role="region" aria-label={`${file.name} 预览`} hidden={!open} inert={!open || undefined}>{open && file.preview}</div>}
  </div>;
}

function FilesBlock({ block }: { block: ConversationFilesBlock }) {
  const titleId = useId();
  return <section className="studio-conversation-files" aria-labelledby={block.title ? titleId : undefined} aria-label={block.title ? undefined : "附件"}>
    {block.title && <h3 id={titleId} className="studio-conversation-block__title">{block.title}</h3>}
    <div className="studio-conversation-files__items">{block.files.map(file => <FileRow key={file.id} file={file} />)}</div>
  </section>;
}

function AuthorizationBlock({ block }: { block: ConversationAuthorizationBlock }) {
  const titleId = useId();
  const actionable = block.status === "pending" || block.status === "error";
  const cancelable = actionable || block.status === "running";
  return <section className="studio-conversation-authorization" data-status={block.status} aria-labelledby={titleId}>
    <div className="studio-conversation-authorization__heading">
      <span className="studio-conversation-authorization__icon" aria-hidden="true"><StatusIcon status={block.status} completeIcon={<ConversationAuthorizationIcon />} /></span>
      <h3 id={titleId} className="studio-conversation-block__title">{block.title}</h3>
      <span className="studio-conversation-authorization__status" role="status">{block.status === "pending" ? "等待授权" : block.status === "running" ? "授权中" : conversationStatusLabels[block.status]}</span>
    </div>
    {block.description != null && <div className="studio-conversation-authorization__description">{block.description}</div>}
    {(actionable && block.onAuthorize || cancelable && block.onCancel) && <div className="studio-conversation-authorization__actions">
      {actionable && block.onAuthorize && <Button onClick={block.onAuthorize}>{block.status === "error" ? "重新授权" : "授权并继续"}</Button>}
      {cancelable && block.onCancel && <Button variant="secondary" onClick={block.onCancel}>取消</Button>}
    </div>}
  </section>;
}

export function ConversationBlocks({ blocks, streaming = false }: { blocks: readonly ConversationBlock[]; streaming?: boolean }) {
  return <div className="studio-conversation-blocks">
    {blocks.map(block => {
      switch (block.type) {
        case "markdown": return <ConversationMarkdown key={block.id} text={block.text} streaming={streaming} />;
        case "visualization": return <ConversationVisualization key={block.id} kind={block.kind} source={block.source} title={block.title} streaming={streaming} />;
        case "media": return <ConversationMedia key={block.id} {...block} />;
        case "reasoning":
        case "tool": return <ConversationStepView key={block.id} step={block} />;
        case "handoff": return <HandoffBlock key={block.id} block={block} />;
        case "plan": return <PlanBlock key={block.id} block={block} />;
        case "files": return <FilesBlock key={block.id} block={block} />;
        case "authorization": return <AuthorizationBlock key={block.id} block={block} />;
        case "custom": return <section key={block.id} className="studio-conversation-custom">{block.title && <h3 className="studio-conversation-block__title">{block.title}</h3>}{block.content}</section>;
      }
    })}
  </div>;
}
