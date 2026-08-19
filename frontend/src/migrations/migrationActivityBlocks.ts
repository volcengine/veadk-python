import type { MigrationActivityItem } from "../adk/migrations";
import type { Block } from "../blocks";

export function migrationActivityBlocks(items: MigrationActivityItem[]): Block[] {
  return items.flatMap<Block>((item) => {
    if (item.kind === "reasoning" && item.detail) {
      return [{
        kind: "thinking",
        text: item.detail,
        done: item.status !== "running",
      }];
    }
    if (item.kind === "message" && item.detail) {
      return [{ kind: "text", text: item.detail }];
    }
    if (item.kind === "plan") {
      return [{
        kind: "plan",
        title: item.title,
        summary: item.detail,
        items: item.plan ?? [],
        done: item.status !== "running",
      }];
    }
    if (item.kind === "command") {
      const tool = item.tool;
      const response = tool?.error || typeof tool?.exitCode === "number"
        ? {
            ...(tool.output !== undefined ? { output: tool.output } : {}),
            ...(tool.error ? { error: tool.error } : {}),
            ...(typeof tool.exitCode === "number"
              ? { exitCode: tool.exitCode }
              : {}),
          }
        : tool?.output;
      return [{
        kind: "tool",
        name: tool?.name ?? item.title,
        args: tool?.input,
        response,
        done: item.status !== "running",
        status: item.status,
      }];
    }
    if (item.kind === "status" && item.status !== "completed") {
      return [{
        kind: "tool",
        name: item.title,
        response: item.detail,
        done: item.status !== "running",
        status: item.status,
      }];
    }
    return [];
  });
}
