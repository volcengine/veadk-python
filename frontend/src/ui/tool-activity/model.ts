export type ToolActivityStatus = "queued" | "running" | "completed" | "failed";
export type ToolActivityCategory =
  | "command"
  | "read"
  | "search"
  | "file-change"
  | "mcp"
  | "authorization"
  | "generic";

export interface ToolActivityInput {
  name: string;
  title?: string;
  callId?: string;
  args?: unknown;
  response?: unknown;
  done: boolean;
  status?: "running" | "completed" | "failed";
  defaultOpen?: boolean;
  source?: "codex-sandbox" | "studio" | "runtime";
}

export interface ToolOutputPreview {
  text: string;
  head: string[];
  tail: string[];
  omittedLines: number;
  omittedCharacters: number;
}

export interface ToolPresentation {
  category: ToolActivityCategory;
  titleKey: string;
  title?: string;
  summary: string;
  status: ToolActivityStatus;
  source?: ToolActivityInput["source"];
  command?: string;
  cwd?: string;
  output?: ToolOutputPreview;
  exitCode?: number;
  durationMs?: number;
  resultCount?: number;
  paths: string[];
  defaultOpen: boolean;
  rawArgs?: unknown;
  rawResponse?: unknown;
}

export type ToolActivityGroup =
  | { kind: "activity"; item: ToolPresentation }
  | { kind: "exploration"; items: ToolPresentation[] };

const MASK = "••••••••";
const OUTPUT_EDGE_LINES = 5;
const OUTPUT_EDGE_CHARACTERS = 8_000;
const MAX_RAW_DEPTH = 8;
const MAX_RAW_ITEMS = 50;
const MAX_RAW_STRING_LENGTH = 4_000;
const MAX_RAW_NODES = 500;
const SENSITIVE_KEY =
  /(?:authorization|cookie|password|passwd|secret|token|api[_-]?key|access[_-]?key|credential|signature|^env(?:ironment)?$|^ak$|^sk$)/i;
const ANSI_CSI_ESCAPE = /\u001b\[[0-?]*[ -/]*[@-~]/g;
const ANSI_OSC_ESCAPE = /\u001b\][^\u0007]*(?:\u0007|\u001b\\)/g;
const UNSAFE_CONTROL =
  /[\u0000-\u0008\u000b\u000c\u000e-\u001a\u001c-\u001f\u007f-\u009f]/g;
const COMMAND_NAMES = new Set([
  "exec_command",
  "commandExecution",
  "command_execution",
  "run_code",
  "execute_in_sandbox",
  "Run command",
]);
const SEARCH_NAMES = new Set(["web_search", "search", "grep", "rg"]);
const READ_NAMES = new Set(["read_file", "read", "list_files", "glob", "ls"]);
const FILE_CHANGE_NAMES = new Set(["apply_patch", "file_change", "fileChange"]);

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function stringValue(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function numberValue(...values: unknown[]): number | undefined {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (
      typeof value === "string" &&
      value.trim() &&
      Number.isFinite(Number(value))
    ) {
      return Number(value);
    }
  }
  return undefined;
}

