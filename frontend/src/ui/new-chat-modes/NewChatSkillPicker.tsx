import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { NewChatSkillAction } from "./types";
import "./new-chat-workspace.css";

const SKILL_ACTIONS = [
  { value: "create", label: "技能生成" },
  { value: "optimize", label: "技能优化" },
] as const;

const HOVER_OPEN_DELAY_MS = 120;
const HOVER_CLOSE_DELAY_MS = 180;

export interface NewChatSkillPickerProps {
  value: NewChatSkillAction;
  onChange: (value: NewChatSkillAction) => void;
  disabled?: boolean;
}

function ChevronIcon() {
  return (
    <svg className="new-chat-skill-picker__chevron" viewBox="0 0 16 16" aria-hidden="true">
      <path d="m4.75 6.25 3.25 3.5 3.25-3.5" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="new-chat-skill-picker__check" viewBox="0 0 16 16" aria-hidden="true">
      <path d="m3.25 8.25 3 3 6.5-6.5" />
    </svg>
  );
}

export function NewChatSkillPicker({
  value,
  onChange,
  disabled = false,
}: NewChatSkillPickerProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(() =>
    Math.max(0, SKILL_ACTIONS.findIndex((action) => action.value === value)),
  );
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const hoverOpenTimerRef = useRef<number | null>(null);
  const hoverCloseTimerRef = useRef<number | null>(null);
  const current = SKILL_ACTIONS.find((action) => action.value === value) ?? SKILL_ACTIONS[0];

  const closeMenu = useCallback((returnFocus = false) => {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) closeMenu();
    };
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [closeMenu, open]);

  useEffect(() => () => {
    if (hoverOpenTimerRef.current !== null) window.clearTimeout(hoverOpenTimerRef.current);
    if (hoverCloseTimerRef.current !== null) window.clearTimeout(hoverCloseTimerRef.current);
  }, []);

  function openMenu() {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
    setActiveIndex(Math.max(0, SKILL_ACTIONS.findIndex((action) => action.value === value)));
    setOpen(true);
  }

  function scheduleHoverOpen() {
    if (disabled || open || hoverOpenTimerRef.current !== null) return;
    hoverOpenTimerRef.current = window.setTimeout(() => {
      hoverOpenTimerRef.current = null;
      openMenu();
    }, HOVER_OPEN_DELAY_MS);
  }

  function cancelHoverClose() {
    if (hoverCloseTimerRef.current === null) return;
    window.clearTimeout(hoverCloseTimerRef.current);
    hoverCloseTimerRef.current = null;
  }

  function scheduleHoverClose() {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (!open || hoverCloseTimerRef.current !== null) return;
    hoverCloseTimerRef.current = window.setTimeout(() => {
      hoverCloseTimerRef.current = null;
      closeMenu();
    }, HOVER_CLOSE_DELAY_MS);
  }

  function choose(index: number) {
    const action = SKILL_ACTIONS[index];
    if (!action) return;
    onChange(action.value);
    setActiveIndex(index);
    closeMenu(true);
  }

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      closeMenu(true);
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
      if (open && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        choose(activeIndex);
      }
      return;
    }
    event.preventDefault();
    if (!open) {
      openMenu();
      return;
    }
    const delta = event.key === "ArrowDown" ? 1 : -1;
    setActiveIndex((index) => (index + delta + SKILL_ACTIONS.length) % SKILL_ACTIONS.length);
  }

  return (
    <div
      className="new-chat-skill-picker"
      ref={rootRef}
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse") cancelHoverClose();
      }}
      onPointerLeave={(event) => {
        if (event.pointerType === "mouse") scheduleHoverClose();
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        className="new-chat-skill-picker__trigger"
        aria-label="选择技能定制方式"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") scheduleHoverOpen();
        }}
        onClick={() => {
          if (open) closeMenu();
          else openMenu();
        }}
        onKeyDown={onKeyDown}
      >
        <span>{current.label}</span>
        <ChevronIcon />
      </button>

      {open ? (
        <div
          className="new-chat-skill-picker__menu"
          role="listbox"
          aria-label="技能定制方式"
          tabIndex={-1}
          onKeyDown={onKeyDown}
        >
          {SKILL_ACTIONS.map((action, index) => (
            <button
              key={action.value}
              type="button"
              role="option"
              aria-selected={action.value === value}
              className={`new-chat-skill-picker__option${index === activeIndex ? " is-active" : ""}`}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => choose(index)}
            >
              <span>{action.label}</span>
              {action.value === value ? <CheckIcon /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
