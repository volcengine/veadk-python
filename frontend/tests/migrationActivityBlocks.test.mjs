import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(
      new URL("../src/migrations/migrationActivityBlocks.ts", import.meta.url),
    ),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
const { migrationActivityBlocks } = await import(moduleUrl);

/** The shared presentation module, compiled the same way the page consumes it. */
async function loadDevelopmentPresentation() {
  const presentation = await build({
    entryPoints: [
      fileURLToPath(
        new URL("../src/create/developmentPresentation.ts", import.meta.url),
      ),
    ],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  return import(
    `data:text/javascript;base64,${Buffer.from(
      presentation.outputFiles[0].contents,
    ).toString("base64")}`
  );
}

test("maps ordered Codex activity into the shared block contract", () => {
  const blocks = migrationActivityBlocks([
    {
      id: "reasoning",
      kind: "reasoning",
      status: "running",
      title: "Codex 思考",
      detail: "检查项目结构",
      itemType: "reasoning",
      durationMs: 1200,
    },
    {
      id: "message",
      kind: "message",
      status: "completed",
      title: "Codex 更新",
      detail: "已识别入口。",
      itemType: "agentMessage",
      phase: "commentary",
    },
    {
      id: "plan",
      kind: "plan",
      status: "running",
      title: "项目迁移计划",
      detail: "已完成 1/2 项",
      plan: [
        { text: "识别入口", status: "completed" },
        { text: "迁移工具", status: "in_progress" },
      ],
    },
    {
      id: "command",
      kind: "command",
      status: "failed",
      title: "命令执行未完成",
      tool: {
        name: "命令执行未完成",
        input: { command: "python migrate.py" },
        output: "trace",
        error: "exit failed",
        exitCode: 1,
      },
      itemType: "commandExecution",
      durationMs: 800,
    },
    {
      id: "status",
      kind: "status",
      status: "failed",
      title: "Codex 事件流异常",
      detail: "connection closed",
    },
    {
      id: "complete",
      kind: "status",
      status: "completed",
      title: "旧版固定完成消息",
    },
  ]);

  assert.deepEqual(blocks, [
    {
      kind: "thinking",
      id: "reasoning",
      itemType: "reasoning",
      durationMs: 1200,
      text: "检查项目结构",
      done: false,
    },
    {
      kind: "text",
      id: "message",
      itemType: "agentMessage",
      phase: "commentary",
      text: "已识别入口。",
    },
    {
      kind: "plan",
      id: "plan",
      title: "项目迁移计划",
      summary: "已完成 1/2 项",
      items: [
        { text: "识别入口", status: "completed" },
        { text: "迁移工具", status: "in_progress" },
      ],
      done: false,
    },
    {
      kind: "tool",
      id: "command",
      itemType: "commandExecution",
      durationMs: 800,
      name: "命令执行未完成",
      args: { command: "python migrate.py" },
      response: {
        status: "failed",
        exitCode: 1,
        output: "trace",
        error: "exit failed",
      },
      done: true,
      status: "failed",
      defaultOpen: true,
    },
    {
      kind: "tool",
      id: "status",
      name: "Codex 事件流异常",
      response: "connection closed",
      done: true,
      status: "failed",
      defaultOpen: true,
    },
  ]);
});

test("keeps legacy activity useful without inventing missing details", () => {
  const blocks = migrationActivityBlocks([
    {
      id: "empty-reasoning",
      kind: "reasoning",
      status: "completed",
      title: "Codex 思考",
    },
    {
      id: "empty-message",
      kind: "message",
      status: "completed",
      title: "Codex 更新",
    },
    {
      id: "legacy-plan",
      kind: "plan",
      status: "completed",
      title: "项目分析计划",
      detail: "已完成 2/2 项",
    },
    {
      id: "legacy-command",
      kind: "command",
      status: "completed",
      title: "已检查项目结构",
    },
    {
      id: "output-command",
      kind: "command",
      status: "completed",
      title: "已验证迁移结果",
      tool: { name: "已验证迁移结果", output: "passed" },
    },
    {
      id: "running-status",
      kind: "status",
      status: "running",
      title: "正在处理",
    },
  ]);

  assert.deepEqual(blocks, [
    {
      kind: "plan",
      id: "legacy-plan",
      title: "项目分析计划",
      summary: "已完成 2/2 项",
      items: [],
      done: true,
    },
    {
      kind: "tool",
      id: "legacy-command",
      name: "已检查项目结构",
      args: undefined,
      response: undefined,
      done: true,
      status: "completed",
    },
    {
      kind: "tool",
      id: "output-command",
      name: "已验证迁移结果",
      args: undefined,
      response: { status: "completed", output: "passed" },
      done: true,
      status: "completed",
    },
    {
      kind: "tool",
      id: "running-status",
      name: "正在处理",
      response: undefined,
      done: false,
      status: "running",
    },
  ]);
});

test("renders a migration command as the intelligent build's native row", async () => {
  const { developmentToolLabel, isDevelopmentProcess } = await loadDevelopmentPresentation();

  const [command] = migrationActivityBlocks([
    {
      id: "delivery:1:call_1",
      kind: "command",
      status: "completed",
      title: "已拉取迁移产物并核对字节",
      itemType: "dynamicToolCall",
      durationMs: 2400,
      tool: { name: "已拉取迁移产物并核对字节", input: { path: "migration-result.zip" } },
    },
  ]);

  // Without itemType the shared renderer falls back to a generic row: another icon and
  // an output truncated at 2000 characters. The native fields are what make a
  // migration turn render like the intelligent build's own.
  assert.equal(command.itemType, "dynamicToolCall");
  assert.equal(command.durationMs, 2400);
  assert.equal(isDevelopmentProcess(command), true);
  assert.equal(developmentToolLabel(command), "已拉取迁移产物并核对字节");
});

test("labels a migration command with the same name the app-server gave it", async () => {
  const { developmentToolLabel } = await loadDevelopmentPresentation();

  // The app-server names its own tool rows and the intelligent build labels them from
  // that name; the migration row carries the same name, so it reads the same instead of
  // falling back to the migration's own status copy.
  const native = migrationActivityBlocks([
    {
      id: "migration:1:call_1",
      kind: "command",
      status: "completed",
      itemType: "commandExecution",
      title: "命令执行完成",
      tool: { name: "运行命令", input: { command: "ak migrate any source" } },
    },
  ])[0];
  assert.equal(developmentToolLabel(native), "运行命令");

  const scripted = migrationActivityBlocks([
    {
      id: "migration:1:call_2",
      kind: "command",
      status: "completed",
      itemType: "commandExecution",
      title: "命令执行完成",
      tool: { name: "命令执行完成", input: { command: "ak migrate any source" } },
    },
  ])[0];
  assert.equal(developmentToolLabel(scripted), "命令执行完成");
});

test("hands a settled turn's own cost to the shared turn summary", async () => {
  const value = {
    turnId: "turn-1",
    status: "completed",
    model: "codex-mini",
    durationMs: 8_000,
    startedAt: 1_000,
    completedAt: 9_000,
    toolCalls: 3,
    toolDurationMs: 1_200,
    toolDurationComplete: true,
    usage: { totalTokens: 900, inputTokens: 800, outputTokens: 100 },
  };
  const blocks = migrationActivityBlocks([
    {
      id: "command",
      kind: "command",
      status: "completed",
      title: "命令执行完成",
      tool: { name: "运行命令", input: { command: "ls" } },
      itemType: "commandExecution",
      durationMs: 1_200,
    },
    {
      id: "analysis:1:turn-summary",
      kind: "summary",
      status: "completed",
      title: "本轮执行完成",
      turn: value,
    },
  ]);

  // 迁移页和智能构建用同一个 turn-summary 块与同一个组件：这里只交出读数，
  // 不重算、不改写，否则两边的本轮耗时/token 会对不上。
  assert.deepEqual(blocks[1], {
    kind: "turn-summary",
    id: "analysis:1:turn-summary",
    value,
  });

  // 汇总不是「过程」块：它不会被折进可折叠的工具组里，而是单独一行亮出来。
  const { developmentProcessGroups } = await loadDevelopmentPresentation();
  const groups = developmentProcessGroups(blocks);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].process, true);
  assert.equal(groups[1].process, false);
  assert.equal(groups[1].blocks.length, 1);
});

test("ignores a summary item that carries no numbers", () => {
  const blocks = migrationActivityBlocks([
    {
      id: "analysis:1:turn-summary",
      kind: "summary",
      status: "completed",
      title: "本轮执行完成",
    },
  ]);

  assert.deepEqual(blocks, []);
});
