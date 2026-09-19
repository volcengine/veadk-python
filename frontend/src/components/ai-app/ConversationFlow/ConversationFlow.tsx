import { useEffect, useRef, useState } from "react";
import { Loading } from "../../primitives/Loading";
import { Button } from "../../primitives/Button";
import { ScrollArea } from "../../primitives/ScrollArea";
import type { ConversationAssistantMessage, ConversationFlowProps, ConversationMessage } from "./ConversationFlow.types";
import { ConversationCheckIcon, ConversationCopyIcon, ConversationDislikeIcon, ConversationErrorIcon, ConversationLikeIcon, ConversationRetryIcon, ConversationStopIcon } from "./ConversationFlowIcons";
import { ConversationBlocks, ConversationStepView, conversationStatusLabels, formatConversationDuration } from "./ConversationBlocks";
import { ConversationMessageTimingScope, ConversationTimingProvider, useConversationElapsedTime } from "./ConversationTiming";
import { ConversationMessageEntranceScope, ConversationStepEntranceProvider } from "./ConversationStepEntrance";
import "./ConversationFlow.css";

function MessageMetrics({ message }: { message: ConversationAssistantMessage }) {
  const elapsedMs = useConversationElapsedTime("message", message.id, message);
  const duration = formatConversationDuration(elapsedMs, message.status === "running");
  const ttft = formatConversationDuration(message.ttftMs);
  const tokens = message.tokens !== undefined && Number.isFinite(message.tokens) && message.tokens >= 0 ? Math.round(message.tokens) : null;
  if (duration === null && ttft === null && tokens === null && !message.model) return null;
  return <dl className="studio-conversation-message__metrics">
    {duration !== null && <div className="studio-conversation-message__metric"><dt>执行时间</dt><dd>{duration}</dd></div>}
    {ttft !== null && <div className="studio-conversation-message__metric"><dt>TTFT</dt><dd>{ttft}</dd></div>}
    {tokens !== null && <div className="studio-conversation-message__metric"><dt>Tokens</dt><dd>{tokens}</dd></div>}
    {message.model && <div className="studio-conversation-message__metric"><dt>模型</dt><dd>{message.model}</dd></div>}
  </dl>;
}

function MessageActions({ message, onRetry, onFeedback, onStop }: { message: ConversationMessage } & Pick<ConversationFlowProps, "onRetry" | "onFeedback" | "onStop">) {
  const markdownBlocks = message.blocks?.filter(block => block.type === "markdown");
  const text = message.copyText ?? (message.blocks !== undefined ? markdownBlocks?.length ? markdownBlocks.map(block => block.text).join("\n\n") : undefined : typeof message.content === "string" ? message.content : undefined);
  const [copyState, setCopyState] = useState<"idle" | "pending" | "copied" | "error">("idle");
  const copyAttempt = useRef(0);
  useEffect(() => {
    copyAttempt.current += 1;
    setCopyState("idle");
    return () => { copyAttempt.current += 1; };
  }, [text]);

  async function copy() {
    if (text === undefined) return;
    const attempt = ++copyAttempt.current;
    setCopyState("pending");
    try {
      await navigator.clipboard.writeText(text);
      if (attempt === copyAttempt.current) setCopyState("copied");
    } catch {
      if (attempt === copyAttempt.current) setCopyState("error");
    }
  }

  if (message.role === "assistant" && message.actions !== undefined) {
    return message.actions == null ? null : <div className="studio-conversation-message__actions">{message.actions}</div>;
  }
  const canRetry = message.role === "assistant" && onRetry !== undefined;
  const canFeedback = message.role === "assistant" && onFeedback !== undefined;
  const running = message.role === "assistant" && message.status === "running";
  const canStop = running && onStop !== undefined;
  if (text === undefined && !canRetry && !canFeedback && !canStop) return null;
  const feedback = message.role === "assistant" ? message.feedback : null;
  const statusText = copyState === "copied" ? "已复制" : copyState === "error" ? "复制失败，请选择文字手动复制" : "";

  return <div className="studio-conversation-message__actions" role="group" aria-label="消息操作">
    {canStop && <Button variant="ghost" iconOnly className="studio-conversation-message__action" aria-label="停止生成" title="停止生成" onClick={() => onStop?.(message.id)} startIcon={<ConversationStopIcon />} />}
    {text !== undefined && <Button variant="ghost" iconOnly className="studio-conversation-message__action" aria-label={copyState === "copied" ? "已复制消息" : "复制消息"} title={statusText || "复制消息"} disabled={copyState === "pending"} aria-busy={copyState === "pending"} onClick={copy} startIcon={copyState === "copied" ? <ConversationCheckIcon /> : <ConversationCopyIcon />} />}
    {canRetry && <Button variant="ghost" iconOnly className="studio-conversation-message__action" aria-label="重新生成回复" title="重新生成回复" disabled={running} onClick={() => onRetry?.(message.id)} startIcon={<ConversationRetryIcon />} />}
    {canFeedback && <>
      <Button variant="ghost" iconOnly className="studio-conversation-message__action" aria-label="有帮助" title="有帮助" aria-pressed={feedback === "like"} disabled={running} onClick={() => onFeedback?.(message.id, feedback === "like" ? null : "like")} startIcon={<ConversationLikeIcon />} />
      <Button variant="ghost" iconOnly className="studio-conversation-message__action" aria-label="没有帮助" title="没有帮助" aria-pressed={feedback === "dislike"} disabled={running} onClick={() => onFeedback?.(message.id, feedback === "dislike" ? null : "dislike")} startIcon={<ConversationDislikeIcon />} />
    </>}
    <span className="studio-conversation-message__action-status" data-error={copyState === "error" || undefined} role="status" aria-live="polite">{statusText}</span>
  </div>;
}

