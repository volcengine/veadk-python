import type { AgentDraft } from "./types";
import { createT } from "./i18n";

const ADK_AGENT_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

type AgentNameNode = Pick<AgentDraft, "name" | "subAgents">;

/** Return the Google ADK name validation error, or null when valid. */
export function agentNameProblem(
  name: string,
  translate: (key: string) => string = (key) =>
    createT(`validation.agentName.${key}`),
): string | null {
  if (name.trim().length === 0) return translate("required");
  if (name === "user") return translate("reserved");
  if (!ADK_AGENT_NAME_PATTERN.test(name)) {
    return translate("characters");
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
