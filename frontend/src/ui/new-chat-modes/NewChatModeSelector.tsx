import { useEffect, useRef, useState } from "react";
import type { NewChatMode } from "./types";
import "./new-chat-modes.css";

interface ModeOption {
  value: NewChatMode;
  label: string;
  description: string;
  disabled?: boolean;
}

const MODES: ModeOption[] = [
  {
    value: "agent",
    label: "Agent 模式",
    description: "与当前选择的 Agent 对话",
  },
  {
    value: "temporary",
    label: "临时会话",
    description: "快速执行一次性任务",
    disabled: true,
  },
  {
    value: "skill-create",
    label: "Skill 创建",
    description: "使用两个模型生成并对比 Skill",
  },
];

export interface NewChatModeSelectorProps {
  value: NewChatMode;
  onChange: (value: NewChatMode) => void;
  disabled?: boolean;
}

function ModeIcon({ mode }: { mode: NewChatMode }) {
  if (mode === "skill-create") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="M10 2.2l1.35 4.1 4.15 1.35-4.15 1.35L10 13.1 8.65 9 4.5 7.65 8.65 6.3 10 2.2Z" />
        <path d="M15.6 12.2l.6 1.8 1.8.6-1.8.6-.6 1.8-.6-1.8-1.8-.6 1.8-.6.6-1.8Z" />
      </svg>
    );
  }
  if (mode === "temporary") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="10" cy="10" r="6.5" />
        <path d="M10 6.2v4.1l2.8 1.6" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <rect x="4" y="5.5" width="12" height="9.5" rx="3" />
      <path d="M10 3.1v2.4M7.3 10h.01M12.7 10h.01M7.8 12.5h4.4" />
    </svg>
  );
}

export function NewChatModeSelector({
  value,
  onChange,
  disabled = false,
}: NewChatModeSelectorProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(() =>
    MODES.findIndex((mode) => mode.value === value),
  );
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const current = MODES.find((mode) => mode.value === value) ?? MODES[0];

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  function moveActive(delta: number) {
    let next = activeIndex;
    do {
      next = (next + delta + MODES.length) % MODES.length;
    } while (MODES[next].disabled);
    setActiveIndex(next);
  }

  function choose(mode: ModeOption) {
    if (mode.disabled) return;
    onChange(mode.value);
    setOpen(false);
    triggerRef.current?.focus();
  }

  return (
    <div className="new-chat-mode" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="new-chat-mode__trigger"
        aria-label="选择新会话模式"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => {
          setActiveIndex(MODES.findIndex((mode) => mode.value === value));
          setOpen((currentOpen) => !currentOpen);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!open) setOpen(true);
            else moveActive(event.key === "ArrowDown" ? 1 : -1);
          } else if (open && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            choose(MODES[activeIndex]);
          } else if (open && event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
          }
        }}
      >
        <span className="new-chat-mode__icon"><ModeIcon mode={current.value} /></span>
        <span>{current.label}</span>
        <svg className="new-chat-mode__chevron" viewBox="0 0 12 12" aria-hidden="true">
          <path d="m3 4.5 3 3 3-3" />
        </svg>
      </button>

      {open ? (
        <div
          className="new-chat-mode__menu"
          role="listbox"
          aria-label="新会话模式"
          tabIndex={-1}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              moveActive(event.key === "ArrowDown" ? 1 : -1);
            } else if (event.key === "Enter") {
              event.preventDefault();
              choose(MODES[activeIndex]);
            } else if (event.key === "Escape") {
              event.preventDefault();
              setOpen(false);
              triggerRef.current?.focus();
            }
          }}
        >
          {MODES.map((mode, index) => (
            <button
              key={mode.value}
              type="button"
              role="option"
              aria-selected={value === mode.value}
              aria-disabled={mode.disabled}
              disabled={mode.disabled}
              className={`new-chat-mode__option${index === activeIndex ? " is-active" : ""}`}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => choose(mode)}
            >
              <span className="new-chat-mode__option-icon"><ModeIcon mode={mode.value} /></span>
              <span className="new-chat-mode__copy">
                <span className="new-chat-mode__label">
                  {mode.label}
                  {mode.disabled ? <span className="new-chat-mode__soon">接入中</span> : null}
                </span>
                <span>{mode.description}</span>
              </span>
              {value === mode.value ? (
                <svg className="new-chat-mode__check" viewBox="0 0 16 16" aria-hidden="true">
                  <path d="m3.5 8.2 2.8 2.8 6.2-6" />
                </svg>
              ) : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
