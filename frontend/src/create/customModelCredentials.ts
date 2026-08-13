import type { AgentDraft } from "./types";

export interface CustomModelCredentialRequirement {
  key: string;
  label: string;
}

function envSegment(value: string, fallback: string): string {
  const segment = value.trim().toUpperCase().replace(/[^A-Z0-9]+/g, "_");
  return segment.replace(/^_+|_+$/g, "") || fallback;
}

function nextEnvName(base: string, used: ReadonlySet<string>): string {
  if (!used.has(base)) return base;
  let suffix = 2;
  while (used.has(`${base}_${suffix}`)) suffix += 1;
  return `${base}_${suffix}`;
}

export function isProviderModelApiBase(
  rawUrl: string | undefined,
  officialBaseUrl: string,
): boolean {
  const value = rawUrl?.trim();
  if (!value) return false;
  try {
    const candidate = new URL(value);
    const official = new URL(officialBaseUrl);
    const candidatePath = candidate.pathname.replace(/\/+$/, "");
    const officialPath = official.pathname.replace(/\/+$/, "");
    return (
      candidate.protocol === "https:" &&
      candidate.username === "" &&
      candidate.password === "" &&
      candidate.search === "" &&
      candidate.hash === "" &&
      candidate.hostname.toLowerCase() === official.hostname.toLowerCase() &&
      candidate.port === official.port &&
      candidatePath === officialPath
    );
  } catch {
    return false;
  }
}

/** Mirror backend codegen names without storing any credential in the draft. */
export function customModelCredentialRequirements(
  root: AgentDraft,
  officialBaseUrl: string,
): CustomModelCredentialRequirement[] {
  const requirements: CustomModelCredentialRequirement[] = [];
  const used = new Set<string>();

  const visit = (node: AgentDraft) => {
    if (
      node.agentType === "llm" &&
      node.modelApiBase?.trim() &&
      !isProviderModelApiBase(node.modelApiBase, officialBaseUrl)
    ) {
      const segment = envSegment(node.name, "AGENT");
      const key = nextEnvName(`CUSTOM_MODEL_${segment}_API_KEY`, used);
      used.add(key);
      requirements.push({
        key,
        label: `${node.name.trim() || "自定义模型"} 模型 API Key`,
      });
    }
    node.subAgents.forEach(visit);
  };

  visit(root);
  return requirements;
}
