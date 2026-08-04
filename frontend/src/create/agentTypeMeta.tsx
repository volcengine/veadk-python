import type { ComponentType, SVGProps } from "react";
import { GitBranch, Globe, Repeat, Split } from "lucide-react";
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

const AGENT_TYPE_META: Record<AgentTypeId, AgentTypeMeta> = {
  llm: {
    id: "llm",
    label: "LLM 智能体",
    desc: "大模型驱动，自主完成任务",
    icon: LlmIcon,
  },
  sequential: {
    id: "sequential",
    label: "顺序型智能体",
    desc: "子 Agent 按顺序依次执行",
    icon: GitBranch,
  },
  parallel: {
    id: "parallel",
    label: "并行型智能体",
    desc: "子 Agent 并行执行后汇总",
    icon: Split,
  },
  loop: {
    id: "loop",
    label: "循环型智能体",
    desc: "子 Agent 循环执行到满足条件",
    icon: Repeat,
  },
  a2a: {
    id: "a2a",
    label: "远程智能体",
    desc: "通过 A2A 协议调用远程 Agent",
    icon: Globe,
  },
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
