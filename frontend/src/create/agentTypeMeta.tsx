import type { ComponentType, SVGProps } from "react";
import { GitBranch, Globe, Repeat, Split } from "lucide-react";
import { createT } from "./i18n";
import type { AgentDraft } from "./types";

export type AgentTypeId = NonNullable<AgentDraft["agentType"]>;

export interface AgentTypeMeta {
  id: AgentTypeId;
  label: string;
  desc: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

/** Custom mark for the LLM agent type: a chat bubble with a generative
 *  "spark", drawn in the lucide stroke style so it sits with the other icons. */
function LlmIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
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
      {...props}
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <path d="M12 6.5c.4 2.4 1 3 3.4 3.4-2.4.4-3 1-3.4 3.4-.4-2.4-1-3-3.4-3.4 2.4-.4 3-1 3.4-3.4Z" />
    </svg>
  );
}

function localizedAgentType(
  id: AgentTypeId,
  icon: ComponentType<SVGProps<SVGSVGElement>>,
): AgentTypeMeta {
  return {
    id,
    get label() {
      return createT(`traditional.agentTypes.${id}.fullLabel`);
    },
    get desc() {
      return createT(`traditional.agentTypes.${id}.description`);
    },
    icon,
  };
}

const AGENT_TYPE_META: Record<AgentTypeId, AgentTypeMeta> = {
  llm: localizedAgentType("llm", LlmIcon),
  sequential: localizedAgentType("sequential", GitBranch),
  parallel: localizedAgentType("parallel", Split),
  loop: localizedAgentType("loop", Repeat),
  a2a: localizedAgentType("a2a", Globe),
};

/** Agent kinds selectable in the create wizard. */
export const AGENT_TYPES: AgentTypeMeta[] = [
  AGENT_TYPE_META.llm,
  AGENT_TYPE_META.sequential,
  AGENT_TYPE_META.parallel,
  AGENT_TYPE_META.loop,
  AGENT_TYPE_META.a2a,
];

export function agentTypeMeta(type: AgentDraft["agentType"]): AgentTypeMeta {
  return AGENT_TYPE_META[type ?? "llm"];
}

/** Orchestrators own sub-agents but no model. */
export const isOrchestratorType = (type: AgentDraft["agentType"]): boolean =>
  type === "sequential" || type === "parallel" || type === "loop";

export const isA2aType = (type: AgentDraft["agentType"]): boolean => type === "a2a";
