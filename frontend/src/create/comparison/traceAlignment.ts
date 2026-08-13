export interface ComparisonTraceSpan {
  id: string;
  name: string;
  invocationId?: string;
  toolCallId?: string;
  parentId?: string;
  startTime?: number;
}

function exactIdentity(span: ComparisonTraceSpan): string | null {
  if (span.toolCallId) return `tool:${span.toolCallId}`;
  if (span.invocationId) {
    return `invocation:${span.invocationId}:${span.name}`;
  }
  return null;
}

function logicalOperationName(name: string): string {
  const operation = name.trim().split(/\s+/, 1)[0];
  return operation === "generate_content" ? operation : name;
}

function logicalPathIdentities(
  spans: ComparisonTraceSpan[],
): Map<string, string> {
  const byId = new Map(spans.map((span) => [span.id, span]));
  const sourceIndex = new Map(spans.map((span, index) => [span.id, index]));
  const siblingGroups = new Map<string, ComparisonTraceSpan[]>();

  for (const span of spans) {
    const key = `${span.parentId ?? ""}\u0000${logicalOperationName(span.name)}`;
    siblingGroups.set(key, [...(siblingGroups.get(key) ?? []), span]);
  }
  for (const siblings of siblingGroups.values()) {
    siblings.sort((left, right) => {
      if (left.startTime !== undefined && right.startTime !== undefined) {
        const timeDifference = left.startTime - right.startTime;
        if (timeDifference !== 0) return timeDifference;
      }
      return (sourceIndex.get(left.id) ?? 0) - (sourceIndex.get(right.id) ?? 0);
    });
  }

  const siblingIndex = new Map<string, number>();
  for (const siblings of siblingGroups.values()) {
    siblings.forEach((span, index) => siblingIndex.set(span.id, index));
  }

  const result = new Map<string, string>();
  const visiting = new Set<string>();
  const pathFor = (span: ComparisonTraceSpan): string | null => {
    const cached = result.get(span.id);
    if (cached) return cached;
    if (visiting.has(span.id)) return null;

    visiting.add(span.id);
    const segment = `${logicalOperationName(span.name)}[${siblingIndex.get(span.id) ?? 0}]`;
    const parent = span.parentId ? byId.get(span.parentId) : undefined;
    const parentPath = parent ? pathFor(parent) : null;
    visiting.delete(span.id);
    const path = parentPath ? `${parentPath}/${segment}` : `path:${segment}`;
    result.set(span.id, path);
    return path;
  };

  for (const span of spans) pathFor(span);
  return result;
}

export function alignTraceEvidence(
  baseline: ComparisonTraceSpan[],
  candidate: ComparisonTraceSpan[],
): {
  matches: Array<{ baselineId: string; candidateId: string; key: string }>;
  unmatchedBaselineIds: string[];
  unmatchedCandidateIds: string[];
} {
  const byIdentity = (
    spans: ComparisonTraceSpan[],
    identity: (span: ComparisonTraceSpan) => string | null,
  ) => {
    const result = new Map<string, ComparisonTraceSpan[]>();
    for (const span of spans) {
      const key = identity(span);
      if (!key) continue;
      result.set(key, [...(result.get(key) ?? []), span]);
    }
    return result;
  };
  const matchedBaseline = new Set<string>();
  const matchedCandidate = new Set<string>();
  const matches: Array<{
    baselineId: string;
    candidateId: string;
    key: string;
  }> = [];
  const matchUnique = (
    baselineIdentity: (span: ComparisonTraceSpan) => string | null,
    candidateIdentity: (span: ComparisonTraceSpan) => string | null,
  ) => {
    const unmatchedBaseline = baseline.filter(
      (span) => !matchedBaseline.has(span.id),
    );
    const unmatchedCandidate = candidate.filter(
      (span) => !matchedCandidate.has(span.id),
    );
    const baselineByIdentity = byIdentity(unmatchedBaseline, baselineIdentity);
    const candidateByIdentity = byIdentity(unmatchedCandidate, candidateIdentity);
    for (const baselineSpan of unmatchedBaseline) {
      const key = baselineIdentity(baselineSpan);
      if (!key) continue;
      const baselineMatches = baselineByIdentity.get(key) ?? [];
      const candidateMatches = candidateByIdentity.get(key) ?? [];
      if (baselineMatches.length !== 1 || candidateMatches.length !== 1) continue;
      matches.push({
        baselineId: baselineSpan.id,
        candidateId: candidateMatches[0].id,
        key,
      });
      matchedBaseline.add(baselineSpan.id);
      matchedCandidate.add(candidateMatches[0].id);
    }
  };

  matchUnique(exactIdentity, exactIdentity);

  const baselinePaths = logicalPathIdentities(baseline);
  const candidatePaths = logicalPathIdentities(candidate);
  matchUnique(
    (span) => baselinePaths.get(span.id) ?? null,
    (span) => candidatePaths.get(span.id) ?? null,
  );

  const baselineOrder = new Map(
    baseline.map((span, index) => [span.id, index]),
  );
  matches.sort(
    (left, right) =>
      (baselineOrder.get(left.baselineId) ?? 0) -
      (baselineOrder.get(right.baselineId) ?? 0),
  );
  return {
    matches,
    unmatchedBaselineIds: baseline
      .filter((span) => !matchedBaseline.has(span.id))
      .map((span) => span.id),
    unmatchedCandidateIds: candidate
      .filter((span) => !matchedCandidate.has(span.id))
      .map((span) => span.id),
  };
}

export function attributionLevel(input: {
  agentCount: number;
  dimensionCount: number;
  inputDiverged: boolean;
}): "dimension" | "scheme" {
  return input.agentCount === 1 &&
    input.dimensionCount === 1 &&
    !input.inputDiverged
    ? "dimension"
    : "scheme";
}
