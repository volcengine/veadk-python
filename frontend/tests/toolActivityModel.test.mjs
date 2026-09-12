import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/ui/tool-activity/model.ts", import.meta.url)),
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
  groupToolActivities,
  maskToolRawValue,
  presentToolActivity,
  previewToolOutput,
} = await import(moduleUrl);
const blocksResult = await build({
  entryPoints: [fileURLToPath(new URL("../src/blocks.ts", import.meta.url))],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const blocksUrl = `data:text/javascript;base64,${Buffer.from(
  blocksResult.outputFiles[0].contents,
).toString("base64")}`;
const {
  applyEvent,
  createAssistantEventProjector,
  emptyAcc,
  eventsToTurns,
  flattenCodexActivityBlocks,
} = await import(blocksUrl);

test("uses repository-owned SVG icons for tool activity", () => {
  const componentSource = readFileSync(
    new URL("../src/ui/tool-activity/ToolActivityCard.tsx", import.meta.url),
    "utf8",
  );
  const iconSource = readFileSync(
    new URL("../src/ui/tool-activity/ToolActivityIcons.tsx", import.meta.url),
    "utf8",
  );

  assert.equal(componentSource.includes('from "lucide-react"'), false);
  assert.equal(componentSource.includes('from "./ToolActivityIcons"'), true);
  assert.match(iconSource, /strokeWidth: "1.75"/);
});

test("presents command execution without exposing JSON as primary content", () => {
  const presentation = presentToolActivity({
    name: "Run command",
    callId: "call-1",
    args: { command: "pytest -q", cwd: "/workspace" },
    response: { output: "81 passed\n", exitCode: 0, durationMs: 21400 },
    done: true,
    status: "completed",
  });

  assert.equal(presentation.category, "command");
  assert.equal(presentation.titleKey, "command.completed");
  assert.equal(presentation.summary, "pytest -q");
  assert.equal(presentation.command, "pytest -q");
  assert.equal(presentation.cwd, "/workspace");
  assert.equal(presentation.output?.text, "81 passed");
  assert.equal(presentation.exitCode, 0);
  assert.equal(presentation.durationMs, 21400);
  assert.equal(presentation.defaultOpen, false);
});

test("keeps failures open and masks sensitive raw values", () => {
  const presentation = presentToolActivity({
    name: "exec_command",
    callId: "call-2",
    args: { command: "npm run build", apiKey: "secret-value" },
    response: { status: "failed", output: "missing vite", exitCode: 1 },
    done: true,
    status: "failed",
  });

  assert.equal(presentation.titleKey, "command.failed");
  assert.equal(presentation.defaultOpen, true);
  assert.equal(presentation.rawArgs.apiKey, "••••••••");
  assert.equal(presentation.rawResponse.output, "missing vite");
});

test("treats explicit unsuccessful responses as failures", () => {
  const presentation = presentToolActivity({
    name: "custom_tool",
    response: { ok: false, message: "request failed" },
    done: true,
  });

  assert.equal(presentation.status, "failed");
  assert.equal(presentation.defaultOpen, true);
});

test("bounds raw tool data and redacts credentials embedded in strings", () => {
  const circular = {
    command:
      "curl -H 'Cookie: session=plain-cookie' 'https://example.test?api_key=query-secret'",
    note: "access_token=body-secret AKLTabcdefghijklmnop",
    long: "x".repeat(5_000),
    items: Array.from({ length: 80 }, (_, index) => `item-${index}`),
    values: Object.fromEntries(
      Array.from({ length: 80 }, (_, index) => [`field-${index}`, index]),
    ),
  };
  circular.self = circular;

  const masked = maskToolRawValue(circular);
  const serialized = JSON.stringify(masked);

  assert.doesNotMatch(
    serialized,
    /plain-cookie|query-secret|body-secret|AKLTabcdefghijklmnop/,
  );
  assert.ok(masked.long.length < 5_000);
  assert.ok(masked.items.length < 80);
  assert.ok(Object.keys(masked.values).length < 80);
  assert.equal(masked.self, "[circular]");
});

test("redacts environment maps and signed URL credentials", () => {
  const masked = maskToolRawValue({
    env: { HOME: "/root", DATABASE_URL: "postgres://private" },
    environment: { INTERNAL_HOST: "private.local" },
    url: "https://example.test/file?X-Amz-Credential=credential-value&X-Amz-Signature=signature-value",
  });
  const serialized = JSON.stringify(masked);

  assert.doesNotMatch(
    serialized,
    /\/root|postgres:\/\/private|private\.local|credential-value|signature-value/,
  );
  assert.equal(masked.env, "••••••••");
  assert.equal(masked.environment, "••••••••");
});

test("uses one aggregate budget for deeply nested raw tool data", () => {
  const branch = (depth) =>
    depth === 0 ? "leaf" : Array.from({ length: 20 }, () => branch(depth - 1));

  const serialized = JSON.stringify(maskToolRawValue(branch(4)));

  assert.ok(serialized.length < 30_000);
  assert.match(serialized, /\[truncated\]/);
});

test("keeps the head and tail of long output with an omission count", () => {
  const output = previewToolOutput(
    Array.from({ length: 14 }, (_, index) => `line-${index + 1}`).join("\n"),
  );

  assert.deepEqual(output.head, [
    "line-1",
    "line-2",
    "line-3",
    "line-4",
    "line-5",
  ]);
  assert.deepEqual(output.tail, [
    "line-10",
    "line-11",
    "line-12",
    "line-13",
    "line-14",
  ]);
  assert.equal(output.omittedLines, 4);
});

test("bounds a single long output line", () => {
  const output = previewToolOutput("a".repeat(50_000));

  assert.ok(output.text.length < 25_000);
  assert.ok(output.omittedCharacters > 0);
  assert.equal(output.head.length, 1);
  assert.equal(output.tail.length, 1);
});

test("masks visible command details and removes terminal control sequences", () => {
  const presentation = presentToolActivity({
    name: "exec_command",
    args: {
      command: "curl 'https://example.test?api_key=visible-secret'",
      cwd: "/tmp/token=path-secret",
    },
    response: {
      output: "\u001b[31mfailed\u001b[0m\u0000",
      status: "failed",
      paths: ["https://example.test?access_token=file-secret"],
    },
    done: true,
  });

  assert.doesNotMatch(
    JSON.stringify(presentation),
    /visible-secret|path-secret|file-secret|\u001b|\u0000/,
  );
  assert.equal(presentation.output?.text, "failed");
});

test("groups only adjacent successful read-only activities", () => {
  const activities = [
    presentToolActivity({
      name: "search",
      callId: "s1",
      args: { query: "A2A" },
      done: true,
    }),
    presentToolActivity({
      name: "read_file",
      callId: "r1",
      args: { path: "src/a.ts" },
      done: true,
    }),
    presentToolActivity({
      name: "exec_command",
      callId: "c1",
      args: { command: "npm test" },
      done: true,
    }),
    presentToolActivity({
      name: "read_file",
      callId: "r2",
      args: { path: "src/b.ts" },
      done: true,
      status: "failed",
    }),
  ];

  const groups = groupToolActivities(activities);

  assert.equal(groups.length, 3);
  assert.equal(groups[0].kind, "exploration");
  assert.deepEqual(
    groups[0].items.map((item) => item.category),
    ["search", "read"],
  );
  assert.equal(groups[1].kind, "activity");
  assert.equal(groups[2].kind, "activity");
});

test("merges command aliases with one call id in live and history projections", () => {
  const events = [
    {
      id: "start-1",
      author: "default",
      invocationId: "inv-1",
      content: {
        parts: [
          {
            functionCall: {
              id: "cmd-1",
              name: "exec_command",
              args: { command: "echo ok" },
            },
          },
        ],
      },
    },
    {
      id: "start-2",
      author: "default",
      invocationId: "inv-1",
      content: {
        parts: [
          {
            functionCall: {
              id: "cmd-1",
              name: "commandExecution",
              args: { command: "echo ok" },
            },
          },
        ],
      },
    },
    {
      id: "result-1",
      author: "default",
      invocationId: "inv-1",
      content: {
        parts: [
          {
            functionResponse: {
              id: "cmd-1",
              name: "commandExecution",
              response: { output: "ok\n", exitCode: 0 },
            },
          },
        ],
      },
    },
  ];

  let live = emptyAcc();
  for (const event of events) live = applyEvent(live, event);
  const history = eventsToTurns(events);
  const liveTools = live.blocks.filter((block) => block.kind === "tool");
  const historyTools = history
    .flatMap((turn) => turn.blocks)
    .filter((block) => block.kind === "tool");

  assert.equal(liveTools.length, 1);
  assert.equal(liveTools[0].done, true);
  assert.equal(liveTools[0].response.output, "ok\n");
  assert.deepEqual(historyTools, liveTools);
});

test("keeps partial command output running until the terminal result", () => {
  let accumulator = applyEvent(emptyAcc(), {
    content: {
      parts: [
        {
          functionCall: {
            id: "cmd-stream",
            name: "commandExecution",
            args: { command: "echo ok" },
          },
        },
      ],
    },
  });
  accumulator = applyEvent(accumulator, {
    partial: true,
    content: {
      parts: [
        {
          functionResponse: {
            id: "cmd-stream",
            name: "commandExecution",
            response: { status: "running", output: "partial\n" },
          },
        },
      ],
    },
  });
  assert.equal(accumulator.blocks[0].done, false);
  assert.equal(accumulator.blocks[0].status, "running");

  accumulator = applyEvent(accumulator, {
    partial: false,
    content: {
      parts: [
        {
          functionResponse: {
            id: "cmd-stream",
            name: "commandExecution",
            response: { status: "completed", output: "ok\n", exitCode: 0 },
          },
        },
      ],
    },
  });
  assert.equal(accumulator.blocks[0].done, true);
  assert.equal(accumulator.blocks[0].status, "completed");
  assert.equal(accumulator.blocks[0].response.output, "ok\n");
});

test("keeps an explicit partial failure terminal", () => {
  let accumulator = applyEvent(emptyAcc(), {
    content: {
      parts: [
        {
          functionCall: {
            id: "cmd-partial-failure",
            name: "commandExecution",
            args: { command: "false" },
          },
        },
      ],
    },
  });
  accumulator = applyEvent(accumulator, {
    partial: true,
    content: {
      parts: [
        {
          functionResponse: {
            id: "cmd-partial-failure",
            name: "commandExecution",
            response: { status: "failed", output: "failed", exitCode: 1 },
          },
        },
      ],
    },
  });

  assert.equal(accumulator.blocks[0].done, true);
  assert.equal(accumulator.blocks[0].status, "failed");
});

test("keeps an out-of-order tool result visible and merges the later call", () => {
  let accumulator = applyEvent(emptyAcc(), {
    content: {
      parts: [
        {
          functionResponse: {
            id: "late-call",
            name: "search",
            response: { status: "completed", count: 2 },
          },
        },
      ],
    },
  });
  assert.equal(accumulator.blocks.length, 1);
  assert.equal(accumulator.blocks[0].kind, "tool");
  assert.equal(accumulator.blocks[0].done, true);

  accumulator = applyEvent(accumulator, {
    content: {
      parts: [
        {
          functionCall: {
            id: "late-call",
            name: "search",
            args: { query: "A2A" },
          },
        },
      ],
    },
  });

  assert.equal(accumulator.blocks.length, 1);
  assert.equal(accumulator.blocks[0].kind, "tool");
  assert.deepEqual(accumulator.blocks[0].args, { query: "A2A" });
  assert.deepEqual(accumulator.blocks[0].response, {
    status: "completed",
    count: 2,
  });
  assert.equal(accumulator.blocks[0].done, true);
  assert.equal(accumulator.blocks[0].status, "completed");
});

test("ignores duplicate event ids across completed assistant turns", () => {
  const projector = createAssistantEventProjector("dedupe");
  const event = {
    id: "event-1",
    author: "default",
    invocationId: "inv-1",
    content: { parts: [{ text: "done" }] },
  };

  const first = projector.project(event);
  const duplicate = projector.project(event);

  assert.equal(first.completed, true);
  assert.equal(duplicate.ignored, true);
  assert.equal(duplicate.turn.blocks.length, 0);
});

test("ignores A2A transport heartbeats without creating a transcript turn", () => {
  const projector = createAssistantEventProjector("heartbeat");
  const projection = projector.project({
    id: "a2a-task-1-working",
    author: "default",
    partial: true,
    content: { role: "model", parts: [] },
    customMetadata: { a2aStatus: "working" },
  });

  assert.equal(projection.ignored, true);
  assert.equal(projection.turn.blocks.length, 0);
  assert.deepEqual(projector.finish(), []);
});

test("bounds duplicate event tracking for long-running projector instances", () => {
  const projector = createAssistantEventProjector("bounded-dedupe");
  for (let index = 0; index < 2_100; index += 1) {
    projector.project({
      id: "event-" + index,
      author: "default",
      invocationId: "inv-" + index,
      content: { parts: [{ text: "answer-" + index }] },
    });
  }

  const replayedOldEvent = projector.project({
    id: "event-0",
    author: "default",
    invocationId: "inv-replayed",
    content: { parts: [{ text: "old event can be processed after eviction" }] },
  });

  assert.equal(replayedOldEvent.ignored, undefined);
  assert.equal(replayedOldEvent.completed, true);
});

test("flattens structured Codex activity without mutating source blocks", () => {
  const blocks = [
    {
      kind: "tool",
      name: "delegate_to_codex_sandbox",
      callId: "outer-1",
      done: false,
      codexActivity: {
        title: "Codex Sandbox",
        items: [
          {
            id: "cmd-1",
            block: {
              kind: "tool",
              name: "Run command",
              callId: "cmd-1",
              args: { command: "npm test" },
              done: false,
              status: "running",
            },
          },
        ],
      },
    },
  ];

  const flattened = flattenCodexActivityBlocks(blocks);

  assert.equal(flattened.length, 2);
  assert.deepEqual(flattened[0], {
    kind: "activity-source",
    label: "Codex Sandbox",
  });
  assert.equal(flattened[1].kind, "tool");
  assert.equal(flattened[1].source, "codex-sandbox");
  assert.equal(blocks[0].kind, "tool");
  assert.equal(blocks[0].codexActivity.items[0].block.source, undefined);
});

test("keeps the outer sandbox activity while no child activity exists", () => {
  const blocks = [
    {
      kind: "tool",
      name: "delegate_to_codex_sandbox",
      callId: "outer-1",
      done: false,
      codexActivity: { title: "Codex Sandbox", items: [] },
    },
  ];

  assert.deepEqual(flattenCodexActivityBlocks(blocks), blocks);
});
