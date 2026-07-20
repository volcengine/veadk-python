import type { AgentDraft } from "./types";

const ADK_AGENT_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

type AgentNameNode = Pick<AgentDraft, "name" | "subAgents">;

/** Return the Google ADK name validation error, or null when valid. */
export function agentNameProblem(name: string): string | null {
  if (name.trim().length === 0) return "名称为必填项";
  if (name === "user") return "user 是 Google ADK 保留名称，请使用其他名称";
  if (!ADK_AGENT_NAME_PATTERN.test(name)) {
    return "名称须以英文字母或下划线开头，且只能包含英文字母、数字和下划线";
  }
  return null;
}

/** Return every valid name that occurs more than once in the Agent tree. */
export function duplicateAgentNames(root: AgentNameNode): ReadonlySet<string> {
  const seen = new Set<string>();
  const duplicates = new Set<string>();

  const visit = (node: AgentNameNode) => {
    if (agentNameProblem(node.name) === null) {
      if (seen.has(node.name)) duplicates.add(node.name);
      else seen.add(node.name);
    }
    node.subAgents.forEach(visit);
  };

  visit(root);
  return duplicates;
}
