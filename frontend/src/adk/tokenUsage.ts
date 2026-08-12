import type { AdkEvent, AdkUsage } from "./client";

export interface TokenUsage {
  totalTokenCount: number;
  promptTokenCount: number;
  candidatesTokenCount: number;
  thoughtsTokenCount: number;
  cachedContentTokenCount: number;
}

export interface SessionTokenUsage {
  /** Latest non-empty model version observed for this app/session. */
  modelName: string;
  /** Latest model call, used to estimate the active context occupancy. */
  current: TokenUsage;
  /** Sum of all model calls, useful for understanding session consumption. */
  cumulative: TokenUsage;
}

export interface SystemContextMetadata {
  instruction?: string;
  tools?: readonly string[];
  skills?: readonly { name: string; description?: string }[];
}

export type ContextSegmentKind = "system" | "input" | "output" | "remaining";

export interface ContextComposition {
  systemTokens: number;
  inputTokens: number;
  outputTokens: number;
  remainingTokens: number;
  usedTokens: number;
  contextWindow: number;
}

export interface ContextGridCell {
  index: number;
  slices: Array<{ kind: ContextSegmentKind; share: number }>;
}

const EMPTY_TOKEN_USAGE: TokenUsage = Object.freeze({
  totalTokenCount: 0,
  promptTokenCount: 0,
  candidatesTokenCount: 0,
  thoughtsTokenCount: 0,
  cachedContentTokenCount: 0,
});

export const EMPTY_SESSION_TOKEN_USAGE: SessionTokenUsage = Object.freeze({
  modelName: "",
  current: EMPTY_TOKEN_USAGE,
  cumulative: EMPTY_TOKEN_USAGE,
});

type UsageField = keyof TokenUsage;

const SNAKE_CASE_USAGE_FIELDS: Record<UsageField, string> = {
  totalTokenCount: "total_token_count",
  promptTokenCount: "prompt_token_count",
  candidatesTokenCount: "candidates_token_count",
  thoughtsTokenCount: "thoughts_token_count",
  cachedContentTokenCount: "cached_content_token_count",
};

const SYSTEM_WRAPPER_TOKENS = 24;
const TOOL_SCHEMA_OVERHEAD_TOKENS = 64;
const SKILL_WRAPPER_TOKENS = 16;

function estimateTextTokens(value: string): number {
  const text = value.trim();
  if (!text) return 0;
  const cjkPattern = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/gu;
  const cjkCount = text.match(cjkPattern)?.length ?? 0;
  const withoutCjk = text.replace(cjkPattern, " ");
  const wordTokens = (withoutCjk.match(/[A-Za-z0-9_]+/g) ?? []).reduce(
    (total, word) => total + Math.max(1, Math.ceil(word.length / 4)),
    0,
  );
  const punctuationTokens = withoutCjk.match(/[^\sA-Za-z0-9_]/g)?.length ?? 0;
  return cjkCount + wordTokens + punctuationTokens;
}

/**
 * Estimate the prompt space occupied before the first user message. Providers
 * do not expose system/tool tokens separately, so this remains deliberately
 * approximate and is labelled as such in the UI.
 */
export function estimateSystemContextTokens(
  metadata: SystemContextMetadata,
): number {
  const instruction = metadata.instruction?.trim() ?? "";
  const tools = metadata.tools?.filter((tool) => tool.trim()) ?? [];
  const skills = metadata.skills?.filter((skill) => skill.name.trim()) ?? [];
  const instructionTokens = estimateTextTokens(instruction);
  const toolTokens = tools.reduce(
    (total, tool) =>
      total + TOOL_SCHEMA_OVERHEAD_TOKENS + estimateTextTokens(tool),
    0,
  );
  const skillTokens = skills.reduce(
    (total, skill) =>
      total +
      SKILL_WRAPPER_TOKENS +
      estimateTextTokens(skill.name) +
      estimateTextTokens(skill.description ?? ""),
    0,
  );
  return SYSTEM_WRAPPER_TOKENS + instructionTokens + toolTokens + skillTokens;
}

