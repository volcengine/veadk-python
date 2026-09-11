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
const {
  createMigrationTask,
  getMigrationActivity,
  getMigrationArtifact,
  getMigrationCapabilities,
  getMigrationEvaluationReport,
  getMigrationEvaluation,
  getMigrationTask,
  MigrationApiError,
  putMigrationEvaluationDataset,
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

test("submits only the explicitly selected custom evaluation dimensions", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const selected = ["semantic_fidelity", "safety_refusal_fidelity"];
  let requestBody;
  globalThis.fetch = async (_url, init) => {
    requestBody = JSON.parse(init.body);
    return new Response(
      JSON.stringify(
        migrationTask({
          sessionTtlSeconds: 7200,
          evaluation: {
            enabled: true,
            preset: "custom",
            dimensions: selected,
            state: "waiting_dataset",
            message: "请添加并锁定评测用例",
            canResume: false,
            canRetry: false,
          },
        }),
      ),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  };

  const created = await createMigrationTask({
    taskId: `migration-v1-${"1".repeat(32)}`,
    sourceFileName: "source.zip",
    instruction: "",
    evaluation: {
      enabled: true,
      preset: "custom",
      dimensions: selected,
      locale: "en-US",
    },
  });

  assert.deepEqual(requestBody.evaluation, {
    enabled: true,
    preset: "custom",
    dimensions: selected,
    locale: "en-US",
  });
  assert.deepEqual(created.evaluation.dimensions, selected);
});

test("creates, locks, and reads an HTML migration effect report without expected tools", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const asset = {
    schemaVersion: 1,
    kind: "dataset",
    assetId: `task-1/dataset/${"a".repeat(32)}`,
    version: "a".repeat(32),
    versionId: "a".repeat(32),
    sha256: "a".repeat(64),
    sizeBytes: 128,
    size: 128,
    createdAt: "2026-09-07T08:00:00Z",
    acl: "owner",
    viewReady: true,
    downloadReady: true,
    caseCount: 1,
  };
  const requests = [];
  const responses = [
    migrationTask({
      sessionTtlSeconds: 7200,
      evaluation: {
        enabled: true,
        state: "waiting_dataset",
        message: "请添加并锁定评测用例",
        preset: "standard",
        dimensions: [
          "semantic_fidelity",
          "output_contract",
          "workflow_tool_fidelity",
        ],
        canResume: false,
        canRetry: false,
      },
    }),
    {
      locked: true,
      asset,
      cases: [
        {
          caseId: "case-1",
          userInput: "查询订单状态",
          expectedOutcome: null,
          criteria: [],
          priorMessages: [],
        },
      ],
    },
    "<!doctype html><html><body><h1>迁移效果评测报告</h1></body></html>",
  ];
  globalThis.fetch = async (url, init = {}) => {
    requests.push({ url: String(url), init });
    const body = responses.shift();
    const html = typeof body === "string";
    return new Response(html ? body : JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": html ? "text/html" : "application/json" },
    });
  };

  const created = await createMigrationTask({
    taskId: `migration-v1-${"1".repeat(32)}`,
    sourceFileName: "source.zip",
    instruction: "",
    evaluation: { enabled: true, preset: "standard" },
  });
  const dataset = await putMigrationEvaluationDataset(created.id, [
    {
      caseId: "case-1",
      userInput: "查询订单状态",
      expectedOutcome: null,
      criteria: [],
      priorMessages: [],
    },
  ]);
  const report = await getMigrationEvaluationReport("task-1", "a".repeat(32));

  assert.equal(created.evaluation.state, "waiting_dataset");
  assert.equal(dataset.locked, true);
  assert.match(report, /<!doctype html>/);
  assert.match(report, /迁移效果评测报告/);
  assert.deepEqual(JSON.parse(requests[0].init.body).evaluation, {
    enabled: true,
    preset: "standard",
  });
  const datasetBody = JSON.parse(requests[1].init.body);
  assert.equal(datasetBody.cases[0].userInput, "查询订单状态");
  assert.equal(Object.hasOwn(datasetBody.cases[0], "expectedTools"), false);
  assert.match(requests[1].url, /\/evaluation\/dataset$/);
  assert.match(
    requests[2].url,
    /\/evaluation\/report\?versionId=a{32}$/,
  );
});

test("preserves required and optional evaluation environment variables", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        enabled: true,
        state: "waiting_environment",
        message: "请补充环境变量",
        environment: {
          required: ["MODEL_AGENT_API_KEY"],
          optional: ["MODEL_AGENT_API_BASE", "TZ"],
          defaults: {
            MODEL_AGENT_API_BASE: "https://ark.example/api/v3",
            TZ: "Asia/Shanghai",
          },
        },
        canResume: true,
        canRetry: false,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );

  const status = await getMigrationEvaluation("task-1");

  assert.deepEqual(status.environment, {
    required: ["MODEL_AGENT_API_KEY"],
    optional: ["MODEL_AGENT_API_BASE", "TZ"],
    defaults: {
      MODEL_AGENT_API_BASE: "https://ark.example/api/v3",
      TZ: "Asia/Shanghai",
    },
  });
});

test("accepts the migration default model while preserving legacy capabilities", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const base = {
    enabled: true,
    reason: "",
    maxUploadBytes: 20 * 1024 * 1024,
    sessionTtlSeconds: 3600,
    frameworks: ["langchain", "dify", "any"],
  };
  const responses = [
    {
      ...base,
      provider: "volcengine",
      model: { configured: true, id: "doubao-seed-2-1-pro-260628" },
      evaluation: {
        available: true,
        reason: "",
        maxCases: 100,
        maxDatasetBytes: 10 * 1024 * 1024,
        maxMessagesPerCase: 20,
        maxMessagesBytes: 32 * 1024,
        maxReferenceOutputBytes: 16 * 1024,
        maxCriteria: 20,
        maxCriterionBytes: 2 * 1024,
        maxCapturedOutputBytes: 64 * 1024,
        inputMode: "page",
        pageInputMethods: ["manual", "bulk_paste"],
        defaultPreset: "standard",
        maximumSessionTtlSeconds: 7200,
        dimensions: [
          {
            id: "semantic_fidelity",
            label: "语义一致性",
            description: "检查语义。",
          },
        ],
      },
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
  assert.equal(current.evaluation.maximumSessionTtlSeconds, 7200);
  assert.deepEqual(current.evaluation.pageInputMethods, [
    "manual",
    "bulk_paste",
  ]);
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
  assert.equal(
    task.analysis.summary,
    "ZIP 中没有足以恢复 Agent 行为的项目材料。",
  );
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
      items: [
        {
          id: "tool",
          kind: "command",
          status: "running",
          title: "执行工具",
          tool: { name: 1 },
        },
      ],
    },
    {
      available: true,
      complete: false,
      items: [
        {
          id: "plan",
          kind: "plan",
          status: "running",
          title: "迁移计划",
          plan: [{ text: "迁移", status: "done" }],
        },
      ],
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
