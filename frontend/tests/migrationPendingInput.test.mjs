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
const { getMigrationTask, submitMigrationAnalysisInput } = await import(moduleUrl);

const TASK_ID = `migration-v1-${"1".repeat(32)}`;

function pendingInput(overrides = {}) {
  return {
    id: "request-1",
    questions: [
      {
        id: "framework",
        header: "目标框架",
        question: "迁移到 langchain 还是 dify？",
        options: [
          { label: "langchain", description: "保留 LangChain 结构。" },
          { label: "dify", description: "输出 Dify 应用。" },
        ],
      },
    ],
    ...overrides,
  };
}

function taskPayload(overrides = {}) {
  return {
    id: TASK_ID,
    state: "analyzing",
    message: "分析正在等待你的回答",
    sourceFileName: "source.zip",
    instruction: "",
    createdAt: "2026-08-14T08:00:00Z",
    expiresAt: "2026-08-14T09:00:00Z",
    sessionTtlSeconds: 3600,
    canModify: false,
    canUpload: false,
    canAnswer: false,
    canConfirm: false,
    canStop: true,
    artifact: {
      state: "none",
      previewReady: false,
      downloadReady: false,
      deployReady: false,
    },
    ...overrides,
  };
}

function stubFetch(t, handler) {
  const previous = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previous;
  });
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return handler(String(url), init);
  };
  return calls;
}

test("keeps the questions the running analysis turn is waiting on", async (t) => {
  stubFetch(
    t,
    async () =>
      new Response(JSON.stringify(taskPayload({ pendingInput: pendingInput() })), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );

  const task = await getMigrationTask(TASK_ID);

  assert.equal(task.state, "analyzing");
  assert.equal(task.pendingInput.id, "request-1");
  assert.equal(task.pendingInput.questions[0].header, "目标框架");
  assert.deepEqual(task.pendingInput.questions[0].options[1], {
    label: "dify",
    description: "输出 Dify 应用。",
  });
});

test("a task without pending questions keeps no pending input", async (t) => {
  stubFetch(
    t,
    async () =>
      new Response(JSON.stringify(taskPayload()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );

  const task = await getMigrationTask(TASK_ID);

  assert.equal(task.pendingInput, undefined);
});

test("rejects a question set that cannot be rendered", async (t) => {
  stubFetch(
    t,
    async () =>
      new Response(
        JSON.stringify(
          taskPayload({
            pendingInput: pendingInput({
              questions: [{ id: "framework", header: "目标框架" }],
            }),
          }),
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
  );

  await assert.rejects(() => getMigrationTask(TASK_ID), (cause) => {
    assert.match(cause.message, /分析问题/);
    return true;
  });

  await assert.rejects(
    () => getMigrationTask(TASK_ID),
    (cause) => cause instanceof Error,
  );
});

test("posts the answers for an in-turn question to the input endpoint", async (t) => {
  const calls = stubFetch(
    t,
    async () =>
      new Response(JSON.stringify(taskPayload({ pendingInput: undefined })), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );

  const next = await submitMigrationAnalysisInput({
    taskId: TASK_ID,
    requestId: "request-1",
    answers: { framework: "dify" },
  });

  assert.equal(next.pendingInput, undefined);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `/web/agent-migrations/tasks/${TASK_ID}/input`);
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    requestId: "request-1",
    answers: { framework: "dify" },
  });
});
