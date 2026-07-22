import { useLayoutEffect, useRef, useState } from "react";
import {
  ArrowUp,
  AtSign,
  Bot,
  Check,
  Copy,
  FileText,
  FileVideo2,
  ImageIcon,
  Loader2,
  Plus,
  Sparkles,
} from "lucide-react";
import { motion } from "motion/react";
import type {
  AgentSkill,
  AgentTarget,
  Attachment,
  FrontendInvocation,
} from "../adk/client";
import { InvocationChips } from "./InvocationChips";
import { MediaGroup } from "./Media";
import { isImeCompositionEvent } from "./composerKeyboard";

interface CompletionTrigger {
  kind: "skill" | "agent";
  query: string;
  start: number;
  end: number;
}

type CompletionItem =
  | { kind: "skill"; value: AgentSkill }
  | { kind: "agent"; value: AgentTarget };

export interface ComposerProps {
  sessionId: string;
  sessionInitializing?: boolean;
  appName: string;
  agentName: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean; // not connected yet
  busy: boolean; // a turn is streaming
  showMeta: boolean;
  attachments: Attachment[];
  skills: AgentSkill[];
  agents: AgentTarget[];
  invocation: FrontendInvocation;
  capabilitiesLoading?: boolean;
  onInvocationChange: (value: FrontendInvocation) => void;
  onAddFiles: (files: FileList | File[]) => void;
  onRemoveAttachment: (id: string) => void;
}

