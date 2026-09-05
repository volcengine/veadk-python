import { AtSign, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { FrontendInvocation } from "../adk/client";

export interface InvocationChipsProps {
  value: FrontendInvocation;
  skillPrefix?: "/" | "$";
  onRemoveSkill?: (name: string) => void;
  onRemoveAgent?: () => void;
}

export function InvocationChips({
  value,
  skillPrefix = "/",
  onRemoveSkill,
  onRemoveAgent,
}: InvocationChipsProps) {
  const { t } = useTranslation("conversation");
  if (value.skills.length === 0 && !value.targetAgent) return null;

  return (
    <div className="invocation-chips" aria-label={t("invocation.ariaLabel")}>
      {value.skills.map((skill) => (
        <span className="invocation-chip invocation-chip--skill" key={skill.name} title={skill.description}>
          <Sparkles aria-hidden />
          <span>{skillPrefix}{skill.name}</span>
          {onRemoveSkill ? (
            <button type="button" onClick={() => onRemoveSkill(skill.name)} aria-label={t("invocation.removeSkill", { name: skill.name })}>
              <X />
            </button>
          ) : null}
        </span>
      ))}
      {value.targetAgent ? (
        <span
          className="invocation-chip invocation-chip--agent"
          title={value.targetAgent.description}
        >
          <AtSign aria-hidden />
          <span>{value.targetAgent.name}</span>
          {onRemoveAgent ? (
            <button type="button" onClick={onRemoveAgent} aria-label={t("invocation.removeAgent", { name: value.targetAgent.name })}>
              <X />
            </button>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}
