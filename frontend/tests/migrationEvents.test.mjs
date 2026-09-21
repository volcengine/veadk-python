import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

globalThis.window = {
  location: { search: "", pathname: "/", hash: "", origin: "http://localhost" },
  history: { replaceState() {} },
};
globalThis.sessionStorage = memoryStorage();
globalThis.localStorage = memoryStorage();
globalThis.localStorage.setItem("agentkit.studio.locale", "zh-CN");
globalThis.window.localStorage = globalThis.localStorage;

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/adk/migrations.ts", import.meta.url)),
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
const { MigrationApiError, observeMigrationTask, parseMigrationStreamFrame } =
  await import(moduleUrl);

function taskPayload(state = "analyzing") {
  return {
    id: `migration-v1-${"1".repeat(32)}`,
    state,
    message: "migration environment ready",
    sourceFileName: "source.zip",
    instruction: "",
    createdAt: "2026-08-14T08:00:00Z",
    expiresAt: "2026-08-14T09:00:00Z",
    sessionTtlSeconds: 3600,
    canModify: true,
    canUpload: true,
    canAnswer: false,
    canConfirm: false,
    canStop: true,
    artifact: {
      state: "none",
      previewReady: false,
      downloadReady: false,
      deployReady: false,
    },
  };
}

function activityPayload() {
  return {
    available: true,
    complete: false,
    items: [
      {
        id: "item-1",
        kind: "command",
        status: "completed",
        title: "read the source tree",
        tool: { name: "shell", exitCode: 0 },
      },
    ],
  };
}

