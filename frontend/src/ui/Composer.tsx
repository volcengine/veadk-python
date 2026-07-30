import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ComponentType, SVGProps } from "react";
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
  MonitorPlay,
  Plus,
  Sparkles,
  X,
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
import { NewChatModeSelector } from "./new-chat-modes/NewChatModeSelector";
import type { NewChatMode, NewChatTask } from "./new-chat-modes/types";
import { NEW_CHAT_TASK_TOOLS } from "./new-chat-modes/taskTools";
import { SKILL_MODELS } from "./skill-create/types";
import { VideoGenerateIcon } from "./builtin-tools/icons";

function SkillCreateIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <rect x="4.25" y="6.25" width="13.5" height="13.5" rx="2.5" />
      <path d="M11 10v6M8 13h6" />
      <path d="m19.25 2.75.53 1.47 1.47.53-1.47.53-.53 1.47-.53-1.47-1.47-.53 1.47-.53.53-1.47Z" fill="currentColor" stroke="none" />
    </svg>
  );
}

interface CompletionTrigger {
  kind: "skill" | "agent";
  query: string;
  start: number;
  end: number;
}

type CompletionItem =
  | { kind: "skill"; value: AgentSkill }
  | { kind: "agent"; value: AgentTarget };

function AnalyzePromptIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="8.2" cy="8.2" r="4.7" />
      <path d="m11.7 11.7 4.1 4.1" />
      <path d="M14.8 2.7v3.2M13.2 4.3h3.2" />
      <circle cx="8.2" cy="8.2" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

function PlanPromptIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="4.2" cy="15.4" r="1.4" />
      <circle cx="15.7" cy="4.2" r="1.4" />
      <path d="M5.7 15.1c3.5-.3 1.8-4.7 5.1-5.1 2.8-.4 2.1-3.7 3.5-4.8" />
      <path d="m12.7 14.2 1.5 1.5 2.9-3.3" />
    </svg>
  );
}

function RewritePromptIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M3.2 5.2h7.1M3.2 9.5h5.2M3.2 13.8h4" />
      <path d="m10.1 14.8.6-2.8 4.7-4.7 2.2 2.2-4.7 4.7-2.8.6Z" />
      <path d="M14.5 3.1v2.5M13.2 4.4h2.6" />
    </svg>
  );
}

const STARTER_PROMPTS = [
  { icon: AnalyzePromptIcon, text: "帮我分析一个问题，并给出清晰的解决思路" },
  { icon: PlanPromptIcon, text: "根据我的目标，制定一份可执行的行动计划" },
  { icon: RewritePromptIcon, text: "帮我整理并润色一段内容，让表达更清晰" },
] as const;

