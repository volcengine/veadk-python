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