export function Composer({
  sessionId,
  sessionInitializing = false,
  appName,
  agentName,
  value,
  onChange,
  onSubmit,
  disabled,
  busy,
  showMeta,
  attachments,
  skills,
  agents,
  invocation,
  capabilitiesLoading = false,
  onInvocationChange,
  onAddFiles,
  onRemoveAttachment,
}: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const documentInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [trigger, setTrigger] = useState<CompletionTrigger | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [sessionIdCopied, setSessionIdCopied] = useState(false);

  async function copySessionId() {
    if (!sessionId) return;
    try {
      await navigator.clipboard.writeText(sessionId);
      setSessionIdCopied(true);
      setTimeout(() => setSessionIdCopied(false), 1500);
    } catch {
      setSessionIdCopied(false);
    }
  }

  // Auto-grow the textarea up to a max height, then scroll.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const uploadPending = attachments.some((attachment) => attachment.status !== "ready");
  const canSend = !disabled && !busy && !uploadPending &&
    (value.trim().length > 0 || attachments.length > 0);

  const query = trigger?.query.toLocaleLowerCase() ?? "";
  const suggestions: CompletionItem[] = trigger?.kind === "skill"
    ? skills
        .filter((skill) => !invocation.skills.some((selected) => selected.name === skill.name))
        .filter((skill) => `${skill.name} ${skill.description}`.toLocaleLowerCase().includes(query))
        .map((value) => ({ kind: "skill" as const, value }))
    : trigger?.kind === "agent"
      ? agents
          .filter((agent) => `${agent.name} ${agent.description}`.toLocaleLowerCase().includes(query))
          .map((value) => ({ kind: "agent" as const, value }))
      : [];

  function pick(input: React.RefObject<HTMLInputElement | null>) {
    setMenuOpen(false);
    setTrigger(null);
    input.current?.click();
  }

  function updateCompletion(nextValue: string, cursor: number) {
    const prefix = nextValue.slice(0, cursor);
    const match = /(^|\s)([/@])([^\s/@]*)$/.exec(prefix);
    if (!match) {
      setTrigger(null);
      return;
    }
    const tokenLength = match[2].length + match[3].length;
    const nextTrigger: CompletionTrigger = {
      kind: match[2] === "/" ? "skill" : "agent",
      query: match[3],
      start: cursor - tokenLength,
      end: cursor,
    };
    const completionChanged = !trigger ||
      trigger.kind !== nextTrigger.kind ||
      trigger.query !== nextTrigger.query ||
      trigger.start !== nextTrigger.start ||
      trigger.end !== nextTrigger.end;
    setTrigger(nextTrigger);
    if (completionChanged) setActiveIndex(0);
    setMenuOpen(false);
  }

  function choose(item: CompletionItem) {
    if (!trigger) return;
    const nextValue = value.slice(0, trigger.start) + value.slice(trigger.end);
    onChange(nextValue);
    if (item.kind === "skill") {
      onInvocationChange({
        ...invocation,
        skills: [...invocation.skills, item.value],
      });
    } else {
      onInvocationChange({ skills: [], targetAgent: item.value });
    }
    const cursor = trigger.start;
    setTrigger(null);
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(cursor, cursor);
    });
  }

  function removeLastInvocation() {
    if (invocation.targetAgent) {
      onInvocationChange({ skills: [] });
      return;
    }
    if (invocation.skills.length > 0) {
      onInvocationChange({ ...invocation, skills: invocation.skills.slice(0, -1) });
    }
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files ? Array.from(e.target.files) : [];
    if (selected.length) onAddFiles(selected);
    e.target.value = ""; // allow re-picking the same file
  }

  return (
    <div className="composer">
      <InvocationChips
        value={invocation}
        onRemoveSkill={(name) => onInvocationChange({
          ...invocation,
          skills: invocation.skills.filter((skill) => skill.name !== name),
        })}
        onRemoveAgent={() => onInvocationChange({ skills: [] })}
      />
      {attachments.length > 0 && (
        <MediaGroup
          appName={appName}
          compact
          items={attachments}
          onRemove={onRemoveAttachment}
        />
      )}

      <div className="composer-box">
        {trigger ? (
          <div className="composer-command-menu" role="listbox" aria-label={trigger.kind === "skill" ? "可用技能" : "可用子 Agent"}>
            <div className="composer-command-head">
              {trigger.kind === "skill" ? <Sparkles /> : <AtSign />}
              <span>{trigger.kind === "skill" ? "调用技能" : "使用子 Agent"}</span>
              <kbd>{trigger.kind === "skill" ? "/" : "@"}</kbd>
            </div>
            {capabilitiesLoading ? (
              <div className="composer-command-empty"><Loader2 className="spin" /> 正在读取 Agent 能力…</div>
            ) : suggestions.length === 0 ? (
              <div className="composer-command-empty">
                {trigger.kind === "skill" ? "当前 Agent 没有匹配技能" : "当前 Agent 没有匹配子 Agent"}
              </div>
            ) : (
              <div className="composer-command-list">
                {suggestions.map((item, index) => (
                  <button
                    type="button"
                    role="option"
                    aria-selected={index === activeIndex}
                    className={`composer-command-item${index === activeIndex ? " is-active" : ""}`}
                    key={`${item.kind}-${item.value.name}`}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      choose(item);
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                  >
                    <span className={`composer-command-icon composer-command-icon--${item.kind}`}>
                      {item.kind === "skill" ? <Sparkles /> : <Bot />}
                    </span>
                    <span className="composer-command-copy">
                      <strong>{item.kind === "skill" ? "/" : "@"}{item.value.name}</strong>
                      <span>{item.value.description || (item.kind === "skill" ? "加载并执行该技能" : "将本轮交给该 Agent")}</span>
                    </span>
                    <kbd>{index === activeIndex ? "↵" : item.kind === "skill" ? "技能" : "Agent"}</kbd>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : null}
        <div className="composer-menu-wrap">
          <button
            type="button"
            className="comp-icon"
            title="添加"
            aria-label="添加"
            disabled={disabled}
            onClick={() => {
              setTrigger(null);
              setMenuOpen((o) => !o);
            }}
          >
            <Plus className="icon" />
          </button>
          {menuOpen && (
            <>
              <div className="menu-scrim" onClick={() => setMenuOpen(false)} />
              <div className="composer-menu" role="menu">
                <button
                  type="button"
                  className="menu-item"
                  onClick={() => pick(imageInput)}
                >
                  <ImageIcon className="icon" />
                  上传图片
                </button>
                <button
                  type="button"
                  className="menu-item"
                  onClick={() => pick(documentInput)}
                >
                  <FileText className="icon" />
                  上传文档或 PDF
                </button>
                <button
                  type="button"
                  className="menu-item"
                  onClick={() => pick(videoInput)}
                >
                  <FileVideo2 className="icon" />
                  上传视频
                </button>
              </div>
            </>
          )}
        </div>

        <textarea
          ref={ref}
          className="comp-input scroll"
          rows={1}
          value={value}
          disabled={disabled}
          placeholder={disabled ? "请选择 Agent" : `向 ${agentName} 发消息…`}
          aria-expanded={Boolean(trigger)}
          onChange={(e) => {
            onChange(e.target.value);
            updateCompletion(e.target.value, e.target.selectionStart);
          }}
          onSelect={(e) => updateCompletion(e.currentTarget.value, e.currentTarget.selectionStart)}
          onBlur={() => setTimeout(() => setTrigger(null), 0)}
          onKeyDown={(e) => {
            if (isImeCompositionEvent(e.nativeEvent)) return;
            if (trigger) {
              if (e.key === "ArrowDown" && suggestions.length > 0) {
                e.preventDefault();
                setActiveIndex((index) => (index + 1) % suggestions.length);
                return;
              }
              if (e.key === "ArrowUp" && suggestions.length > 0) {
                e.preventDefault();
                setActiveIndex((index) => (index - 1 + suggestions.length) % suggestions.length);
                return;
              }
              if ((e.key === "Enter" || e.key === "Tab") && suggestions[activeIndex]) {
                e.preventDefault();
                choose(suggestions[activeIndex]);
                return;
              }
              if (e.key === "Escape") {
                e.preventDefault();
                setTrigger(null);
                return;
              }
            }
            if (
              e.key === "Backspace" &&
              !value &&
              e.currentTarget.selectionStart === 0 &&
              e.currentTarget.selectionEnd === 0
            ) {
              removeLastInvocation();
              return;
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSend) onSubmit();
            }
          }}
        />
        <motion.button
          type="button"
          className="comp-send"
          disabled={!canSend}
          onClick={onSubmit}
          aria-label="发送"
          whileTap={canSend ? { scale: 0.9 } : undefined}
          transition={{ type: "spring", stiffness: 600, damping: 22 }}
        >
          {busy ? <Loader2 className="icon spin" /> : <ArrowUp className="icon" />}
        </motion.button>
      </div>

      {showMeta && (
        <div className="composer-meta">
          <span className="composer-session-line">
            会话 ID：
            <span
              className="composer-session-id"
              title={sessionId || undefined}
              aria-live="polite"
            >
              {sessionInitializing ? "初始化中" : sessionId || "—"}
            </span>
            {sessionId && (
              <button
                type="button"
                className="composer-session-copy"
                title={sessionIdCopied ? "已复制" : "复制会话 ID"}
                aria-label={sessionIdCopied ? "已复制会话 ID" : "复制会话 ID"}
                onClick={() => void copySessionId()}
              >
                {sessionIdCopied ? <Check /> : <Copy />}
              </button>
            )}
          </span>
          <span className="composer-meta-separator" aria-hidden>
            |
          </span>
          <span>回答仅供参考</span>
        </div>
      )}

      {/* hidden pickers */}
      <input
        ref={imageInput}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={onInputChange}
      />
      <input
        ref={documentInput}
        type="file"
        accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
        multiple
        hidden
        onChange={onInputChange}
      />
      <input
        ref={videoInput}
        type="file"
        accept="video/mp4,video/webm,video/quicktime"
        multiple
        hidden
        onChange={onInputChange}
      />
    </div>
  );
}
