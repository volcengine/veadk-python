import { AtSign, Sparkles, X } from "lucide-react";
import type { FrontendInvocation } from "../adk/client";

export interface InvocationChipsProps {
  value: FrontendInvocation;
  onRemoveSkill?: (name: string) => void;
  onRemoveAgent?: () => void;
}

export function InvocationChips({
  value,
  onRemoveSkill,
  onRemoveAgent,
}: InvocationChipsProps) {
  if (value.skills.length === 0 && !value.targetAgent) return null;

  return (
    <div className="invocation-chips" aria-label="本轮调用上下文">
      {value.skills.map((skill) => (
        <span className="invocation-chip invocation-chip--skill" key={skill.name} title={skill.description}>
          <Sparkles aria-hidden />
          <span>/{skill.name}</span>
          {onRemoveSkill ? (
            <button type="button" onClick={() => onRemoveSkill(skill.name)} aria-label={`移除技能 ${skill.name}`}>
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
            <button type="button" onClick={onRemoveAgent} aria-label={`移除 Agent ${value.targetAgent.name}`}>
              <X />
            </button>
          ) : null}
        </span>
      ) : null}
    </div>
  );
}