function frame(name, payload) {
  return `id: ${payload.seq}\nevent: ${name}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function sseResponse(chunks, status = 200) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
    { status, headers: { "Content-Type": "text/event-stream" } },
  );
}

function stubFetch(t, handler) {
  const previous = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previous;
  });
  const urls = [];
  globalThis.fetch = async (url, init) => {
    urls.push(String(url));
    return handler(String(url), init, urls.length);
  };
  return urls;
}

test("parses task, activity, error and done frames", () => {
  const task = parseMigrationStreamFrame(
    frame("task", { seq: 3, taskId: "task-1", ...taskPayload("migrating") }),
  );
  assert.equal(task.kind, "task");
  assert.equal(task.seq, 3);
  assert.equal(task.task.state, "migrating");

  const activity = parseMigrationStreamFrame(
    frame("activity", { seq: 4, taskId: "task-1", ...activityPayload() }),
  );
  assert.equal(activity.kind, "activity");
  assert.equal(activity.activity.items.length, 1);
  assert.equal(activity.activity.items[0].tool.name, "shell");

  const failure = parseMigrationStreamFrame(
    frame("error", {
      seq: 5,
      taskId: "task-1",
      code: "MIGRATION_EVENT_READ_FAILED",
      message: "sandbox is temporarily unreadable",
      retryable: true,
    }),
  );
  assert.equal(failure.kind, "error");
  assert.equal(failure.code, "MIGRATION_EVENT_READ_FAILED");
  assert.equal(failure.retryable, true);

  const cleared = parseMigrationStreamFrame(
    frame("error", { seq: 6, taskId: "task-1" }),
  );
  assert.equal(cleared.kind, "error");
  assert.equal(cleared.code, "");
  assert.equal(cleared.message, "");
  assert.equal(cleared.retryable, false);

  const done = parseMigrationStreamFrame(
    frame("done", { seq: 7, taskId: "task-1", state: "analysis_ready" }),
  );
  assert.equal(done.kind, "done");
  assert.equal(done.state, "analysis_ready");
});

test("ignores heartbeats, comments and event names this build does not know", () => {
  assert.equal(parseMigrationStreamFrame(": heartbeat"), null);
  assert.equal(parseMigrationStreamFrame(""), null);
  assert.equal(parseMigrationStreamFrame("event: task\ndata:\n"), null);
  assert.equal(
    parseMigrationStreamFrame(frame("evaluation", { seq: 8, state: "judging" })),
    null,
  );
});

test("rejects frames without a usable sequence number or payload", () => {
  assert.throws(() => parseMigrationStreamFrame("event: task\ndata: {"), Error);
  assert.throws(
    () => parseMigrationStreamFrame('event: task\ndata: {"state":"analyzing"}'),
    Error,
  );
  assert.throws(
    () =>
      parseMigrationStreamFrame(
        frame("task", { seq: 0, taskId: "task-1", ...taskPayload() }),
      ),
    Error,
  );
  assert.throws(
    () => parseMigrationStreamFrame('event: done\ndata: {"seq":1.5}'),
    Error,
  );
  assert.throws(
    () => parseMigrationStreamFrame('event: task\ndata: ["not","an","object"]'),
    Error,
  );
  assert.throws(
    () => parseMigrationStreamFrame('event: task\ndata: {"seq":1,"taskId":"t"}'),
    Error,
  );
});

test("follows one task, resumes from its cursor and stops on done", async (t) => {
  const urls = stubFetch(t, (_url, _init, attempt) => {
    if (attempt === 1) {
      return sseResponse([
        ": heartbeat\n\n",
        frame("task", { seq: 1, taskId: "task-1", ...taskPayload("migrating") }),
        frame("activity", { seq: 2, taskId: "task-1", ...activityPayload() }),
      ]);
    }
    return sseResponse([
      frame("task", { seq: 3, taskId: "task-1", ...taskPayload("packaging") }),
      frame("done", { seq: 4, taskId: "task-1", state: "packaging" }),
    ]);
  });

  const events = [];
  const connections = [];
  await observeMigrationTask({
    taskId: "task-1",
    signal: new AbortController().signal,
    onEvent: (event) => events.push(event),
    onConnection: (message) => connections.push(message),
  });

  assert.match(urls[0], /\/web\/agent-migrations\/tasks\/task-1\/events\?after=0$/);
  assert.match(urls[1], /after=2$/);
  assert.deepEqual(
    events.map((event) => [event.kind, event.seq]),
    [
      ["task", 1],
      ["activity", 2],
      ["task", 3],
      ["done", 4],
    ],
  );
});

test("reports a reconnect and recovers without replaying what it already applied", async (t) => {
  const urls = stubFetch(t, (_url, _init, attempt) => {
    if (attempt === 1) throw new TypeError("network down");
    if (attempt === 2) {
      return sseResponse([
        frame("task", { seq: 1, taskId: "task-1", ...taskPayload("analyzing") }),
      ]);
    }
    return sseResponse([
      frame("done", { seq: 2, taskId: "task-1", state: "needs_input" }),
    ]);
  });

  const events = [];
  const connections = [];
  await observeMigrationTask({
    taskId: "task-1",
    signal: new AbortController().signal,
    onEvent: (event) => events.push(event),
    onConnection: (message) => connections.push(message),
  });

  assert.equal(urls.length, 3);
  assert.deepEqual(events.map((event) => event.seq), [1, 2]);
  assert.equal(connections.length, 2);
  assert.ok(connections[0].length > 0);
  assert.equal(connections[1], "");
});

test("stops at once on an unauthorized or missing task", async (t) => {
  const urls = stubFetch(
    t,
    () =>
      new Response(JSON.stringify({ detail: "not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
  );

  await assert.rejects(
    () =>
      observeMigrationTask({
        taskId: "task-1",
        signal: new AbortController().signal,
        onEvent: () => undefined,
      }),
    (cause) => {
      assert.equal(cause instanceof MigrationApiError, true);
      assert.equal(cause.status, 404);
      return true;
    },
  );
  assert.equal(urls.length, 1);
});

test("stops following as soon as the caller aborts", async (t) => {
  const controller = new AbortController();
  const urls = stubFetch(t, () => {
    controller.abort();
    return sseResponse([]);
  });

  await observeMigrationTask({
    taskId: "task-1",
    signal: controller.signal,
    onEvent: () => undefined,
  });
  assert.equal(urls.length, 1);
});
