import { useEffect, useRef, useState } from "react";
import arkClawLogo from "../../assets/builtin-agents/arkclaw.png";
import codexLogo from "../../assets/builtin-agents/codex.png";
import hermesLogo from "../../assets/builtin-agents/hermes.png";
import { AgentIdentityIcon } from "../AgentIdentityIcon";
import type { NewChatMode } from "./types";
import "./new-chat-modes.css";

interface ModeOption {
  value: NewChatMode;
  label: string;
  description: string;
}

const MODES: ModeOption[] = [
  {
    value: "agent",
    label: "Agent",
    description: "与当前选择的 Agent 对话",
  },
  {
    value: "temporary",
    label: "内置智能体",
    description: "使用平台提供的智能体",
  },
  {
    value: "skill-create",
    label: "创建 Skill",
    description: "使用两个模型生成并对比 Skill",
  },
];

const UNAVAILABLE_BUILTIN_AGENTS = [
  { label: "ArkClaw", logo: arkClawLogo },
  { label: "Hermes 智能体", logo: hermesLogo },
];

export interface NewChatModeSelectorProps {
  value: NewChatMode;
  onChange: (value: NewChatMode) => void;
  disabled?: boolean;
  temporaryEnabled?: boolean;
  skillCreateEnabled?: boolean;
}

function ModeIcon({ mode }: { mode: NewChatMode }) {
  if (mode === "skill-create") {
    return (
      <svg className="new-chat-mode__skill-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M10 2.2l1.35 4.1 4.15 1.35-4.15 1.35L10 13.1 8.65 9 4.5 7.65 8.65 6.3 10 2.2Z" />
        <path d="M15.6 12.2l.6 1.8 1.8.6-1.8.6-.6 1.8-.6-1.8-1.8-.6 1.8-.6.6-1.8Z" />
      </svg>
    );
  }
  if (mode === "temporary") {
    return (
      <svg className="new-chat-mode__temporary-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path d="m10 2.8 6.1 3.45v7.5L10 17.2l-6.1-3.45v-7.5L10 2.8Z" />
        <path d="m3.9 6.25 6.1 3.5 6.1-3.5M10 9.75v7.45" />
      </svg>
    );
  }
  return <AgentIdentityIcon className="new-chat-mode__agent-icon" />;
}

function NestedChevron() {
  return (
    <svg className="new-chat-mode__nested-chevron" viewBox="0 0 12 12" aria-hidden="true">
      <path d="m4.5 3 3 3-3 3" />
    </svg>
  );
}

export function NewChatModeSelector({
  value,
  onChange,
  disabled = false,
  temporaryEnabled,
  skillCreateEnabled,
}: NewChatModeSelectorProps) {
  const [open, setOpen] = useState(false);
  const [builtinOpen, setBuiltinOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(() =>
    MODES.findIndex((mode) => mode.value === value),
  );
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const current = MODES.find((mode) => mode.value === value) ?? MODES[0];
  const currentLabel = current.value === "temporary" ? "Codex 智能体" : current.label;

  function modeEnabled(mode: ModeOption): boolean | undefined {
    if (mode.value === "temporary") return temporaryEnabled;
    if (mode.value === "skill-create") return skillCreateEnabled;
    return true;
  }

  function modeDisabled(mode: ModeOption): boolean {
    return modeEnabled(mode) !== true;
  }

  function modeDescription(mode: ModeOption): string {
    const enabled = modeEnabled(mode);
    if (enabled === undefined) return "正在检查配置";
    if (!enabled) return "管理员未配置";
    return mode.description;
  }

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setBuiltinOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  function moveActive(delta: number) {
    let next = activeIndex;
    do {
      next = (next + delta + MODES.length) % MODES.length;
    } while (modeDisabled(MODES[next]));
    setActiveIndex(next);
    setBuiltinOpen(MODES[next].value === "temporary");
  }

  function choose(mode: ModeOption) {
    if (modeDisabled(mode)) return;
    if (mode.value === "temporary") {
      setBuiltinOpen(true);
      return;
    }
    onChange(mode.value);
    setOpen(false);
    setBuiltinOpen(false);
    triggerRef.current?.focus();
  }

  function chooseBuiltinAgent() {
    onChange("temporary");
    setOpen(false);
    setBuiltinOpen(false);
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
          setOpen((currentOpen) => {
            if (currentOpen) setBuiltinOpen(false);
            return !currentOpen;
          });
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
            setBuiltinOpen(false);
          }
        }}
      >
        <span className="new-chat-mode__icon"><ModeIcon mode={current.value} /></span>
        <span className="new-chat-mode__current" title={currentLabel}>{currentLabel}</span>
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
              setBuiltinOpen(false);
              triggerRef.current?.focus();
            }
          }}
        >
          {MODES.map((mode, index) => {
            const nested = mode.value === "temporary";
            return (
              <button
                key={mode.value}
                type="button"
                role="option"
                aria-selected={value === mode.value}
                aria-haspopup={nested ? "menu" : undefined}
                aria-expanded={nested ? builtinOpen : undefined}
                aria-disabled={modeDisabled(mode)}
                disabled={modeDisabled(mode)}
                className={`new-chat-mode__option${index === activeIndex ? " is-active" : ""}`}
                onMouseEnter={() => {
                  setActiveIndex(index);
                  setBuiltinOpen(mode.value === "temporary");
                }}
                onClick={() => choose(mode)}
              >
                <span className="new-chat-mode__option-icon"><ModeIcon mode={mode.value} /></span>
                <span className="new-chat-mode__copy">
                  <span className="new-chat-mode__label">
                    {mode.label}
                    {mode.value === "skill-create" ? (
                      <span className="new-chat-mode__beta">Beta</span>
                    ) : null}
                  </span>
                  <span>{modeDescription(mode)}</span>
                </span>
                {nested ? <NestedChevron /> : value === mode.value ? (
                  <svg className="new-chat-mode__check" viewBox="0 0 16 16" aria-hidden="true">
                    <path d="m3.5 8.2 2.8 2.8 6.2-6" />
                  </svg>
                ) : null}
              </button>
            );
          })}
        </div>
      ) : null}

      {open && builtinOpen ? (
        <div className="new-chat-mode__submenu" role="menu" aria-label="内置智能体">
          <button
            type="button"
            role="menuitem"
            className="new-chat-mode__submenu-option"
            onClick={chooseBuiltinAgent}
          >
            <img className="new-chat-mode__builtin-icon" src={codexLogo} alt="" aria-hidden="true" />
            <span className="new-chat-mode__copy">
              <span className="new-chat-mode__label">Codex 智能体</span>
              <span>在沙箱中执行任务</span>
            </span>
          </button>
          {UNAVAILABLE_BUILTIN_AGENTS.map(({ label, logo }) => (
            <button key={label} type="button" role="menuitem" className="new-chat-mode__submenu-option" disabled>
              <img className="new-chat-mode__builtin-icon" src={logo} alt="" aria-hidden="true" />
              <span className="new-chat-mode__copy">
                <span className="new-chat-mode__label">{label}</span>
                <span>暂不可用</span>
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
