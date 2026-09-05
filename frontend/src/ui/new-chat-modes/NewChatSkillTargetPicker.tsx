import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type SVGProps,
} from "react";
import { useTranslation } from "react-i18next";
import type {
  SkillSpaceRef,
  SkillSpaceSkill,
} from "../../create/skills/skillspace";
import "./new-chat-agent-picker.css";
import "./new-chat-skill-target-picker.css";

const HOVER_OPEN_DELAY_MS = 120;
const HOVER_CLOSE_DELAY_MS = 180;

interface NewChatSkillTargetPickerProps {
  spaces: SkillSpaceRef[];
  skills: SkillSpaceSkill[];
  activeSpaceId: string;
  selectedSpaceId: string;
  selectedSkillId: string;
  selectedSkillLabel: string;
  spacesLoading?: boolean;
  skillsLoading?: boolean;
  spacesError?: string;
  skillsError?: string;
  disabled?: boolean;
  onActivateSpace: (spaceId: string) => void;
  onSelect: (space: SkillSpaceRef, skill: SkillSpaceSkill) => void;
  onRetrySpaces: () => void;
  onRetrySkills: () => void;
}

function ChevronIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="m5.75 3.75 4.25 4.25-4.25 4.25"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="m3.25 8.25 3 3 6.5-6.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function spaceLabel(space: SkillSpaceRef, unnamedLabel: string): string {
  return space.name.trim() || unnamedLabel;
}

