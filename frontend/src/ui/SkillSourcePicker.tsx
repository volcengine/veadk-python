import {
  type CSSProperties,
  type ComponentType,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { FolderUp, Globe, Plus, Sparkles, X } from "lucide-react";

import type { CloudProvider } from "../adk/cloudProvider";
import { LocalPicker } from "../create/LocalPicker";
import { SkillHubPicker } from "../create/SkillHubPicker";
import { SkillSpacePicker } from "../create/SkillSpacePicker";
import { displayDescription } from "../create/displayText";
import type { SelectedSkill, SkillSource } from "../create/skills/types";
import "./SkillSourcePicker.css";

function AgentKitSkillsIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5.5 7.5h10.75a2 2 0 0 1 2 2v7.75a2 2 0 0 1-2 2H5.5a2 2 0 0 1-2-2V9.5a2 2 0 0 1 2-2Z" />
      <path d="M7 4.75h9.5a2 2 0 0 1 2 2" opacity=".58" />
      <path d="m11 10.25.72 1.48 1.63.24-1.18 1.15.28 1.62-1.45-.77-1.45.77.28-1.62-1.18-1.15 1.63-.24.72-1.48Z" />
      <path d="M19.25 11.25h1.5M20 10.5V12" opacity=".72" />
    </svg>
  );
}

function skillKey(skill: SelectedSkill): string {
  if (skill.source === "skillhub") return `hub:${skill.namespace}/${skill.slug}`;
  if (skill.source === "local") return `local:${skill.folder}`;
  return `ss:${skill.skillSpaceId}/${skill.skillId}/${skill.version || ""}`;
}

function skillSourceLabel(skill: SelectedSkill): string {
  if (skill.source === "local") return "本地";
  if (skill.source === "skillspace") return "AgentKit Skills 中心";
  return "火山 Find Skill 技能广场";
}

function SelectedSkillRow({
  skill,
  onRemove,
  disabled,
}: {
  skill: SelectedSkill;
  onRemove: () => void;
  disabled: boolean;
}) {
  let Icon: ComponentType<{ className?: string }> = Sparkles;
  if (skill.source === "local") Icon = FolderUp;
  else if (skill.source === "skillspace") Icon = AgentKitSkillsIcon;
  return (
    <motion.div
      className="cw-selected-skill-row"
      layout
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.16 }}
    >
      <span className="cw-selected-skill-icon" aria-hidden="true">
        <Icon className="cw-i cw-i-sm" />
      </span>
      <span className="cw-selected-skill-meta">
        <span className="cw-selected-skill-name">{skill.name}</span>
        <span className="cw-selected-skill-detail">
          {skillSourceLabel(skill)}
          {skill.description ? ` · ${displayDescription(skill.description)}` : ""}
        </span>
      </span>
      <button
        type="button"
        className="cw-selected-skill-remove"
        onClick={onRemove}
        disabled={disabled}
        aria-label={`移除 ${skill.name}`}
        title={`移除 ${skill.name}`}
      >
        <X className="cw-i cw-i-sm" />
      </button>
    </motion.div>
  );
}

const SKILL_SOURCES: Array<{
  id: SkillSource;
  label: string;
  shortLabel: string;
  icon: ComponentType<{ className?: string }>;
}> = [
  { id: "local", label: "本地文件", shortLabel: "本地文件", icon: FolderUp },
  {
    id: "skillspace",
    label: "AgentKit Skills 中心",
    shortLabel: "AgentKit",
    icon: AgentKitSkillsIcon,
  },
  {
    id: "skillhub",
    label: "火山 Find Skill 技能广场",
    shortLabel: "Find Skill",
    icon: Globe,
  },
];

export function SkillSourcePicker({
  selected,
  onChange,
  cloudProvider,
  disabled = false,
  addLabel = "添加 Skill",
}: {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
  cloudProvider: CloudProvider;
  disabled?: boolean;
  addLabel?: string;
}) {
  const [active, setActive] = useState<SkillSource>("local");
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const panelId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const activeIndex = SKILL_SOURCES.findIndex((source) => source.id === active);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [open]);

  const remove = (key: string) => {
    onChange(selected.filter((skill) => skillKey(skill) !== key));
  };

  return (
    <div className="cw-skillspane">
      <button
        type="button"
        className="cw-skill-add"
        aria-haspopup="dialog"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        <span className="cw-skill-add-icon" aria-hidden="true">
          <Plus className="cw-i" />
        </span>
        <span>{addLabel}</span>
      </button>

      {selected.length > 0 && (
        <div className="cw-skill-selected">
          <span className="cw-skill-selected-label">已加入技能 · {selected.length}</span>
          <div className="cw-selected-skill-list">
            <AnimatePresence initial={false}>
              {selected.map((skill) => (
                <SelectedSkillRow
                  key={skillKey(skill)}
                  skill={skill}
                  disabled={disabled}
                  onRemove={() => remove(skillKey(skill))}
                />
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {createPortal(
        <AnimatePresence>
          {open && (
            <motion.div
              className="cw-skill-dialog-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.16 }}
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) setOpen(false);
              }}
            >
              <motion.section
                className="cw-skill-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                initial={{ opacity: 0, y: 10, scale: 0.985 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 6, scale: 0.99 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
              >
                <header className="cw-skill-dialog-head">
                  <h3 id={titleId}>{addLabel}</h3>
                  <button
                    ref={closeButtonRef}
                    type="button"
                    className="cw-skill-dialog-close"
                    aria-label={`关闭${addLabel}`}
                    onClick={() => setOpen(false)}
                  >
                    <X className="cw-i" />
                  </button>
                </header>
                <div className="cw-skill-dialog-body">
                  <div
                    className="cw-skill-sourcetabs"
                    role="tablist"
                    style={{
                      "--cw-skill-tab-slider-width": `calc((100% - 16px) / ${SKILL_SOURCES.length})`,
                      "--cw-active-skill-tab-offset": `calc(${activeIndex * 100}% + ${activeIndex * 4}px)`,
                    } as CSSProperties}
                  >
                    <span className="cw-skill-tab-slider" aria-hidden="true" />
                    {SKILL_SOURCES.map(({ id, label, shortLabel, icon: Icon }) => (
                      <button
                        key={id}
                        type="button"
                        role="tab"
                        id={`${panelId}-${id}`}
                        aria-controls={panelId}
                        aria-selected={active === id}
                        className={`cw-skill-pickertab ${active === id ? "is-on" : ""}`}
                        onClick={() => setActive(id)}
                      >
                        <Icon className="cw-i cw-i-sm" />
                        <span className="cw-skill-tab-label-full">{label}</span>
                        <span className="cw-skill-tab-label-short">{shortLabel}</span>
                      </button>
                    ))}
                  </div>

                  <div
                    id={panelId}
                    className="cw-skill-tabbody"
                    role="tabpanel"
                    aria-labelledby={`${panelId}-${active}`}
                  >
                    {active === "skillhub" && (
                      <SkillHubPicker selected={selected} onChange={onChange} />
                    )}
                    {active === "local" && (
                      <LocalPicker selected={selected} onChange={onChange} />
                    )}
                    {active === "skillspace" && (
                      <SkillSpacePicker
                        selected={selected}
                        onChange={onChange}
                        cloudProvider={cloudProvider}
                      />
                    )}
                  </div>
                </div>
              </motion.section>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </div>
  );
}
