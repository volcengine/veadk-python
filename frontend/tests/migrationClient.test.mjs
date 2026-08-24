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
  location: {
    search: "",
    pathname: "/",
    hash: "",
    origin: "http://localhost",
  },
  history: { replaceState() {} },
};
globalThis.sessionStorage = memoryStorage();
globalThis.localStorage = memoryStorage();

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
const {
  createMigrationTask,
  getMigrationActivity,
  getMigrationArtifact,
  getMigrationCapabilities,
  getMigrationTask,
  MigrationApiError,
} = await import(moduleUrl);

function migrationTask(overrides = {}) {
  return {
    id: `migration-v1-${"1".repeat(32)}`,
    state: "awaiting_upload",
    message: "迁移环境已就绪",
    sourceFileName: "source.zip",
    instruction: "",
    createdAt: "2026-08-14T08:00:00Z",
    expiresAt: "2026-08-14T09:00:00Z",
    sessionTtlSeconds: 3600,
    canModify: true,
    canUpload: true,
    canAnswer: false,
    canConfirm: false,
    canStop: false,
    artifact: {
      state: "none",
      previewReady: false,
      downloadReady: false,
      deployReady: false,
    },
    ...overrides,
  };
}

function migrationArtifact(environment) {
  return {
    schema_version: 1,
    run_id: `migration-v1-${"1".repeat(32)}`,
    cli: { name: "agentkit-cli", version: "0.52.1" },
    migration: {
      engine: "agentic",
      framework: "any",
      source_sha256: "2".repeat(64),
      provenance_sha256: "3".repeat(64),
    },
    status: "succeeded",
    files: [
      {
        path: "main.py",
        size: 10,
        sha256: "4".repeat(64),
        mode: "0644",
      },
    ],
    startup: { module: "main.py", object: "app" },
    environment,
    verification: { status: "passed", checks: [] },
    warnings: [],
    report: { path: "main.py" },
    artifact: {
      path: "migration-result.zip",
      size: 20,
      sha256: "5".repeat(64),
    },
    created_at: "2026-08-15T08:00:00Z",
  };
}

test("surfaces FastAPI validation details without blaming the proxy", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        detail: [
          {
            type: "missing",
            loc: ["body", "sourceFileName"],
            msg: "Field required",
            input: { secret: "must-not-be-rendered" },
          },
        ],
      }),
      {
        status: 422,
        headers: { "Content-Type": "application/json" },
      },
    );

  await assert.rejects(
    () => getMigrationCapabilities(),
    (cause) => {
      assert.equal(cause instanceof MigrationApiError, true);
      assert.equal(cause.code, "MIGRATION_REQUEST_INVALID");
      assert.equal(cause.retryable, false);
      assert.match(cause.message, /body\.sourceFileName: Field required/);
      assert.doesNotMatch(cause.message, /代理|网关|must-not-be-rendered/);
      return true;
    },
  );
});

test("sends an optional migration model without changing legacy requests", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const bodies = [];
  globalThis.fetch = async (_url, init) => {
    const body = JSON.parse(init.body);
    bodies.push(body);
    return new Response(
      JSON.stringify(
        migrationTask(body.modelId ? { modelId: body.modelId } : {}),
      ),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  };

  const selected = await createMigrationTask({
    taskId: `migration-v1-${"1".repeat(32)}`,
    sourceFileName: "source.zip",
    instruction: "",
    modelId: "doubao-seed-2-1-pro-260628",
  });
  const legacy = await createMigrationTask({
    taskId: `migration-v1-${"2".repeat(32)}`,
    sourceFileName: "source.zip",
    instruction: "",
  });

  assert.equal(selected.modelId, "doubao-seed-2-1-pro-260628");
  assert.equal(legacy.modelId, undefined);
  assert.equal(bodies[0].modelId, "doubao-seed-2-1-pro-260628");
  assert.equal(Object.hasOwn(bodies[1], "modelId"), false);
});

