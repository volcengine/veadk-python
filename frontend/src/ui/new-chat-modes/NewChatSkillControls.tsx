import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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

const DEFAULT_STYLE_KEYS = ["concise", "strict", "tutorial", "automation"] as const;

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
  const { t } = useTranslation("newChat");
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
          setCapabilityError(errorMessage(error, t("skill.modelLoadFailed")));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setCapabilityLoading(false);
      });
    return () => controller.abort();
  }, [action, capability, capabilityReloadKey, t]);

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
        if (!cancelled) setSpacesError(errorMessage(error, t("skill.spaceLoadFailed")));
      })
      .finally(() => {
        if (!cancelled) setSpacesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [action, spaces.length, spacesReloadKey, t]);

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
        if (!cancelled) setSkillsError(errorMessage(error, t("skill.skillLoadFailed")));
      })
      .finally(() => {
        if (!cancelled) setSkillsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [action, activeSpace, skillsReloadKey, t]);

  const styleOptions = useMemo<NewChatCompactSelectOption[]>(() => {
    const keys = capability ? Object.keys(capability.styles) : DEFAULT_STYLE_KEYS;
    return keys.map((value) => ({
      value,
      label: DEFAULT_STYLE_KEYS.includes(value as (typeof DEFAULT_STYLE_KEYS)[number])
        ? t(`skill.styles.${value}`)
        : value,
    }));
  }, [capability, t]);
  const modelOptions = useMemo<NewChatCompactSelectOption[]>(
    () => capability?.models.map((item) => ({ value: item.id, label: item.label })) || [],
    [capability],
  );
  return (
    <div className={`new-chat-skill-controls is-${action}`} aria-label={t("skill.configuration")}>
      <NewChatSkillPicker
        value={action}
        onChange={onActionChange}
        disabled={disabled}
      />

      {action === "create" ? (
        <>
          <div className="new-chat-skill-controls__style">
            <NewChatCompactSelect
              label={t("skill.style")}
              value={style}
              options={styleOptions}
              onChange={setStyle}
              placeholder={t("skill.selectStyle")}
              disabled={disabled}
            />
          </div>
          <div className="new-chat-skill-controls__model">
            <NewChatCompactSelect
              label={t("skill.model")}
              hideLabel
              value={model}
              options={modelOptions}
              onChange={setModel}
              placeholder={t("skill.selectModel")}
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