export function contextComposition({
  usage,
  contextWindow,
  estimatedSystemTokens,
}: {
  usage: SessionTokenUsage;
  contextWindow: number;
  estimatedSystemTokens: number | null;
}): ContextComposition {
  const normalizedWindow = Math.max(1, Math.round(contextWindow));
  const promptTokens = Math.max(0, usage.current.promptTokenCount);
  const reportedTokens = Math.max(
    promptTokens,
    usage.current.totalTokenCount,
  );
  const systemTokens = Math.min(
    normalizedWindow,
    promptTokens > 0
      ? Math.min(promptTokens, Math.max(0, estimatedSystemTokens ?? 0))
      : Math.max(0, estimatedSystemTokens ?? 0),
  );
  const inputTokens = Math.max(0, promptTokens - systemTokens);
  const outputTokens = promptTokens > 0
    ? Math.max(0, reportedTokens - promptTokens)
    : Math.max(0, reportedTokens);
  const usedTokens = promptTokens > 0
    ? reportedTokens
    : systemTokens + outputTokens;
  return {
    systemTokens,
    inputTokens,
    outputTokens,
    remainingTokens: Math.max(0, normalizedWindow - usedTokens),
    usedTokens,
    contextWindow: normalizedWindow,
  };
}

export function buildContextGrid(
  composition: ContextComposition,
): ContextGridCell[] {
  const segments: Array<{ kind: ContextSegmentKind; tokens: number }> = [
    { kind: "system", tokens: composition.systemTokens },
    { kind: "input", tokens: composition.inputTokens },
    { kind: "output", tokens: composition.outputTokens },
    { kind: "remaining", tokens: composition.remainingTokens },
  ];
  const tokensPerCell = composition.contextWindow / 100;
  let segmentStart = 0;
  const ranges = segments.map((segment) => {
    const start = segmentStart;
    segmentStart += segment.tokens;
    return { ...segment, start, end: segmentStart };
  });

  return Array.from({ length: 100 }, (_, index) => {
    const cellStart = index * tokensPerCell;
    const cellEnd = cellStart + tokensPerCell;
    const slices = ranges.flatMap((range) => {
      const overlap = Math.max(
        0,
        Math.min(cellEnd, range.end) - Math.max(cellStart, range.start),
      );
      return overlap > 0
        ? [{ kind: range.kind, share: overlap / tokensPerCell }]
        : [];
    });
    return { index, slices };
  });
}

function countOf(usage: AdkUsage, field: UsageField): number {
  const record = usage as Record<string, unknown>;
  const value = record[field] ?? record[SNAKE_CASE_USAGE_FIELDS[field]];
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.round(value)
    : 0;
}

function normalizeTokenUsage(usage: AdkUsage): TokenUsage {
  const promptTokenCount = countOf(usage, "promptTokenCount");
  const candidatesTokenCount = countOf(usage, "candidatesTokenCount");
  const thoughtsTokenCount = countOf(usage, "thoughtsTokenCount");
  const reportedTotal = countOf(usage, "totalTokenCount");
  return {
    totalTokenCount:
      reportedTotal ||
      promptTokenCount + candidatesTokenCount + thoughtsTokenCount,
    promptTokenCount,
    candidatesTokenCount,
    thoughtsTokenCount,
    cachedContentTokenCount: countOf(usage, "cachedContentTokenCount"),
  };
}

function sumTokenUsage(left: TokenUsage, right: TokenUsage): TokenUsage {
  return {
    totalTokenCount: left.totalTokenCount + right.totalTokenCount,
    promptTokenCount: left.promptTokenCount + right.promptTokenCount,
    candidatesTokenCount:
      left.candidatesTokenCount + right.candidatesTokenCount,
    thoughtsTokenCount: left.thoughtsTokenCount + right.thoughtsTokenCount,
    cachedContentTokenCount:
      left.cachedContentTokenCount + right.cachedContentTokenCount,
  };
}

export function addTokenUsage(
  current: SessionTokenUsage,
  event: AdkEvent | undefined,
): SessionTokenUsage {
  if (!event) return current;
  const camelModelName = typeof event.modelVersion === "string"
    ? event.modelVersion.trim()
    : "";
  const snakeModelName = typeof event.model_version === "string"
    ? event.model_version.trim()
    : "";
  const modelName = camelModelName || snakeModelName || current.modelName;
  const usage = event.usageMetadata ?? event.usage_metadata;
  if (!usage) {
    return modelName === current.modelName
      ? current
      : { ...current, modelName };
  }
  const next = normalizeTokenUsage(usage);
  if (next.totalTokenCount === 0) {
    return modelName === current.modelName
      ? current
      : { ...current, modelName };
  }
  return {
    modelName,
    current: next,
    cumulative: sumTokenUsage(current.cumulative, next),
  };
}

export function aggregateTokenUsage(events: AdkEvent[]): SessionTokenUsage {
  return events.reduce(
    (current, event) => addTokenUsage(current, event),
    EMPTY_SESSION_TOKEN_USAGE,
  );
}