test("accepts the migration default model while preserving legacy capabilities", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const base = {
    enabled: true,
    reason: "",
    maxUploadBytes: 50 * 1024 * 1024,
    sessionTtlSeconds: 3600,
    frameworks: ["langchain", "dify", "any"],
  };
  const responses = [
    {
      ...base,
      provider: "volcengine",
      model: { configured: true, id: "doubao-seed-2-1-pro-260628" },
    },
    base,
  ];
  globalThis.fetch = async () =>
    new Response(JSON.stringify(responses.shift()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  const current = await getMigrationCapabilities();
  const legacy = await getMigrationCapabilities();

  assert.deepEqual(current.model, {
    configured: true,
    id: "doubao-seed-2-1-pro-260628",
  });
  assert.equal(legacy.model, undefined);
});

test("accepts an actionable unsupported analysis without a fake recommendation", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        id: `migration-v1-${"1".repeat(32)}`,
        state: "failed",
        message: "ZIP 中没有足以恢复 Agent 行为的项目材料。",
        sourceFileName: "compiled-only.zip",
        instruction: "",
        createdAt: "2026-08-14T08:00:00Z",
        expiresAt: "2026-08-14T09:00:00Z",
        sessionTtlSeconds: 3600,
        canModify: false,
        canUpload: false,
        canAnswer: false,
        canConfirm: false,
        canStop: false,
        artifact: {
          state: "none",
          previewReady: false,
          downloadReady: false,
          deployReady: false,
        },
        analysis: {
          schema_version: 1,
          status: "unsupported",
          attempt: 1,
          input_sha256: "2".repeat(64),
          summary: "ZIP 中没有足以恢复 Agent 行为的项目材料。",
          frameworks: [],
          recommended: null,
          entries: [],
          boundary: { include: [], exclude: ["编译产物"] },
          assumptions: [],
          questions: [],
          warnings: ["请上传源码、工作流定义或提示词。"],
        },
        analysisRef: {
          attempt: 1,
          sha256: "3".repeat(64),
          inputSha256: "2".repeat(64),
        },
        error: {
          code: "MIGRATION_ANALYSIS_UNSUPPORTED",
          message: "项目材料不足。",
          retryable: false,
        },
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );

  const task = await getMigrationTask(`migration-v1-${"1".repeat(32)}`);

  assert.equal(task.analysis.recommended, null);
  assert.equal(task.analysis.summary, "ZIP 中没有足以恢复 Agent 行为的项目材料。");
  assert.equal(task.canConfirm, false);
});

test("normalizes public migration environment defaults and legacy artifacts", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const responses = [
    migrationArtifact({
      required: ["ARK_API_KEY"],
      optional: ["ENABLE_LLM_SHIELD", "MODEL_AGENT_API_BASE"],
      defaults: {
        ENABLE_LLM_SHIELD: "false",
        MODEL_AGENT_API_BASE: "https://ark.example/api/v3",
      },
    }),
    migrationArtifact({ required: [], optional: [] }),
  ];
  globalThis.fetch = async () =>
    new Response(JSON.stringify(responses.shift()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  const artifact = await getMigrationArtifact(`migration-v1-${"1".repeat(32)}`);
  const legacyArtifact = await getMigrationArtifact(
    `migration-v1-${"1".repeat(32)}`,
  );

  assert.deepEqual(artifact.environment.defaults, {
    ENABLE_LLM_SHIELD: "false",
    MODEL_AGENT_API_BASE: "https://ark.example/api/v3",
  });
  assert.deepEqual(legacyArtifact.environment.defaults, {});
});

test("normalizes structured migration activity while accepting legacy items", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const responses = [
    {
      available: true,
      complete: false,
      items: [
        {
          id: "migration:1:command",
          kind: "command",
          status: "failed",
          title: "命令执行未完成",
          tool: {
            name: "命令执行未完成",
            input: { command: "python migrate.py" },
            output: "exit 1",
            error: "execution failed",
            exitCode: 1,
          },
        },
        {
          id: "migration:1:plan",
          kind: "plan",
          status: "running",
          title: "项目迁移计划",
          detail: "已完成 1/2 项",
          plan: [
            { text: "识别入口", status: "completed" },
            { text: "迁移工具", status: "in_progress" },
          ],
        },
      ],
    },
    {
      available: true,
      complete: true,
      items: [
        {
          id: "migration:1:message",
          kind: "message",
          status: "completed",
          title: "Codex 更新",
          detail: "迁移代码已生成。",
        },
      ],
    },
  ];
  globalThis.fetch = async () =>
    new Response(JSON.stringify(responses.shift()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  const structured = await getMigrationActivity("task-1");
  const legacy = await getMigrationActivity("task-1");

  assert.deepEqual(structured.items[0].tool, {
    name: "命令执行未完成",
    input: { command: "python migrate.py" },
    output: "exit 1",
    error: "execution failed",
    exitCode: 1,
  });
  assert.deepEqual(structured.items[1].plan, [
    { text: "识别入口", status: "completed" },
    { text: "迁移工具", status: "in_progress" },
  ]);
  assert.equal(legacy.items[0].detail, "迁移代码已生成。");
  assert.equal("tool" in legacy.items[0], false);
  assert.equal("plan" in legacy.items[0], false);
});

test("rejects malformed optional migration activity fields", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const responses = [
    {
      available: true,
      complete: false,
      items: [{
        id: "tool",
        kind: "command",
        status: "running",
        title: "执行工具",
        tool: { name: 1 },
      }],
    },
    {
      available: true,
      complete: false,
      items: [{
        id: "plan",
        kind: "plan",
        status: "running",
        title: "迁移计划",
        plan: [{ text: "迁移", status: "done" }],
      }],
    },
  ];
  globalThis.fetch = async () =>
    new Response(JSON.stringify(responses.shift()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  await assert.rejects(
    () => getMigrationActivity("task-1"),
    /迁移执行工具项格式错误/,
  );
  await assert.rejects(
    () => getMigrationActivity("task-1"),
    /迁移执行计划项格式错误/,
  );
});
