import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(
      new URL("../src/ui/builtin-tools/codexSandboxProgress.ts", import.meta.url),
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
const {
  applyCodexSandboxProgress,
  parseCodexSandboxProgress,
} = await import(moduleUrl);
const blocksResult = await build({
  entryPoints: [fileURLToPath(new URL("../src/blocks.ts", import.meta.url))],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const blocksModuleUrl = `data:text/javascript;base64,${Buffer.from(
  blocksResult.outputFiles[0].contents,
).toString("base64")}`;
const { applyEvent, emptyAcc, eventsToTurns } = await import(blocksModuleUrl);

function metadata(event, extra = {}) {
  return {
    veadkStudioToolProgress: {
      kind: "codex",
      toolName: "execute_in_sandbox",
      requestId: "call-1",
      title: "ANR Engineer",
      event,
      ...extra,
    },
  };
}

test("parses Codex Studio tool progress and normalizes terminal statuses", () => {
  assert.deepEqual(
    parseCodexSandboxProgress(metadata({
      id: "command-1",
      kind: "command_execution",
      status: "error",
      command: "pytest -q",
      cwd: "/workspace",
      aggregated_output: "1 failed",
      exit_code: 1,
    })),
    {
      toolName: "execute_in_sandbox",
      requestId: "call-1",
      title: "ANR Engineer",
      event: {
        id: "command-1",
        block: {
          kind: "tool",
          name: "运行命令",
          callId: "command-1",
          args: { command: "pytest -q", cwd: "/workspace" },
          response: { output: "1 failed", exitCode: 1 },
          done: true,
          status: "failed",
          defaultOpen: true,
        },
      },
    },
  );
  assert.equal(parseCodexSandboxProgress({}), null);
  assert.equal(parseCodexSandboxProgress(metadata({ kind: "thinking" })), null);
  assert.equal(
    parseCodexSandboxProgress(metadata({ id: "thinking-1", kind: "thinking" }, {
      toolName: "",
    })),
    null,
  );
});

test("upserts reasoning and keeps ordered detailed Codex output", () => {
  const started = parseCodexSandboxProgress(metadata({
    id: "reasoning-1",
    kind: "thinking",
    status: "running",
    text: "检查项目",
  }));
  assert.ok(started);
  let activity = applyCodexSandboxProgress(undefined, started);

  const completed = parseCodexSandboxProgress(metadata({
    id: "reasoning-1",
    kind: "thinking",
    status: "done",
    text: "检查项目结构",
  }));
  assert.ok(completed);
  activity = applyCodexSandboxProgress(activity, completed);

  const fileChange = parseCodexSandboxProgress(metadata({
    id: "files-1",
    kind: "file_change",
    status: "completed",
    changes: [{ path: "agent.py", kind: "update" }],
  }));
  assert.ok(fileChange);
  activity = applyCodexSandboxProgress(activity, fileChange);

  const approval = parseCodexSandboxProgress(metadata({
    id: "approval-1",
    kind: "approval",
    status: "running",
    name: "允许执行命令？",
    approval: { command: "pytest -q" },
  }));
  assert.ok(approval);
  activity = applyCodexSandboxProgress(activity, approval);

  const finalMessage = parseCodexSandboxProgress(metadata({
    id: "answer-1",
    kind: "assistant_final",
    status: "done",
    text: "实现完成。",
  }));
  assert.ok(finalMessage);
  activity = applyCodexSandboxProgress(activity, finalMessage);

  assert.deepEqual(activity, {
    title: "ANR Engineer",
    items: [
      {
        id: "reasoning-1",
        block: { kind: "thinking", text: "检查项目结构", done: true },
      },
      {
        id: "files-1",
        block: {
          kind: "tool",
          name: "修改文件",
          callId: "files-1",
          args: { changes: [{ path: "agent.py", kind: "update" }] },
          response: undefined,
          done: true,
          status: "completed",
        },
      },
      {
        id: "approval-1",
        block: {
          kind: "tool",
          name: "允许执行命令？",
          callId: "approval-1",
          args: { command: "pytest -q" },
          response: undefined,
          done: false,
          status: "running",
        },
      },
      {
        id: "answer-1",
        block: { kind: "text", text: "实现完成。" },
      },
    ],
  });
});

test("appends delta text and preserves the last explicit sandbox title", () => {
  const first = parseCodexSandboxProgress(metadata({
    id: "message-1",
    kind: "message",
    status: "running",
    delta: "Hello ",
  }));
  assert.ok(first);
  let activity = applyCodexSandboxProgress(undefined, first);

  const second = parseCodexSandboxProgress(metadata({
    id: "message-1",
    kind: "message",
    status: "running",
    delta: "world",
  }, { title: undefined }));
  assert.ok(second);
  activity = applyCodexSandboxProgress(activity, second);

  assert.equal(activity.title, "ANR Engineer");
  assert.deepEqual(activity.items, [{
    id: "message-1",
    block: { kind: "text", text: "Hello world" },
  }]);
});

test("preserves Agent, Sandbox, and Codex Thread identities across progress", () => {
  const started = parseCodexSandboxProgress(metadata({
    id: "turn-1",
    kind: "status",
    status: "running",
    text: "Codex Sandbox 已接收任务",
    agentSessionId: "agent-session-1",
    sandboxSessionId: "sandbox-session-1",
    threadId: "thread-1",
  }));
  assert.ok(started);
  assert.equal(started.agentSessionId, "agent-session-1");
  assert.equal(started.sandboxSessionId, "sandbox-session-1");
  assert.equal(started.threadId, "thread-1");

  let activity = applyCodexSandboxProgress(undefined, started);
  const command = parseCodexSandboxProgress(metadata({
    id: "command-1",
    kind: "command_execution",
    status: "completed",
    command: "anr review",
  }));
  assert.ok(command);
  activity = applyCodexSandboxProgress(activity, command);

  assert.equal(activity.agentSessionId, "agent-session-1");
  assert.equal(activity.sandboxSessionId, "sandbox-session-1");
  assert.equal(activity.threadId, "thread-1");
});

test("uses terminal Codex status progress for the outer tool state", () => {
  let accumulator = applyEvent(emptyAcc(), {
    content: {
      parts: [{
        functionCall: {
          id: "adk-function-call-terminal",
          name: "delegate_to_codex_sandbox",
          args: { environment_id: "e".repeat(32), task: "Review this project" },
        },
      }],
    },
  });

  accumulator = applyEvent(accumulator, {
    partial: true,
    content: {
      parts: [{
        partMetadata: metadata({
          id: "turn-terminal",
          kind: "status",
          status: "failed",
          text: "Codex Sandbox 执行失败",
        }, {
          toolName: "delegate_to_codex_sandbox",
          requestId: "adk-function-call-terminal",
        }),
      }],
    },
  });

  assert.equal(accumulator.blocks[0].done, true);
  assert.equal(accumulator.blocks[0].status, "failed");
});

test("hydrates persisted Codex activity when replaying session history", () => {
  const turns = eventsToTurns([
    {
      id: "event-call",
      author: "review_agent",
      content: {
        parts: [{
          functionCall: {
            id: "adk-function-call-history",
            name: "delegate_to_codex_sandbox",
            args: { environment_id: "e".repeat(32), task: "Review this project" },
          },
        }],
      },
    },
    {
      id: "event-response",
      author: "review_agent",
      content: {
        parts: [{
          functionResponse: {
            id: "adk-function-call-history",
            name: "delegate_to_codex_sandbox",
            response: {
              ok: true,
              message: "完整 Codex 最终答案",
              codex_activity: {
                title: "ANR Reviewer",
                agent_session_id: "agent-session-history",
                sandbox_session_id: "sandbox-session-history",
                thread_id: "thread-history",
                events: [{
                  id: "command-history",
                  kind: "command_execution",
                  status: "completed",
                  command: "anr review --dry-run",
                  aggregatedOutput: "Review plan ready",
                  exitCode: 0,
                }],
              },
            },
          },
        }],
      },
    },
  ]);

  assert.equal(turns.length, 1);
  const tool = turns[0].blocks[0];
  assert.equal(tool.kind, "tool");
  assert.equal(tool.done, true);
  assert.equal(tool.status, "completed");
  assert.equal(tool.codexActivity.title, "ANR Reviewer");
  assert.equal(tool.codexActivity.agentSessionId, "agent-session-history");
  assert.equal(tool.codexActivity.sandboxSessionId, "sandbox-session-history");
  assert.equal(tool.codexActivity.threadId, "thread-history");
  assert.equal(tool.codexActivity.items[0].id, "command-history");
  assert.deepEqual(turns[0].blocks[1], {
    kind: "text",
    text: "完整 Codex 最终答案",
  });
});

test("keeps persisted final text out of the Codex activity card", () => {
  const turns = eventsToTurns([
    {
      content: {
        parts: [{
          functionCall: {
            id: "adk-function-call-no-duplicate-card",
            name: "delegate_to_codex_sandbox",
            args: { environment_id: "e".repeat(32), task: "Write the PRD" },
          },
        }],
      },
    },
    {
      content: {
        parts: [{
          functionResponse: {
            id: "adk-function-call-no-duplicate-card",
            name: "delegate_to_codex_sandbox",
            response: {
              ok: true,
              message: "完整 PRD",
              codex_activity: {
                events: [
                  { id: "message-1", kind: "text", status: "done", text: "完整 PRD" },
                  { id: "commentary-1", kind: "commentary", status: "done", text: "正在整理需求" },
                  { id: "command-1", kind: "command_execution", status: "completed", command: "anr design" },
                ],
              },
            },
          },
        }],
      },
    },
  ]);

  const tool = turns[0].blocks[0];
  assert.equal(tool.kind, "tool");
  assert.deepEqual(tool.codexActivity.items.map((item) => item.id), [
    "commentary-1",
    "command-1",
  ]);
  assert.deepEqual(turns[0].blocks[1], { kind: "text", text: "完整 PRD" });
});

test("does not replay a persisted text delta over live Codex activity", () => {
  let accumulator = applyEvent(emptyAcc(), {
    content: {
      parts: [{
        functionCall: {
          id: "adk-function-call-live-snapshot",
          name: "delegate_to_codex_sandbox",
          args: { environment_id: "e".repeat(32), task: "Write the PRD" },
        },
      }],
    },
  });
  accumulator = applyEvent(accumulator, {
    partial: true,
    content: {
      parts: [{
        partMetadata: metadata({
          id: "assistant-live-snapshot",
          kind: "text",
          status: "done",
          delta: "内部最终答案",
        }, {
          toolName: "delegate_to_codex_sandbox",
          requestId: "adk-function-call-live-snapshot",
        }),
      }],
    },
  });
  accumulator = applyEvent(accumulator, {
    content: {
      parts: [{
        functionResponse: {
          id: "adk-function-call-live-snapshot",
          name: "delegate_to_codex_sandbox",
          response: {
            ok: true,
            message: "内部最终答案",
            codex_activity: {
              events: [{
                id: "assistant-live-snapshot",
                kind: "text",
                status: "done",
                delta: "内部最终答案",
              }],
            },
          },
        },
      }],
    },
  });

  assert.equal(accumulator.blocks[0].codexActivity.items.length, 0);
  assert.deepEqual(accumulator.blocks[1], {
    kind: "text",
    text: "内部最终答案",
  });
});

test("does not append the same successful Codex response twice", () => {
  const response = { ok: true, message: "唯一最终答案" };
  let accumulator = applyEvent(emptyAcc(), {
    content: { parts: [{ functionCall: {
      id: "adk-function-call-idempotent",
      name: "delegate_to_codex_sandbox",
      args: { environment_id: "e".repeat(32), task: "Do it" },
    } }] },
  });
  const responseEvent = {
    content: { parts: [{ functionResponse: {
      id: "adk-function-call-idempotent",
      name: "delegate_to_codex_sandbox",
      response,
    } }] },
  };

  accumulator = applyEvent(accumulator, responseEvent);
  accumulator = applyEvent(accumulator, responseEvent);

  assert.equal(accumulator.blocks.filter((block) => block.kind === "text").length, 1);
  assert.equal(accumulator.blocks.at(-1).text, "唯一最终答案");
});

test("does not render failed or busy Codex messages as direct answers", () => {
  for (const [suffix, response] of [
    ["failed", { ok: false, status: "error", message: "Codex 执行失败" }],
    ["busy", { ok: false, status: "busy", message: "Codex 正在执行其他任务" }],
  ]) {
    let accumulator = applyEvent(emptyAcc(), {
      content: {
        parts: [{
          functionCall: {
            id: `adk-function-call-${suffix}`,
            name: "delegate_to_codex_sandbox",
            args: { environment_id: "e".repeat(32), task: "Review this project" },
          },
        }],
      },
    });
    accumulator = applyEvent(accumulator, {
      content: {
        parts: [{
          functionResponse: {
            id: `adk-function-call-${suffix}`,
            name: "delegate_to_codex_sandbox",
            response,
          },
        }],
      },
    });

    assert.equal(accumulator.blocks.length, 1);
    assert.equal(accumulator.blocks[0].kind, "tool");
    assert.equal(accumulator.blocks[0].done, true);
  }
});

test("marks a persisted failed Codex response as failed", () => {
  let accumulator = applyEvent(emptyAcc(), {
    content: {
      parts: [{
        functionCall: {
          id: "adk-function-call-failed",
          name: "delegate_to_codex_sandbox",
          args: { environment_id: "e".repeat(32), task: "Review this project" },
        },
      }],
    },
  });
  accumulator = applyEvent(accumulator, {
    content: {
      parts: [{
        functionResponse: {
          id: "adk-function-call-failed",
          name: "delegate_to_codex_sandbox",
          response: {
            status: "error",
            error: "Codex Sandbox timed out",
            codex_activity: {
              title: "ANR Reviewer",
              events: [{
                id: "turn-failed",
                kind: "status",
                status: "failed",
                text: "Codex Sandbox 执行超时",
              }],
            },
          },
        },
      }],
    },
  });

  assert.equal(accumulator.blocks[0].done, true);
  assert.equal(accumulator.blocks[0].status, "failed");
  assert.equal(accumulator.blocks[0].codexActivity.items[0].id, "turn-failed");
});

test("bounds retained Codex output by item count and aggregate characters", () => {
  let activity;
  for (let index = 0; index < 220; index += 1) {
    const progress = parseCodexSandboxProgress(metadata({
      id: `message-${index}`,
      kind: "message",
      status: "running",
      text: `${index}:`.padEnd(2_100, "x"),
    }));
    assert.ok(progress);
    activity = applyCodexSandboxProgress(activity, progress);
  }

  assert.ok(activity.items.length < 200);
  assert.ok(JSON.stringify(activity.items).length <= 280_000);
  assert.equal(activity.items.at(-1).id, "message-219");
});

test("parses native Codex item events using the repository activity convention", () => {
  const command = parseCodexSandboxProgress(metadata({
    type: "item.completed",
    item: {
      id: "command-2",
      type: "command_execution",
      command: "npm test",
      aggregated_output: "16 passed",
      exit_code: 0,
    },
  }));
  assert.ok(command);
  assert.deepEqual(command.event, {
    id: "command-2",
    block: {
      kind: "tool",
      name: "命令执行完成",
      callId: "command-2",
      args: { command: "npm test" },
      response: { output: "16 passed", exitCode: 0 },
      done: true,
      status: "completed",
    },
  });

  const plan = parseCodexSandboxProgress(metadata({
    type: "item.updated",
    item: {
      id: "plan-1",
      type: "todo_list",
      items: [
        { text: "检查代码", status: "completed" },
        { text: "运行测试", status: "in_progress" },
      ],
    },
  }));
  assert.ok(plan);
  assert.equal(plan.event.block.kind, "plan");
  assert.equal(plan.event.block.summary, "已完成 1/2 项");
});

test("wires Codex progress into the active outer tool and renders the nested card", () => {
  const blocksSource = readFileSync(new URL("../src/blocks.ts", import.meta.url), "utf8");
  const rendererSource = readFileSync(new URL("../src/ui/Blocks.tsx", import.meta.url), "utf8");
  const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

  assert.match(blocksSource, /parseCodexSandboxProgress/);
  assert.match(blocksSource, /block\.codexActivity = applyCodexSandboxProgress/);
  assert.match(rendererSource, /className="codex-sandbox-run"/);
  assert.match(rendererSource, /<span>Codex Sandbox<\/span>/);
  assert.match(rendererSource, /Agent Session/);
  assert.match(rendererSource, /Sandbox Session/);
  assert.match(rendererSource, /Codex Thread/);
  assert.match(
    rendererSource,
    /codexActivity\.items\.map\(\(item\)\s*=>\s*item\.block\)/,
  );
  assert.match(
    rendererSource,
    /:\s*!codexActivity\s*\?\s*\(\s*<div className="tool-detail">/,
  );
  assert.match(stylesSource, /\.codex-sandbox-run\s*\{/);
  assert.match(stylesSource, /\.codex-sandbox-run__label\s*\{[^}]*position:\s*absolute/s);
  assert.match(stylesSource, /\.codex-sandbox-run__identity\s*\{/);
  assert.match(stylesSource, /@media \(max-width: 700px\)[\s\S]*?\.codex-sandbox-run/);
});

test("applies progress to the matching ADK function call id", () => {
  let accumulator = applyEvent(emptyAcc(), {
    content: {
      parts: [{
        functionCall: {
          id: "adk-function-call-1",
          name: "delegate_to_codex_sandbox",
          args: { environment_id: "e".repeat(32), task: "Review this project" },
        },
      }],
    },
  });

  accumulator = applyEvent(accumulator, {
    partial: true,
    content: {
      parts: [{
        partMetadata: metadata({
          id: "command-1",
          kind: "tool",
          status: "running",
          name: "运行命令",
          arguments: { command: "anr review" },
        }, {
          toolName: "delegate_to_codex_sandbox",
          requestId: "adk-function-call-1",
        }),
      }],
    },
  });

  assert.equal(accumulator.blocks.length, 1);
  assert.equal(accumulator.blocks[0].callId, "adk-function-call-1");
  assert.equal(accumulator.blocks[0].codexActivity.items[0].id, "command-1");

  const legacyFallback = applyEvent(accumulator, {
    partial: true,
    content: {
      parts: [{
        partMetadata: metadata({
          id: "command-2",
          kind: "tool",
          status: "running",
          name: "运行命令",
        }, {
          toolName: "delegate_to_codex_sandbox",
          requestId: "unrelated-call",
        }),
      }],
    },
  });
  assert.equal(legacyFallback.blocks[0].codexActivity.items.length, 2);
});

test("binds legacy mismatched progress only when one Codex call is active", () => {
  let accumulator = applyEvent(emptyAcc(), {
    content: {
      parts: [{
        functionCall: {
          id: "outer-call-legacy",
          name: "delegate_to_codex_sandbox",
          args: { environment_id: "e".repeat(32), task: "Review this project" },
        },
      }],
    },
  });
  accumulator = applyEvent(accumulator, {
    partial: true,
    content: {
      parts: [{
        partMetadata: metadata({
          id: "legacy-progress",
          kind: "status",
          status: "running",
          text: "Codex Sandbox 已接收任务",
        }, {
          toolName: "delegate_to_codex_sandbox",
          requestId: "transport-request-id",
        }),
      }],
    },
  });

  assert.equal(accumulator.pendingCodexProgress.length, 0);
  assert.equal(accumulator.blocks[0].codexActivity.items[0].id, "legacy-progress");
});

test("prefers an explicit outer call id when multiple Codex calls exist", () => {
  let accumulator = applyEvent(emptyAcc(), {
    content: {
      parts: [
        {
          functionCall: {
            id: "outer-call-1",
            name: "delegate_to_codex_sandbox",
            args: { environment_id: "a".repeat(32), task: "Review A" },
          },
        },
        {
          functionCall: {
            id: "outer-call-2",
            name: "delegate_to_codex_sandbox",
            args: { environment_id: "b".repeat(32), task: "Review B" },
          },
        },
      ],
    },
  });
  accumulator = applyEvent(accumulator, {
    partial: true,
    content: {
      parts: [{
        partMetadata: metadata({
          id: "explicit-progress",
          kind: "status",
          status: "running",
          text: "Codex Sandbox 已接收任务",
        }, {
          toolName: "delegate_to_codex_sandbox",
          requestId: "outer-call-2",
        }),
      }],
    },
  });

  assert.equal(accumulator.blocks[0].codexActivity, undefined);
  assert.equal(accumulator.blocks[1].codexActivity.items[0].id, "explicit-progress");

  const unmatched = applyEvent(accumulator, {
    partial: true,
    content: {
      parts: [{
        partMetadata: metadata({
          id: "ambiguous-progress",
          kind: "status",
          status: "running",
          text: "Codex Sandbox 已接收任务",
        }, {
          toolName: "delegate_to_codex_sandbox",
          requestId: "unknown-transport-id",
        }),
      }],
    },
  });
  assert.equal(unmatched.pendingCodexProgress.length, 1);
});

test("replays Codex progress that arrives before its ADK function call", () => {
  let accumulator = applyEvent(emptyAcc(), {
    partial: true,
    content: {
      parts: [{
        partMetadata: metadata({
          id: "turn-call-race",
          kind: "status",
          status: "running",
          text: "Codex Sandbox 已接收任务",
        }, {
          toolName: "delegate_to_codex_sandbox",
          requestId: "adk-function-call-race",
        }),
      }],
    },
  });

  assert.equal(accumulator.blocks.length, 0);
  assert.equal(accumulator.pendingCodexProgress.length, 1);

  accumulator = applyEvent(accumulator, {
    content: {
      parts: [{
        functionCall: {
          id: "adk-function-call-race",
          name: "delegate_to_codex_sandbox",
          args: { environment_id: "e".repeat(32), task: "Review this project" },
        },
      }],
    },
  });

  assert.equal(accumulator.pendingCodexProgress.length, 0);
  assert.equal(accumulator.blocks.length, 1);
  assert.equal(accumulator.blocks[0].callId, "adk-function-call-race");
  assert.equal(accumulator.blocks[0].status, "running");
  assert.equal(accumulator.blocks[0].codexActivity.items[0].id, "turn-call-race");
});

test("bounds unmatched Codex progress while waiting for a function call", () => {
  let accumulator = emptyAcc();
  for (let index = 0; index < 80; index += 1) {
    accumulator = applyEvent(accumulator, {
      partial: true,
      content: {
        parts: [{
          partMetadata: metadata({
            id: `queued-${index}`,
            kind: "status",
            status: "running",
            text: `queued ${index}`,
          }, {
            toolName: "delegate_to_codex_sandbox",
            requestId: `unmatched-${index}`,
          }),
        }],
      },
    });
  }

  assert.equal(accumulator.pendingCodexProgress.length, 64);
  assert.equal(accumulator.pendingCodexProgress[0].requestId, "unmatched-16");
  assert.equal(accumulator.pendingCodexProgress.at(-1).requestId, "unmatched-79");
});
