import { requestAgentsMd } from "./client";

export interface AgentsMdTarget {
  runtimeId: string;
  region: string;
}
export interface AgentsMdDocument {
  content: string;
  revision: number;
}
export class AgentsMdError extends Error {
  constructor(public readonly status: number) {
    super(`AGENTS.md request failed: ${status}`);
  }
}

export async function requestAgentsMdDocument(
  target: AgentsMdTarget,
  signal: AbortSignal,
  document?: AgentsMdDocument,
): Promise<AgentsMdDocument> {
  const response = await requestAgentsMd(target.runtimeId, target.region, {
    signal,
    ...(document ? { method: "POST", body: JSON.stringify(document) } : {}),
  });
  if (!response.ok) throw new AgentsMdError(response.status);
  const value: unknown = await response.json();
  if (
    typeof value !== "object" ||
    value === null ||
    !("content" in value) ||
    !("revision" in value) ||
    typeof value.content !== "string" ||
    typeof value.revision !== "number" ||
    !Number.isSafeInteger(value.revision) ||
    value.revision < 0
  ) {
    throw new Error("Invalid AGENTS.md response");
  }
  return { content: value.content, revision: value.revision };
}