const TASK_SHORTCUTS = [
  {
    value: "ppt",
    label: "PPT",
    icon: MonitorPlay,
    prompts: [
      "复盘【季度】经营表现，提炼指标差距、原因与行动建议",
      "汇报【项目名称】进展：里程碑、风险、预算和资源诉求",
      "为【客户行业】输出解决方案：痛点、架构、实施路径与收益",
      "分析【行业主题】趋势，给出竞争格局、机会与战略建议",
    ],
  },
  {
    value: "image",
    label: "图片生成",
    icon: ImageIcon,
    prompts: [
      "为【品牌或产品】设计【高级科技】风格的发布会主视觉",
      "生成【产品名称】电商海报，突出【核心卖点】与品牌色",
      "呈现【产品或空间】在【使用场景】中的写实概念效果图",
      "围绕【传播主题】制作简洁专业的企业社媒配图",
    ],
  },
  {
    value: "video",
    label: "视频生成",
    icon: VideoGenerateIcon,
    prompts: [
      "制作【品牌名称】30 秒宣传片，突出【品牌价值】",
      "为【产品名称】制作 45 秒发布视频：痛点、功能、场景与行动号召",
      "制作【培训主题】企业培训视频，讲清【关键操作或规范】",
      "生成【活动名称】20 秒预热视频，包含亮点、时间地点和报名信息",
    ],
  },
] as const satisfies ReadonlyArray<{
  value: NewChatTask;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  prompts: readonly string[];
}>;

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
  allowAttachments?: boolean;
  onInvocationChange: (value: FrontendInvocation) => void;
  onAddFiles: (files: FileList | File[]) => void;
  onRemoveAttachment: (id: string) => void;
  newChatMode?: NewChatMode;
  newChatTask?: NewChatTask | null;
  newChatLayout?: boolean;
  showModeSelector?: boolean;
  onModeChange?: (value: NewChatMode) => void;
  onTaskChange?: (value: NewChatTask | null) => void;
  temporaryEnabled?: boolean;
  skillCreateEnabled?: boolean;
  harnessEnabled?: boolean;
  builtinTools?: readonly string[];
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
  allowAttachments = true,
  onInvocationChange,
  onAddFiles,
  onRemoveAttachment,
  newChatMode = "agent",
  newChatTask = null,
  newChatLayout = false,
  showModeSelector = false,
  onModeChange,
  onTaskChange,
  temporaryEnabled,
  skillCreateEnabled,
  harnessEnabled = false,
  builtinTools = [],
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

  const skillMode = newChatMode === "skill-create";
  useEffect(() => {
    if (!skillMode) return;
    setMenuOpen(false);
    setTrigger(null);
  }, [skillMode]);
  const uploadPending = !skillMode && attachments.some((attachment) => attachment.status !== "ready");
  const canSend = !disabled && !busy && !uploadPending &&
    (value.trim().length > 0 || (!skillMode && attachments.length > 0));

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

  function applyStarterPrompt(prompt: string) {
    onChange(prompt);
    setMenuOpen(false);
    setTrigger(null);
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(prompt.length, prompt.length);
    });
  }

  function applyTaskShortcut(task: (typeof TASK_SHORTCUTS)[number]) {
    onTaskChange?.(task.value);
    setMenuOpen(false);
    setTrigger(null);
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(value.length, value.length);
    });
  }

  function applyTaskPrompt(prompt: string) {
    onChange(prompt);
    setMenuOpen(false);
    setTrigger(null);
    requestAnimationFrame(() => {
      ref.current?.focus();
      const placeholderStart = prompt.indexOf("【");
      const placeholderEnd = prompt.indexOf("】", placeholderStart + 1);
      if (placeholderStart >= 0 && placeholderEnd > placeholderStart) {
        ref.current?.setSelectionRange(placeholderStart + 1, placeholderEnd);
      } else {
        ref.current?.setSelectionRange(prompt.length, prompt.length);
      }
    });
  }

  function clearTask() {
    onTaskChange?.(null);
    onChange("");
    setMenuOpen(false);
    setTrigger(null);
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(0, 0);
    });
  }

  const selectedTask = TASK_SHORTCUTS.find((task) => task.value === newChatTask);
  const availableTaskShortcuts = TASK_SHORTCUTS.filter((task) =>
    NEW_CHAT_TASK_TOOLS[task.value].every((tool) => builtinTools.includes(tool)),
  );

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
    <div className={`composer${newChatLayout ? " composer--new-chat" : ""}${skillMode ? " composer--skill-mode" : ""}${selectedTask ? ` composer--has-task composer--task-${selectedTask.value}` : ""}`}>
      {!skillMode ? (
        <InvocationChips
          value={invocation}
          onRemoveSkill={(name) => onInvocationChange({
            ...invocation,
            skills: invocation.skills.filter((skill) => skill.name !== name),
          })}
          onRemoveAgent={() => onInvocationChange({ skills: [] })}
        />
      ) : null}
      {!skillMode && attachments.length > 0 && (
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
        {!skillMode ? <div className="composer-menu-wrap">
          <button
            type="button"
            className="comp-icon"
            title="添加"
            aria-label="添加"
            disabled={disabled || !allowAttachments}
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
        </div> : null}

        {showModeSelector && onModeChange ? (
          <NewChatModeSelector
            value={newChatMode}
            onChange={onModeChange}
            disabled={busy}
            temporaryEnabled={temporaryEnabled}
            skillCreateEnabled={skillCreateEnabled}
          />
        ) : null}

        {newChatLayout && newChatMode === "agent" && selectedTask && onTaskChange ? (
          <button
            type="button"
            className={`new-chat-task-chip new-chat-task-chip--${selectedTask.value}`}
            aria-label={`取消${selectedTask.label}任务`}
            disabled={busy}
            onClick={clearTask}
          >
            <span className="new-chat-task-chip__icon" aria-hidden="true">
              <selectedTask.icon className="new-chat-task-chip__task-icon" />
              <X className="new-chat-task-chip__remove-icon" />
            </span>
            <span>{selectedTask.label}</span>
          </button>
        ) : null}

        {newChatLayout && skillMode && onModeChange ? (
          <button
            type="button"
            className="new-chat-task-chip new-chat-task-chip--skill"
            aria-label="退出创建 Skill"
            disabled={busy}
            onClick={() => onModeChange("agent")}
          >
            <span className="new-chat-task-chip__icon" aria-hidden="true">
              <SkillCreateIcon className="new-chat-task-chip__task-icon" />
              <X className="new-chat-task-chip__remove-icon" />
            </span>
            <span>Skill</span>
          </button>
        ) : null}

        <div className="composer-input-stack">
          <textarea
            ref={ref}
            className="comp-input scroll"
            rows={newChatLayout ? 4 : 1}
            value={value}
            disabled={disabled}
            placeholder={skillMode
              ? `描述你想创建的 Skill，将使用 ${SKILL_MODELS.join(" 和 ")} 并行创建…`
              : disabled ? "请在页面左上角选择智能体" : `向 ${agentName} 发消息…`}
            aria-expanded={Boolean(trigger)}
            onChange={(e) => {
              onChange(e.target.value);
              if (!skillMode) updateCompletion(e.target.value, e.target.selectionStart);
            }}
            onSelect={(e) => {
              if (!skillMode) updateCompletion(e.currentTarget.value, e.currentTarget.selectionStart);
            }}
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
        </div>
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

      {newChatLayout && newChatMode === "agent" && harnessEnabled && !selectedTask ? (
        <div className="task-shortcuts" aria-label="选择任务类型">
          {availableTaskShortcuts.map((task) => {
            const TaskIcon = task.icon;
            return (
              <button
                key={task.value}
                type="button"
                className="task-shortcut"
                disabled={disabled || busy}
                onClick={() => applyTaskShortcut(task)}
              >
                <TaskIcon />
                <span>{task.label}</span>
              </button>
            );
          })}
          {skillCreateEnabled === true ? (
            <button
              type="button"
              className="task-shortcut"
              disabled={busy}
              onClick={() => onModeChange?.("skill-create")}
            >
              <SkillCreateIcon />
              <span>创建 Skill</span>
            </button>
          ) : null}
        </div>
      ) : null}

      {newChatLayout && newChatMode === "agent" && selectedTask ? (
        <div className="prompt-suggestions" aria-label={`${selectedTask.label}企业提示词`}>
          {selectedTask.prompts.map((prompt) => {
            const PromptIcon = selectedTask.icon;
            return (
              <button
                key={prompt}
                type="button"
                className="prompt-suggestion"
                disabled={disabled || busy}
                onClick={() => applyTaskPrompt(prompt)}
              >
                <PromptIcon />
                <span>{prompt}</span>
              </button>
            );
          })}
        </div>
      ) : null}

      {newChatLayout && newChatMode === "agent" && !harnessEnabled && !value.trim() ? (
        <div className="prompt-suggestions" aria-label="快捷提示">
          {STARTER_PROMPTS.map((prompt) => {
            const PromptIcon = prompt.icon;
            return (
              <button
                key={prompt.text}
                type="button"
                className="prompt-suggestion"
                disabled={disabled || busy}
                onClick={() => applyStarterPrompt(prompt.text)}
              >
                <PromptIcon />
                <span>{prompt.text}</span>
              </button>
            );
          })}
        </div>
      ) : null}

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
