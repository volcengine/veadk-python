import type { Block } from "../blocks";
import { activeLocale, adkT } from "../adk/i18n";
import type { DevelopmentRun } from "../adk/developmentRuns";

export function developmentRunStatus(run: DevelopmentRun | null | undefined): string {
  if (!run) return "";
  if (["stopping", "waiting_user", "failed", "cancelled"].includes(run.state)) return run.statusMessage;
  if (run.phase === "reporting") return adkT("developmentRuns.reporting");
  if (run.state === "recovering") return run.statusMessage;
  if (["outcome_read", "delivery"].includes(run.phase)) return adkT("developmentRuns.packaging");
  if (run.phase === "version") return adkT("developmentRuns.savingVersion");
  if (run.phase === "cycle_complete") return adkT("developmentRuns.finishing");
  return run.statusMessage;
}

export function formatDevelopmentDuration(value: number | undefined): string {
  if (value == null || !Number.isFinite(value) || value < 0) return adkT("developmentRuns.notReported");
  const ms = Math.round(value);
  if (ms === 0) return `<${adkT("developmentRuns.durationUnits.milliseconds", { value: "1" })}`;
  if (ms < 1000) return adkT("developmentRuns.durationUnits.milliseconds", { value: ms.toLocaleString(activeLocale()) });
  // Round before splitting units so 59.95 seconds becomes one minute.
  const tenths = Math.round(ms / 100);
  const parts = [
    ["hours", Math.floor(tenths / 36000)],
    ["minutes", Math.floor(tenths % 36000 / 600)],
    ["seconds", tenths % 600 / 10],
  ] as const;
  return parts.filter(([, count]) => count > 0).map(([unit, count]) =>
    adkT(`developmentRuns.durationUnits.${unit}`, { value: count.toLocaleString(activeLocale(), { maximumFractionDigits: 1 }) })
  ).join(" ");
}

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const short = (value: unknown) => typeof value === "string" ? value.replace(/\s+/g, " ").trim().slice(0, 160) : "";

export function developmentToolLabel(block: Extract<Block, { kind: "tool" }>): string {
  const args = record(block.args);
  if (block.itemType === "dynamicToolCall" && block.name === "submit_build_result") return adkT("developmentRuns.submitResult");
  if (block.itemType === "commandExecution") {
    const actions = Array.isArray(args.commandActions) ? args.commandActions.map(record) : [];
    const types = new Set(actions.map(action => action.type));
    if (actions.length && types.size === 1) {
      if (types.has("read")) return adkT("developmentRuns.read", { target: "Read project files" });
      if (types.has("listFiles")) return adkT("developmentRuns.listFiles", { target: "List directory" });
      if (types.has("search")) return adkT("developmentRuns.search", { target: "Search project files" });
    }
    const command = typeof args.command === "string" ? args.command : "";
    const rules: [RegExp, string][] = [
      [/\b(?:pytest|vitest|jest)\b|\b(?:npm|pnpm|yarn) (?:run )?test\b/, "Run tests"],
      [/\b(?:npm|pnpm|yarn) (?:ci|install|add)\b|\b(?:pip|pip3|uv pip) install\b|\buv sync\b/, "Install dependencies"],
      [/\b(?:ruff|eslint|prettier|pyright|tsc)\b/, "Check code quality"],
      [/\b(?:npm|pnpm|yarn) (?:run )?build\b|\bpython[^;]* -m build\b/, "Build project"],
      [/\bgit (?:status|diff|log|show)\b/, "Inspect Git changes"],
      [/\bgit (?:add|commit)\b/, "Save Git changes"],
      [/\b(?:curl|wget)\b/, "Send HTTP request"],
      [/\bcompileall\b/, "Check Python syntax"],
    ];
    const summary = rules.find(([pattern]) => pattern.test(command))?.[1];
    // A caller that already names the row keeps its own wording: the migration
    // publishes commands as native status ("命令执行完成") instead of guessing what
    // the shell command does, and that decision must survive the native row.
    return summary ? adkT("developmentRuns.command", { target: summary }) : block.name;
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
