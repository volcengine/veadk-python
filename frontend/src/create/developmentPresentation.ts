import type { Block } from "../blocks";
import { adkT } from "../adk/i18n";

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const short = (value: unknown) => typeof value === "string" ? value.replace(/\s+/g, " ").trim().slice(0, 160) : "";

export function developmentToolLabel(block: Extract<Block, { kind: "tool" }>): string {
  const args = record(block.args);
  if (block.itemType === "commandExecution") {
    const actions = Array.isArray(args.commandActions) ? args.commandActions.map(record) : [];
    const labels = actions.map((action) => {
      const target = short(action.name || action.path);
      if (action.type === "read") return adkT("developmentRuns.read", { target });
      if (action.type === "listFiles") return adkT("developmentRuns.listFiles", { target });
      if (action.type === "search") return adkT("developmentRuns.search", { target: short(action.query || action.path) });
      return "";
    }).filter(Boolean);
    if (labels.length && labels.length === actions.length) return [...new Set(labels)].join(" · ");
    return adkT("developmentRuns.command", { target: short(args.command) });
  }
  if (block.itemType === "fileChange") {
    const paths = Array.isArray(args.changes) ? args.changes.map((change) => short(record(change).path)).filter(Boolean) : [];
    return adkT("developmentRuns.editFiles", { target: paths.join(", ") });
  }
  if (block.itemType === "webSearch") return adkT("developmentRuns.webSearch", { target: short(args.query) });
  return block.name;
}
export const isDevelopmentProcess = (block: Block) =>
  ["tool", "thinking", "plan", "diff"].includes(block.kind);
export function developmentProcessGroups(blocks: Block[]): { id: string; process: boolean; blocks: Block[] }[] {
  const groups: { id: string; process: boolean; blocks: Block[] }[] = [];
  blocks.forEach((block, index) => {
    if (block.kind === "progress") return;
    const process = isDevelopmentProcess(block);
    const last = groups[groups.length - 1];
    if (process && last?.process) last.blocks.push(block);
    else groups.push({ id: block.id || `${block.kind}:${index}`, process, blocks: [block] });
  });
  return groups;
}
