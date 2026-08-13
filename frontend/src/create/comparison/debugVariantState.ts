export type DebugComparisonDimension = "model" | "instruction" | "skills";

export interface DebugChangeState<TSkill = unknown> {
  id: string;
  modelName: string;
  modelProvider: string;
  modelApiBase: string;
  apiKey: string;
  apiKeyLocked: boolean;
  apiKeyVisible: boolean;
  instruction: string;
  selectedSkills: TSkill[];
  agentKey: string;
  dimension: DebugComparisonDimension;
}

export interface DebugVariantConfiguration<TSkill = unknown>
  extends DebugChangeState<TSkill> {
  additionalChanges: DebugChangeState<TSkill>[];
}

export interface DebugVariantEvidence<TMessage = unknown> {
  messages: TMessage[];
  ttftMs: number | null;
  latencyMs: number | null;
  toolCalls: number | null;
  tokens: number | null;
  error: string | null;
  verdict: string;
  verdictReason: string;
}

export interface DebugChangeSummaryItem<TSkill = unknown> {
  change: DebugChangeState<TSkill>;
  active: boolean;
}

export interface DebugChangeSummaryGroup<TSkill = unknown> {
  agentKey: string;
  changes: DebugChangeSummaryItem<TSkill>[];
}

const dimensionOrder: Record<DebugComparisonDimension, number> = {
  model: 0,
  instruction: 1,
  skills: 2,
};

/** Stable Session identity for semantic changes, excluding editor focus and secrets. */
export function semanticDebugConfigurationKey<TSkill>(
  changes: DebugChangeState<TSkill>[],
): string {
  return JSON.stringify(
    changes
      .map((change) => ({
        modelName: change.modelName.trim(),
        modelProvider: change.modelProvider.trim(),
        modelApiBase: change.modelApiBase.trim(),
        instruction: change.instruction.trim(),
        selectedSkills: change.selectedSkills,
        agentKey: change.agentKey,
        dimension: change.dimension,
      }))
      .sort((left, right) =>
        `${left.agentKey}:${left.dimension}`.localeCompare(
          `${right.agentKey}:${right.dimension}`,
        ),
      ),
  );
}

/** Clear every candidate credential when its Agent topology or cloud changes. */
export function invalidateDebugVariantCredentials<
  TSkill,
  TVariant extends DebugVariantConfiguration<TSkill>,
>(variant: TVariant): TVariant {
  return {
    ...variant,
    apiKey: "",
    apiKeyLocked: false,
    apiKeyVisible: false,
    additionalChanges: variant.additionalChanges.map((change) => ({
      ...change,
      apiKey: "",
      apiKeyLocked: false,
      apiKeyVisible: false,
    })),
  };
}

/** Apply a semantic configuration edit without rewriting prior Session evidence. */
export function updateDebugVariantConfiguration<
  TVariant extends DebugVariantEvidence,
>(variant: TVariant, patch: Partial<TVariant>): TVariant {
  return {
    ...variant,
    ...patch,
    messages: variant.messages,
    ttftMs: variant.ttftMs,
    latencyMs: variant.latencyMs,
    toolCalls: variant.toolCalls,
    tokens: variant.tokens,
    error: variant.error,
    verdict: variant.verdict,
    verdictReason: variant.verdictReason,
  };
}

function changeKey(change: DebugChangeState): string {
  return `${change.agentKey}:${change.dimension}`;
}

function sameSkills(left: unknown[], right: unknown[]): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function hasRelevantChange<TSkill>(
  change: DebugChangeState<TSkill>,
  baseline: DebugChangeState<TSkill>,
): boolean {
  if (change.dimension === "model") {
    return (
      change.modelName !== baseline.modelName ||
      change.modelProvider !== baseline.modelProvider ||
      change.modelApiBase !== baseline.modelApiBase ||
      change.apiKey !== baseline.apiKey ||
      change.apiKeyLocked !== baseline.apiKeyLocked
    );
  }
  if (change.dimension === "instruction") {
    return change.instruction !== baseline.instruction;
  }
  return !sameSkills(change.selectedSkills, baseline.selectedSkills);
}

function primaryChange<TSkill>(
  variant: DebugVariantConfiguration<TSkill>,
): DebugChangeState<TSkill> {
  return {
    id: changeKey(variant),
    modelName: variant.modelName,
    modelProvider: variant.modelProvider,
    modelApiBase: variant.modelApiBase,
    apiKey: variant.apiKey,
    apiKeyLocked: variant.apiKeyLocked,
    apiKeyVisible: variant.apiKeyVisible,
    instruction: variant.instruction,
    selectedSkills: variant.selectedSkills,
    agentKey: variant.agentKey,
    dimension: variant.dimension,
  };
}

