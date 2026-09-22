import type { MigrationActivityItem } from "../adk/migrations";
import type { Block } from "../blocks";

type RowFields = {
  id: string;
  itemType?: string;
  durationMs?: number;
  phase?: string;
};

/** The fields the shared row renderer reads, carried over from the Codex item. */
function rowFields(item: MigrationActivityItem): RowFields {
  return {
    id: item.id,
    ...(item.itemType ? { itemType: item.itemType } : {}),
    ...(typeof item.durationMs === "number" ? { durationMs: item.durationMs } : {}),
    ...(item.phase ? { phase: item.phase } : {}),
  };
}

/**
 * The intelligent build answers a Codex call with a typed result object, and the
 * shared row renders exactly that. A migration item carries the same pieces in flat
 * keys, so they are re-shaped here rather than handed over as a different contract.
 */
function toolResponse(
  item: MigrationActivityItem,
  tool: MigrationActivityItem["tool"],
): unknown {
  if (!tool) return item.detail;
  const response: Record<string, unknown> = { status: item.status };
  if (typeof tool.exitCode === "number") response.exitCode = tool.exitCode;
  if (tool.output !== undefined) response.output = tool.output;
  if (tool.error) response.error = tool.error;
  return response;
}

export function migrationActivityBlocks(items: MigrationActivityItem[]): Block[] {
  return items.flatMap<Block>((item) => {
    if (item.kind === "summary" && item.turn) {
      return [{ kind: "turn-summary", id: item.id, value: item.turn }];
    }
    if (item.kind === "reasoning" && item.detail) {
      return [{
        kind: "thinking",
        text: item.detail,
        done: item.status !== "running",
        ...rowFields(item),
      }];
    }
    if (item.kind === "message" && item.detail) {
      return [{ kind: "text", text: item.detail, ...rowFields(item) }];
    }
    if (item.kind === "plan") {
      return [{
        kind: "plan",
        title: item.title,
        summary: item.detail,
        items: item.plan ?? [],
        done: item.status !== "running",
        ...rowFields(item),
      }];
    }
    if (item.kind === "command") {
      const tool = item.tool;
      return [{
        kind: "tool",
        name: tool?.name ?? item.title,
        args: tool?.input,
        response: toolResponse(item, tool),
        done: item.status !== "running",
        status: item.status,
        ...(item.status === "failed" ? { defaultOpen: true } : {}),
        ...rowFields(item),
      }];
    }
    if (item.kind === "status" && item.status !== "completed") {
      return [{
        kind: "tool",
        name: item.title,
        response: item.detail,
        done: item.status !== "running",
        status: item.status,
        ...(item.status === "failed" ? { defaultOpen: true } : {}),
        ...rowFields(item),
      }];
    }
    return [];
  });
}
