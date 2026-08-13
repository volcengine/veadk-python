export interface ComparisonHistoryRecord {
  timestamp: number;
  fingerprint: string;
  candidateName: string;
  configDiffs: Array<{ agentKey: string; dimension: string }>;
  metrics: {
    ttftMs?: number | null;
    latencyMs: number | null;
    toolCalls?: number | null;
    tokens: number | null;
  };
  verdict: string;
  reason: string;
  inputDiverged?: boolean;
  runId: string;
  sessionId: string;
  traceId?: string;
}

export function appendComparisonRecord(
  records: ComparisonHistoryRecord[],
  record: ComparisonHistoryRecord,
): ComparisonHistoryRecord[] {
  return [record, ...records].slice(0, 20);
}

export function serializeComparisonRecords(records: unknown[]): string {
  return JSON.stringify(
    records.map((value) => {
      const record = value as Partial<ComparisonHistoryRecord>;
      return {
        timestamp: record.timestamp,
        fingerprint: record.fingerprint,
        candidateName: record.candidateName,
        configDiffs: Array.isArray(record.configDiffs)
          ? record.configDiffs.map((diff) => ({
              agentKey: diff.agentKey,
              dimension: diff.dimension,
            }))
          : [],
        metrics: {
          ttftMs: record.metrics?.ttftMs ?? null,
          latencyMs: record.metrics?.latencyMs ?? null,
          toolCalls: record.metrics?.toolCalls ?? null,
          tokens: record.metrics?.tokens ?? null,
        },
        verdict: record.verdict,
        reason: record.reason,
        inputDiverged: Boolean(record.inputDiverged),
        runId: record.runId,
        sessionId: record.sessionId,
        traceId: record.traceId,
      };
    }),
  );
}

function storageKey(draftKey: string): string {
  return `veadk.multiAgentComparison.${encodeURIComponent(draftKey)}`;
}

export function readComparisonRecords(
  draftKey: string,
): ComparisonHistoryRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(
      window.localStorage.getItem(storageKey(draftKey)) ?? "[]",
    );
    return Array.isArray(value) ? value.slice(0, 20) : [];
  } catch {
    return [];
  }
}

export function persistComparisonRecord(
  draftKey: string,
  record: ComparisonHistoryRecord,
): void {
  if (typeof window === "undefined") return;
  const next = appendComparisonRecord(readComparisonRecords(draftKey), record);
  window.localStorage.setItem(storageKey(draftKey), serializeComparisonRecords(next));
}
