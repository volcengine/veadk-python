import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AgentFaceIcon } from "../AgentFaceIcon";
import {
  SandboxAgentIcon,
  type SandboxAgentIconKind,
} from "../icons/SandboxAgentIcons";
import type { NewChatMode } from "./types";
import "./new-chat-modes.css";

interface ModeOption {
  value: NewChatMode;
  labelKey: string;
  descriptionKey: string;
}

const MODES: ModeOption[] = [
  {
    value: "agent",
    labelKey: "mode.agent.label",
    descriptionKey: "mode.agent.description",
  },
  {
    value: "temporary",
    labelKey: "mode.builtin.label",
    descriptionKey: "mode.builtin.description",
  },
];

const BUILTIN_AGENTS = [
  {
    labelKey: "mode.codex.label",
    kind: "codex",
    value: "temporary",
    descriptionKey: "mode.codex.description",
  },
  {
    labelKey: "mode.deepseekHarness.label",
    kind: "deepseek-harness",
    value: "deepseek-harness",
    descriptionKey: "mode.deepseekHarness.description",
  },
] satisfies Array<{
  labelKey: string;
  kind: SandboxAgentIconKind;
  value: NewChatMode;
  descriptionKey: string;
}>;

const UNAVAILABLE_BUILTIN_AGENTS = [
  { labelKey: "mode.arkClaw", kind: "openclaw" },
  { labelKey: "mode.hermes", kind: "hermes" },
] satisfies Array<{
  labelKey: string;
  kind: SandboxAgentIconKind;
}>;

export interface NewChatModeSelectorProps {
  value: NewChatMode;
  onChange: (value: NewChatMode) => void;
  disabled?: boolean;
  temporaryEnabled?: boolean;
  deepseekHarnessEnabled?: boolean;
}

function ModeIcon({ mode }: { mode: NewChatMode }) {
  if (mode === "temporary") {
    return (
      <svg className="new-chat-mode__temporary-icon" viewBox="0 0 20 20" aria-hidden="true">
        <path d="m10 2.8 6.1 3.45v7.5L10 17.2l-6.1-3.45v-7.5L10 2.8Z" />
        <path d="m3.9 6.25 6.1 3.5 6.1-3.5M10 9.75v7.45" />
      </svg>
    );
  }
  return <AgentFaceIcon className="new-chat-mode__agent-icon" />;
}

function NestedChevron() {
  return (
    <svg className="new-chat-mode__nested-chevron" viewBox="0 0 12 12" aria-hidden="true">
      <path d="m4.5 3 3 3-3 3" />
    </svg>
  );
}

function modeIndexForValue(value: NewChatMode): number {
  const index = MODES.findIndex((mode) => mode.value === value);
  return index >= 0 ? index : MODES.findIndex((mode) => mode.value === "temporary");
}

export function NewChatModeSelector({
  value,
  onChange,
  disabled = false,
  temporaryEnabled,
  deepseekHarnessEnabled,
}: NewChatModeSelectorProps) {
  const { t } = useTranslation("newChat");
  const [open, setOpen] = useState(false);
  const [builtinOpen, setBuiltinOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(() => modeIndexForValue(value));
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const current = value === "agent" ? MODES[0] : MODES[1];
  const currentBuiltin = BUILTIN_AGENTS.find((agent) => agent.value === value);
  const currentLabel = t(currentBuiltin?.labelKey ?? current.labelKey);

  function modeEnabled(mode: ModeOption): boolean | undefined {
    if (mode.value === "temporary") {
      if (temporaryEnabled === true || deepseekHarnessEnabled === true) return true;
      if (temporaryEnabled === false && deepseekHarnessEnabled === false) return false;
      return undefined;
    }
    return true;
  }

  function builtinEnabled(mode: NewChatMode): boolean | undefined {
    if (mode === "temporary") return temporaryEnabled;
    if (mode === "deepseek-harness") return deepseekHarnessEnabled;
    return false;
  }

  function modeDisabled(mode: ModeOption): boolean {
    return modeEnabled(mode) !== true;
  }

  function modeDescription(mode: ModeOption): string {
    const enabled = modeEnabled(mode);
    if (enabled === undefined) return t("mode.checking");
    if (!enabled) return t("mode.notConfigured");
    return t(mode.descriptionKey);
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

  function chooseBuiltinAgent(mode: NewChatMode) {
    if (builtinEnabled(mode) !== true) return;
    onChange(mode);
    setOpen(false);
    setBuiltinOpen(false);
  }

  return (
    <div className="new-chat-mode" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="new-chat-mode__trigger"
        aria-label={t("mode.select")}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => {
          setActiveIndex(modeIndexForValue(value));
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
        <div className="new-chat-mode__menus">
          <div
            className="new-chat-mode__menu"
            role="listbox"
            aria-label={t("mode.select")}
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
                  aria-selected={current.value === mode.value}
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
                      {t(mode.labelKey)}
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

          {builtinOpen ? (
            <div className="new-chat-mode__submenu" role="menu" aria-label={t("mode.builtin.label")}>
              {BUILTIN_AGENTS.map((agent) => {
                const enabled = builtinEnabled(agent.value);
                return (
                  <button
                    key={agent.value}
                    type="button"
                    role="menuitem"
                    className="new-chat-mode__submenu-option"
                    disabled={enabled !== true}
                    onClick={() => chooseBuiltinAgent(agent.value)}
                  >
                    <SandboxAgentIcon kind={agent.kind} className="new-chat-mode__builtin-icon" />
                    <span className="new-chat-mode__copy">
                      <span className="new-chat-mode__label">{t(agent.labelKey)}</span>
                      <span>
                        {enabled === undefined
                          ? t("mode.checking")
                          : enabled
                            ? t(agent.descriptionKey)
                            : t("mode.notConfigured")}
                      </span>
                    </span>
                  </button>
                );
              })}
              {UNAVAILABLE_BUILTIN_AGENTS.map(({ labelKey, kind }) => (
                <button key={labelKey} type="button" role="menuitem" className="new-chat-mode__submenu-option" disabled>
                  <SandboxAgentIcon kind={kind} className="new-chat-mode__builtin-icon" />
                  <span className="new-chat-mode__copy">
                    <span className="new-chat-mode__label">{t(labelKey)}</span>
                    <span>{t("mode.unavailable")}</span>
                  </span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
