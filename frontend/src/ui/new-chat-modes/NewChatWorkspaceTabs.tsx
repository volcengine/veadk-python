import { useRef, type KeyboardEvent } from "react";
import { motion } from "motion/react";
import { ToolsSkills } from "@openai/apps-sdk-ui/components/Icon";
import { AgentFaceIcon } from "../AgentFaceIcon";
import { VideoGenerateIcon } from "../builtin-tools/icons";
import type { NewChatWorkspaceMode } from "./types";
import "./new-chat-workspace.css";

function AnimatedSkillIcon({ className = "" }: { className?: string }) {
  return (
    <span
      className={`${className} new-chat-workspace-tabs__skill-icon`}
      aria-hidden="true"
    >
      <ToolsSkills className="new-chat-workspace-tabs__skill-shape is-triangle" />
      <ToolsSkills className="new-chat-workspace-tabs__skill-shape is-circle" />
      <ToolsSkills className="new-chat-workspace-tabs__skill-shape is-square" />
    </span>
  );
}

function VibeTaskIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 5.5h14v13H5z" />
      <path d="m8 9 2 2-2 2M12.5 13H16" />
    </svg>
  );
}

const WORKSPACE_MODES = [
  { value: "agent", label: "智能体", icon: AgentFaceIcon },
  { value: "vibe", label: "Vibe 创建", icon: VibeTaskIcon },
  { value: "skill", label: "技能定制", icon: AnimatedSkillIcon },
  { value: "video", label: "视频创作", icon: VideoGenerateIcon },
] as const;

export interface NewChatWorkspaceTabsProps {
  value: NewChatWorkspaceMode;
  onChange: (value: NewChatWorkspaceMode) => void;
  disabled?: boolean;
  skillCustomizationEnabled?: boolean;
}

export function NewChatWorkspaceTabs({
  value,
  onChange,
  disabled = false,
  skillCustomizationEnabled = false,
}: NewChatWorkspaceTabsProps) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const visibleModes = skillCustomizationEnabled
    ? WORKSPACE_MODES
    : WORKSPACE_MODES.filter((mode) => mode.value !== "skill");
  function selectAt(index: number) {
    const mode = visibleModes[index];
    if (!mode || disabled) return;
    onChange(mode.value);
    tabRefs.current[index]?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % visibleModes.length;
    if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + visibleModes.length) % visibleModes.length;
    }
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = visibleModes.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    selectAt(nextIndex);
  }

  return (
    <div
      className="new-chat-workspace-tabs"
      role="tablist"
      aria-label="新会话模式"
    >
      {visibleModes.map((mode, index) => {
        const Icon = mode.icon;
        const selected = value === mode.value;
        return (
          <button
            key={mode.value}
            ref={(node) => {
              tabRefs.current[index] = node;
            }}
            id={`new-chat-workspace-tab-${mode.value}`}
            type="button"
            role="tab"
            aria-controls="new-chat-workspace-panel"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            className={`new-chat-workspace-tabs__tab${selected ? " is-active" : ""}`}
            disabled={disabled}
            onClick={() => onChange(mode.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {selected ? (
              <motion.span
                className="new-chat-workspace-tabs__slider"
                layoutId="new-chat-workspace-active-pill"
                initial={false}
                transition={{
                  layout: {
                    duration: 0.24,
                    ease: [0.22, 1, 0.36, 1],
                  },
                }}
                aria-hidden="true"
              />
            ) : null}
            <Icon className="new-chat-workspace-tabs__icon" />
            <span className="new-chat-workspace-tabs__label">{mode.label}</span>
          </button>
        );
      })}
    </div>
  );
}
