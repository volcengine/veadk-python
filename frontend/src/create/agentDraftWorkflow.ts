import type { AgentDraft } from "./types";

export interface VisibleAgentDraft {
  id: string;
  agent: AgentDraft;
}

/**
 * Studio presents a workflow as ordinary Agent nodes. A sequential root is an
 * internal execution wrapper, so only its ordered children belong on canvas.
 */
export function visibleAgentDrafts(draft: AgentDraft): VisibleAgentDraft[] {
  if (draft.agentType === "sequential" && draft.subAgents.length > 0) {
    return draft.subAgents.map((agent, index) => ({
      id: `agent-${index}`,
      agent,
    }));
  }
  return [{ id: "agent-root", agent: draft }];
}

export function agentDraftAtNodeId(
  draft: AgentDraft,
  nodeId: string,
): AgentDraft | null {
  if (nodeId === "agent-root") return draft;
  const rootChildMatch = /^agent-root-(\d+)$/.exec(nodeId);
  if (rootChildMatch) {
    return draft.subAgents[Number(rootChildMatch[1])] ?? null;
  }
  const match = /^agent-(\d+(?:-\d+)*)$/.exec(nodeId);
  if (!match) return null;

  let current = draft;
  for (const segment of match[1].split("-")) {
    const child = current.subAgents[Number(segment)];
    if (!child) return null;
    current = child;
  }
  return current;
}

export function updateAgentDraftAtNodeId(
  draft: AgentDraft,
  nodeId: string,
  update: (agent: AgentDraft) => AgentDraft,
): AgentDraft {
  if (nodeId === "agent-root") return update(draft);
  const rootChildMatch = /^agent-root-(\d+)$/.exec(nodeId);
  if (rootChildMatch) {
    const index = Number(rootChildMatch[1]);
    const child = draft.subAgents[index];
    if (!child) return draft;
    const subAgents = [...draft.subAgents];
    subAgents[index] = update(child);
    return { ...draft, subAgents };
  }
  const match = /^agent-(\d+(?:-\d+)*)$/.exec(nodeId);
  if (!match) return draft;
  const path = match[1].split("-").map(Number);

  const updateAtPath = (agent: AgentDraft, depth: number): AgentDraft => {
    const index = path[depth];
    const child = agent.subAgents[index];
    if (!child) return agent;
    const nextChild =
      depth === path.length - 1
        ? update(child)
        : updateAtPath(child, depth + 1);
    if (nextChild === child) return agent;
    const subAgents = [...agent.subAgents];
    subAgents[index] = nextChild;
    return { ...agent, subAgents };
  };

  return updateAtPath(draft, 0);
}

/** Remove credentials and bulky local skill source before sharing context. */
export function agentDraftForConversation(draft: AgentDraft): AgentDraft {
  const deployment = draft.deployment
    ? (({ envValues: _envValues, ...safeDeployment }) => safeDeployment)(
        draft.deployment,
      )
    : undefined;
  const mcpTools = draft.mcpTools?.map(
    ({ authToken: _authToken, ...safeTool }) => safeTool,
  );
  const selectedSkills = draft.selectedSkills?.map((skill) => ({
    ...skill,
    localFiles: [],
  }));

  return {
    ...draft,
    deployment,
    mcpTools,
    selectedSkills,
    subAgents: draft.subAgents.map(agentDraftForConversation),
  };
}