/**
 * Build the stable, complete scheme summary independently from editor focus.
 * Agent order follows the current topology and dimensions use product order.
 */
export function summarizeDebugChanges<TSkill>(
  changes: DebugChangeState<TSkill>[],
  agentOrder: string[],
  activeAgentKey: string,
  activeDimension: DebugComparisonDimension,
): DebugChangeSummaryGroup<TSkill>[] {
  const agentPosition = new Map(
    agentOrder.map((agentKey, index) => [agentKey, index]),
  );
  const sorted = [...changes].sort((left, right) => {
    const agentDifference =
      (agentPosition.get(left.agentKey) ?? Number.MAX_SAFE_INTEGER) -
      (agentPosition.get(right.agentKey) ?? Number.MAX_SAFE_INTEGER);
    if (agentDifference !== 0) return agentDifference;
    const unknownAgentDifference = left.agentKey.localeCompare(right.agentKey);
    if (unknownAgentDifference !== 0) return unknownAgentDifference;
    return dimensionOrder[left.dimension] - dimensionOrder[right.dimension];
  });
  const groups: DebugChangeSummaryGroup<TSkill>[] = [];
  sorted.forEach((change) => {
    let group = groups[groups.length - 1];
    if (!group || group.agentKey !== change.agentKey) {
      group = { agentKey: change.agentKey, changes: [] };
      groups.push(group);
    }
    group.changes.push({
      change,
      active:
        change.agentKey === activeAgentKey &&
        change.dimension === activeDimension,
    });
  });
  return groups;
}

export function previewDebugChangeSummary<TSkill>(
  groups: DebugChangeSummaryGroup<TSkill>[],
  limit: number,
): {
  groups: DebugChangeSummaryGroup<TSkill>[];
  hiddenCount: number;
} {
  const safeLimit = Math.max(0, Math.floor(limit));
  const total = groups.reduce(
    (count, group) => count + group.changes.length,
    0,
  );
  let remaining = safeLimit;
  const preview = groups.flatMap((group) => {
    if (remaining <= 0) return [];
    const changes = group.changes.slice(0, remaining);
    remaining -= changes.length;
    return changes.length ? [{ ...group, changes }] : [];
  });
  return {
    groups: preview,
    hiddenCount: Math.max(0, total - safeLimit),
  };
}

/** Remove one Agent/dimension change while keeping the editor on that target. */
export function removeDebugChange<
  TSkill,
  TVariant extends DebugVariantConfiguration<TSkill>,
>(variant: TVariant, targetBaseline: DebugChangeState<TSkill>): TVariant {
  const targetKey = changeKey(targetBaseline);
  if (changeKey(variant) === targetKey) {
    return {
      ...variant,
      ...targetBaseline,
      id: variant.id,
      additionalChanges: variant.additionalChanges.filter(
        (change) => changeKey(change) !== targetKey,
      ),
    } as TVariant;
  }
  if (
    !variant.additionalChanges.some(
      (change) => changeKey(change) === targetKey,
    )
  ) {
    return variant;
  }
  return {
    ...variant,
    additionalChanges: variant.additionalChanges.filter(
      (change) => changeKey(change) !== targetKey,
    ),
  } as TVariant;
}

/**
 * Move the focused editor to another Agent/dimension without discarding edits.
 * Only edited combinations are retained in additionalChanges, so navigating the
 * baseline configuration does not create duplicate candidate changes.
 */
export function switchPrimaryDebugChange<
  TSkill,
  TVariant extends DebugVariantConfiguration<TSkill>,
>(
  variant: TVariant,
  currentBaseline: DebugChangeState<TSkill>,
  targetBaseline: DebugChangeState<TSkill>,
): TVariant {
  const current = primaryChange(variant);
  const currentKey = changeKey(current);
  const targetKey = changeKey(targetBaseline);
  if (currentKey === targetKey) return variant;

  const promoted =
    variant.additionalChanges.find((change) => changeKey(change) === targetKey) ??
    targetBaseline;
  const remaining = variant.additionalChanges.filter((change) => {
    const key = changeKey(change);
    return key !== currentKey && key !== targetKey;
  });
  if (hasRelevantChange(current, currentBaseline)) {
    remaining.push({ ...current, id: currentKey });
  }

  return {
    ...variant,
    ...promoted,
    id: variant.id,
    additionalChanges: remaining,
  } as TVariant;
}
