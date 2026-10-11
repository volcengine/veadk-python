import type { AgentNode } from "./adk/client";
import type { Turn } from "./blocks";

export interface TranscriptRow {
  key: string;
  turnIndexes: number[];
  parallelParent?: string;
}

function directParallelParent(
  node: AgentNode,
  author: string,
  parent?: AgentNode,
): AgentNode | undefined {
  if (node.name === author || node.id === author) {
    return parent?.type === "parallel" ? parent : undefined;
  }
  for (const child of node.children) {
    const found = directParallelParent(child, author, node);
    if (found) return found;
  }
  return undefined;
}

function parallelGroupKey(
  turn: Turn,
  root?: AgentNode,
): { key: string; parent: string } | undefined {
  if (turn.role !== "assistant" || !root) return undefined;
  const author = turn.meta?.author;
  if (!author) return undefined;
  const parent = directParallelParent(root, author);
  if (!parent) return undefined;
  const parentKey = parent.id || parent.path.join("/") || parent.name;
  const invocationId = turn.meta?.invocationId ?? "";
  return {
    key: `${invocationId}::${parentKey}`,
    parent: parent.name,
  };
}

/** Build presentation rows without changing the source turn indexes. Only
 * direct children of the same Parallel Agent and invocation share a row, so
 * Sequential stages and Loop rounds keep their original vertical order. */
export function buildTranscriptRows(
  turns: Turn[],
  root?: AgentNode,
): TranscriptRow[] {
  const rows: Array<TranscriptRow & { groupKey?: string }> = [];

  turns.forEach((turn, index) => {
    const parallel = parallelGroupKey(turn, root);
    const previous = rows[rows.length - 1];
    if (parallel && previous?.groupKey === parallel.key) {
      previous.turnIndexes.push(index);
      return;
    }
    rows.push({
      key: parallel ? `parallel-${parallel.key}-${index}` : `turn-${index}`,
      turnIndexes: [index],
      parallelParent: parallel?.parent,
      groupKey: parallel?.key,
    });
  });

  return rows.map(({ groupKey, ...row }) => row);
}

/** Derive MPA response regions without changing persisted/projected turns. */
export function groupMpaTranscriptTurns(
  turns: Turn[],
  enabled: boolean,
  requestBusy: boolean,
): Turn[] {
  if (!enabled) return turns;
  const result: Turn[] = [];
  for (let index = 0; index < turns.length;) {
    const first = turns[index];
    if (first.role !== "assistant") {
      result.push(first);
      index += 1;
      continue;
    }
    const fragments: Turn[] = [];
    while (index < turns.length && turns[index].role === "assistant") {
      fragments.push(turns[index++]);
    }
    const sandboxAnswers = new Set(fragments.flatMap((turn) =>
      turn.meta?.mpaFinalAnswer ? [turn.meta.mpaFinalAnswer.trim()] : []
    ));
    const visibleFragments = fragments.map((turn) => {
      const answerText = turn.blocks.filter((block) => block.kind === "text")
        .map((block) => block.text).join("").trim();
      // This is a reversible view filter: later extensions restore all text.
      if (!turn.meta?.mpaFinalAnswer && answerText && sandboxAnswers.has(answerText)) {
        return { ...turn, blocks: turn.blocks.filter((block) => block.kind !== "text") };
      }
      return turn;
    });
    const answer = [...visibleFragments].reverse().find((turn) =>
      turn.blocks.some((block) => block.kind === "text" && block.text.trim())
    ) ?? fragments[fragments.length - 1];
    const usage: Record<string, number> = {};
    const legacyUsage = new Map<string, number>();
    const hasLedger = fragments.some((turn) => turn.meta?.mpaUsage);
    for (const fragment of fragments) {
      for (const [key, count] of Object.entries(fragment.meta?.mpaUsage ?? {})) {
        usage[key] = Math.max(usage[key] ?? 0, count);
      }
      const tokens = fragment.meta?.tokens;
      if (typeof tokens === "number" && Number.isFinite(tokens) && tokens >= 0) {
        const key = fragment.meta?.invocationId || "unidentified";
        legacyUsage.set(key, Math.max(legacyUsage.get(key) ?? 0, tokens));
      }
    }
    const counts = hasLedger ? Object.values(usage) : [...legacyUsage.values()];
    const timestamps = fragments.flatMap((turn) => turn.meta?.ts ? [turn.meta.ts] : []);
    result.push({
      role: "assistant",
      blocks: visibleFragments.flatMap((turn) => turn.blocks),
      meta: {
        ...answer.meta,
        localId: first.meta?.localId,
        // Do not label the consolidated MPA response as one of its subagents.
        author: undefined,
        streaming: (index === turns.length && requestBusy) ||
          fragments.some((turn) => turn.meta?.streaming === true),
        a2aStatus: fragments[fragments.length - 1].meta?.a2aStatus,
        ts: timestamps.length ? Math.max(...timestamps) : undefined,
        tokens: counts.length ? counts.reduce((total, count) => total + count, 0) : undefined,
        ...(hasLedger ? { mpaUsage: usage } : {}),
      },
    });
  }
  return result;
}
