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

test("maps ordered Codex activity into the shared block contract", () => {
  const blocks = migrationActivityBlocks([
    {
      id: "reasoning",
      kind: "reasoning",
      status: "running",
      title: "Codex 思考",
      detail: "检查项目结构",
    },
    {
      id: "message",
      kind: "message",
      status: "completed",
      title: "Codex 更新",
      detail: "已识别入口。",
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
      text: "检查项目结构",
      done: false,
    },
    { kind: "text", text: "已识别入口。" },
    {
      kind: "plan",
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
      name: "命令执行未完成",
      args: { command: "python migrate.py" },
      response: { output: "trace", error: "exit failed", exitCode: 1 },
      done: true,
      status: "failed",
      defaultOpen: true,
    },
    {
      kind: "tool",
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
      title: "项目分析计划",
      summary: "已完成 2/2 项",
      items: [],
      done: true,
    },
    {
      kind: "tool",
      name: "已检查项目结构",
      args: undefined,
      response: undefined,
      done: true,
      status: "completed",
    },
    {
      kind: "tool",
      name: "已验证迁移结果",
      args: undefined,
      response: "passed",
      done: true,
      status: "completed",
    },
    {
      kind: "tool",
      name: "正在处理",
      response: undefined,
      done: false,
      status: "running",
    },
  ]);
});
