import { useEffect, useMemo, useState } from "react";
import {
  listSkillSpaces,
  listSkillsInSpace,
  type SkillSpaceRef,
  type SkillSpaceSkill,
} from "../../create/skills/skillspace";
import { getSkillWorkbenchCapability } from "../skill-workbench/api";
import type { SkillWorkbenchCapability } from "../skill-workbench/types";
import { NewChatCompactSelect, type NewChatCompactSelectOption } from "./NewChatCompactSelect";
import { NewChatSkillPicker } from "./NewChatSkillPicker";
import { NewChatSkillTargetPicker } from "./NewChatSkillTargetPicker";
import type { NewChatSkillAction, NewChatSkillTarget } from "./types";
import "./new-chat-workspace.css";

const STYLE_LABELS: Record<string, string> = {
  concise: "简洁实用",
  strict: "严谨稳健",
  tutorial: "教程友好",
  automation: "自动化优先",
};

interface NewChatSkillControlsProps {
  action: NewChatSkillAction;
  onActionChange: (value: NewChatSkillAction) => void;
  optimizationSource?: NewChatSkillTarget | null;
  onOptimizationSourceChange?: (value: NewChatSkillTarget | null) => void;
  disabled?: boolean;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function NewChatSkillControls({
  action,
  onActionChange,
  optimizationSource = null,
  onOptimizationSourceChange,
  disabled = false,
}: NewChatSkillControlsProps) {
  const [capability, setCapability] = useState<SkillWorkbenchCapability | null>(null);
  const [capabilityLoading, setCapabilityLoading] = useState(false);
  const [capabilityError, setCapabilityError] = useState("");
  const [capabilityReloadKey, setCapabilityReloadKey] = useState(0);
  const [style, setStyle] = useState("concise");
  const [model, setModel] = useState("");

  const [spaces, setSpaces] = useState<SkillSpaceRef[]>([]);
  const [spacesLoading, setSpacesLoading] = useState(false);
  const [spacesError, setSpacesError] = useState("");
  const [spacesReloadKey, setSpacesReloadKey] = useState(0);
  const [activeSpaceId, setActiveSpaceId] = useState("");
  const [skills, setSkills] = useState<SkillSpaceSkill[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState("");
  const [skillsReloadKey, setSkillsReloadKey] = useState(0);

  useEffect(() => {
    if (action !== "create" || capability) return;
    const controller = new AbortController();
    setCapabilityLoading(true);
    setCapabilityError("");
    void getSkillWorkbenchCapability(controller.signal)
      .then((value) => {
        setCapability(value);
        setModel((current) => current || value.models[0]?.id || "");
        if (!value.enabled && value.reason) setCapabilityError(value.reason);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setCapabilityError(errorMessage(error, "模型配置加载失败"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setCapabilityLoading(false);
      });
    return () => controller.abort();
  }, [action, capability, capabilityReloadKey]);

  useEffect(() => {
    if (action !== "optimize" || spaces.length > 0) return;
    let cancelled = false;
    setSpacesLoading(true);
    setSpacesError("");
    void listSkillSpaces()
      .then((items) => {
        if (!cancelled) setSpaces(items);
      })
      .catch((error: unknown) => {
        if (!cancelled) setSpacesError(errorMessage(error, "Skill Space 加载失败"));
      })
      .finally(() => {
        if (!cancelled) setSpacesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [action, spaces.length, spacesReloadKey]);

  const activeSpace = spaces.find((space) => space.id === activeSpaceId);
  useEffect(() => {
    if (action !== "optimize" || !activeSpace) {
      setSkills([]);
      setSkillsError("");
      setSkillsLoading(false);
      return;
    }
    let cancelled = false;
    setSkills([]);
    setSkillsLoading(true);
    setSkillsError("");
    void listSkillsInSpace(activeSpace.id, activeSpace.region)
      .then((items) => {
        if (!cancelled) setSkills(items);
      })
      .catch((error: unknown) => {
        if (!cancelled) setSkillsError(errorMessage(error, "Skill 加载失败"));
      })
      .finally(() => {
        if (!cancelled) setSkillsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [action, activeSpace, skillsReloadKey]);

  const styleOptions = useMemo<NewChatCompactSelectOption[]>(() => {
    const keys = capability ? Object.keys(capability.styles) : Object.keys(STYLE_LABELS);
    return keys.map((value) => ({ value, label: STYLE_LABELS[value] || value }));
  }, [capability]);
  const modelOptions = useMemo<NewChatCompactSelectOption[]>(
    () => capability?.models.map((item) => ({ value: item.id, label: item.label })) || [],
    [capability],
  );
  return (
    <div className={`new-chat-skill-controls is-${action}`} aria-label="技能定制配置">
      <NewChatSkillPicker
        value={action}
        onChange={onActionChange}
        disabled={disabled}
      />

      {action === "create" ? (
        <>
          <div className="new-chat-skill-controls__style">
            <NewChatCompactSelect
              label="风格"
              value={style}
              options={styleOptions}
              onChange={setStyle}
              placeholder="选择风格"
              disabled={disabled}
            />
          </div>
          <div className="new-chat-skill-controls__model">
            <NewChatCompactSelect
              label="模型"
              hideLabel
              value={model}
              options={modelOptions}
              onChange={setModel}
              placeholder="选择模型"
              loading={capabilityLoading}
              error={capabilityError}
              disabled={disabled}
              onRetry={() => {
                setCapability(null);
                setCapabilityReloadKey((key) => key + 1);
              }}
            />
          </div>
        </>
      ) : (
        <NewChatSkillTargetPicker
          spaces={spaces}
          skills={skills}
          activeSpaceId={activeSpaceId}
          selectedSpaceId={optimizationSource?.space.id || ""}
          selectedSkillId={optimizationSource?.skill.skillId || ""}
          selectedSkillLabel={optimizationSource?.skill.skillName || optimizationSource?.skill.skillId || ""}
          spacesLoading={spacesLoading}
          skillsLoading={skillsLoading}
          spacesError={spacesError}
          skillsError={skillsError}
          disabled={disabled}
          onActivateSpace={setActiveSpaceId}
          onSelect={(space, skill) => {
            onOptimizationSourceChange?.({ space, skill });
          }}
          onRetrySpaces={() => {
            setSpaces([]);
            setSpacesReloadKey((key) => key + 1);
          }}
          onRetrySkills={() => {
            setSkills([]);
            setSkillsReloadKey((key) => key + 1);
          }}
        />
      )}
    </div>
  );
}