function MessageView({ message, onRetry, onFeedback, onStop }: { message: ConversationMessage } & Pick<ConversationFlowProps, "onRetry" | "onFeedback" | "onStop">) {
  const assistant = message.role === "assistant";
  const status = assistant ? message.status ?? "complete" : undefined;
  const name = message.name ?? (assistant ? "模型回复" : message.role === "system" ? "系统消息" : "用户消息");
  const hasContent = message.content != null && message.content !== false && message.content !== "";
  const steps = assistant ? message.steps : undefined;
  return <li className="studio-conversation-message" data-role={message.role} data-status={status} aria-label={name}>
    <div className="studio-conversation-message__main">
      <div className="studio-conversation-message__body">
        {message.blocks !== undefined ? <ConversationBlocks blocks={message.blocks} streaming={status === "running"} /> : <>
          {steps && steps.length > 0 && <div className="studio-conversation-message__steps">{steps.map(step => <ConversationStepView key={step.id} step={step} />)}</div>}
          {hasContent && <div className="studio-conversation-message__content">{message.content}</div>}
        </>}
      </div>
      {assistant && message.error != null && <div className="studio-conversation-message__error" role="alert"><ConversationErrorIcon /><div>{message.error}</div></div>}
      {assistant && status === "running" && (message.blocks !== undefined ? message.blocks.length === 0 : !hasContent && !steps?.length) && <div className="studio-conversation-message__pending"><Loading size={32} label="正在生成回复" /></div>}
      <footer className="studio-conversation-message__footer">
        {assistant && status !== "complete" && <span className="studio-conversation-message__status" role="status">{status === "running" ? "生成中" : status === "error" ? "执行出错" : status === "cancelled" ? "已停止" : conversationStatusLabels[status ?? "complete"]}</span>}
        {assistant && <MessageMetrics message={message} />}
        <MessageActions message={message} onRetry={onRetry} onFeedback={onFeedback} onStop={onStop} />
      </footer>
    </div>
  </li>;
}

export function ConversationFlow({ messages, onRetry, onFeedback, onStop, height = 600, scrollAreaProps, className = "", style, ...props }: ConversationFlowProps) {
  return <ConversationTimingProvider messages={messages}><ConversationStepEntranceProvider messages={messages}><div {...props} className={`studio-conversation-flow ${className}`.trim()} style={{ height, ...style }}>
    <ScrollArea {...scrollAreaProps} orientation="vertical" tabIndex={scrollAreaProps?.tabIndex ?? 0} aria-label={scrollAreaProps?.["aria-label"] ?? "对话消息滚动区域"} className={`studio-conversation-flow__scroll ${scrollAreaProps?.className ?? ""}`.trim()}>
    <ol className="studio-conversation-flow__messages" aria-label="对话消息">
      {messages.map(message => <ConversationMessageTimingScope key={message.id} messageId={message.id}>
        <ConversationMessageEntranceScope messageId={message.id}><MessageView message={message} onRetry={onRetry} onFeedback={onFeedback} onStop={onStop} /></ConversationMessageEntranceScope>
      </ConversationMessageTimingScope>)}
    </ol>
    </ScrollArea>
  </div></ConversationStepEntranceProvider></ConversationTimingProvider>;
}