function maskText(value: string): string {
  return value
    .replace(/\bBearer\s+[^\s,;]+/gi, `Bearer ${MASK}`)
    .replace(/\b(?:set-)?cookie\s*:\s*[^\r\n]*/gi, `cookie: ${MASK}`)
    .replace(/\bAKLT[A-Za-z0-9_-]{6,}\b/g, MASK)
    .replace(
      /((?:access[_-]?key(?:[_-]?id)?|secret(?:[_-]?(?:access)?[_-]?key)?|session[_-]?token|security[_-]?token|client[_-]?secret|api[_-]?key|authorization|cookie|[a-z0-9_-]*(?:password|secret|token)|credential|ak|sk)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&]+)/gi,
      `$1${MASK}`,
    )
    .replace(
      /([?&](?:access[_-]?key|api[_-]?key|client[_-]?secret|security[_-]?token|session[_-]?token|secret|token|password|authorization|cookie|credential)=)[^&#\s]+/gi,
      `$1${MASK}`,
    )
    .replace(
      /([?&](?:x-amz-(?:credential|signature|security-token)|x-tos-signature|signature)=)[^&#\s]+/gi,
      `$1${MASK}`,
    );
}

function safeVisibleText(value: string): string {
  return maskText(value)
    .replace(ANSI_CSI_ESCAPE, "")
    .replace(ANSI_OSC_ESCAPE, "")
    .replace(UNSAFE_CONTROL, "");
}

export function maskToolRawValue(
  value: unknown,
  depth = 0,
  seen = new WeakSet<object>(),
  budget = { remaining: MAX_RAW_NODES },
): unknown {
  if (budget.remaining <= 0) return "[truncated]";
  budget.remaining -= 1;
  if (depth >= MAX_RAW_DEPTH) return "[truncated]";
  if (typeof value === "string") {
    const masked = safeVisibleText(value);
    return masked.length > MAX_RAW_STRING_LENGTH
      ? `${masked.slice(0, MAX_RAW_STRING_LENGTH)}… [truncated]`
      : masked;
  }
  if (value === null || typeof value !== "object") return value;
  if (seen.has(value)) return "[circular]";
  seen.add(value);
  if (Array.isArray(value)) {
    const items = value
      .slice(0, MAX_RAW_ITEMS)
      .map((item) => maskToolRawValue(item, depth + 1, seen, budget));
    if (value.length > MAX_RAW_ITEMS || budget.remaining <= 0) {
      items.push("[truncated]");
    }
    return items;
  }
  const object = record(value);
  if (!object) return value;
  return Object.fromEntries(
    Object.entries(object)
      .slice(0, MAX_RAW_ITEMS)
      .map(([key, item]) => [
        key,
        SENSITIVE_KEY.test(key)
          ? MASK
          : maskToolRawValue(item, depth + 1, seen, budget),
      ]),
  );
}

export function previewToolOutput(
  value: string,
): ToolOutputPreview | undefined {
  const text = safeVisibleText(value).trimEnd();
  if (!text) return undefined;
  const lines = text.split(/\r?\n/);
  if (lines.length === 1 && text.length > OUTPUT_EDGE_CHARACTERS * 2) {
    return {
      text:
        text.slice(0, OUTPUT_EDGE_CHARACTERS) +
        text.slice(-OUTPUT_EDGE_CHARACTERS),
      head: [text.slice(0, OUTPUT_EDGE_CHARACTERS)],
      tail: [text.slice(-OUTPUT_EDGE_CHARACTERS)],
      omittedLines: 0,
      omittedCharacters: text.length - OUTPUT_EDGE_CHARACTERS * 2,
    };
  }
  if (lines.length <= OUTPUT_EDGE_LINES * 2) {
    return {
      text,
      head: lines,
      tail: [],
      omittedLines: 0,
      omittedCharacters: 0,
    };
  }
  return {
    text,
    head: lines.slice(0, OUTPUT_EDGE_LINES),
    tail: lines.slice(-OUTPUT_EDGE_LINES),
    omittedLines: lines.length - OUTPUT_EDGE_LINES * 2,
    omittedCharacters: 0,
  };
}

function categoryFor(name: string): ToolActivityCategory {
  if (COMMAND_NAMES.has(name)) return "command";
  if (SEARCH_NAMES.has(name) || /search/i.test(name)) return "search";
  if (READ_NAMES.has(name) || /(?:read|list|glob)/i.test(name)) return "read";
  if (
    FILE_CHANGE_NAMES.has(name) ||
    /(?:write|edit|patch|file.?change)/i.test(name)
  ) {
    return "file-change";
  }
  if (/^(?:mcp|tool__)/i.test(name) || name.includes("/")) return "mcp";
  if (/auth|credential|approval/i.test(name)) return "authorization";
  return "generic";
}

function statusFor(
  input: ToolActivityInput,
  response: Record<string, unknown> | undefined,
): ToolActivityStatus {
  if (input.status) return input.status;
  const declared = stringValue(response?.status).toLowerCase();
  if (
    response?.ok === false ||
    ["failed", "error", "cancelled", "denied", "timeout"].includes(declared)
  )
    return "failed";
  if (input.done || ["completed", "done", "success"].includes(declared))
    return "completed";
  return "running";
}

function pathValues(value: unknown): string[] {
  if (typeof value === "string") return value.trim() ? [value.trim()] : [];
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item === "string") return item.trim() ? [item.trim()] : [];
    const itemRecord = record(item);
    const path = stringValue(
      itemRecord?.path,
      itemRecord?.filename,
      itemRecord?.name,
    );
    return path ? [path] : [];
  });
}

