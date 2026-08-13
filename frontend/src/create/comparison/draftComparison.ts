import type { AgentDraft } from "../types";

export type ComparisonDimension = "model" | "instruction" | "skills";

export interface ModelComparisonValue {
  modelName: string;
  modelProvider: string;
  modelApiBase: string;
}

export interface AgentComparisonOverride {
  agentKey: string;
  dimensions: ComparisonDimension[];
  model?: ModelComparisonValue;
  instruction?: string;
  selectedSkills?: AgentDraft["selectedSkills"];
}

export interface ConfigurableAgent {
  key: string;
  path: number[];
  name: string;
}

function pathKey(path: number[]): string {
  return path.length === 0 ? "root" : path.join(".");
}

function parseAgentKey(key: string): number[] {
  if (key === "root") return [];
  const path = key.split(".").map(Number);
  if (path.some((part) => !Number.isInteger(part) || part < 0)) {
    throw new Error(`Invalid agent key: ${key}`);
  }
  return path;
}

function agentAtPath(draft: AgentDraft, path: number[]): AgentDraft {
  let current = draft;
  for (const index of path) {
    const child = current.subAgents[index];
    if (!child) throw new Error(`Agent path does not exist: ${pathKey(path)}`);
    current = child;
  }
  return current;
}

export function listConfigurableAgents(draft: AgentDraft): ConfigurableAgent[] {
  const result: ConfigurableAgent[] = [];
  const visit = (agent: AgentDraft, path: number[]) => {
    if (!agent.agentType || agent.agentType === "llm") {
      result.push({ key: pathKey(path), path, name: agent.name });
    }
    agent.subAgents.forEach((child, index) => visit(child, [...path, index]));
  };
  visit(draft, []);
  return result;
}

/** Pick the editor target shown when a comparison group is first created. */
export function firstConfigurableAgent(
  draft: AgentDraft,
): ConfigurableAgent | null {
  return listConfigurableAgents(draft)[0] ?? null;
}

export function effectiveComparisonOverrides(
  baseline: AgentDraft,
  overrides: AgentComparisonOverride[],
): AgentComparisonOverride[] {
  return overrides.flatMap((override) => {
    const target = agentAtPath(baseline, parseAgentKey(override.agentKey));
    const dimensions = override.dimensions.filter((dimension) => {
      if (dimension === "model") {
        return (
          (override.model?.modelName ?? "").trim() !==
            (target.modelName ?? "").trim() ||
          (override.model?.modelProvider ?? "").trim() !==
            (target.modelProvider ?? "").trim() ||
          (override.model?.modelApiBase ?? "").trim() !==
            (target.modelApiBase ?? "").trim()
        );
      }
      if (dimension === "instruction") {
        return (override.instruction ?? "").trim() !== target.instruction.trim();
      }
      return (
        JSON.stringify(stableValue(override.selectedSkills ?? [])) !==
        JSON.stringify(stableValue(target.selectedSkills ?? []))
      );
    });
    return dimensions.length ? [{ ...override, dimensions }] : [];
  });
}

export function buildCandidateDraft(
  baseline: AgentDraft,
  overrides: AgentComparisonOverride[],
): AgentDraft {
  const candidate = structuredClone(baseline);
  for (const override of overrides) {
    const target = agentAtPath(candidate, parseAgentKey(override.agentKey));
    if (target.agentType && target.agentType !== "llm") {
      throw new Error(`Agent is not configurable: ${override.agentKey}`);
    }
    if (override.dimensions.includes("model")) {
      if (!override.model?.modelName.trim()) {
        throw new Error("Model ID is required");
      }
      target.modelName = override.model.modelName;
      target.modelProvider = override.model.modelProvider;
      target.modelApiBase = override.model.modelApiBase;
    }
    if (override.dimensions.includes("instruction")) {
      if (override.instruction === undefined) {
        throw new Error("Instruction override is required");
      }
      target.instruction = override.instruction;
    }
    if (override.dimensions.includes("skills")) {
      if (!override.selectedSkills) {
        throw new Error("Skills override is required");
      }
      target.selectedSkills = structuredClone(override.selectedSkills);
    }
  }
  return candidate;
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, child]) => [key, stableValue(child)]),
    );
  }
  return value;
}

export async function fingerprintDraft(draft: AgentDraft): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(stableValue(draft)));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export async function applyCandidateAtomically(
  current: AgentDraft,
  baselineFingerprint: string,
  overrides: AgentComparisonOverride[],
): Promise<
  | { ok: true; draft: AgentDraft }
  | { ok: false; reason: string }
> {
  if ((await fingerprintDraft(current)) !== baselineFingerprint) {
    return {
      ok: false,
      reason: "当前 Draft 已变化，请基于最新配置重新创建对照。",
    };
  }
  try {
    return { ok: true, draft: buildCandidateDraft(current, overrides) };
  } catch (error) {
    return {
      ok: false,
      reason: `候选配置已失效：${error instanceof Error ? error.message : String(error)}`,
    };
  }
}