export function NewChatSkillTargetPicker({
  spaces,
  skills,
  activeSpaceId,
  selectedSpaceId,
  selectedSkillId,
  selectedSkillLabel,
  spacesLoading = false,
  skillsLoading = false,
  spacesError = "",
  skillsError = "",
  disabled = false,
  onActivateSpace,
  onSelect,
  onRetrySpaces,
  onRetrySkills,
}: NewChatSkillTargetPickerProps) {
  const { t } = useTranslation("newChat");
  const [open, setOpen] = useState(false);
  const [activeSpaceIndex, setActiveSpaceIndex] = useState(0);
  const [activeSkillIndex, setActiveSkillIndex] = useState(0);
  const [keyboardPanel, setKeyboardPanel] = useState<"spaces" | "skills">("spaces");
  const [keyboardNavigating, setKeyboardNavigating] = useState(false);
  const [menuPlacement, setMenuPlacement] = useState<"above" | "below">("below");
  const [menuMaxHeight, setMenuMaxHeight] = useState(286);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const hoverOpenTimerRef = useRef<number | null>(null);
  const hoverCloseTimerRef = useRef<number | null>(null);
  const activeSpace = spaces.find((space) => space.id === activeSpaceId) ?? null;
  const unnamedSpaceLabel = t("skill.unnamedSpace");
  const activeSpaceLabel = activeSpace
    ? spaceLabel(activeSpace, unnamedSpaceLabel)
    : "Skill Space";
  const triggerLabel = selectedSkillLabel || t("skill.select");

  const close = useCallback((returnFocus = false) => {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
    setOpen(false);
    setKeyboardPanel("spaces");
    setKeyboardNavigating(false);
    onActivateSpace("");
    if (returnFocus) triggerRef.current?.focus();
  }, [onActivateSpace]);

  useEffect(() => {
    if (!open) return;
    const onOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [close, open]);

  useEffect(() => {
    if (disabled && open) close();
  }, [close, disabled, open]);

  const updateMenuLayout = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const viewportMargin = 12;
    const menuGap = 7;
    const availableBelow = window.innerHeight - rect.bottom - menuGap - viewportMargin;
    const availableAbove = rect.top - menuGap - viewportMargin;
    const nextPlacement = availableBelow >= 220 || availableBelow >= availableAbove
      ? "below"
      : "above";
    const availableHeight = nextPlacement === "below" ? availableBelow : availableAbove;
    setMenuPlacement(nextPlacement);
    setMenuMaxHeight(Math.max(120, Math.floor(availableHeight)));
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    updateMenuLayout();
    window.addEventListener("resize", updateMenuLayout);
    window.addEventListener("scroll", updateMenuLayout, true);
    return () => {
      window.removeEventListener("resize", updateMenuLayout);
      window.removeEventListener("scroll", updateMenuLayout, true);
    };
  }, [open, updateMenuLayout]);

  useEffect(() => () => {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
    }
  }, []);

  function activateSpace(index: number) {
    if (spaces.length === 0) return;
    const normalized = (index + spaces.length) % spaces.length;
    const nextSpace = spaces[normalized];
    setActiveSpaceIndex(normalized);
    setActiveSkillIndex(0);
    if (nextSpace.id !== activeSpaceId) onActivateSpace(nextSpace.id);
  }

  function openPicker(focusMenu: boolean, fromKeyboard = false) {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
    const selectedIndex = spaces.findIndex((space) => space.id === selectedSpaceId);
    const initialIndex = selectedIndex >= 0 ? selectedIndex : 0;
    setActiveSpaceIndex(initialIndex);
    setActiveSkillIndex(0);
    setKeyboardPanel("spaces");
    setKeyboardNavigating(fromKeyboard);
    setOpen(true);
    if (fromKeyboard && spaces[initialIndex]) onActivateSpace(spaces[initialIndex].id);
    else onActivateSpace("");
    if (focusMenu) requestAnimationFrame(() => menuRef.current?.focus());
  }

  function scheduleHoverOpen() {
    if (disabled || open || hoverOpenTimerRef.current !== null) return;
    hoverOpenTimerRef.current = window.setTimeout(() => {
      hoverOpenTimerRef.current = null;
      openPicker(false);
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
      close();
    }, HOVER_CLOSE_DELAY_MS);
  }

  function chooseSkill(skill: SkillSpaceSkill) {
    if (!activeSpace) return;
    onSelect(activeSpace, skill);
    close(true);
  }

  function onMenuKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
      return;
    }
    if (["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Enter"].includes(event.key)) {
      setKeyboardNavigating(true);
    }
    if (keyboardPanel === "spaces") {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        activateSpace(activeSpaceIndex + (event.key === "ArrowDown" ? 1 : -1));
      } else if (event.key === "ArrowRight" || event.key === "Enter") {
        event.preventDefault();
        if (!activeSpace) activateSpace(activeSpaceIndex);
        setKeyboardPanel("skills");
      }
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setKeyboardPanel("spaces");
    } else if (skills.length > 0 && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setActiveSkillIndex((index) => (index + delta + skills.length) % skills.length);
    } else if (event.key === "Enter" && skills[activeSkillIndex]) {
      event.preventDefault();
      chooseSkill(skills[activeSkillIndex]);
    }
  }

  return (
    <div
      className="new-chat-skill-target-picker"
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
        className="new-chat-agent-picker__trigger new-chat-skill-target-picker__trigger"
        aria-label={t("skill.selectAria", { skill: triggerLabel })}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") scheduleHoverOpen();
        }}
        onClick={() => open ? close() : openPicker(true)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!open) openPicker(true, true);
          } else if (event.key === "Escape" && open) {
            event.preventDefault();
            close(true);
          }
        }}
      >
        <span title={triggerLabel}>{triggerLabel}</span>
        <ChevronIcon className="new-chat-agent-picker__trigger-chevron" />
      </button>

      {open ? (
        <div
          ref={menuRef}
          className={`new-chat-agent-picker__menus new-chat-skill-target-picker__menus is-${menuPlacement}`}
          style={{ "--new-chat-skill-menu-max-height": `${menuMaxHeight}px` } as CSSProperties}
          tabIndex={-1}
          onKeyDown={onMenuKeyDown}
          onPointerMove={(event) => {
            if (event.pointerType === "mouse") setKeyboardNavigating(false);
          }}
        >
          <div className="new-chat-agent-picker__menu" role="menu" aria-label={t("skill.spaceAria")}>
            {spacesLoading && spaces.length === 0 ? (
              <div className="new-chat-agent-picker__status" role="status" aria-live="polite">
                <span className="new-chat-agent-picker__spinner new-chat-skill-target-picker__spinner" aria-hidden="true" />
                <span className="sr-only">{t("skill.loadingSpaces")}</span>
              </div>
            ) : spacesError && spaces.length === 0 ? (
              <div className="new-chat-agent-picker__error" role="alert">
                <span>{spacesError}</span>
                <button type="button" onClick={onRetrySpaces}>{t("skill.reload")}</button>
              </div>
            ) : spaces.length === 0 ? (
              <div className="new-chat-skill-target-picker__empty">{t("skill.emptySpaces")}</div>
            ) : spaces.map((space, index) => (
              <button
                key={space.id}
                type="button"
                role="menuitem"
                aria-haspopup="listbox"
                aria-expanded={activeSpaceId === space.id}
                className={`new-chat-agent-picker__type new-chat-skill-target-picker__space${activeSpaceId === space.id ? " is-previewed" : ""}${keyboardNavigating && keyboardPanel === "spaces" && activeSpaceIndex === index ? " is-keyboard-active" : ""}`}
                title={spaceLabel(space, unnamedSpaceLabel)}
                onMouseEnter={() => activateSpace(index)}
                onClick={() => {
                  activateSpace(index);
                  setKeyboardPanel("skills");
                }}
              >
                <span>{spaceLabel(space, unnamedSpaceLabel)}</span>
                <ChevronIcon className="new-chat-agent-picker__nested-chevron" />
              </button>
            ))}
          </div>

          {activeSpace ? (
            <div
              className="new-chat-agent-picker__submenu new-chat-skill-target-picker__submenu"
              role="listbox"
              aria-label={t("skill.skillList", { space: activeSpaceLabel })}
            >
              {skillsLoading && skills.length === 0 ? (
                <div className="new-chat-agent-picker__status" role="status" aria-live="polite">
                  <span className="new-chat-agent-picker__spinner new-chat-skill-target-picker__spinner" aria-hidden="true" />
                  <span className="sr-only">{t("skill.loadingSkills")}</span>
                </div>
              ) : skillsError && skills.length === 0 ? (
                <div className="new-chat-agent-picker__error" role="alert">
                  <span>{skillsError}</span>
                  <button type="button" onClick={onRetrySkills}>{t("skill.reload")}</button>
                </div>
              ) : skills.length === 0 ? (
                <div className="new-chat-skill-target-picker__empty">{t("skill.emptySkills")}</div>
              ) : (
                <div className="new-chat-agent-picker__runtime-list">
                  {skills.map((skill, index) => {
                    const selected = activeSpace.id === selectedSpaceId && skill.skillId === selectedSkillId;
                    return (
                      <button
                        key={skill.skillId}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        className={`new-chat-agent-picker__runtime new-chat-skill-target-picker__skill${keyboardNavigating && keyboardPanel === "skills" && activeSkillIndex === index ? " is-keyboard-active" : ""}`}
                        title={skill.skillDescription || skill.skillName || skill.skillId}
                        onMouseEnter={() => setActiveSkillIndex(index)}
                        onClick={() => chooseSkill(skill)}
                      >
                        <span>{skill.skillName || skill.skillId}</span>
                        {skill.skillDescription ? <small>{skill.skillDescription}</small> : null}
                        {selected ? <CheckIcon className="new-chat-agent-picker__check" /> : null}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