function summaryFor(
  category: ToolActivityCategory,
  name: string,
  args: Record<string, unknown> | undefined,
  response: Record<string, unknown> | undefined,
  paths: string[],
): string {
  if (category === "command") {
    return safeVisibleText(
      stringValue(args?.command, args?.cmd, args?.script, response?.command),
    );
  }
  if (category === "search") {
    return safeVisibleText(
      stringValue(args?.query, args?.pattern, args?.search, response?.query),
    );
  }
  if (category === "read" || category === "file-change") {
    return paths.slice(0, 2).map(safeVisibleText).join(", ");
  }
  if (category === "mcp") {
    return safeVisibleText(
      stringValue(args?.query, args?.resource, args?.path),
    );
  }
  return safeVisibleText(
    stringValue(
      args?.title,
      args?.name,
      response?.message,
      response?.status,
      name,
    ),
  );
}

export function presentToolActivity(
  input: ToolActivityInput,
): ToolPresentation {
  const args = record(input.args);
  const response = record(input.response);
  const category = categoryFor(input.name);
  const status = statusFor(input, response);
  const nestedDisplay = record(response?.display) ?? record(args?.display);
  const output = stringValue(
    response?.aggregatedOutput,
    response?.aggregated_output,
    response?.output,
    response?.errorMessage,
    response?.error_message,
  );
  const paths = [
    ...pathValues(args?.paths ?? args?.files ?? args?.changes ?? args?.path),
    ...pathValues(response?.paths ?? response?.files ?? response?.changes),
  ];
  const exitCode = numberValue(response?.exitCode, response?.exit_code);
  const durationMs = numberValue(
    response?.durationMs,
    response?.duration_ms,
    nestedDisplay?.durationMs,
  );
  const resultCount = numberValue(
    response?.count,
    response?.total,
    response?.totalCount,
  );

  return {
    category,
    titleKey: `${category}.${status}`,
    title: input.title,
    summary: summaryFor(category, input.name, args, response, paths),
    status,
    source: input.source,
    command:
      category === "command"
        ? safeVisibleText(
            stringValue(
              args?.command,
              args?.cmd,
              args?.script,
              response?.command,
            ),
          )
        : undefined,
    cwd:
      category === "command"
        ? safeVisibleText(stringValue(args?.cwd, response?.cwd)) || undefined
        : undefined,
    output: previewToolOutput(output),
    exitCode,
    durationMs,
    resultCount,
    paths: [...new Set(paths.map(safeVisibleText))],
    defaultOpen:
      input.defaultOpen === true || status === "running" || status === "failed",
    rawArgs:
      input.args === undefined ? undefined : maskToolRawValue(input.args),
    rawResponse:
      input.response === undefined
        ? undefined
        : maskToolRawValue(input.response),
  };
}

export function isSafeExploration(item: ToolPresentation): boolean {
  return (
    item.status === "completed" &&
    (item.category === "read" || item.category === "search")
  );
}

export function groupToolActivities(
  activities: ToolPresentation[],
): ToolActivityGroup[] {
  const groups: ToolActivityGroup[] = [];
  for (const item of activities) {
    const previous = groups[groups.length - 1];
    if (!isSafeExploration(item)) {
      groups.push({ kind: "activity", item });
      continue;
    }
    if (
      previous?.kind === "exploration" &&
      previous.items[previous.items.length - 1]?.source === item.source
    ) {
      previous.items.push(item);
      continue;
    }
    groups.push({ kind: "exploration", items: [item] });
  }
  return groups;
}
