import type { Block, CodexSandboxActivity } from "../../blocks";

export interface CodexSandboxProgressEvent {
  id: string;
  block: Block;
  appendText?: boolean;
  finalAnswer?: boolean;
}

export interface CodexSandboxProgress {
  toolName: string;
  requestId: string;
  title?: string;
  agentSessionId?: string;
  sandboxSessionId?: string;
  threadId?: string;
  terminalStatus?: "completed" | "failed";
  event: CodexSandboxProgressEvent;
}

const MAX_ACTIVITY_ITEMS = 200;
const MAX_ACTIVITY_CHARACTERS = 280_000;

function activitySize(item: CodexSandboxActivity["items"][number]): number {
  try {
    return JSON.stringify(item).length;
  } catch {
    return MAX_ACTIVITY_CHARACTERS;
  }
}

function trimActivityItems(
  items: CodexSandboxActivity["items"],
): CodexSandboxActivity["items"] {
  const retained = items.slice(-MAX_ACTIVITY_ITEMS);
  let totalCharacters = retained.reduce(
    (total, item) => total + activitySize(item),
    0,
  );
  while (retained.length > 1 && totalCharacters > MAX_ACTIVITY_CHARACTERS) {
    totalCharacters -= activitySize(retained.shift()!);
  }
  return retained;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function normalizedStatus(
  value: unknown,
  eventType = "",
): "running" | "completed" | "failed" {
  const status = asString(value).toLowerCase();
  if (eventType.endsWith(".failed") || ["failed", "error", "declined", "cancelled"].includes(status)) {
    return "failed";
  }
  if (eventType.endsWith(".completed") || ["completed", "done", "success"].includes(status)) {
    return "completed";
  }
  return "running";
}

function responseValue(event: Record<string, unknown>): unknown {
  if (event.response !== undefined) return event.response;
  if (event.result !== undefined) return event.result;
  const output = event.aggregatedOutput ?? event.aggregated_output ?? event.output;
  const exitCode = event.exitCode ?? event.exit_code;
  if (output === undefined && exitCode === undefined) return undefined;
  return {
    ...(output !== undefined ? { output } : {}),
    ...(exitCode !== undefined ? { exitCode } : {}),
  };
}

function argumentsValue(event: Record<string, unknown>): unknown {
  if (event.args !== undefined) return event.args;
  if (event.arguments !== undefined) return event.arguments;
  if (event.input !== undefined) return event.input;
  const command = asString(event.command);
  const cwd = asString(event.cwd);
  if (command || cwd) {
    return { ...(command ? { command } : {}), ...(cwd ? { cwd } : {}) };
  }
  if (event.changes !== undefined) return { changes: event.changes };
  if (event.approval !== undefined) return event.approval;
  return undefined;
}

function toolBlock(
  name: string,
  id: string,
  status: "running" | "completed" | "failed",
  args?: unknown,
  response?: unknown,
): Block {
  return {
    kind: "tool",
    name,
    callId: id,
    args,
    response,
    done: status !== "running",
    status,
    ...(status === "failed" ? { defaultOpen: true } : {}),
  };
}

function parseNormalizedEvent(
  event: Record<string, unknown>,
): CodexSandboxProgressEvent | null {
  const id = asString(event.id || event.itemId || event.item_id);
  const kind = asString(event.kind);
  if (!id || !kind) return null;
  const status = normalizedStatus(event.status);
  const text = asString(event.text || event.detail || event.delta);
  const appendText = !asString(event.text || event.detail) && typeof event.delta === "string";

  if (kind === "thinking" || kind === "reasoning") {
    return text
      ? { id, block: { kind: "thinking", text, done: status !== "running" }, appendText }
      : null;
  }
  if (kind === "commentary") {
    return text ? { id, block: { kind: "text", text }, appendText } : null;
  }
  if (["message", "text", "assistant_final", "final"].includes(kind)) {
    return text
      ? { id, block: { kind: "text", text }, appendText, finalAnswer: true }
      : null;
  }
  if (kind === "plan") {
    const plan = Array.isArray(event.plan) ? event.plan : [];
    return {
      id,
      block: {
        kind: "plan",
        title: asString(event.title) || "Codex 执行计划",
        summary: text || undefined,
        items: plan.flatMap((value) => {
          const item = asRecord(value);
          const itemText = asString(item?.text);
          if (!itemText) return [];
          const itemStatus = asString(item?.status);
          return [{
            text: itemText,
            status: (["pending", "in_progress", "completed", "failed"].includes(itemStatus)
              ? itemStatus
              : "pending") as "pending" | "in_progress" | "completed" | "failed",
          }];
        }),
        done: status !== "running",
      },
    };
  }
  if ([
    "tool",
    "command",
    "command_execution",
    "commandExecution",
    "file_change",
    "fileChange",
    "mcp_tool_call",
    "mcpToolCall",
    "collab_tool_call",
    "web_search",
    "approval",
    "status",
  ].includes(kind)) {
    const fallbackName = kind === "file_change" || kind === "fileChange"
      ? "修改文件"
      : kind === "approval"
        ? "等待操作批准"
        : kind === "status"
          ? "Codex 状态"
          : "运行命令";
    const args = argumentsValue(event);
    const response = responseValue(event) ?? (kind === "status" ? text || undefined : undefined);
    return {
      id,
      block: toolBlock(asString(event.name || event.title) || fallbackName, id, status, args, response),
    };
  }
  return null;
}

function parseRawCodexEvent(
  event: Record<string, unknown>,
): CodexSandboxProgressEvent | null {
  const eventType = asString(event.type);
  const item = asRecord(event.item);
  const itemType = asString(item?.type);
  const id = asString(item?.id || event.id) || (eventType === "turn.failed" ? "turn" : "");
  if (!id) return null;
  const status = normalizedStatus(item?.status, eventType);

  if (itemType === "reasoning" || itemType === "agent_message") {
    const text = asString(item?.text);
    if (!text) return null;
    return {
      id,
      block: itemType === "reasoning"
        ? { kind: "thinking", text, done: status !== "running" }
        : { kind: "text", text },
      ...(itemType === "agent_message" && item?.phase !== "commentary"
        ? { finalAnswer: true }
        : {}),
    };
  }

  if (itemType === "todo_list") {
    const todos = Array.isArray(item?.items) ? item.items : [];
    const plan = todos.flatMap((value) => {
      const todo = asRecord(value);
      const text = asString(todo?.text);
      if (!text) return [];
      const rawStatus = asString(todo?.status).toLowerCase();
      const todoStatus = todo?.completed === true || ["completed", "done"].includes(rawStatus)
        ? "completed"
        : ["failed", "error"].includes(rawStatus)
          ? "failed"
          : ["in_progress", "running"].includes(rawStatus)
            ? "in_progress"
            : "pending";
      return [{ text, status: todoStatus as "pending" | "in_progress" | "completed" | "failed" }];
    });
    if (!plan.length) return null;
    return {
      id,
      block: {
        kind: "plan",
        title: "Codex 执行计划",
        summary: `已完成 ${plan.filter((todo) => todo.status === "completed").length}/${plan.length} 项`,
        items: plan,
        done: status !== "running",
      },
    };
  }

  if (itemType === "command_execution") {
    const name = status === "running" ? "正在执行命令" : status === "failed" ? "命令执行失败" : "命令执行完成";
    return { id, block: toolBlock(name, id, status, argumentsValue(item ?? {}), responseValue(item ?? {})) };
  }
  if (itemType === "file_change") {
    const changes = Array.isArray(item?.changes) ? item.changes : [];
    const subject = changes.length ? `${changes.length} 个项目文件` : "项目文件";
    const name = status === "running" ? `正在更新${subject}` : status === "failed" ? `更新${subject}失败` : `已更新${subject}`;
    return { id, block: toolBlock(name, id, status, changes.length ? { changes } : undefined) };
  }
  if (itemType === "mcp_tool_call") {
    const label = [asString(item?.server), asString(item?.tool)].filter(Boolean).join("/") || "外部工具";
    const name = status === "running" ? `正在调用工具 ${label}` : status === "failed" ? `工具 ${label} 调用未完成` : `已调用工具 ${label}`;
    const error = asRecord(item?.error);
    const response = item?.result !== undefined ? item.result : asString(error?.message) || undefined;
    return { id, block: toolBlock(name, id, status, item?.arguments, response) };
  }
  if (itemType === "collab_tool_call") {
    const operation = asString(item?.tool);
    const labels: Record<string, [string, string, string]> = {
      spawn_agent: ["正在启动子任务", "子任务已启动", "子任务启动失败"],
      send_input: ["正在向子任务发送信息", "已向子任务发送信息", "向子任务发送信息失败"],
      wait: ["正在等待子任务", "子任务等待已结束", "等待子任务失败"],
      close_agent: ["正在结束子任务", "子任务已结束", "子任务结束失败"],
    };
    const names = labels[operation] ?? ["正在协调子任务", "子任务协作已完成", "子任务协作失败"];
    const name = names[status === "running" ? 0 : status === "completed" ? 1 : 2];
    const args = Object.fromEntries(
      ["tool", "receiver_thread_ids", "prompt"]
        .filter((key) => item?.[key] !== undefined)
        .map((key) => [key, item?.[key]]),
    );
    return {
      id,
      block: toolBlock(name, id, status, Object.keys(args).length ? args : undefined, item?.agents_states),
    };
  }
  if (itemType === "web_search") {
    const name = status === "running" ? "正在进行网络搜索" : status === "failed" ? "网络搜索未完成" : "已完成网络搜索";
    const args = Object.fromEntries(
      ["query", "action"]
        .filter((key) => item?.[key] !== undefined)
        .map((key) => [key, item?.[key]]),
    );
    return { id, block: toolBlock(name, id, status, Object.keys(args).length ? args : undefined) };
  }
  if (itemType === "error" || eventType === "error" || eventType === "turn.failed") {
    const error = asRecord(event.error);
    const detail = asString(item?.message || event.message || error?.message) || "Codex 执行未完成。";
    return { id, block: toolBlock("Codex 执行遇到错误", id, "failed", undefined, detail) };
  }
  return null;
}

export function parseCodexSandboxProgress(
  partMetadata: unknown,
): CodexSandboxProgress | null {
  const metadata = asRecord(partMetadata);
  const progress = asRecord(metadata?.veadkStudioToolProgress);
  if (!progress || progress.kind !== "codex") return null;
  const toolName = asString(progress.toolName);
  const requestId = asString(progress.requestId);
  if (!toolName || !requestId) return null;
  const rawEvent = asRecord(progress.event ?? progress.activity);
  if (!rawEvent) return null;
  const event = asRecord(rawEvent.item) || asString(rawEvent.type)
    ? parseRawCodexEvent(rawEvent)
    : parseNormalizedEvent(rawEvent);
  if (!event) return null;
  const title = asString(progress.title || progress.label);
  const agentSessionId = asString(
    rawEvent.agentSessionId ?? rawEvent.agent_session_id,
  );
  const sandboxSessionId = asString(
    rawEvent.sandboxSessionId ?? rawEvent.sandbox_session_id,
  );
  const threadId = asString(rawEvent.threadId ?? rawEvent.thread_id);
  const eventStatus = normalizedStatus(rawEvent.status, asString(rawEvent.type));
  const eventKind = asString(rawEvent.kind);
  const terminalStatus = eventKind === "status" && eventStatus !== "running"
    ? eventStatus
    : undefined;
  return {
    toolName,
    requestId,
    ...(title ? { title } : {}),
    ...(agentSessionId ? { agentSessionId } : {}),
    ...(sandboxSessionId ? { sandboxSessionId } : {}),
    ...(threadId ? { threadId } : {}),
    ...(terminalStatus ? { terminalStatus } : {}),
    event,
  };
}

export function hydrateCodexSandboxActivity(
  current: CodexSandboxActivity | undefined,
  response: unknown,
): CodexSandboxActivity | undefined {
  const result = asRecord(response);
  const snapshot = asRecord(result?.codexActivity ?? result?.codex_activity);
  if (!snapshot) return current;

  const title = asString(snapshot.title) || current?.title || "Codex Sandbox";
  const agentSessionId = asString(
    snapshot.agentSessionId ?? snapshot.agent_session_id,
  ) || current?.agentSessionId;
  const sandboxSessionId = asString(
    snapshot.sandboxSessionId ?? snapshot.sandbox_session_id,
  ) || current?.sandboxSessionId;
  const threadId = asString(snapshot.threadId ?? snapshot.thread_id)
    || current?.threadId;
  let activity: CodexSandboxActivity = {
    title,
    ...(agentSessionId ? { agentSessionId } : {}),
    ...(sandboxSessionId ? { sandboxSessionId } : {}),
    ...(threadId ? { threadId } : {}),
    items: current?.items.slice() ?? [],
  };
  const events = Array.isArray(snapshot.events) ? snapshot.events : [];
  for (const value of events) {
    const rawEvent = asRecord(value);
    if (!rawEvent) continue;
    const event = asRecord(rawEvent.item) || asString(rawEvent.type)
      ? parseRawCodexEvent(rawEvent)
      : parseNormalizedEvent(rawEvent);
    if (!event) continue;
    // Persisted snapshots from older servers may contain the streamed final
    // answer. The function response renders that answer as ordinary message
    // text, while commentary remains useful execution context in the card.
    if (event.finalAnswer) continue;
    activity = applyCodexSandboxProgress(activity, {
      toolName: "delegate_to_codex_sandbox",
      requestId: "persisted-response",
      title,
      ...(agentSessionId ? { agentSessionId } : {}),
      ...(sandboxSessionId ? { sandboxSessionId } : {}),
      ...(threadId ? { threadId } : {}),
      event,
    });
  }
  return activity;
}

export function applyCodexSandboxProgress(
  current: CodexSandboxActivity | undefined,
  progress: CodexSandboxProgress,
): CodexSandboxActivity {
  const items = current?.items.slice() ?? [];
  const index = items.findIndex((item) => item.id === progress.event.id);
  if (index >= 0) {
    const previous = items[index].block;
    const next = progress.event.block;
    if (progress.event.appendText && previous.kind === "text" && next.kind === "text") {
      items[index] = {
        id: progress.event.id,
        block: { ...next, text: previous.text + next.text },
      };
    } else if (
      progress.event.appendText
      && previous.kind === "thinking"
      && next.kind === "thinking"
    ) {
      items[index] = {
        id: progress.event.id,
        block: { ...next, text: previous.text + next.text },
      };
    } else {
      items[index] = { id: progress.event.id, block: next };
    }
  } else {
    items.push({ id: progress.event.id, block: progress.event.block });
  }
  return {
    title: progress.title || current?.title || "Codex Sandbox",
    ...((progress.agentSessionId || current?.agentSessionId)
      ? { agentSessionId: progress.agentSessionId || current?.agentSessionId }
      : {}),
    ...((progress.sandboxSessionId || current?.sandboxSessionId)
      ? { sandboxSessionId: progress.sandboxSessionId || current?.sandboxSessionId }
      : {}),
    ...((progress.threadId || current?.threadId)
      ? { threadId: progress.threadId || current?.threadId }
      : {}),
    items: trimActivityItems(items),
  };
}
